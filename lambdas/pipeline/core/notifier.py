"""Slack Block Kit 形式での配信。詳細仕様は docs/spec.md §5.2, §6 を参照。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Final

import requests
from boto3.dynamodb.conditions import Attr, Key
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


# Bedrock APAC Cross-Region Inference Profile（東京含む APAC 内リージョンに自動分散）
SUMMARIZER_MODEL: Final[str] = "apac.amazon.nova-pro-v1:0"
ABSTRACT_MAX_CHARS: Final[int] = 1500

SUMMARY_SYSTEM_PROMPT: Final[str] = """\
あなたは論文を日本語で簡潔に要約するアシスタントです。
英語のタイトルとアブストラクトから、以下の観点で要約してください。

- title_ja: 日本語タイトル（30文字以内）
- summary_ja: 要点を3つ（各40文字程度、技術用語は原語OK）

submit_summary ツールを使って結果を返してください。
"""

# Bedrock Converse API の toolSpec 形式
SUMMARY_TOOL: Final[dict[str, Any]] = {
    "toolSpec": {
        "name": "submit_summary",
        "description": "論文要約を返す",
        "inputSchema": {
            "json": {
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
            }
        },
    }
}


def fetch_top_n(table: Any, collected_date: str, n: int) -> list[dict[str, Any]]:
    """指定日のスコア上位 N 本のうち、未配信のものを返す（score 降順）。

    delivered_at が設定済みの論文は過去日に配信済みなので除外する。これにより
    高スコア論文が連日 Top に居座り続けて毎日同じ Slack 投稿になる問題を防ぐ。
    Limit は GSI Query 段階では指定せず（FilterExpression と組み合わせると
    Limit 適用後にフィルタされて N 未満になりがちなため）、Python 側で n 件に
    切り詰める。1 日の収集上限が 50 件程度なので全件読みでも問題ない。
    """
    response = table.query(
        IndexName="gsi_collected_date_score",
        KeyConditionExpression=Key("collected_date").eq(collected_date),
        ScanIndexForward=False,
        FilterExpression=Attr("delivered_at").not_exists(),
    )
    items = response.get("Items", [])
    return items[:n]


def summarize_papers(
    client: Any, papers: list[dict[str, Any]]
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
def _summarize_one(client: Any, paper: dict[str, Any]) -> dict[str, Any]:
    user_message = (
        f"title: {paper.get('title', '')}\n\n"
        f"abstract: {paper.get('abstract', '')[:ABSTRACT_MAX_CHARS]}"
    )
    response = client.converse(
        modelId=SUMMARIZER_MODEL,
        system=[{"text": SUMMARY_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        toolConfig={
            "tools": [SUMMARY_TOOL],
            "toolChoice": {"tool": {"name": "submit_summary"}},
        },
        inferenceConfig={"maxTokens": 1024},
    )
    content_blocks = response["output"]["message"]["content"]
    for block in content_blocks:
        tool_use = block.get("toolUse")
        if tool_use and tool_use.get("name") == "submit_summary":
            return dict(tool_use["input"])
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


def build_blocks(papers: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
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
        summary_lines = "\n".join(f"• {s}" for s in paper.get("summary_ja", []))

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
                        "🤖 Powered by Amazon Nova Pro | "
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
