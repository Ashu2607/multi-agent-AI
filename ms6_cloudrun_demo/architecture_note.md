# Production Architecture Note — AI Platform (M6 demo)

**The core (M3/M4/M5, unchanged in the middle):** api-gateway (FastAPI) fronting
chat-service, memory-service, and sql-service, backed by Postgres. Nothing in
this box changed for M6 — same rule M5 used for its own diagram.

**The new M6 ring around it:**

```
                     ┌─────────────────────────────────────────┐
                     │              M6 production ring          │
                     │                                            │
   student/curl ───► │  JWT + API-key  ──►  prompt-injection      │
                     │  check (auth.py)     guardrail             │
                     │        │            (guardrails.py)        │
                     │        ▼                    │              │
                     │   ┌─────────────────────────▼──────────┐   │
                     │   │        api-gateway (unchanged       │   │
                     │   │        routing logic underneath)    │   │
                     │   └───┬─────────────┬──────────────┬───┘   │
                     │       │             │              │        │
                     │       ▼             ▼              ▼        │
                     │  chat-service  memory-service  sql-service  │
                     │       │                              │      │
                     │       └──────────────┬───────────────┘      │
                     │                      ▼                      │
                     │                  Postgres                    │
                     │                                            │
                     │  Docker Compose (local, all 6 services)    │
                     │  Cloud Run (api-gateway only, light-touch)  │
                     │  Locust (500-user run, targets Compose)     │
                     │  AIF360 + Model Card + NIST (docs, offline) │
                     └─────────────────────────────────────────┘
```

**4-6 sentences:**

1. The M3-M5 core — api-gateway, chat-service, memory-service, sql-service,
   Postgres — is unchanged; M6 wraps it, it doesn't rebuild it.
2. Every request into api-gateway now passes two independent gates before
   reaching any business logic: an API key (M5 baseline) and a JWT (M6,
   identity + expiry), both required.
3. Chat messages that pass auth are then checked by a prompt-injection
   guardrail before they ever reach the LLM — a flagged message gets a
   safe refusal and never leaves this service.
4. The whole stack runs as one Docker Compose unit on a single VM; only
   api-gateway additionally gets a light-touch Cloud Run deployment, since
   it's the one stateless piece that actually benefits from serverless —
   the UI and data store stay on the VM.
5. Load (Locust, 500 users) and security (red-team) testing both target the
   VM's own Compose stack, not Cloud Run — real traffic against a $10
   total credit budget stays where it's free.
6. Responsible AI evidence (bias audit, red-team results, Model Card, NIST
   worksheet) is generated from this same deployed stack, not written from
   assumptions — every number in those documents traces back to a real run
   against this architecture.
