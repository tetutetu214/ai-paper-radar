"""scorer モジュールのテスト。"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from core import scorer


def _mock_anthropic_response(results: list[dict[str, Any]]) -> MagicMock:
    """Anthropic レスポンスを擬似生成。tool_use ブロック 1 個。"""
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"results": results}
    response = MagicMock()
    response.content = [block]
    return response


def _make_anthropic_client(results: list[dict[str, Any]]) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response(results)
    return client


def test_score_papers_returns_results() -> None:
    """論文を Anthropic に渡してスコアを取得できる。"""
    papers = [
        {"paper_id": "2401.00001", "title": "T1", "abstract": "A1"},
        {"paper_id": "2401.00002", "title": "T2", "abstract": "A2"},
    ]
    expected = [
        {"paper_id": "2401.00001", "score": 87, "reason": "関連性高い"},
        {"paper_id": "2401.00002", "score": 45, "reason": "やや関連"},
    ]
    client = _make_anthropic_client(expected)
    results = scorer.score_papers(client, papers, "テスト興味")
    assert results == expected
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["tool_choice"]["name"] == "submit_scores"


def test_score_papers_batches_at_10(monkeypatch: pytest.MonkeyPatch) -> None:
    """11 本以上は複数バッチに分割される。"""
    papers = [
        {"paper_id": f"2401.{i:05d}", "title": "T", "abstract": "A"}
        for i in range(15)
    ]
    call_log: list[int] = []

    def fake_batch(
        client: Any, batch: list[dict[str, Any]], interest: str
    ) -> list[dict[str, Any]]:
        call_log.append(len(batch))
        return [
            {"paper_id": p["paper_id"], "score": 50, "reason": "ok"}
            for p in batch
        ]

    monkeypatch.setattr(scorer, "_score_batch", fake_batch)
    client = MagicMock()
    results = scorer.score_papers(client, papers, "test")
    assert call_log == [10, 5]
    assert len(results) == 15


def test_score_papers_continues_on_batch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 バッチが失敗しても他バッチは続行される。"""
    papers = [
        {"paper_id": f"p{i}", "title": "T", "abstract": "A"} for i in range(15)
    ]
    call_log: list[str] = []

    def fake_batch(
        client: Any, batch: list[dict[str, Any]], interest: str
    ) -> list[dict[str, Any]]:
        call_log.append(batch[0]["paper_id"])
        if batch[0]["paper_id"] == "p0":
            raise RuntimeError("first batch fails")
        return [
            {"paper_id": p["paper_id"], "score": 50, "reason": "ok"}
            for p in batch
        ]

    monkeypatch.setattr(scorer, "_score_batch", fake_batch)
    client = MagicMock()
    results = scorer.score_papers(client, papers, "test")
    assert call_log == ["p0", "p10"]
    assert len(results) == 5


@mock_aws
def test_update_scores_writes_to_dynamodb() -> None:
    """スコア結果が DynamoDB に書き込まれる。"""
    dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
    table = dynamodb.create_table(
        TableName="test-papers",
        KeySchema=[{"AttributeName": "paper_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "paper_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    table.put_item(Item={"paper_id": "2401.00001", "title": "T"})

    results = [{"paper_id": "2401.00001", "score": 87, "reason": "良い"}]
    updated = scorer.update_scores(table, results)
    assert updated == 1

    item = table.get_item(Key={"paper_id": "2401.00001"})["Item"]
    assert int(item["score"]) == 87
    assert item["score_padded"] == "087"
    assert item["score_reason"] == "良い"


@mock_aws
def test_fetch_unscored_papers_filters_by_date_and_score() -> None:
    """score 未設定かつ指定日の論文のみ返る。"""
    dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
    table = dynamodb.create_table(
        TableName="test-papers",
        KeySchema=[{"AttributeName": "paper_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "paper_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    table.put_item(Item={"paper_id": "p1", "collected_date": "2026-05-05"})
    table.put_item(
        Item={
            "paper_id": "p2",
            "collected_date": "2026-05-05",
            "score": 80,
            "score_padded": "080",
        }
    )
    table.put_item(Item={"paper_id": "p3", "collected_date": "2026-05-04"})

    items = scorer.fetch_unscored_papers(table, "2026-05-05")
    paper_ids = {i["paper_id"] for i in items}
    assert paper_ids == {"p1"}
