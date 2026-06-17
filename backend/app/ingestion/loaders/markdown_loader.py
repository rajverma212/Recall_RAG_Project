"""Markdown loader using markdown-it-py.

Splits a markdown document into sections at heading boundaries (H1/H2/H3).
Each section inherits the full heading_path down to its nearest heading and
carries the text between that heading and the next same-or-higher heading.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.ingestion.loaders.base import BaseLoader, LoadedSection

logger = get_logger(__name__)


def _heading_level(token) -> int | None:
    """Return the heading level (1-6) for an *h_open* token, else None."""
    if token.type == "heading_open":
        return int(token.tag[1])  # "h1" -> 1
    return None


class MarkdownLoader(BaseLoader):
    def load(self, raw_bytes: bytes, filename: str) -> list[LoadedSection]:
        try:
            from markdown_it import MarkdownIt
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("markdown-it-py is required for Markdown loading") from exc

        source = raw_bytes.decode("utf-8", errors="replace")
        md = MarkdownIt()
        tokens = md.parse(source)

        sections: list[LoadedSection] = []
        # Track the current heading hierarchy: level -> title
        heading_stack: dict[int, str] = {}
        current_title: str | None = None
        buffer: list[str] = []
        ordinal = 0

        def flush_section():
            nonlocal ordinal
            text = "\n".join(buffer).strip()
            if not text:
                return
            # Build heading path from the stack
            path_parts = [heading_stack[lvl] for lvl in sorted(heading_stack)]
            heading_path = " > ".join(path_parts) if path_parts else None
            # The section_title is the innermost heading
            title = current_title
            sections.append(
                LoadedSection(
                    text=text,
                    page_number=None,
                    section_title=title,
                    heading_path=heading_path,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
            buffer.clear()

        i = 0
        while i < len(tokens):
            token = tokens[i]
            level = _heading_level(token)

            if level is not None:
                # Flush whatever was buffered before this heading
                flush_section()

                # Grab the inline content of the heading
                heading_text = ""
                if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                    heading_text = tokens[i + 1].content.strip()
                    i += 2  # skip inline + heading_close
                else:
                    i += 1

                # Update the heading stack: clear any deeper levels
                for lvl in list(heading_stack.keys()):
                    if lvl >= level:
                        del heading_stack[lvl]
                heading_stack[level] = heading_text
                current_title = heading_text
            else:
                # Collect rendered text from non-heading tokens
                if token.type == "inline" and token.content:
                    buffer.append(token.content)
                elif token.type in ("fence", "code_block") and token.content:
                    buffer.append(token.content)
                i += 1

        # Flush the last section
        flush_section()

        # If the document had no headings at all, emit one big section
        if not sections:
            text = "\n".join(
                t.content for t in tokens if t.type == "inline" and t.content
            ).strip()
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

        logger.info(f"MarkdownLoader: {filename} → {len(sections)} sections")
        return sections
