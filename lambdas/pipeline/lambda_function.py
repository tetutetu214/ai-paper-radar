"""AI Paper Radar Lambda エントリポイント。

EventBridge Scheduler から毎日 JST 6:00 に起動され、HF Daily Papers と arXiv
から論文を収集してスコアリング、上位 N 本を Slack へ配信する。
詳細フローは docs/spec.md §4.5 を参照。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from anthropic import AnthropicBedrock

from core import collector, notifier, scorer
from core.settings import get_settings

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda ハンドラ。collector → scorer → notifier を順に実行。

    各ステップは独立して try/except で囲む。一部失敗しても他は継続し、
    エラーは errors リストに集約して戻り値に含める（CloudWatch Logs にも残る）。
    """
    logger.info("Pipeline started")
    settings = get_settings()

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(settings.dynamodb_table_name)
    # Bedrock 経由（IAM 認証）。aws_region は Lambda の実行リージョン
    anthropic_client = AnthropicBedrock(aws_region=settings.aws_region)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    errors: list[str] = []

    # Step 1: 収集
    collected = 0
    try:
        papers = collector.fetch_all()
        collected = collector.upsert_dynamodb(table, papers)
        logger.info("Collected %d papers", collected)
    except Exception as e:
        logger.exception("Collector failed")
        errors.append(f"collector: {e}")

    # Step 2: スコアリング
    scored = 0
    try:
        unscored = scorer.fetch_unscored_papers(table, today)
        if unscored:
            results = scorer.score_papers(
                anthropic_client, unscored, settings.interest_prompt
            )
            scored = scorer.update_scores(table, results)
        logger.info("Scored %d papers", scored)
    except Exception as e:
        logger.exception("Scorer failed")
        errors.append(f"scorer: {e}")

    # Step 3: 配信
    delivered = 0
    try:
        top_n = notifier.fetch_top_n(table, today, settings.top_n_delivery)
        if top_n:
            enriched = notifier.summarize_papers(anthropic_client, top_n)
            notifier.post_to_slack(settings.slack_webhook_url, enriched)
            notifier.mark_delivered(table, top_n)
            delivered = len(top_n)
        logger.info("Delivered %d papers", delivered)
    except Exception as e:
        logger.exception("Notifier failed")
        errors.append(f"notifier: {e}")

    return {
        "collected": collected,
        "scored": scored,
        "delivered": delivered,
        "errors": errors,
    }
