"""collector モジュールのテスト。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
import requests_mock as rm_module
from moto import mock_aws

from core import collector
from core.collector import Paper


# --- HF Daily Papers ---


def test_fetch_hf_daily_papers_parses_response(
    requests_mock: rm_module.Mocker,
) -> None:
    """HF Daily Papers のレスポンスを Paper に変換できる。"""
    requests_mock.get(
        "https://huggingface.co/api/daily_papers?date=2026-05-04",
        json=[
            {
                "paper": {
                    "id": "2401.13782v2",
                    "title": "Tweets to Citations",
                    "summary": "Abstract text.",
                    "authors": [{"name": "Author A"}, {"name": "Author B"}],
                    "publishedAt": "2024-01-25T00:00:00Z",
                    "upvotes": 42,
                }
            }
        ],
    )
    papers = collector.fetch_hf_daily_papers(date="2026-05-04")
    assert len(papers) == 1
    p = papers[0]
    assert p.paper_id == "2401.13782"
    assert p.title == "Tweets to Citations"
    assert p.authors == ["Author A", "Author B"]
    assert p.upvotes == 42
    assert p.sources == {"hf_daily"}


# --- arXiv ---


def _make_arxiv_atom(entries: list[tuple[str, str, datetime]]) -> str:
    items = "\n".join(
        f"""
        <entry>
            <id>http://arxiv.org/abs/{eid}v1</id>
            <title>{title}</title>
            <summary>Test abstract.</summary>
            <published>{dt.strftime("%Y-%m-%dT%H:%M:%SZ")}</published>
            <author><name>Auth</name></author>
        </entry>
        """
        for eid, title, dt in entries
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
    {items}
    </feed>"""


def test_fetch_arxiv_filters_by_age(requests_mock: rm_module.Mocker) -> None:
    """過去24h以内の論文のみが返ること。"""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(hours=2)
    old = now - timedelta(hours=48)
    atom = _make_arxiv_atom(
        [
            ("2401.00001", "Recent paper", recent),
            ("2401.00002", "Old paper", old),
        ]
    )
    requests_mock.get("http://export.arxiv.org/api/query", text=atom)
    papers = collector.fetch_arxiv(hours=24)
    paper_ids = {p.paper_id for p in papers}
    assert "2401.00001" in paper_ids
    assert "2401.00002" not in paper_ids


# --- HF Trending ---


def test_fetch_hf_trending_parses_response(
    requests_mock: rm_module.Mocker,
) -> None:
    requests_mock.get(
        "https://huggingface.co/api/papers?sort=trending",
        json=[
            {
                "paper": {
                    "id": "2502.12345",
                    "title": "Trending paper",
                    "summary": "Hot research",
                    "authors": [],
                    "publishedAt": "2025-02-15T00:00:00Z",
                    "upvotes": 100,
                }
            }
        ],
    )
    papers = collector.fetch_hf_trending()
    assert len(papers) == 1
    assert papers[0].sources == {"hf_trending"}


# --- 重複排除 ---


def test_merge_paper_combines_sources() -> None:
    papers_by_id: dict[str, Paper] = {}
    p1 = Paper(
        paper_id="2401.00001",
        title="Test",
        authors=[],
        abstract="",
        published_at="",
        sources={"hf_daily"},
        upvotes=10,
    )
    p2 = Paper(
        paper_id="2401.00001",
        title="Test",
        authors=[],
        abstract="",
        published_at="",
        sources={"arxiv"},
        upvotes=5,
    )
    collector._merge_paper(papers_by_id, p1)
    collector._merge_paper(papers_by_id, p2)
    merged = papers_by_id["2401.00001"]
    assert merged.sources == {"hf_daily", "arxiv"}
    assert merged.upvotes == 10


# --- DynamoDB upsert ---


def _create_table() -> object:
    dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
    table = dynamodb.create_table(
        TableName="test-papers",
        KeySchema=[{"AttributeName": "paper_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "paper_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    return table


@mock_aws
def test_upsert_dynamodb_creates_new_item() -> None:
    """新規論文を DynamoDB に書き込めること。"""
    table = _create_table()
    paper = Paper(
        paper_id="2401.00001",
        title="Test",
        authors=["A"],
        abstract="abstract",
        published_at="2024-01-01T00:00:00Z",
        sources={"hf_daily"},
        upvotes=10,
    )
    count = collector.upsert_dynamodb(table, [paper])
    assert count == 1

    item = table.get_item(Key={"paper_id": "2401.00001"})["Item"]
    assert item["title"] == "Test"
    assert item["source"] == {"hf_daily"}


@mock_aws
def test_upsert_dynamodb_merges_sources() -> None:
    """既存項目があればソースをマージする。"""
    table = _create_table()
    p1 = Paper(
        paper_id="2401.00001",
        title="Test",
        authors=[],
        abstract="",
        published_at="",
        sources={"hf_daily"},
    )
    collector.upsert_dynamodb(table, [p1])

    p2 = Paper(
        paper_id="2401.00001",
        title="Test",
        authors=[],
        abstract="",
        published_at="",
        sources={"arxiv"},
    )
    collector.upsert_dynamodb(table, [p2])

    item = table.get_item(Key={"paper_id": "2401.00001"})["Item"]
    assert item["source"] == {"hf_daily", "arxiv"}
