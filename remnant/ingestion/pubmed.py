"""PubMed ingestion adapter via NCBI E-utilities."""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx

from remnant.config import NCBI_API_KEY
from remnant.models import IngestedDocument, SourceType
from .base import BaseIngester

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedIngester(BaseIngester):
    source_name = "pubmed"

    async def fetch(self, query: str, max_results: int = 100,
                    since_year: int | None = None) -> AsyncIterator[IngestedDocument]:
        params: dict = {
            "db": "pubmed", "term": query,
            "retmax": max_results, "retmode": "json",
            "usehistory": "y",
        }
        if since_year:
            params["mindate"] = f"{since_year}/01/01"
            params["datetype"] = "pdat"
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{_BASE}/esearch.fcgi", params=params)
            r.raise_for_status()
            data = r.json()
            ids = data["esearchresult"].get("idlist", [])
            if not ids:
                return

            # Fetch abstracts
            fetch_params = {
                "db": "pubmed", "id": ",".join(ids),
                "retmode": "xml", "rettype": "abstract",
            }
            if NCBI_API_KEY:
                fetch_params["api_key"] = NCBI_API_KEY
            r2 = await client.get(f"{_BASE}/efetch.fcgi", params=fetch_params)
            r2.raise_for_status()

        root = ET.fromstring(r2.text)
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//PMID")
            title_el = article.find(".//ArticleTitle")
            abstract_el = article.find(".//AbstractText")
            if pmid_el is None or title_el is None:
                continue

            pmid = pmid_el.text or ""
            title = title_el.text or ""
            abstract = abstract_el.text if abstract_el is not None else ""

            year_el = article.find(".//PubDate/Year")
            pub_year = int(year_el.text) if year_el is not None else 2000

            authors = [
                f"{a.findtext('LastName', '')} {a.findtext('ForeName', '')}".strip()
                for a in article.findall(".//Author")
            ]
            mesh = [m.get("UI", "") for m in article.findall(".//MeshHeading/DescriptorName")]

            yield IngestedDocument(
                id=f"pubmed:{pmid}",
                source=SourceType.PUBMED,
                title=title,
                abstract=abstract or "",
                authors=authors,
                published_at=datetime(pub_year, 1, 1, tzinfo=timezone.utc),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                domain_tags=mesh,
                raw_metadata={"pmid": pmid},
            )
