### FastAPI backend image (M6 Step 1 + Step 2).
#
# Used two ways from the same file:
#   1. `docker compose up -d`      -> runs as the "backend" service on the
#      VM's Compose network, talking to `vectorstore`/`redis` by service name.
#   2. `gcloud run deploy --source .` -> Cloud Build builds this exact
#      Dockerfile and Cloud Run runs it, injecting $PORT (default 8080).
#
# Only the API is deployed to Cloud Run (see README "Cloud Run deploy") -
# the UI and vector store stay on the VM's Compose stack.

FROM python:3.13-slim

# build-essential: chromadb's hnswlib dependency needs a C++ compiler to
# build from source on slim images; removed from the final layer isn't
# worth the complexity of a multi-stage build for a capstone-sized image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Baked-in fallback knowledge base + sales.db so the container answers
# something useful even before a fresh `build_knowledge_base.py` re-run;
# chroma_store/approvals.db are re-created at runtime under /app if absent.
RUN mkdir -p /app/logs /app/reports /app/chroma_store

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Cloud Run sets $PORT (default 8080); Compose leaves it unset so this
# falls back to 8000, matching the rest of this repo's docs/examples.
CMD ["sh", "-c", "uvicorn app.api:api --host 0.0.0.0 --port ${PORT:-8000}"]
