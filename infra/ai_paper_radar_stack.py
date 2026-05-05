"""AI Paper Radar スタック定義。詳細仕様は docs/spec.md §7 を参照。"""
from __future__ import annotations

from aws_cdk import Stack
from constructs import Construct


class AiPaperRadarStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # TODO Phase 2: DynamoDB テーブル ai-paper-radar-papers
        # TODO Phase 2: Secrets Manager シークレット ai-paper-radar/runtime
        # TODO Phase 2: Lambda 関数 ai-paper-radar-pipeline
        # TODO Phase 2: EventBridge Scheduler cron(0 21 * * ? *) = JST 6:00
        # TODO Phase 2: CloudWatch Billing Alarm $10/月
