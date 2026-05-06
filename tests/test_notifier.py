"""notifier モジュールのテスト。"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import boto3
import pytest
import requests_mock as rm_module
from moto import mock_aws

from core import notifier


def _mock_anthropic_response(input_dict: dict[str, Any]) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = input_dict
    response = MagicMock()
    response.content = [block]
    return response


def test_summarize_papers_enriches_with_japanese_fields() -> None:
    """Anthropic 要約結果を title_ja / summary_ja に詰める。"""
    papers = [{"paper_id": "p1", "title": "Original Title", "abstract": "Long text"}]
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response(
        {"title_ja": "原文タイトル", "summary_ja": ["要点1", "要点2", "要点3"]}
    )
    enriched = notifier.summarize_papers(client, papers)
    assert enriched[0]["title_ja"] == "原文タイトル"
    assert enriched[0]["summary_ja"] == ["要点1", "要点2", "要点3"]
    # 元のフィールドも残る
    assert enriched[0]["title"] == "Original Title"


def test_summarize_papers_fallback_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """要約に失敗してもフォールバックで配信を止めない。"""
    papers = [{"paper_id": "p1", "title": "OT", "abstract": "A"}]

    def fail(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("summary failure")

    monkeypatch.setattr(notifier, "_summarize_one", fail)
    client = MagicMock()
    enriched = notifier.summarize_papers(client, papers)
    assert enriched[0]["summary_ja"] == ["（要約失敗）"]
    assert enriched[0]["title_ja"] == "OT"


def test_build_blocks_structure() -> None:
    """Block Kit 構造が期待通り（header / section / divider / context）。"""
    papers = [
        {
            "paper_id": "2401.13782",
            "title": "Tweets to Citations",
            "title_ja": "ツイートと被引用",
            "summary_ja": ["要点1", "要点2", "要点3"],
            "score": 87,
            "score_reason": "理由",
        },
    ]
    blocks = notifier.build_blocks(papers, "2026-05-05")
    assert blocks[0]["type"] == "header"
    assert "2026-05-05" in blocks[0]["text"]["text"]
    # 論文セクションが含まれる
    section_texts = [
        b["text"]["text"] for b in blocks if b["type"] == "section"
    ]
    paper_section = next(s for s in section_texts if "2401.13782" in s)
    assert "Tweets to Citations" in paper_section
    assert "87" in paper_section
    # 末尾は context
    assert blocks[-1]["type"] == "context"


def test_post_to_slack_sends_blocks(requests_mock: rm_module.Mocker) -> None:
    """Slack Webhook に blocks 付きで POST される。"""
    webhook = "https://hooks.slack.com/services/test"
    requests_mock.post(webhook, status_code=200)
    papers = [
        {
            "paper_id": "p1",
            "title": "T",
            "title_ja": "タ",
            "summary_ja": ["a", "b", "c"],
            "score": 50,
            "score_reason": "r",
        }
    ]
    notifier.post_to_slack(webhook, papers)
    last_request = requests_mock.last_request
    assert last_request.method == "POST"
    body = last_request.json()
    assert "blocks" in body
    assert any(b["type"] == "header" for b in body["blocks"])


@mock_aws
def test_fetch_top_n_uses_gsi() -> None:
    """GSI でスコア降順、上位 N を取得できる。"""
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
    for pid, score in [("p1", 50), ("p2", 87), ("p3", 30), ("p4", 95)]:
        table.put_item(
            Item={
                "paper_id": pid,
                "collected_date": "2026-05-05",
                "score": score,
                "score_padded": f"{score:03d}",
            }
        )

    top3 = notifier.fetch_top_n(table, "2026-05-05", n=3)
    paper_ids = [i["paper_id"] for i in top3]
    assert paper_ids == ["p4", "p2", "p1"]  # 95, 87, 50


@mock_aws
def test_mark_delivered_sets_timestamp() -> None:
    """delivered_at 属性が設定される。"""
    dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
    table = dynamodb.create_table(
        TableName="test-papers",
        KeySchema=[{"AttributeName": "paper_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "paper_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    table.put_item(Item={"paper_id": "p1", "title": "T"})

    notifier.mark_delivered(table, [{"paper_id": "p1"}])
    item = table.get_item(Key={"paper_id": "p1"})["Item"]
    assert "delivered_at" in item
