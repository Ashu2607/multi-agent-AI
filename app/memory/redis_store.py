"""Real Redis-backed episodic memory.

Requires a running Redis server (REDIS_URL in .env). Each session's turns are
stored as a capped Redis list at key `session:{session_id}:history`, entries
are JSON-encoded {"role", "content", "timestamp"}.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import redis

from app.memory.base import EpisodicMemory


class RedisMemoryStore(EpisodicMemory):
    def __init__(self, redis_url: str, max_turns: int = 200):
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._max_turns = max_turns

    def ping(self) -> bool:
        return bool(self._client.ping())

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}:history"

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        entry = json.dumps(
            {"role": role, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()}
        )
        key = self._key(session_id)
        self._client.rpush(key, entry)
        self._client.ltrim(key, -self._max_turns, -1)

    def get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        raw = self._client.lrange(self._key(session_id), -limit, -1)
        return [json.loads(item) for item in raw]
