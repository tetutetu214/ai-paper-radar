"""Claude Haiku 4.5 による論文スコアリング。

詳細仕様は docs/spec.md §5.1, §5.3 を参照。
"""
from __future__ import annotations

import logging
from typing import Any, Final

from anthropic import AnthropicBedrock
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


# Bedrock Global Cross-Region Inference Profile（複数リージョンに自動分散）
SCORER_MODEL: Final[str] = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
SCORER_BATCH_SIZE: Final[int] = 10
ABSTRACT_MAX_CHARS: Final[int] = 1000

SYSTEM_PROMPT_TEMPLATE: Final[str] = """\
あなたは生成AI/LLM分野の論文を、ユーザーの興味に対して0-100点で評価するアシスタントです。
ユーザーの興味は以下の通りです。

{interest_prompt}

各論文のタイトルとアブストラクトを読み、以下の観点で評価してください。
- ユーザーの興味領域との関連性（最重要）
- 実装・評価・アーキテクチャ提案を含むかどうか
- 新規性、実用性

submit_scores ツールを使い、各論文の paper_id, score (0-100), reason (日本語1-2文) を返してください。
"""

SCORE_TOOL: Final[dict[str, Any]] = {
    "name": "submit_scores",
    "description": "論文スコアの結果を返す",
    "input_schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "paper_id": {"type": "string"},
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "reason": {"type": "string"},
                    },
                    "required": ["paper_id", "score", "reason"],
                },
            },
        },
        "required": ["results"],
    },
}


def fetch_unscored_papers(
    table: Any, collected_date: str
) -> list[dict[str, Any]]:
    """指定日に収集された論文のうち score 未設定のものを返す。"""
    response = table.scan(
        FilterExpression="collected_date = :d AND attribute_not_exists(score)",
        ExpressionAttributeValues={":d": collected_date},
    )
    return response.get("Items", [])


def score_papers(
    client: AnthropicBedrock,
    papers: list[dict[str, Any]],
    interest_prompt: str,
) -> list[dict[str, Any]]:
    """論文を 10 本ずつバッチで評価し、結果を集約して返す。"""
    all_results: list[dict[str, Any]] = []
    for i in range(0, len(papers), SCORER_BATCH_SIZE):
        batch = papers[i : i + SCORER_BATCH_SIZE]
        try:
            results = _score_batch(client, batch, interest_prompt)
            all_results.extend(results)
        except Exception:
            logger.exception(
                "Score batch failed (size=%d, starting paper_id=%s)",
                len(batch),
                batch[0].get("paper_id") if batch else None,
            )
    return all_results


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=20),
)
def _score_batch(
    client: AnthropicBedrock,
    batch: list[dict[str, Any]],
    interest_prompt: str,
) -> list[dict[str, Any]]:
    """1 バッチ（最大 10 本）を Claude Haiku で評価。"""
    user_message = "評価対象の論文:\n\n" + "\n\n".join(
        f"[{i + 1}] paper_id: {p['paper_id']}\n"
        f"title: {p.get('title', '')}\n"
        f"abstract: {p.get('abstract', '')[:ABSTRACT_MAX_CHARS]}"
        for i, p in enumerate(batch)
    )

    response = client.messages.create(
        model=SCORER_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT_TEMPLATE.format(interest_prompt=interest_prompt),
        tools=[SCORE_TOOL],
        tool_choice={"type": "tool", "name": "submit_scores"},
        messages=[{"role": "user", "content": user_message}],
    )

    # response.content の tool_use ブロックから dict を取り出す
    for block in response.content:
        if block.type == "tool_use":
            return list(block.input.get("results", []))

    logger.warning("No tool_use block in scorer response")
    return []


def update_scores(table: Any, results: list[dict[str, Any]]) -> int:
    """スコア結果を DynamoDB に書き戻す。score_padded は 3 桁ゼロパディング。"""
    updated = 0
    for r in results:
        paper_id = r["paper_id"]
        score = int(r["score"])
        reason = r["reason"]
        score_padded = f"{score:03d}"
        table.update_item(
            Key={"paper_id": paper_id},
            UpdateExpression=(
                "SET score = :s, score_padded = :sp, score_reason = :r"
            ),
            ExpressionAttributeValues={
                ":s": score,
                ":sp": score_padded,
                ":r": reason,
            },
        )
        updated += 1
    return updated
