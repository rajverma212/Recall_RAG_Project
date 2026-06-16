"""HTML loader using BeautifulSoup4 + lxml.

Strips <script> and <style> tags, then walks the DOM collecting text sections
delimited by heading elements (h1..h6). Each section carries its full heading
hierarchy as heading_path.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.ingestion.loaders.base import BaseLoader, LoadedSection

logger = get_logger(__name__)

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _heading_level(tag_name: str) -> int | None:
    if tag_name in _HEADING_TAGS:
        return int(tag_name[1])
    return None


class HTMLLoader(BaseLoader):
    def load(self, raw_bytes: bytes, filename: str) -> list[LoadedSection]:
        try:
            from bs4 import BeautifulSoup, NavigableString, Tag
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("beautifulsoup4 is required for HTML loading") from exc

        html = raw_bytes.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")

        # Remove non-content tags
        for tag in soup(["script", "style", "noscript", "meta", "head"]):
            tag.decompose()

        body = soup.body or soup

        sections: list[LoadedSection] = []
        heading_stack: dict[int, str] = {}  # level -> title text
        current_title: str | None = None
        buffer: list[str] = []
        ordinal = 0

        def flush():
            nonlocal ordinal
            text = " ".join(buffer).strip()
            if not text:
                buffer.clear()
                return
            path_parts = [heading_stack[lvl] for lvl in sorted(heading_stack)]
            heading_path = " > ".join(path_parts) if path_parts else None
            sections.append(
                LoadedSection(
                    text=text,
                    page_number=None,
                    section_title=current_title,
                    heading_path=heading_path,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
            buffer.clear()

        for element in body.descendants:
            if isinstance(element, NavigableString):
                text = str(element).strip()
                if text:
                    buffer.append(text)
            elif isinstance(element, Tag):
                level = _heading_level(element.name)
                if level is not None:
                    flush()
                    heading_text = element.get_text(separator=" ").strip()
                    # Clear deeper headings
                    for lvl in list(heading_stack.keys()):
                        if lvl >= level:
                            del heading_stack[lvl]
                    heading_stack[level] = heading_text
                    current_title = heading_text

        flush()

        # If nothing found, fall back to full text
        if not sections:
            text = body.get_text(separator=" ").strip()
            if text:
                sections.append(
                    LoadedSection(
                        text=text,
                        page_number=None,
                        section_title=None,
                        heading_path=None,
                        ordinal=0,
                    )
                )

        logger.info(f"HTMLLoader: {filename} → {len(sections)} sections")
        return sections
