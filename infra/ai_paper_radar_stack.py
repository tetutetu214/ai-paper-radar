"""AI Paper Radar スタック定義。詳細仕様は docs/spec.md §7 を参照。"""
from __future__ import annotations

from aws_cdk import (
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
)
from constructs import Construct


class AiPaperRadarStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 論文メタデータテーブル
        # PK=paper_id（arXiv ID, バージョン番号なし）
        # GSI=gsi_collected_date_score（収集日ごとのスコア降順取得用）
        # オンデマンド課金 + TTL 90日（属性ttlに UNIX timestamp を入れて自動削除）
        self.papers_table = dynamodb.Table(
            self,
            "PapersTable",
            table_name="ai-paper-radar-papers",
            partition_key=dynamodb.Attribute(
                name="paper_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.papers_table.add_global_secondary_index(
            index_name="gsi_collected_date_score",
            partition_key=dynamodb.Attribute(
                name="collected_date",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="score_padded",
                type=dynamodb.AttributeType.STRING,
            ),
        )

        # TODO: Secrets Manager シークレット ai-paper-radar/runtime
        # TODO: Lambda 関数 ai-paper-radar-pipeline
        # TODO: EventBridge Scheduler cron(0 21 * * ? *) = JST 6:00
        # TODO: CloudWatch Billing Alarm $10/月
