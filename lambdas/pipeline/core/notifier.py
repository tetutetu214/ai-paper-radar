"""Slack Block Kit 形式での配信。詳細仕様は docs/spec.md §5.2, §6 を参照。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Final

import requests
from anthropic import Anthropic
from boto3.dynamodb.conditions import Key
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


SUMMARIZER_MODEL: Final[str] = "claude-haiku-4-5-20251001"
ABSTRACT_MAX_CHARS: Final[int] = 1500

SUMMARY_SYSTEM_PROMPT: Final[str] = """\
あなたは論文を日本語で簡潔に要約するアシスタントです。
英語のタイトルとアブストラクトから、以下の観点で要約してください。

- title_ja: 日本語タイトル（30文字以内）
- summary_ja: 要点を3つ（各40文字程度、技術用語は原語OK）

submit_summary ツールを使って結果を返してください。
"""

SUMMARY_TOOL: Final[dict[str, Any]] = {
    "name": "submit_summary",
    "description": "論文要約を返す",
    "input_schema": {
        "type": "object",
        "properties": {
            "title_ja": {"type": "string"},
            "summary_ja": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
        },
        "required": ["title_ja", "summary_ja"],
    },
}


def fetch_top_n(
    table: Any, collected_date: str, n: int
) -> list[dict[str, Any]]:
    """指定日のスコア上位 N 本を GSI で取得（score 降順）。"""
    response = table.query(
        IndexName="gsi_collected_date_score",
        KeyConditionExpression=Key("collected_date").eq(collected_date),
        ScanIndexForward=False,
        Limit=n,
    )
    return response.get("Items", [])


def summarize_papers(
    client: Anthropic, papers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """各論文を日本語要約し、title_ja / summary_ja を追加して返す。"""
    enriched: list[dict[str, Any]] = []
    for paper in papers:
        try:
            summary = _summarize_one(client, paper)
            enriched_paper = dict(paper)
            enriched_paper.update(summary)
            enriched.append(enriched_paper)
        except Exception:
            logger.exception(
                "Summarize failed for paper_id=%s; using fallback",
                paper.get("paper_id"),
            )
            fallback = dict(paper)
            fallback["title_ja"] = paper.get("title", "")
            fallback["summary_ja"] = ["（要約失敗）"]
            enriched.append(fallback)
    return enriched


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=2, max=20))
def _summarize_one(
    client: Anthropic, paper: dict[str, Any]
) -> dict[str, Any]:
    user_message = (
        f"title: {paper.get('title', '')}\n\n"
        f"abstract: {paper.get('abstract', '')[:ABSTRACT_MAX_CHARS]}"
    )
    response = client.messages.create(
        model=SUMMARIZER_MODEL,
        max_tokens=1024,
        system=SUMMARY_SYSTEM_PROMPT,
        tools=[SUMMARY_TOOL],
        tool_choice={"type": "tool", "name": "submit_summary"},
        messages=[{"role": "user", "content": user_message}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return dict(block.input)
    return {"title_ja": paper.get("title", ""), "summary_ja": ["（要約失敗）"]}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception_type((requests.RequestException,)),
)
def post_to_slack(webhook_url: str, papers: list[dict[str, Any]]) -> None:
    """Slack Incoming Webhook へ Block Kit 形式で投稿。"""
    today = datetime.now().strftime("%Y-%m-%d")
    blocks = build_blocks(papers, today)
    response = requests.post(webhook_url, json={"blocks": blocks}, timeout=10)
    response.raise_for_status()


def build_blocks(
    papers: list[dict[str, Any]], date: str
) -> list[dict[str, Any]]:
    """Slack Block Kit 構造を組み立てる（テスト容易性のため公開）。"""
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📚 AI Paper Radar — {date}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"本日の注目論文 *{len(papers)}本* をお届けします。",
            },
        },
        {"type": "divider"},
    ]

    for i, paper in enumerate(papers, start=1):
        url = f"https://arxiv.org/abs/{paper['paper_id']}"
        title_ja = paper.get("title_ja", paper.get("title", ""))
        title_en = paper.get("title", "")
        score = paper.get("score", 0)
        reason = paper.get("score_reason", "")
        summary_lines = "\n".join(
            f"• {s}" for s in paper.get("summary_ja", [])
        )

        block_text = (
            f"*[{i}位 / score: {score}]* <{url}|{title_en}>\n"
            f"_{title_ja}_\n\n"
            f"{summary_lines}\n\n"
            f"*採用理由*: {reason}"
        )
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": block_text}}
        )
        blocks.append({"type": "divider"})

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "🤖 Powered by Claude Haiku 4.5 | "
                        "<https://huggingface.co/papers|HF Daily Papers> + arXiv"
                    ),
                }
            ],
        }
    )
    return blocks


def mark_delivered(table: Any, papers: list[dict[str, Any]]) -> None:
    """配信済み論文に delivered_at を記録。"""
    now_iso = datetime.now().isoformat()
    for paper in papers:
        table.update_item(
            Key={"paper_id": paper["paper_id"]},
            UpdateExpression="SET delivered_at = :d",
            ExpressionAttributeValues={":d": now_iso},
        )
