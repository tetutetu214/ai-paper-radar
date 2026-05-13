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


# --- upvotes 降順ソートと件数上限カット ---


def _make_paper(paper_id: str, upvotes: int) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=[],
        abstract="",
        published_at="",
        sources={"hf_daily"},
        upvotes=upvotes,
    )


def test_select_top_papers_sorts_by_upvotes_desc() -> None:
    """upvotes 降順、同点は paper_id 昇順で並ぶこと。"""
    papers = [
        _make_paper("2401.00003", 10),
        _make_paper("2401.00001", 50),
        _make_paper("2401.00002", 10),
        _make_paper("2401.00004", 30),
    ]
    sorted_papers = collector._select_top_papers(papers, limit=None)
    paper_ids = [p.paper_id for p in sorted_papers]
    # upvotes 50, 30, 10(2401.00002), 10(2401.00003) の順
    assert paper_ids == ["2401.00001", "2401.00004", "2401.00002", "2401.00003"]


def test_select_top_papers_respects_limit() -> None:
    """limit が指定されていれば先頭 limit 件に絞る。"""
    papers = [
        _make_paper("p1", 10),
        _make_paper("p2", 50),
        _make_paper("p3", 30),
        _make_paper("p4", 5),
    ]
    result = collector._select_top_papers(papers, limit=2)
    assert [p.paper_id for p in result] == ["p2", "p3"]


def test_select_top_papers_with_limit_larger_than_papers_returns_all() -> None:
    """limit が件数より大きい場合は全件返す（パディングしない）。"""
    papers = [_make_paper("p1", 10), _make_paper("p2", 5)]
    result = collector._select_top_papers(papers, limit=10)
    assert len(result) == 2


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


@mock_aws
def test_upsert_dynamodb_preserves_score_fields() -> None:
    """既存レコードに score/summary/delivered 系があれば、再 upsert でも保持される。

    HF Trending で複数日にまたがって露出する論文が、毎日再採点されないことを保証する。
    """
    table = _create_table()
    # 1日目: 新規収集 → 採点 → 配信 までの状態を再現
    p1 = Paper(
        paper_id="2401.00001",
        title="Test",
        authors=[],
        abstract="abstract v1",
        published_at="2024-01-01T00:00:00Z",
        sources={"hf_daily"},
        upvotes=5,
    )
    collector.upsert_dynamodb(table, [p1])
    table.update_item(
        Key={"paper_id": "2401.00001"},
        UpdateExpression=(
            "SET score = :s, score_padded = :sp, score_reason = :r, "
            "summary_ja = :sm, delivered_at = :d"
        ),
        ExpressionAttributeValues={
            ":s": 87,
            ":sp": "087",
            ":r": "ユーザー興味と高関連",
            ":sm": ["要点1", "要点2", "要点3"],
            ":d": "2024-01-01T21:00:00Z",
        },
    )

    # 2日目: HF Trending で再露出 → 再 upsert（score 系は触らない想定）
    p2 = Paper(
        paper_id="2401.00001",
        title="Test",
        authors=[],
        abstract="abstract v1",
        published_at="2024-01-01T00:00:00Z",
        sources={"hf_trending"},
        upvotes=8,
    )
    collector.upsert_dynamodb(table, [p2])

    item = table.get_item(Key={"paper_id": "2401.00001"})["Item"]
    assert item["score"] == 87
    assert item["score_padded"] == "087"
    assert item["score_reason"] == "ユーザー興味と高関連"
    assert item["summary_ja"] == ["要点1", "要点2", "要点3"]
    assert item["delivered_at"] == "2024-01-01T21:00:00Z"
    assert item["source"] == {"hf_daily", "hf_trending"}
    assert item["upvotes"] == 8


@mock_aws
def test_upsert_dynamodb_updates_mutable_fields() -> None:
    """既存レコードの title/abstract/authors は新値で上書きされる。"""
    table = _create_table()
    p1 = Paper(
        paper_id="2401.00001",
        title="Old title",
        authors=["Old Author"],
        abstract="Old abstract",
        published_at="2024-01-01T00:00:00Z",
        sources={"hf_daily"},
        upvotes=10,
    )
    collector.upsert_dynamodb(table, [p1])

    p2 = Paper(
        paper_id="2401.00001",
        title="New title",
        authors=["New Author"],
        abstract="New abstract",
        published_at="2024-01-01T00:00:00Z",
        sources={"hf_trending"},
        upvotes=3,
    )
    collector.upsert_dynamodb(table, [p2])

    item = table.get_item(Key={"paper_id": "2401.00001"})["Item"]
    assert item["title"] == "New title"
    assert item["authors"] == ["New Author"]
    assert item["abstract"] == "New abstract"
    # upvotes は両者の max を採用（HF API のカウントは時に減少することがあるため）
    assert item["upvotes"] == 10
