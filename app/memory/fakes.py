"""In-memory stand-ins used by the test suite so it runs without a live
Redis server or Zep Cloud account. Same interface as the real backends
(app/memory/base.py) so agent code never branches on which is active.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.memory.base import EpisodicMemory, SemanticMemory


class InMemoryEpisodicStore(EpisodicMemory):
    def __init__(self, max_turns: int = 200):
        self._sessions: dict[str, list[dict]] = {}
        self._max_turns = max_turns

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        history = self._sessions.setdefault(session_id, [])
        history.append(
            {"role": role, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()}
        )
        del history[: -self._max_turns]

    def get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        return self._sessions.get(session_id, [])[-limit:]


class InMemorySemanticStore(SemanticMemory):
    def __init__(self):
        self._items: list[dict] = []

    def add_memory(self, session_id: str, text: str, metadata: dict | None = None) -> None:
        self._items.append({"session_id": session_id, "content": text, "metadata": metadata or {}})

    def search(self, query: str, limit: int = 5) -> list[dict]:
        query_terms = set(query.lower().split())
        scored = []
        for item in self._items:
            text_terms = set(item["content"].lower().split())
            overlap = len(query_terms & text_terms)
            if overlap:
                scored.append((overlap, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {"content": item["content"], "score": float(score), "session_id": item["session_id"]}
            for score, item in scored[:limit]
        ]
