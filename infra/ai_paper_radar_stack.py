"""AI Paper Radar スタック定義。詳細仕様は docs/spec.md §7 を参照。"""

from __future__ import annotations

from aws_cdk import (
    BundlingOptions,
    Duration,
    RemovalPolicy,
    Stack,
    aws_budgets as budgets,
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
        # bundling: Docker で requirements.txt の依存パッケージを Lambda 用に zip 化。
        # 関数アーキテクチャは x86_64。開発ホスト（WSL2 x86_64）と一致させて
        # native 拡張（pydantic_core 等）のクロスコンパイル問題を回避する。
        self.pipeline_fn = lambda_.Function(
            self,
            "PipelineFunction",
            function_name="ai-paper-radar-pipeline",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.X86_64,
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
            # 同時実行を 1 に固定。EventBridge Scheduler の重複起動や、
            # 手動 invoke の CLI 自動リトライによる二重起動を物理的に防ぐ
            # （2026-05-12 の事故再発防止、knowledge.md §4.4 参照）。
            reserved_concurrent_executions=1,
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
                resources=[f"arn:aws:kms:{self.region}:{self.account}:alias/aws/ssm"],
            )
        )

        # 権限: Bedrock Amazon Nova Pro を APAC Cross-Region Inference Profile 経由で呼ぶ
        # 公式手順（https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html）
        # APAC CRIS は東京・大阪・ソウル・ムンバイ・シンガポール・シドニーへ自動分散する。
        # 3-Statement 構造で最小権限を実装:
        #   ① 自リージョンの apac. inference profile への InvokeModel 許可
        #   ② 自リージョンの Foundation Model（Bedrock がローカル処理した場合）
        #   ③ APAC ルーティング先リージョンの Foundation Model（他リージョン処理時）
        # Statement ②③ には bedrock:InferenceProfileArn 一致条件を付け、別 CRIS profile
        # からこの FM を呼ぶ経路を禁止する（最小権限の核）
        bedrock_model_id = "amazon.nova-pro-v1:0"
        inference_profile_arn = (
            f"arn:aws:bedrock:{self.region}:{self.account}"
            f":inference-profile/apac.{bedrock_model_id}"
        )

        self.pipeline_fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="GrantApacCrisInferenceProfileRegionAccess",
                actions=["bedrock:InvokeModel"],
                resources=[inference_profile_arn],
                conditions={
                    "StringEquals": {
                        "aws:RequestedRegion": self.region,
                    },
                },
            )
        )

        self.pipeline_fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="GrantApacCrisInferenceProfileInRegionModelAccess",
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/{bedrock_model_id}"
                ],
                conditions={
                    "StringEquals": {
                        "aws:RequestedRegion": self.region,
                        "bedrock:InferenceProfileArn": inference_profile_arn,
                    },
                },
            )
        )

        # APAC 内の他リージョンへルーティングされた場合の FM ARN。ワイルドカードで
        # ap-* リージョンを許可しつつ、bedrock:InferenceProfileArn 条件で
        # この apac. プロファイル経由のみに限定する
        self.pipeline_fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="GrantApacCrisInferenceProfileCrossRegionModelAccess",
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:ap-*::foundation-model/{bedrock_model_id}"
                ],
                conditions={
                    "StringEquals": {
                        "bedrock:InferenceProfileArn": inference_profile_arn,
                    },
                },
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

        # 月次予算アラート（AWS Budgets）
        # CloudWatch Billing メトリクスは us-east-1 限定だが、Budgets はリージョン非依存
        # 通知先メアドは Context で指定: cdk deploy -c notification_email=user@example.com
        notification_email = self.node.try_get_context("notification_email")
        if notification_email:
            budgets.CfnBudget(
                self,
                "MonthlyCostBudget",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_type="COST",
                    budget_limit=budgets.CfnBudget.SpendProperty(
                        amount=10,
                        unit="USD",
                    ),
                    time_unit="MONTHLY",
                    budget_name="ai-paper-radar-monthly",
                ),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            comparison_operator="GREATER_THAN",
                            notification_type="ACTUAL",
                            threshold=80,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=[
                            budgets.CfnBudget.SubscriberProperty(
                                address=notification_email,
                                subscription_type="EMAIL",
                            ),
                        ],
                    ),
                ],
            )
