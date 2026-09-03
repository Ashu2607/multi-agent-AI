"""Web Research Tool: live internet search for market trends and competitor
information that isn't in the local structured/knowledge-base data.

Uses Tavily when TAVILY_API_KEY is set (better quality, purpose-built for
LLM agents). Falls back to keyless DuckDuckGo search (via `ddgs`) otherwise,
mirroring the same auto-fallback pattern used for Redis/Zep memory - so the
Researcher agent works out of the box before you sign up for a Tavily key.
"""
from __future__ import annotations

from langchain_core.tools import tool

from app.config import get_settings
from app.instrumentation import get_tracer
from app.logging_utils import get_logger, log_event
from app.schemas import WebSearchResult

logger = get_logger()


def _search_tavily(query: str, max_results: int, api_key: str) -> list[WebSearchResult]:
    from langchain_tavily import TavilySearch

    searcher = TavilySearch(max_results=max_results, tavily_api_key=api_key)
    raw = searcher.invoke({"query": query})
    items = raw.get("results", []) if isinstance(raw, dict) else raw or []
    return [
        WebSearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            content=item.get("content", ""),
            score=item.get("score"),
        )
        for item in items
    ]


def _search_duckduckgo(query: str, max_results: int) -> list[WebSearchResult]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        raw_results = list(ddgs.text(query, max_results=max_results))
    return [
        WebSearchResult(
            title=item.get("title", ""),
            url=item.get("href", ""),
            content=item.get("body", ""),
        )
        for item in raw_results
    ]


def run_web_search(query: str, max_results: int = 5, session_id: str = "-") -> list[WebSearchResult]:
    settings = get_settings()
    backend = "tavily" if settings.tavily_api_key else "duckduckgo"

    with get_tracer().span("tool.web_search", agent="researcher") as span:
        try:
            if backend == "tavily":
                results = _search_tavily(query, max_results, settings.tavily_api_key)
            else:
                results = _search_duckduckgo(query, max_results)
        except Exception as exc:  # noqa: BLE001
            if backend == "tavily":
                logger.warning(f"Tavily search failed ({exc}); falling back to DuckDuckGo")
                results = _search_duckduckgo(query, max_results)
                backend = "duckduckgo"
            else:
                raise
        span.set_metadata(session_id=session_id, query=query, backend=backend, n_results=len(results))

    log_event(
        session_id=session_id,
        agent="researcher",
        action="web_search",
        input_summary=query,
        output_summary=f"{len(results)} results via {backend}",
        backend=backend,
    )
    return results


@tool("web_search")
def web_search_tool(query: str) -> str:
    """Search the live web for competitor news, market trends, funding, or product
    launches that may not be present in the internal knowledge base or database."""
    results = run_web_search(query)
    if not results:
        return "No web results found."
    return "\n\n".join(f"{r.title}\n{r.url}\n{r.content[:400]}" for r in results)
