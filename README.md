# Enterprise AI Multi-Agent Research Assistant

Milestone 3: a LangGraph multi-agent system for competitive market intelligence.
A **Supervisor Agent** plans and routes work to a **Researcher Agent** (web
search + Text-to-SQL + internal knowledge base) and a **Writer Agent**
(compiles an executive report), then files the report through a **Human
Approval** gate before it can be distributed.

## Architecture

```
START -> Supervisor -> Researcher -> Supervisor -> Writer -> Supervisor -> Human Approval -> END
              ^_____________|                          |
              (loops until enough findings, capped by MAX_RESEARCH_ITERATIONS)
```

- **Supervisor** (`app/agents/supervisor.py`) — LLM structured-output routing
  (`RouteDecision`) with deterministic guardrails so the graph always
  terminates correctly (forces `writer` at the iteration cap, `human_approval`
  once a draft exists, `end` once filed for review).
- **Researcher** (`app/agents/researcher.py`) — plans a web query, a
  Text-to-SQL question, and a knowledge-base query per iteration, and records
  each as a typed `ResearchFinding`.
- **Writer** (`app/agents/writer.py`) — compiles findings into a
  Pydantic-validated `ReportDraft`, screens it for sensitive data, saves it to
  `reports/`.
- **Human Approval** (`app/agents/human_approval.py`) — files the report in
  `approvals.db` (SQLite) for compliance/manager sign-off. Approve/reject is
  done out-of-band via the CLI, API, or Streamlit dashboard.

### Tools (`app/tools/`)
| Tool | Purpose |
|---|---|
| `web_search.py` | Live web search via Tavily |
| `text_to_sql.py` + `sql_validation.py` | NL -> SQL -> validate (SELECT-only, table whitelist, no stacked statements, forced LIMIT) -> execute against `data/sales.db`, with one LLM repair attempt on validation failure |
| `knowledge_base.py` | RAG over the product manual / compliance policies / FAQ / market research report (Chroma + OpenAI embeddings) |
| `report_writer.py` | Markdown rendering + regex-based sensitive-data screen (emails, SSN-like, card-like numbers) |
| `approval_store.py` | SQLite-backed HITL approval queue |

### Memory (`app/memory/`)
- **Episodic** (session turn history): real Redis (`redis_store.py`).
- **Semantic** (cross-session recall): real Zep Cloud (`zep_store.py`).
- Both sit behind `MemoryStore`/`EpisodicMemory`/`SemanticMemory` interfaces
  (`base.py`). `memory_backend=auto` (default) uses the real backend when
  reachable and transparently falls back to an in-memory store
  (`fakes.py`) otherwise — so the app and tests run before Redis/Zep are set
  up, and automatically pick up the real ones once they're live.

### Structured data
`scripts/ingest_structured_data.py` loads `market_news.csv` and
`pricing_comparison.csv` into `data/sales.db` alongside the existing
`competitors`, `products`, `quarterly_sales` tables, so Text-to-SQL can query
all five.

### Compliance (from `data/knowledge_base/Customer_Support_Policies.pdf`)
1. Reports reviewed before external distribution -> Human Approval gate.
2. No sensitive customer/financial data exposed -> `report_writer.contains_sensitive_data`.
3. SQL must be validated -> `sql_validation.validate_sql`.
4. Every agent action logged as structured JSON -> `app/logging_utils.py` (`logs/agent_actions.log.jsonl`).
5. LangSmith traces enabled for debugging -> `app/config.py` mirrors `LANGCHAIN_*` settings into env vars at startup.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in OPENAI_API_KEY, TAVILY_API_KEY, etc.

