"""Prompt templates. The active system prompt is resolved from the DB
(PromptVersion) at request time, enabling prompt versioning / A-B testing.
"""
from __future__ import annotations

DEFAULT_SYSTEM_PROMPT = """You are a precise documentation assistant. Answer the \
user's question using ONLY the numbered context passages provided. Follow these \
rules without exception:

1. Use only information present in the context. Never use outside knowledge.
2. Support every factual sentence with a citation marker like [1], [2] that \
refers to the passage(s) it came from. Cite multiple passages when relevant.
3. If the context does not contain the answer, reply exactly: \
"I don't have enough information in the provided documents to answer that." \
Do not guess.
4. State uncertainty explicitly when the context is partial or conflicting.
5. Be concise and factual. Do not invent passage numbers.
"""

USER_TEMPLATE = """Context passages:
{context}

Question: {question}

Answer (with [n] citations):"""


def format_context(chunks: list[dict]) -> str:
    """Render reranked chunks into a numbered context block.

    ``chunks`` items must have keys: ``text``, ``source_file``, ``page_number``.
    """
    lines = []
    for i, c in enumerate(chunks, start=1):
        loc = c.get("source_file", "unknown")
        if c.get("page_number") is not None:
            loc += f" p.{c['page_number']}"
        lines.append(f"[{i}] ({loc})\n{c['text']}")
    return "\n\n".join(lines)
