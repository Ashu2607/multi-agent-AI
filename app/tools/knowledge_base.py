"""Knowledge Base Tool: RAG retrieval over the local corpus (product manual,
support/compliance policies, FAQ, market research report) built by
scripts/build_knowledge_base.py into a Chroma store.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.tools import tool

from app.config import CHROMA_DIR, get_settings
from app.instrumentation import get_tracer
from app.logging_utils import log_event
from app.schemas import KnowledgeBaseSnippet


def chroma_transport_kwargs(settings=None) -> dict:
    """M6 Step 1: which Chroma transport to use. Embedded (default, unchanged
    M3/M5 behavior) reads/writes CHROMA_DIR directly - used for local/CLI
    runs and tests. When CHROMA_SERVER_HOST is set (Docker Compose sets it
    to the `vectorstore` service name), talk to that container's Chroma
    server over HTTP instead - same env-toggled "auto vs local" shape
    already used for Redis/Zep in app/memory."""
    settings = settings or get_settings()
    if settings.chroma_server_host:
        import chromadb

        client = chromadb.HttpClient(host=settings.chroma_server_host, port=settings.chroma_server_port)
        return {"client": client}
    return {"persist_directory": str(CHROMA_DIR)}


@lru_cache
def _get_vectorstore():
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings

    settings = get_settings()
    embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key or "not-set")
    return Chroma(
        collection_name="knowledge_base",
        embedding_function=embeddings,
        **chroma_transport_kwargs(settings),
    )


def search_knowledge_base(query: str, k: int = 4, session_id: str = "-") -> list[KnowledgeBaseSnippet]:
    with get_tracer().span("tool.knowledge_base_search", agent="researcher") as span:
        settings = get_settings()
        # The "is it indexed yet" pre-check only applies to the embedded,
        # local-folder transport - a remote Chroma server has no local
        # CHROMA_DIR to inspect, so just query it and let an empty result
        # set speak for itself.
        if not settings.chroma_server_host and (not CHROMA_DIR.exists() or not any(CHROMA_DIR.iterdir())):
            span.set_metadata(session_id=session_id, query=query, n_results=0, indexed=False)
            return []
        store = _get_vectorstore()
        docs_with_scores = store.similarity_search_with_relevance_scores(query, k=k)
        snippets = [
            KnowledgeBaseSnippet(
                source=doc.metadata.get("source", "unknown"),
                content=doc.page_content,
                score=score,
            )
            for doc, score in docs_with_scores
        ]
        # Embedding call cost: query text in, no completion tokens.
        span.record_llm_usage("text-embedding-3-small", prompt_text=query, completion_text="")
        span.set_metadata(session_id=session_id, query=query, n_results=len(snippets))

    log_event(
        session_id=session_id,
        agent="researcher",
        action="knowledge_base_search",
        input_summary=query,
        output_summary=f"{len(snippets)} snippets",
    )
    return snippets


@tool("knowledge_base_search")
def knowledge_base_search_tool(query: str) -> str:
    """Search internal documents (product manual, compliance policies, FAQ, market
    research report) for company-approved facts and policy context."""
    snippets = search_knowledge_base(query)
    if not snippets:
        return "No knowledge base results. Has scripts/build_knowledge_base.py been run?"
    return "\n\n".join(f"[{s.source}] {s.content[:400]}" for s in snippets)
