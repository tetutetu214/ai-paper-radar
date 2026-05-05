"""AI Paper Radar Lambda エントリポイント。

EventBridge Scheduler から起動され、HF Daily Papers と arXiv から論文を
収集してスコアリング、Slack へ配信する。詳細フローは docs/spec.md §4.5 を参照。
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    logger.info("Pipeline started")
    # TODO Phase 2: collector -> scorer -> notifier の順に実行
    return {"collected": 0, "scored": 0, "delivered": 0, "errors": []}
