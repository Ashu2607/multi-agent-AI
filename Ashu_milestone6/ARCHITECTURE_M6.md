# Milestone 6 — Production Architecture Note

**M6 wraps the unchanged M3 core and M5 API/UI/observability ring in a
deployment, security-hardening, and governance ring — it adds no new
agents, tools, or routing logic.** The Supervisor → Researcher → Writer →
Human Approval graph is exactly M3's; the FastAPI/Streamlit split and the
LLMOps instrumentation are exactly M5's. What's new: the whole stack now
comes up as four Docker Compose services instead of three manually-ordered
terminals; the FastAPI backend also deploys standalone to Cloud Run behind
a real URL; every business request now passes two required auth checks
(API key *and* JWT, not either/or) and a prompt-injection/jailbreak/PII
guardrail (ported and strengthened from M4) before it ever reaches the
graph; and the whole thing ships with the deployment/security evidence a
production sign-off actually asks for, instead of a claim that it works.

```mermaid
flowchart TB
    subgraph Laptop["Your laptop (dev only — cannot reach VM/Cloud Run, firewalled)"]
        Dev[Edit code, zip, upload via SSH-in-browser]
    end

    subgraph VM["GCP VM — Docker Compose stack (docker-compose.yml)"]
        direction TB
        UI["ui service\nStreamlit (Dockerfile.ui)"]
        Backend["backend service\nFastAPI (Dockerfile)"]
        Vec["vectorstore service\nchromadb/chroma"]
        Redis["redis service\nredis:7-alpine"]
        UI -->|http://backend:8000| Backend
        Backend -->|http://vectorstore:8000| Vec
        Backend -->|redis://redis:6379| Redis
    end

    subgraph Ring["M6 Security Ring — every business route"]
        direction TB
        APIKey["Depends(require_api_key)\nX-API-Key, app-wide"]
        JWT["Depends(require_jwt)\nBearer token, required (M6)"]
        Guard["app.guardrails.check_prompt\ninjection/jailbreak/toxicity -> block\nPII -> redact"]
        APIKey --> JWT --> Guard
    end

    subgraph Core["UNCHANGED M3 CORE"]
        Graph["LangGraph:\nSupervisor -> Researcher -> Writer -> Human Approval"]
        Tools["web_search, text_to_sql,\nknowledge_base, report_writer"]
    end

    subgraph CloudRun["Cloud Run — backend only (gcloud run deploy --source .)"]
        CR["research-backend\nsame Dockerfile, verified via curl\nfrom VM/Cloud Shell, not laptop browser"]
    end

    Dev --> VM
    Backend -.same image, also deployed to.-> CR
    Ring --> Core
    Backend --> Ring
    CR --> Ring
    Core --> Tools

    subgraph Evidence["M6 Evidence (see README)"]
        T1["tests/test_api_security.py\nJWT+API-key regression"]
        T2["tests/test_guardrails.py\n20-row dataset regression"]
        T3["scripts/locustfile.py, bias_audit.py,\nredteam_runner.py in repo, ready —\nnot yet executed live; Model Card,\nNIST worksheet still open (see README)"]
    end

    Ring -. proven by .-> T1
    Guard -. proven by .-> T2
```

## Why only the backend goes to Cloud Run

The API is the stateless layer — it holds no data of its own between
requests, so it's the one piece that actually benefits from Cloud Run's
scale-to-zero model. The vector store is stateful (an index that takes
real embedding calls to rebuild) and the Streamlit UI is an internal ops
tool, not a public-facing service; both stay on the VM's Compose stack
where they're cheaper to keep running and don't need to survive traffic
spikes from strangers. This mirrors a real production pattern: serverless
for the request-handling tier, persistent infra for stateful/internal
pieces.

## Why the load test targets the VM, not Cloud Run

The VM is already a sunk cost for the rest of the program regardless of
this milestone, so testing against it costs nothing extra. Cloud Run
bills per request/CPU-second; pointing a 500-concurrent-user Locust burst
at it would burn real, avoidable money out of a ~$10 total remaining
budget for a number that (per the Locust step) is not even meant to be
Cloud-Run-representative — see `DEPLOY.md`.
