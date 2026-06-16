"""PDF loader using pypdf — one LoadedSection per page."""
from __future__ import annotations

import io
import re

from app.core.logging import get_logger
from app.ingestion.loaders.base import BaseLoader, LoadedSection

logger = get_logger(__name__)

# Heuristic: a heading-like line is short, starts with a capital letter or
# number, and contains no sentence-ending punctuation mid-way.
_HEADING_RE = re.compile(r"^[A-Z0-9][^\n]{0,120}$")


def _extract_heading(text: str) -> str | None:
    """Return the first heading-like line from *text*, or None."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and _HEADING_RE.match(stripped) and len(stripped) > 3:
            return stripped
    return None


class PDFLoader(BaseLoader):
    def load(self, raw_bytes: bytes, filename: str) -> list[LoadedSection]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pypdf is required for PDF loading") from exc

        reader = PdfReader(io.BytesIO(raw_bytes))
        sections: list[LoadedSection] = []

        for page_idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if not text:
                logger.debug(f"PDF page {page_idx} of {filename} is empty, skipping")
                continue

            section_title = _extract_heading(text)
            sections.append(
                LoadedSection(
                    text=text,
                    page_number=page_idx,
                    section_title=section_title,
                    heading_path=section_title,
                    ordinal=len(sections),
                )
            )

        logger.info(f"PDFLoader: {filename} → {len(sections)} sections from {len(reader.pages)} pages")
        return sections
