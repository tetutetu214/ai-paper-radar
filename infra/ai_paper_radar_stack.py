"""AI Paper Radar スタック定義。詳細仕様は docs/spec.md §7 を参照。"""
from __future__ import annotations

from aws_cdk import (
    BundlingOptions,
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_scheduler as scheduler,
)
from constructs import Construct


class AiPaperRadarStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 論文メタデータテーブル
        # PK=paper_id（arXiv ID, バージョン番号なし）
        # GSI=gsi_collected_date_score（収集日ごとのスコア降順取得用）
        # オンデマンド課金 + TTL 90日（属性 ttl に UNIX timestamp を入れて自動削除）
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

        # Lambda パイプライン関数
        # bundling: Docker で requirements.txt の依存パッケージを Lambda 用に zip 化
        self.pipeline_fn = lambda_.Function(
            self,
            "PipelineFunction",
            function_name="ai-paper-radar-pipeline",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="lambda_function.handler",
            code=lambda_.Code.from_asset(
                "lambdas/pipeline",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && "
                        "cp -au . /asset-output",
                    ],
                ),
            ),
            memory_size=1024,
            timeout=Duration.minutes(5),
            log_retention=logs.RetentionDays.ONE_MONTH,
            environment={
                "DYNAMODB_TABLE_NAME": self.papers_table.table_name,
                "SSM_PARAMETER_PATH_PREFIX": "/ai-paper-radar/runtime/",
                "LOG_LEVEL": "INFO",
                "MAX_PAPERS_PER_DAY": "50",
                "TOP_N_DELIVERY": "3",
            },
        )

        # 権限: DynamoDB R/W（GSI も含む）
        self.papers_table.grant_read_write_data(self.pipeline_fn)

        # 権限: SSM Parameter Store の SecureString 取得
        # CDK では SecureString パラメータを作成できないため、Lambda が読める権限のみ付与する
        # パラメータ実体はデプロイ後に aws ssm put-parameter で投入（spec.md §7.5 参照）
        self.pipeline_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParametersByPath",
                ],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}"
                    f":parameter/ai-paper-radar/runtime/*"
                ],
            )
        )

        # 権限: KMS Decrypt（SecureString 復号、AWS 管理キー alias/aws/ssm 用）
        self.pipeline_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["kms:Decrypt"],
                resources=[
                    f"arn:aws:kms:{self.region}:{self.account}:alias/aws/ssm"
                ],
            )
        )

        # EventBridge Scheduler が Lambda を invoke するための IAM Role
        scheduler_role = iam.Role(
            self,
            "PipelineSchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            description="Allows EventBridge Scheduler to invoke ai-paper-radar-pipeline",
        )
        self.pipeline_fn.grant_invoke(scheduler_role)

        # EventBridge Scheduler: 毎日 JST 6:00 に Lambda を起動
        # タイムゾーン Asia/Tokyo を指定することで、UTC 換算なしに直接 6 時を書ける
        scheduler.CfnSchedule(
            self,
            "PipelineSchedule",
            name="ai-paper-radar-daily",
            description="Trigger ai-paper-radar-pipeline every JST 6:00",
            schedule_expression="cron(0 6 * * ? *)",
            schedule_expression_timezone="Asia/Tokyo",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="OFF",
            ),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=self.pipeline_fn.function_arn,
                role_arn=scheduler_role.role_arn,
            ),
            state="ENABLED",
        )

        # TODO: CloudWatch Billing Alarm $10/月
