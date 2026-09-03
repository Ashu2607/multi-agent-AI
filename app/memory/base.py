"""Memory interfaces.

Episodic memory: append-only turn history for a session (who said what, when).
Semantic memory: durable facts/summaries recalled across sessions by meaning.

Two concrete backends are provided: Redis (episodic, app/memory/redis_store.py)
and Zep Cloud (semantic, app/memory/zep_store.py). Tests substitute the
in-memory fakes in app/memory/fakes.py so the suite runs without live infra.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import ApprovalStatus  # noqa: F401  (re-export convenience)


class EpisodicMemory(ABC):
    """Short-term, session-scoped conversation history."""

    @abstractmethod
    def append_turn(self, session_id: str, role: str, content: str) -> None: ...

    @abstractmethod
    def get_history(self, session_id: str, limit: int = 20) -> list[dict]: ...


class SemanticMemory(ABC):
    """Long-term memory: durable facts/summaries searchable across sessions."""

    @abstractmethod
    def add_memory(self, session_id: str, text: str, metadata: dict | None = None) -> None: ...

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[dict]: ...
