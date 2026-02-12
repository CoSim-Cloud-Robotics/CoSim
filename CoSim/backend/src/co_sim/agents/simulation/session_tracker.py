from __future__ import annotations

from collections import OrderedDict
from typing import Dict

_active_sessions: Dict[str, str] = OrderedDict()


def handle_session_event(event: dict) -> None:
    session = event.get("session") or {}
    session_id = str(session.get("id"))
    status = session.get("status")
    if not session_id or status is None:
        return
    if status == "terminated":
        _active_sessions.pop(session_id, None)
    else:
        _active_sessions[session_id] = status


def get_active_sessions() -> list[dict[str, str]]:
    return [{"id": session_id, "status": status} for session_id, status in list(_active_sessions.items())]
