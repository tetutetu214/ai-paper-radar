"""論文収集モジュール。詳細仕様は docs/spec.md §2 を参照。

データソース:
- HF Daily Papers API: https://huggingface.co/api/daily_papers?date=YYYY-MM-DD
- arXiv API: http://export.arxiv.org/api/query
- HF Trending Papers: https://huggingface.co/api/papers?sort=trending
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

# arXiv ID 正規化用 (例: "2401.13782v2" -> "2401.13782")
_ARXIV_ID_VERSION_PATTERN = re.compile(r"v\d+$")
_ARXIV_URL_PATTERN = re.compile(r"/abs/(\d+\.\d+)(?:v\d+)?")


@dataclass
class Paper:
    """論文メタデータ。DynamoDB の論文項目と対応。"""

    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    published_at: str
    sources: set[str] = field(default_factory=set)
    upvotes: int = 0


def fetch_all() -> list[Paper]:
    """全データソースから論文を取得し、重複排除して返す。

    1 ソースが失敗しても他で継続する設計。全失敗の場合は空リスト。
    """
    papers_by_id: dict[str, Paper] = {}

    for source_name, fetcher in [
        ("HF Daily Papers", fetch_hf_daily_papers),
        ("arXiv", fetch_arxiv),
        ("HF Trending", fetch_hf_trending),
    ]:
        try:
            for paper in fetcher():
                _merge_paper(papers_by_id, paper)
        except Exception:
            logger.exception(
                "%s fetch failed; continuing with other sources", source_name
            )

    return list(papers_by_id.values())


def _merge_paper(papers_by_id: dict[str, Paper], paper: Paper) -> None:
    """同じ paper_id があればソース・upvote をマージ、なければ追加。"""
    existing = papers_by_id.get(paper.paper_id)
    if existing is None:
        papers_by_id[paper.paper_id] = paper
    else:
        existing.sources.update(paper.sources)
        existing.upvotes = max(existing.upvotes, paper.upvotes)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception_type((requests.RequestException,)),
)
def fetch_hf_daily_papers(date: str | None = None) -> list[Paper]:
    """HF Daily Papers API から指定日（デフォルト: 前日）のキュレーションを取得。"""
    if date is None:
        date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    url = f"https://huggingface.co/api/daily_papers?date={date}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    papers: list[Paper] = []
    for entry in data:
        paper_data = entry.get("paper", {})
        paper_id = _normalize_arxiv_id(paper_data.get("id", ""))
        if not paper_id:
            continue
        papers.append(
            Paper(
                paper_id=paper_id,
                title=paper_data.get("title", ""),
                authors=[a.get("name", "") for a in paper_data.get("authors", [])],
                abstract=paper_data.get("summary", ""),
                published_at=paper_data.get("publishedAt", ""),
                sources={"hf_daily"},
                upvotes=int(paper_data.get("upvotes", 0)),
            )
        )

    return papers


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=3, max=15),
    retry=retry_if_exception_type((requests.RequestException,)),
)
def fetch_arxiv(hours: int = 24, max_results: int = 200) -> list[Paper]:
    """arXiv API から過去 N 時間の cs.CL/cs.AI/cs.LG 新着を取得。"""
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": "cat:cs.CL OR cat:cs.AI OR cat:cs.LG",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
    }
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    feed = feedparser.parse(response.content)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    papers: list[Paper] = []
    for entry in feed.entries:
        if not getattr(entry, "published_parsed", None):
            continue
        published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if published_dt < cutoff:
            continue
        match = _ARXIV_URL_PATTERN.search(entry.id)
        if not match:
            continue
        papers.append(
            Paper(
                paper_id=match.group(1),
                title=entry.title.strip(),
                authors=[a.name for a in getattr(entry, "authors", [])],
                abstract=entry.summary.strip(),
                published_at=published_dt.isoformat(),
                sources={"arxiv"},
            )
        )

    return papers


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception_type((requests.RequestException,)),
)
def fetch_hf_trending(limit: int = 50) -> list[Paper]:
    """HF Trending Papers API から上位を取得。"""
    url = "https://huggingface.co/api/papers?sort=trending"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()[:limit]

    papers: list[Paper] = []
    for entry in data:
        paper_data = entry.get("paper", {}) or entry
        paper_id = _normalize_arxiv_id(paper_data.get("id", ""))
        if not paper_id:
            continue
        papers.append(
            Paper(
                paper_id=paper_id,
                title=paper_data.get("title", ""),
                authors=[a.get("name", "") for a in paper_data.get("authors", [])],
                abstract=paper_data.get("summary", ""),
                published_at=paper_data.get("publishedAt", ""),
                sources={"hf_trending"},
                upvotes=int(paper_data.get("upvotes", 0)),
            )
        )

    return papers


def _normalize_arxiv_id(raw_id: str) -> str:
    if not raw_id:
        return ""
    return _ARXIV_ID_VERSION_PATTERN.sub("", raw_id.strip())


def upsert_dynamodb(table: Any, papers: list[Paper]) -> int:
    """DynamoDB に upsert。

    既存レコードがある場合は update_item で可変メタデータのみ更新し、
    score/score_padded/score_reason/summary_ja/delivered_at は保持する。
    これにより HF Trending などで複数日にまたがって出現する論文が、
    毎日再採点・再要約されてしまう問題を防ぐ。
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    ttl = int((now + timedelta(days=90)).timestamp())
    upserted = 0

    for paper in papers:
        existing = table.get_item(Key={"paper_id": paper.paper_id}).get("Item")
        if existing:
            _update_existing_item(table, paper, existing, now, today, ttl)
        else:
            _put_new_item(table, paper, now, today, ttl)
        upserted += 1

    return upserted


def _update_existing_item(
    table: Any,
    paper: Paper,
    existing: dict[str, Any],
    now: datetime,
    today: str,
    ttl: int,
) -> None:
    """既存レコードを更新。score 系の属性は触らない。"""
    existing_upvotes = int(existing.get("upvotes", 0))
    merged_upvotes = max(paper.upvotes, existing_upvotes)

    # source は予約語ではないが、可読性のため #src エイリアスで統一
    expr_attr_names: dict[str, str] = {"#src": "source", "#ttl": "ttl"}
    expr_attr_values: dict[str, Any] = {
        ":t": paper.title,
        ":a": paper.authors,
        ":ab": paper.abstract,
        ":p": paper.published_at,
        ":ca": now.isoformat(),
        ":cd": today,
        ":u": merged_upvotes,
        ":ttl": ttl,
    }
    set_clause = (
        "SET title = :t, authors = :a, abstract = :ab, published_at = :p, "
        "collected_at = :ca, collected_date = :cd, upvotes = :u, #ttl = :ttl"
    )
    update_expression = set_clause
    # source は集合 ADD で既存値とマージ（put_item 全置換と違い score を保持）
    if paper.sources:
        update_expression += " ADD #src :s"
        expr_attr_values[":s"] = set(paper.sources)

    table.update_item(
        Key={"paper_id": paper.paper_id},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values,
    )


def _put_new_item(
    table: Any, paper: Paper, now: datetime, today: str, ttl: int
) -> None:
    """新規レコードを作成。score 系は最初から存在しない。"""
    item: dict[str, Any] = {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "published_at": paper.published_at,
        "collected_at": now.isoformat(),
        "collected_date": today,
        "source": set(paper.sources),
        "upvotes": paper.upvotes,
        "ttl": ttl,
    }
    table.put_item(Item=item)
