"""arXiv ingestion adapter."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import AsyncIterator

import arxiv

from remnant.models import IngestedDocument, SourceType
from .base import BaseIngester


class ArxivIngester(BaseIngester):
    source_name = "arxiv"

    def __init__(self, page_size: int = 50) -> None:
        self._client = arxiv.Client(page_size=page_size)

    async def fetch(self, query: str, max_results: int = 100,
                    since_year: int | None = None) -> AsyncIterator[IngestedDocument]:
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        for result in self._client.results(search):
            pub_year = result.published.year
            if since_year and pub_year < since_year:
                continue

            doc_id = hashlib.sha1(result.entry_id.encode()).hexdigest()[:16]
            yield IngestedDocument(
                id=f"arxiv:{doc_id}",
                source=SourceType.ARXIV,
                title=result.title,
                abstract=result.summary,
                authors=[a.name for a in result.authors],
                published_at=result.published.replace(tzinfo=timezone.utc)
                    if result.published.tzinfo is None else result.published,
                url=result.entry_id,
                domain_tags=result.categories,
                raw_metadata={
                    "arxiv_id": result.entry_id,
                    "categories": result.categories,
                    "doi": result.doi,
                },
            )
