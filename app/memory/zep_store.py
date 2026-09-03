"""Real Zep Cloud-backed semantic memory.

Requires ZEP_API_KEY in .env (https://www.getzep.com). All sessions write
into one shared knowledge graph (`graph_id`), so `search()` recalls
facts/summaries across every session - that's what makes this "semantic"
memory as opposed to the per-session episodic history in Redis
(app/memory/redis_store.py).

Note: Zep extracts graph facts from added text asynchronously, so a fact
may not be immediately searchable right after `add_memory`.
"""
from __future__ import annotations

from zep_cloud.client import Zep

from app.memory.base import SemanticMemory

DEFAULT_GRAPH_ID = "enterprise-research-assistant"


class ZepMemoryStore(SemanticMemory):
    def __init__(self, api_key: str, graph_id: str = DEFAULT_GRAPH_ID):
        self._client = Zep(api_key=api_key)
        self._graph_id = graph_id
        self._graph_ready = False

    def _ensure_graph(self) -> None:
        if self._graph_ready:
            return
        try:
            self._client.graph.create(graph_id=self._graph_id)
        except Exception:
            pass  # already exists
        self._graph_ready = True

    def add_memory(self, session_id: str, text: str, metadata: dict | None = None) -> None:
        self._ensure_graph()
        self._client.graph.add(
            graph_id=self._graph_id,
            data=text,
            type="text",
            source_description=f"session:{session_id}",
        )

    def search(self, query: str, limit: int = 5) -> list[dict]:
        self._ensure_graph()
        results = self._client.graph.search(
            graph_id=self._graph_id, query=query, limit=limit, scope="edges"
        )
        return [
            {"content": edge.fact, "score": edge.score, "session_id": None}
            for edge in (results.edges or [])
        ]
