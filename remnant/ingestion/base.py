"""Base ingestion adapter interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from remnant.models import IngestedDocument


class BaseIngester(ABC):
    """All source adapters implement this interface."""

    @abstractmethod
    async def fetch(self, query: str, max_results: int = 100,
                    since_year: int | None = None) -> AsyncIterator[IngestedDocument]:
        """Yield normalized documents matching the query."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str: ...
