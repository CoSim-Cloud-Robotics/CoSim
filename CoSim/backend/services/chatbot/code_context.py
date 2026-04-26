"""Context-aware code suggestion helpers.

These utilities format a structured "code context" prompt fragment that the
chatbot service can prepend to the user's message. The context includes:

- The active file path and language
- An optional selection range (so the model knows what the user highlighted)
- A trimmed code snippet
- Recent diagnostics (linter/compiler messages) when available

We also expose ``extract_code_suggestion`` which pulls a single fenced code
block out of a chatbot response so the editor can offer an "Apply
suggestion" action.
"""
from __future__ import annotations

import re
from typing import Optional

MAX_SNIPPET_CHARS = 2_000
_FENCED_CODE_RE = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)


def _truncate(snippet: str, max_chars: int = MAX_SNIPPET_CHARS) -> str:
    if len(snippet) <= max_chars:
        return snippet
    head = snippet[: max_chars // 2]
    tail = snippet[-max_chars // 2 :]
    return f"{head}\n... ({len(snippet) - max_chars} chars truncated) ...\n{tail}"


def format_code_context(
    *,
    file_path: str,
    language: str,
    snippet: str,
    selection: Optional[dict] = None,
    recent_diagnostics: Optional[list[str]] = None,
) -> str:
    """Render a code context block suitable for prepending to the user prompt."""

    parts: list[str] = []
    parts.append(f"Active file: `{file_path}` (language: {language})")
    if selection:
        start = selection.get("start_line")
        end = selection.get("end_line")
        if start is not None and end is not None:
            parts.append(f"User selection: lines {start}-{end}")
    if recent_diagnostics:
        diags = "\n".join(f"- {item}" for item in recent_diagnostics)
        parts.append(f"Recent diagnostics:\n{diags}")
    parts.append(f"Code snippet:\n```{language}\n{_truncate(snippet)}\n```")
    parts.append(
        "When suggesting code, reply with a single fenced code block that the "
        "editor can apply directly. Be concise."
    )
    return "\n\n".join(parts)


def extract_code_suggestion(response: str) -> Optional[dict[str, str]]:
    """Return the first fenced code block found in ``response``.

    Returns ``None`` when no fenced block is present. The returned dict has
    ``language`` (possibly empty) and ``code`` keys.
    """

    match = _FENCED_CODE_RE.search(response)
    if not match:
        return None
    language = (match.group(1) or "").strip()
    code = match.group(2)
    return {"language": language, "code": code}


__all__ = ["MAX_SNIPPET_CHARS", "extract_code_suggestion", "format_code_context"]
