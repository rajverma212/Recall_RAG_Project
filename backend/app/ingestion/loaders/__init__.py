"""Loader factory — maps doc_type strings to concrete loader instances."""
from __future__ import annotations

from app.ingestion.loaders.base import BaseLoader, LoadedSection

__all__ = ["get_loader", "BaseLoader", "LoadedSection"]


def get_loader(doc_type: str) -> BaseLoader:
    """Return the appropriate loader for *doc_type*.

    Supported types: pdf, markdown, html, txt.
    Raises ValueError for unknown types.
    """
    if doc_type == "pdf":
        from app.ingestion.loaders.pdf_loader import PDFLoader
        return PDFLoader()
    elif doc_type == "markdown":
        from app.ingestion.loaders.markdown_loader import MarkdownLoader
        return MarkdownLoader()
    elif doc_type == "html":
        from app.ingestion.loaders.html_loader import HTMLLoader
        return HTMLLoader()
    elif doc_type == "txt":
        from app.ingestion.loaders.txt_loader import TxtLoader
        return TxtLoader()
    else:
        raise ValueError(f"Unsupported doc_type: {doc_type!r}")