python scripts/ingest_structured_data.py   # adds market_news/pricing_comparison tables
python scripts/build_knowledge_base.py     # builds the Chroma knowledge-base index (needs OPENAI_API_KEY)
```

### Real Redis / Zep

Redis (episodic memory):
```bash
docker run -p 6379:6379 --name research-redis -d redis:7
```
Zep (semantic memory): sign up at https://www.getzep.com, put the key in
`ZEP_API_KEY`.

Until both are reachable, the app automatically runs on the in-memory
fallback (`MEMORY_BACKEND=auto`, the default) — nothing else needs to change.

## Run it

**CLI**
```bash
python -m app.cli research "Compare DataSphere 1 and QuantumSoft 2 pricing and Q1 2025 growth"
python -m app.cli approvals list
python -m app.cli approvals show <approval_id>
python -m app.cli approvals approve <approval_id> --reviewer "Jane Doe"
```

**FastAPI** (streams progress over SSE)
```bash
uvicorn app.api:api --reload
# POST /research/stream {"task": "..."}
# GET  /approvals ,  POST /approvals/{id}/decision {"approved": true, "reviewer": "Jane"}
```

**Streamlit dashboard** (deploy target)
```bash
streamlit run app/dashboard.py
```

## Tests

```bash
pytest
```

40+ tests across `tests/`, including a named 20-scenario suite
(`tests/test_scenarios.py`) covering SQL validation, Supervisor routing
accuracy, memory recall, and report/compliance generation, plus a full
offline end-to-end graph run (`tests/test_graph_end_to_end.py`) proving
Supervisor -> Researcher -> Writer -> Human Approval collaboration. All LLM
and external-tool calls are mocked so the suite needs no API keys or live
Redis/Zep/network access.

---

## Milestone 5 — Production Integration

M5 is integration/hardening on top of the M3 core above, **not** new agent
logic - see `ARCHITECTURE_M5.md` for the full picture. Everything below
either exposes, instruments, secures, or evaluates the Supervisor/Researcher/
Writer/Human-Approval graph that already existed.

### What's new

- **FastAPI backend** (`app/api.py`) - thin REST wrapper around
  `app.runner.run_research(_stream)`: `POST /research` (sync), `POST
  /research/stream` (SSE), `GET/POST /approvals...`, `POST /auth/login`,
  `GET /health`. Every route requires an `X-API-Key` header.
- **Streamlit UI** (`app/dashboard.py`) - calls the FastAPI backend over
  HTTP (`httpx`), not a direct pipeline import - a true client/server split.
  Same Run-Research / Approval-Queue tabs as before, now with 👍/👎 feedback
  capture logged to `logs/feedback.jsonl`.
- **LLMOps instrumentation** (`app/instrumentation.py`) - a `Span` context
  manager wrapped around every agent node and tool call
  (`app/agents/*.py`, `app/tools/{knowledge_base,text_to_sql,web_search}.py`),
  logging name/duration/tokens/cost/trace_id as one JSON line per span to
  `logs/spans.jsonl`. One `pipeline.run` span per request ties every
  sub-span together via a shared `trace_id`.
- **Monitoring dashboard** (`app/monitoring_dashboard.py`) - reads
  `logs/spans.jsonl` and charts p50/p95 latency, cost over time, error
  rate, request volume, and a cost/latency breakdown per span name.
- **Evaluation suite** (`app/eval_metrics.py` + `scripts/run_eval.py`) -
  runs the shared `data/eval/golden_set_student.json` (12 questions, 3
  adversarial, identical for every student) through the unmodified
  pipeline and scores it with retrieval hit/MRR, LLM-judge faithfulness/
  relevancy, and keyword-based refusal detection. Saves a baseline JSON
  and can regression-gate a later run against it.
- **API security** (`app/auth.py`) - required `X-API-Key` on every FastAPI
  route (`Depends`, app-wide); optional JWT stretch (`POST /auth/login` +
  `Depends(require_jwt)`) additionally guards
  `POST /approvals/{id}/decision`. No secrets in code - everything comes
  from `.env` (`.env.example` has the full list, no real values).

### Run the full stack

Each process needs its own terminal and a fixed port:

```bash
# Terminal 1 - backend
uvicorn app.api:api --reload --port 8000

# Terminal 2 - user-facing UI (talks to the backend above)
streamlit run app/dashboard.py --server.port 8501

# Terminal 3 - ops monitoring dashboard (reads logs/spans.jsonl)
streamlit run app/monitoring_dashboard.py --server.port 8502
```

Open http://localhost:8000/docs to exercise the API directly (Swagger's
"Authorize" button takes the `X-API-Key`), http://localhost:8501 for the
research UI, http://localhost:8502 for the ops dashboard.

### Run the evaluation suite

```bash
python scripts/run_eval.py --save-baseline
# later, to check for regressions against that baseline:
python scripts/run_eval.py --compare-to reports/eval_baseline.json
```

Runs all 12 shared golden-set questions through the real pipeline (real
OpenAI/Tavily calls) and writes `reports/eval_latest.json` (this run) and
`reports/eval_baseline.json` (`--save-baseline`).

**Saved baseline summary** (`reports/eval_baseline.json`, faithfulness/
relevancy threshold 0.6):

| Metric | Value |
|---|---|
| Overall pass rate | 58.3% (7/12) |
| Non-adversarial pass rate | 55.6% (5/9) |
| Adversarial refusal rate | 66.7% (2/3 - q10, q12 correctly refused) |
| Avg faithfulness / relevancy | 0.50 / 0.58 |
| Retrieval hit rate / MRR | 100% / 0.148 |

**Known findings, reported as-is rather than patched** (M5 = integration/
hardening, not new agent logic) - full root-cause analysis and recommended
(out-of-scope) follow-ups in `reports/EVAL_FINDINGS.md`:

1. q11 ("What is OpenAI's current market share in this dataset?") FAILs -
   the Researcher's `web_search` tool has no boundary keeping it inside the
   synthetic dataset, so it answers with a real-world web figure instead of
   refusing, exactly the trap that question is designed to catch.
2. Several non-adversarial questions (q01, q04, q08, q09) fail faithfulness/
   relevancy because the Writer always compiles a fixed-section competitor
   report even for narrow factual questions - one answer literally contains
   an unfilled `"$X million"` template placeholder instead of the real
   figure.

### New environment variables (M5)

| Variable | Required | Purpose |
|---|---|---|
| `API_KEY` | Yes | Value every FastAPI request must send as `X-API-Key`. |
| `JWT_SECRET` | Only for the JWT stretch | Signs/verifies tokens from `POST /auth/login`. |
| `JWT_ALGORITHM` | No (default `HS256`) | JWT signing algorithm. |
| `JWT_EXPIRES_MINUTES` | No (default `60`) | Token lifetime. |
| `DEMO_USERNAME` / `DEMO_PASSWORD` | Only for the JWT stretch | Hardcoded demo user `/auth/login` accepts. |
| `API_BASE_URL` | No (default `http://localhost:8000`) | Where `app/dashboard.py` sends its API requests. |

Generate a key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

### Evidence included in this submission

- `reports/eval_baseline.json` - saved baseline eval report.
- `logs/spans.jsonl` - real span log from actual pipeline/API/eval runs.
- `logs/agent_actions.log.jsonl` - existing M3 structured action log, still active.
- `screenshots/` - monitoring dashboard populated with real data after a
  20+ query warm-up (eval run + manual UI/API queries).

---

## Milestone 6 — Enterprise Production Release

M6 is a deployment/hardening/governance ring around the unchanged M3 core
and M5 API/UI/observability layer - **no new agents, tools, or business
logic**. Full picture (diagram + rationale): `ARCHITECTURE_M6.md`. Exact
copy-paste deploy commands: `DEPLOY.md`. Honest done/not-done checklist:
`PRODUCTION_READINESS_CHECKLIST.md`.

### What's new in M6

- **Docker Compose** (`docker-compose.yml`, `Dockerfile`, `Dockerfile.ui`) -
  the whole stack (backend, UI, vector store, Redis) as 4 named services on
  one Docker network, brought up with `docker compose up -d --build`.
  Services reach each other by service name (`http://backend:8000`,
  `http://vectorstore:8000`, `redis://redis:6379`), never localhost or a
  hardcoded IP.
- **Chroma as its own Compose service** (`app/tools/knowledge_base.py`,
  `scripts/build_knowledge_base.py`) - M3/M5 used an embedded, local-folder
  Chroma store; M6 adds an optional HTTP-client transport
  (`CHROMA_SERVER_HOST`) so the same code can talk to the official
  `chromadb/chroma` container instead, the same env-toggled "auto vs
  local" shape already used for Redis/Zep. Local/CLI/test use is
  unaffected - the toggle defaults off.
- **Cloud Run deployment** - the FastAPI backend deploys standalone via
  `gcloud run deploy --source .` using the same `Dockerfile` Compose uses.
  Exact command, curl-based verification (from the VM, not a laptop
  browser), and teardown/redeploy steps: `DEPLOY.md`.
- **JWT upgraded from optional stretch to a required second layer**
  (`app/auth.py`, `app/api.py`) - every `/research*` and `/approvals*`
  route now requires both `X-API-Key` (Layer 1, unchanged from M5) *and*
  a valid `Authorization: Bearer` token from `POST /auth/login` (Layer 2).
  Only `/`, `/health`, and `/auth/login` itself skip the JWT check.
  Regression-tested in `tests/test_api_security.py`, including a direct
  test for "API key alone must NOT be enough."
- **Prompt-injection/jailbreak/PII/toxicity guardrail**
  (`app/guardrails/`) - ported from Milestone-4's `src/guardrails/`
  package (not rebuilt), then hardened with additional M6 regex patterns
  for both `prompt_injection` and `jailbreak` (see the "M6 hardening
  additions" comments in those files). Wired into `POST /research` and
  `POST /research/stream` via `app.guardrails.check_prompt`: unsafe
  prompts get a `400` before the pipeline ever runs; PII-bearing prompts
  are redacted and run; every decision is logged to
  `logs/guardrail_decisions.jsonl`. Regression-tested against a 20-row
  dataset (`data/guardrails/guardrail_dataset.json`, the M4 16-row set
  plus 4 new M6 rows) in `tests/test_guardrails.py`, plus a live-endpoint
  test in `tests/test_api_security.py` proving the block actually happens
  before any LLM call.

### Run the full stack (Docker Compose)

```bash
cp .env.example .env   # fill in real values - see DEPLOY.md §3 for what each one does
docker compose up -d --build
docker compose exec backend python scripts/build_knowledge_base.py
docker compose exec backend python scripts/ingest_structured_data.py
```

Backend: http://localhost:8000/docs · UI: http://localhost:8501 · full
verification commands (curl, from inside the VM): `DEPLOY.md` §1.

### Deploy the backend to Cloud Run

```bash
ENV_VARS=$(grep -v '^#' .env | grep '=' | paste -sd ',' -)
gcloud run deploy research-backend \
  --source . --region us-central1 --allow-unauthenticated \
  --memory 1Gi --cpu 1 --min-instances 0 --max-instances 2 --timeout 300 \
  --set-env-vars "$ENV_VARS"
```

Full command with rationale, curl verification, and the "resources are
wiped daily at 9am/9pm - redeploy fresh" note: `DEPLOY.md` §2.

### New environment variables (M6)

| Variable | Required | Purpose |
|---|---|---|
| `JWT_SECRET` / `DEMO_USERNAME` / `DEMO_PASSWORD` | **Yes, now required** (was optional-stretch in M5) | Every business route 401s without a valid token minted from these. |
| `BLOCK_ON_INJECTION` | No (default `true`) | Toggles the guardrail's block behavior; `false` reproduces an undefended baseline for red-team comparison only. |
| `CHROMA_SERVER_HOST` / `CHROMA_SERVER_PORT` | No (Compose sets these itself) | Points the backend at the `vectorstore` Compose service instead of the local `chroma_store/` folder. |

Full table (M5 + M6 vars together): `.env.example`.

### What's honestly not done yet in this pass

The trainer's shared M6 files (`redteam_prompts.csv`, 50 prompts, and
`loan_approval_data.csv`) are now in this repo (`scripts/`,
`data/bias_audit/`), copied verbatim, plus three runnable scripts adapted
to this app's own endpoints rather than the separate GCP-deploy demo's
`/chat` toy app:

| Script | What it does | Run it |
|---|---|---|
| `scripts/redteam_runner.py` | Logs in, POSTs all 50 shared prompts to `/research`, records the real block/pass verdict off the live HTTP response | `python scripts/redteam_runner.py --host <backend-url>` |
| `scripts/locustfile.py` | 500-user Locust load test against the VM Compose stack's `/research` | `python -m locust -f scripts/locustfile.py --headless -u 500 -r 20 -t 60s --host=<vm-url> --csv=reports/load_test` |
| `scripts/bias_audit.py` | AIF360 audit (disparate impact / statistical parity / equal opportunity) against the shared loan-approval dataset | `python scripts/bias_audit.py` |

**Still not done in this pass:** these three haven't actually been
*executed* against a live deployment yet (no VM/Cloud Run instance was
running from this dev machine), so `reports/redteam_results.json`,
`reports/load_test_stats.csv`, and `reports/bias_audit_results.json`
don't exist yet, and the Model Card / NIST AI RMF worksheet (which need
those real numbers) haven't been filled in - flagged here rather than
faked, same disclosure rule this program has used since M5's eval
findings. See `PRODUCTION_READINESS_CHECKLIST.md` for the itemized status.
