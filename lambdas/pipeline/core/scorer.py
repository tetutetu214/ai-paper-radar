"""Amazon Nova Pro による論文スコアリング。

詳細仕様は docs/spec.md §5.1, §5.3 を参照。
"""
from __future__ import annotations

import logging
from typing import Any, Final

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


# Bedrock APAC Cross-Region Inference Profile（東京含む APAC 内リージョンに自動分散）
SCORER_MODEL: Final[str] = "apac.amazon.nova-pro-v1:0"
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

# Bedrock Converse API の toolSpec 形式（Anthropic SDK の input_schema とは別構造）
SCORE_TOOL: Final[dict[str, Any]] = {
    "toolSpec": {
        "name": "submit_scores",
        "description": "論文スコアの結果を返す",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "paper_id": {"type": "string"},
                                "score": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "maximum": 100,
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["paper_id", "score", "reason"],
                        },
                    },
                },
                "required": ["results"],
            }
        },
    }
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
    client: Any,
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
    client: Any,
    batch: list[dict[str, Any]],
    interest_prompt: str,
) -> list[dict[str, Any]]:
    """1 バッチ（最大 10 本）を Nova Pro で評価。"""
    user_message = "評価対象の論文:\n\n" + "\n\n".join(
        f"[{i + 1}] paper_id: {p['paper_id']}\n"
        f"title: {p.get('title', '')}\n"
        f"abstract: {p.get('abstract', '')[:ABSTRACT_MAX_CHARS]}"
        for i, p in enumerate(batch)
    )

    response = client.converse(
        modelId=SCORER_MODEL,
        system=[
            {"text": SYSTEM_PROMPT_TEMPLATE.format(interest_prompt=interest_prompt)}
        ],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        toolConfig={
            "tools": [SCORE_TOOL],
            "toolChoice": {"tool": {"name": "submit_scores"}},
        },
        inferenceConfig={"maxTokens": 2048},
    )

    content_blocks = response["output"]["message"]["content"]
    for block in content_blocks:
        tool_use = block.get("toolUse")
        if tool_use and tool_use.get("name") == "submit_scores":
            return list(tool_use["input"].get("results", []))
    return []


def update_scores(table: Any, results: list[dict[str, Any]]) -> int:
    """スコア結果を DynamoDB に書き戻す。score_padded は GSI 用の3桁ゼロ埋め。"""
    count = 0
    for r in results:
        table.update_item(
            Key={"paper_id": r["paper_id"]},
            UpdateExpression=(
                "SET score = :s, score_padded = :sp, score_reason = :r"
            ),
            ExpressionAttributeValues={
                ":s": int(r["score"]),
                ":sp": f"{int(r['score']):03d}",
                ":r": r["reason"],
            },
        )
        count += 1
    return count
