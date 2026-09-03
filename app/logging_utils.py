"""Structured JSON logging for every agent action (Policy 4)."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from app.schemas import AgentLogEvent

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event"):
            payload["event"] = record.event
        return json.dumps(payload, default=str)


def get_logger(name: str = "agent_actions") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JsonFormatter())
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(LOG_DIR / "agent_actions.log.jsonl", encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


_logger = get_logger()


def log_event(
    session_id: str,
    agent: str,
    action: str,
    input_summary: str = "",
    output_summary: str = "",
    **metadata,
) -> AgentLogEvent:
    event = AgentLogEvent(
        session_id=session_id,
        agent=agent,
        action=action,
        input_summary=input_summary[:500],
        output_summary=output_summary[:500],
        metadata=metadata,
    )
    _logger.info(action, extra={"event": event.model_dump(mode="json")})
    return event
