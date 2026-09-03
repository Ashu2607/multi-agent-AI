"""Build a local Chroma vector store from the knowledge-base documents
(product manual, support policies, FAQ, market research report).

Run once after installing dependencies and setting OPENAI_API_KEY:
    python scripts/build_knowledge_base.py

The Researcher agent's `knowledge_base_search` tool queries the resulting
store at app/tools/knowledge_base.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from langchain_chroma import Chroma
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CHROMA_DIR, KNOWLEDGE_BASE_DIR, get_settings
from app.tools.knowledge_base import chroma_transport_kwargs


def load_documents():
    docs = []
    for path in sorted(KNOWLEDGE_BASE_DIR.iterdir()):
        if path.suffix.lower() == ".pdf":
            loader = PyPDFLoader(str(path))
        elif path.suffix.lower() == ".docx":
            loader = Docx2txtLoader(str(path))
        else:
            continue
        loaded = loader.load()
        for doc in loaded:
            doc.metadata["source"] = path.name
        docs.extend(loaded)
        print(f"Loaded {len(loaded)} page(s)/chunk(s) from {path.name}")
    return docs


def main() -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set. Add it to .env before building the knowledge base "
            "(embeddings require it)."
        )

    docs = load_documents()
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)
    # De-duplicate: the sample source docs repeat the same paragraph many
    # times, which would otherwise flood retrieval with identical hits.
    seen = set()
    deduped = []
    for chunk in chunks:
        key = chunk.page_content.strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    print(f"{len(chunks)} chunks -> {len(deduped)} after de-duplication")

    embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)
    transport = chroma_transport_kwargs(settings)
    if "persist_directory" in transport:
        CHROMA_DIR.mkdir(exist_ok=True)
    Chroma.from_documents(
        documents=deduped,
        embedding=embeddings,
        collection_name="knowledge_base",
        **transport,
    )
    destination = f"Chroma server at {settings.chroma_server_host}:{settings.chroma_server_port}" if "client" in transport else CHROMA_DIR
    print(f"Knowledge base persisted to {destination}")


if __name__ == "__main__":
    main()
