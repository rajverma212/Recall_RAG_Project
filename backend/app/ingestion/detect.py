"""Document type detection from filename and MIME content-type."""
from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)

# Map of MIME type prefixes/exact values to doc_type strings
_MIME_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "text/html": "html",
    "text/markdown": "markdown",
    "text/x-markdown": "markdown",
    "text/plain": "txt",
}

# Map of file extensions (lowercase, with dot) to doc_type strings
_EXT_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "txt",
    ".text": "txt",
}


def detect_doc_type(filename: str, content_type: str) -> str:
    """Detect doc_type from filename extension and/or MIME content-type.

    Extension takes precedence for unambiguous formats (pdf, md, html, htm).
    MIME type is used when the extension is absent or maps to a generic type
    (e.g. text/plain can mean either txt or markdown).

    Returns one of: pdf | markdown | html | txt
    Raises ValueError for unsupported types.
    """
    # Normalise MIME type (strip parameters like "; charset=utf-8")
    mime = content_type.split(";")[0].strip().lower()

    # Try file extension first — extension is more specific than generic MIMEs
    lower_name = filename.lower()
    for ext, doc_type in _EXT_MAP.items():
        if lower_name.endswith(ext):
            logger.debug(f"detect_doc_type: {filename!r} → {doc_type!r} via extension {ext!r}")
            return doc_type

    # Fall back to MIME type
    if mime in _MIME_MAP:
        doc_type = _MIME_MAP[mime]
        logger.debug(f"detect_doc_type: {filename!r} → {doc_type!r} via MIME {mime!r}")
        return doc_type

    raise ValueError(
        f"Unsupported document type for filename={filename!r}, content_type={content_type!r}. "
        f"Supported: pdf, html, markdown, txt."
    )
