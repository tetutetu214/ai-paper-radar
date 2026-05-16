"""lambda_function ハンドラの統合テスト。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from core.collector import Paper


@pytest.fixture
def aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", "test-papers")


@pytest.fixture
def settings_mock() -> MagicMock:
    s = MagicMock()
    s.dynamodb_table_name = "test-papers"
    s.aws_region = "ap-northeast-1"
    s.slack_webhook_url = "https://hooks.slack.com/test"
    s.interest_prompt = "テスト"
    s.top_n_delivery = 3
    s.max_papers_per_day = 50
    return s


def _create_test_table() -> Any:
    dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
    table = dynamodb.create_table(
        TableName="test-papers",
        KeySchema=[{"AttributeName": "paper_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "paper_id", "AttributeType": "S"},
            {"AttributeName": "collected_date", "AttributeType": "S"},
            {"AttributeName": "score_padded", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "gsi_collected_date_score",
                "KeySchema": [
                    {"AttributeName": "collected_date", "KeyType": "HASH"},
                    {"AttributeName": "score_padded", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    return table


@mock_aws
def test_handler_runs_full_pipeline(aws_env: None, settings_mock: MagicMock) -> None:
    """3 ステップが順に実行され、統計情報が返ること。"""
    _create_test_table()

    sample_papers = [
        Paper(
            paper_id="p1",
            title="Test",
            authors=[],
            abstract="abstract",
            published_at="",
            sources={"hf_daily"},
        )
    ]

    with (
        patch("lambda_function.get_settings", return_value=settings_mock),
        patch(
            "lambda_function.collector.fetch_all", return_value=sample_papers
        ) as mock_fetch_all,
        patch(
            "lambda_function.scorer.score_papers",
            return_value=[{"paper_id": "p1", "score": 87, "reason": "good"}],
        ),
        patch(
            "lambda_function.notifier.summarize_papers",
            return_value=[
                {
                    "paper_id": "p1",
                    "title": "T",
                    "title_ja": "タ",
                    "summary_ja": ["a", "b", "c"],
                    "score": 87,
                    "score_reason": "good",
                }
            ],
        ),
        patch("lambda_function.notifier.post_to_slack") as mock_slack,
    ):
        from lambda_function import handler

        result = handler({}, None)

    assert result["collected"] == 1
    assert result["scored"] == 1
    assert result["delivered"] == 1
    assert result["errors"] == []
    mock_slack.assert_called_once()
    # collector.fetch_all は settings.max_papers_per_day を limit に渡して呼ばれる
    mock_fetch_all.assert_called_once_with(limit=50)


@mock_aws
def test_handler_collects_errors_from_step_failures(
    aws_env: None, settings_mock: MagicMock
) -> None:
    """各ステップが失敗してもハンドラは止まらず、errors にメッセージが入る。"""
    _create_test_table()

    with (
        patch("lambda_function.get_settings", return_value=settings_mock),
        patch(
            "lambda_function.collector.fetch_all",
            side_effect=RuntimeError("collect fail"),
        ),
        patch(
            "lambda_function.scorer.fetch_unscored_papers",
            side_effect=RuntimeError("scan fail"),
        ),
        patch(
            "lambda_function.notifier.fetch_top_n",
            side_effect=RuntimeError("query fail"),
        ),
    ):
        from lambda_function import handler

        result = handler({}, None)

    assert result["collected"] == 0
    assert result["scored"] == 0
    assert result["delivered"] == 0
    assert len(result["errors"]) == 3
    assert "collector" in result["errors"][0]
    assert "scorer" in result["errors"][1]
    assert "notifier" in result["errors"][2]
