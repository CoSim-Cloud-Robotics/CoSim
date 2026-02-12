"""Compatibility helpers for typing features across Python versions."""
try:  # pragma: no cover
    from typing import Annotated  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    from typing_extensions import Annotated  # type: ignore

__all__ = ["Annotated"]
