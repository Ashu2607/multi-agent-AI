"""Wires up episodic (Redis) + semantic (Zep) memory behind one facade.

`memory_backend=auto` (default): tries the real backend, falls back to the
in-memory fake with a logged warning if it can't connect - so the CLI/API/
tests keep working before Redis/Zep are actually running. Set
`memory_backend=local` to always use the fakes.
"""
from __future__ import annotations

from app.config import Settings, get_settings
from app.logging_utils import get_logger
from app.memory.base import EpisodicMemory, SemanticMemory
from app.memory.fakes import InMemoryEpisodicStore, InMemorySemanticStore

logger = get_logger()


def _build_episodic(settings: Settings) -> EpisodicMemory:
    if settings.memory_backend == "local":
        return InMemoryEpisodicStore()
    try:
        from app.memory.redis_store import RedisMemoryStore

        store = RedisMemoryStore(settings.redis_url)
        store.ping()
        return store
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Redis unavailable ({exc}); falling back to in-memory episodic store")
        return InMemoryEpisodicStore()


def _build_semantic(settings: Settings) -> SemanticMemory:
    if settings.memory_backend == "local" or not settings.zep_api_key:
        if settings.memory_backend != "local":
            logger.warning("ZEP_API_KEY not set; falling back to in-memory semantic store")
        return InMemorySemanticStore()
    try:
        from app.memory.zep_store import ZepMemoryStore

        return ZepMemoryStore(settings.zep_api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Zep unavailable ({exc}); falling back to in-memory semantic store")
        return InMemorySemanticStore()


class MemoryManager:
    def __init__(self, episodic: EpisodicMemory, semantic: SemanticMemory):
        self.episodic = episodic
        self.semantic = semantic

    def record_turn(self, session_id: str, role: str, content: str) -> None:
        self.episodic.append_turn(session_id, role, content)
        if role == "assistant":
            self.semantic.add_memory(session_id, content, metadata={"role": role})

    def recall_history(self, session_id: str, limit: int = 20) -> list[dict]:
        return self.episodic.get_history(session_id, limit=limit)

    def recall_semantic(self, query: str, limit: int = 5) -> list[dict]:
        return self.semantic.search(query, limit=limit)


_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        settings = get_settings()
        _manager = MemoryManager(_build_episodic(settings), _build_semantic(settings))
    return _manager
