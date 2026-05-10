"""CDK スタックのスナップショットテスト。

`aws_cdk.assertions.Template` で生成された CloudFormation の主要属性を検証する。
詳細仕様は docs/spec.md §7 を参照。
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.ai_paper_radar_stack import AiPaperRadarStack


def _make_template(context: dict[str, str] | None = None) -> Template:
    app = cdk.App(context=context)
    stack = AiPaperRadarStack(app, "TestStack")
    return Template.from_stack(stack)


def test_dynamodb_table_created() -> None:
    """DynamoDB テーブルが規定の属性で作成されること。"""
    template = _make_template()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "ai-paper-radar-papers",
            "BillingMode": "PAY_PER_REQUEST",
            "TimeToLiveSpecification": {
                "AttributeName": "ttl",
                "Enabled": True,
            },
        },
    )


def test_dynamodb_gsi_created() -> None:
    """GSI が collected_date + score_padded で作成されること。"""
    template = _make_template()
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        Match.object_like(
            {
                "GlobalSecondaryIndexes": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "IndexName": "gsi_collected_date_score",
                                "KeySchema": [
                                    {"AttributeName": "collected_date", "KeyType": "HASH"},
                                    {"AttributeName": "score_padded", "KeyType": "RANGE"},
                                ],
                            }
                        )
                    ]
                )
            }
        ),
    )


def test_lambda_function_created() -> None:
    """Lambda 関数が規定の構成で作成されること。"""
    template = _make_template()
    template.has_resource_properties(
        "AWS::Lambda::Function",
        Match.object_like(
            {
                "FunctionName": "ai-paper-radar-pipeline",
                "Runtime": "python3.12",
                "Architectures": ["arm64"],
                "MemorySize": 1024,
                "Timeout": 300,
                "Handler": "lambda_function.handler",
            }
        ),
    )


def test_lambda_environment_variables() -> None:
    """Lambda 環境変数に DynamoDB テーブル名と SSM パスが含まれること。"""
    template = _make_template()
    template.has_resource_properties(
        "AWS::Lambda::Function",
        Match.object_like(
            {
                "FunctionName": "ai-paper-radar-pipeline",
                "Environment": Match.object_like(
                    {
                        "Variables": Match.object_like(
                            {
                                "SSM_PARAMETER_PATH_PREFIX": "/ai-paper-radar/runtime/",
                                "MAX_PAPERS_PER_DAY": "50",
                                "TOP_N_DELIVERY": "3",
                            }
                        )
                    }
                ),
            }
        ),
    )


def test_scheduler_created() -> None:
    """EventBridge Scheduler が JST 6:00 cron で作成されること。"""
    template = _make_template()
    template.has_resource_properties(
        "AWS::Scheduler::Schedule",
        {
            "Name": "ai-paper-radar-daily",
            "ScheduleExpression": "cron(0 6 * * ? *)",
            "ScheduleExpressionTimezone": "Asia/Tokyo",
            "State": "ENABLED",
        },
    )


def test_budget_skipped_without_email_context() -> None:
    """Context 未指定なら Budget リソースは作成されないこと。"""
    template = _make_template()
    template.resource_count_is("AWS::Budgets::Budget", 0)


def test_budget_created_with_email_context() -> None:
    """Context で notification_email を指定すると Budget が作成されること。"""
    template = _make_template(context={"notification_email": "test@example.com"})
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        Match.object_like(
            {
                "Budget": Match.object_like(
                    {
                        "BudgetName": "ai-paper-radar-monthly",
                        "BudgetType": "COST",
                        "TimeUnit": "MONTHLY",
                        "BudgetLimit": {"Amount": 10, "Unit": "USD"},
                    }
                )
            }
        ),
    )


def test_resource_counts() -> None:
    """主要リソースが期待数だけ作成されていること。"""
    template = _make_template()
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    # Lambda 本体 + log_retention 用の Custom Resource Lambda
    template.resource_count_is("AWS::Lambda::Function", 2)
    template.resource_count_is("AWS::Scheduler::Schedule", 1)


def test_lambda_role_has_bedrock_invoke_permission() -> None:
    """Lambda 実行ロールに global cross-Region inference 公式 3-Statement の権限があること。

    出典: https://docs.aws.amazon.com/bedrock/latest/userguide/global-cross-region-inference.html
    """
    template = _make_template()
    model_id = "anthropic.claude-haiku-4-5-20251001-v1:0"

    # ① ソース inference profile への呼び出し（自リージョン限定）
    template.has_resource_properties(
        "AWS::IAM::Policy",
        Match.object_like(
            {
                "PolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Sid": "GrantGlobalCrisInferenceProfileRegionAccess",
                                        "Action": "bedrock:InvokeModel",
                                        "Effect": "Allow",
                                        "Condition": {
                                            "StringEquals": {
                                                "aws:RequestedRegion": Match.any_value(),
                                            },
                                        },
                                    }
                                )
                            ]
                        )
                    }
                )
            }
        ),
    )

    # ② 自リージョンの Foundation Model（ローカル処理時）
    template.has_resource_properties(
        "AWS::IAM::Policy",
        Match.object_like(
            {
                "PolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Sid": "GrantGlobalCrisInferenceProfileInRegionModelAccess",
                                        "Action": "bedrock:InvokeModel",
                                        "Effect": "Allow",
                                        "Condition": {
                                            "StringEquals": Match.object_like(
                                                {
                                                    "bedrock:InferenceProfileArn": Match.any_value(),
                                                }
                                            ),
                                        },
                                    }
                                )
                            ]
                        )
                    }
                )
            }
        ),
    )

    # ③ グローバル Foundation Model（他リージョン経路、ARN のリージョン部空 + RequestedRegion=unspecified）
    template.has_resource_properties(
        "AWS::IAM::Policy",
        Match.object_like(
            {
                "PolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Sid": "GrantGlobalCrisInferenceProfileGlobalModelAccess",
                                        "Action": "bedrock:InvokeModel",
                                        "Effect": "Allow",
                                        "Resource": f"arn:aws:bedrock:::foundation-model/{model_id}",
                                        "Condition": {
                                            "StringEquals": Match.object_like(
                                                {
                                                    "aws:RequestedRegion": "unspecified",
                                                    "bedrock:InferenceProfileArn": Match.any_value(),
                                                }
                                            ),
                                        },
                                    }
                                )
                            ]
                        )
                    }
                )
            }
        ),
    )
