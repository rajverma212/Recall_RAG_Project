"""Base loader contract for all document types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LoadedSection:
    """A contiguous piece of a document extracted by a loader."""

    text: str
    page_number: int | None = None
    section_title: str | None = None
    heading_path: str | None = None
    ordinal: int = 0


class BaseLoader(ABC):
    """Abstract base class for document loaders."""

    @abstractmethod
    def load(self, raw_bytes: bytes, filename: str) -> list[LoadedSection]:
        """Parse *raw_bytes* and return a list of LoadedSection objects."""
        ...
