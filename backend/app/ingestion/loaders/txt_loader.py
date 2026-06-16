"""Plain-text loader.

Splits the document into sections by blank-line-delimited paragraphs.
Each paragraph becomes one LoadedSection with no heading metadata.
"""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.ingestion.loaders.base import BaseLoader, LoadedSection

logger = get_logger(__name__)

_BLANK_LINES = re.compile(r"\n\s*\n")


class TxtLoader(BaseLoader):
    def load(self, raw_bytes: bytes, filename: str) -> list[LoadedSection]:
        source = raw_bytes.decode("utf-8", errors="replace")
        paragraphs = _BLANK_LINES.split(source)

        sections: list[LoadedSection] = []
        for idx, para in enumerate(paragraphs):
            text = para.strip()
            if not text:
                continue
            sections.append(
                LoadedSection(
                    text=text,
                    page_number=None,
                    section_title=None,
                    heading_path=None,
                    ordinal=len(sections),
                )
            )

        # If no blank-line splits exist, treat the whole file as one section
        if not sections and source.strip():
            sections.append(
                LoadedSection(
                    text=source.strip(),
                    page_number=None,
                    section_title=None,
                    heading_path=None,
                    ordinal=0,
                )
            )

        logger.info(f"TxtLoader: {filename} → {len(sections)} sections")
        return sections
