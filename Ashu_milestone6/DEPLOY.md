# Deploy Runbook — Milestone 6

Copy-paste commands for the two things M6 asks you to stand up: the full
stack under Docker Compose on your VM, and the FastAPI backend on Cloud
Run. **Run every command in this file from inside your VM's own SSH-in-
browser session** — not your laptop's terminal, not Cloud Shell upload,
not `git clone`. Your laptop's browser cannot reach your VM's IP, anything
Docker-hosted on it, or (unconfirmed but assume yes) a Cloud Run URL — that
firewall rule is why every check below is a `curl` run from inside the VM.

> **GCP resources are wiped daily at 9am and 9pm.** Nothing survives
> overnight. Redeploy fresh the morning of your review using the exact
> commands below — that's the whole reason they're written down verbatim
> instead of "run gcloud run deploy with your usual flags."
>
> **Budget is ~$10 total for the rest of the program.** Step 2 (Cloud Run)
> is a verify-once step, not a load-test target — the 500-user Locust run
> (M6 Step 6, not yet implemented in this pass — see README) targets the
> VM Compose stack instead, on purpose.

---

## 0. Get the code onto the VM

Same path as every other GCP lab this program has used: the SSH-in-
browser window's **Upload File** button. Zip this project directory on
your laptop, upload the zip, then on the VM:

```bash
unzip Ashutosh_Milestone5.zip -d research-assistant
cd research-assistant
cp .env.example .env
nano .env   # fill in OPENAI_API_KEY, API_KEY, JWT_SECRET, DEMO_PASSWORD, etc.
```

Generate the two secrets you don't already have:

```bash
python3 -c "import secrets; print('API_KEY=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(32))"
```

Put a real value in `DEMO_PASSWORD` too — the Streamlit UI silently fails
every request without it now that JWT is required everywhere (M6).

---

## 1. Docker Compose — full stack, one command

```bash
docker compose up -d --build
docker compose ps                      # all 4 services should show "Up"
```

Build the knowledge base **into the running vectorstore container** (the
`vectorstore` service starts empty):

```bash
docker compose exec backend python scripts/build_knowledge_base.py
docker compose exec backend python scripts/ingest_structured_data.py
```

Verify end-to-end, from inside the VM:

```bash
# API directly
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/auth/login \
  -H "X-API-Key: $(grep ^API_KEY= .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"demo\",\"password\":\"$(grep ^DEMO_PASSWORD= .env | cut -d= -f2)\"}"
# copy the access_token from that response into $TOKEN, then:
curl -s -X POST http://localhost:8000/research \
  -H "X-API-Key: $(grep ^API_KEY= .env | cut -d= -f2)" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task":"Compare DataSphere 1 and QuantumSoft 2 pricing"}'

# UI (Streamlit) - reachable only from inside the VM's own session/tunnel
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501
```

Bring it down when you're done for the day (doesn't survive the 9pm sweep
anyway, but frees VM resources immediately):

```bash
docker compose down          # keeps the named volumes (chroma_data, redis_data)
docker compose down -v       # also wipes them - use if you want a clean re-index
```

---

## 2. Cloud Run — deploy the FastAPI backend, verify, stop

Only the backend goes to Cloud Run. The UI and vector store stay on the
VM's Compose stack (a stateful vector DB and an internal ops UI aren't
what serverless scaling is for — see `ARCHITECTURE_M6.md`).

```bash
gcloud config set project "$(gcloud config get-value project)"

# Turn your .env into a comma-separated --set-env-vars string. Values in
# this .env don't contain commas/spaces, which is what makes this safe;
# if yours does, use --env-vars-file with a YAML file instead.
ENV_VARS=$(grep -v '^#' .env | grep '=' | paste -sd ',' -)

gcloud run deploy research-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 2 \
  --timeout 300 \
  --set-env-vars "$ENV_VARS"
```

`--allow-unauthenticated` opens the *Cloud Run ingress* (so `curl` from
anywhere can reach the URL at all) — the app's own two auth layers
(`X-API-Key` + JWT, M6 Step 3) still gate every business route regardless.
This is a deliberate two-tier design, not a hole: infra-level access vs.
application-level authorization.

This is a real Cloud Build — **get the Dockerfile right and run this
once**, don't iterate by redeploying repeatedly (see the credit warning).

### Verify (from inside the VM, never your laptop's browser)

```bash
SERVICE_URL=$(gcloud run services describe research-backend \
  --region us-central1 --format='value(status.url)')
echo "$SERVICE_URL"

curl -s "$SERVICE_URL/health"
curl -s -o /dev/null -w "%{http_code}\n" "$SERVICE_URL/docs"

API_KEY=$(grep ^API_KEY= .env | cut -d= -f2)
DEMO_PASSWORD=$(grep ^DEMO_PASSWORD= .env | cut -d= -f2)

TOKEN=$(curl -s -X POST "$SERVICE_URL/auth/login" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d "{\"username\":\"demo\",\"password\":\"$DEMO_PASSWORD\"}" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3 real queries, not just /health
for q in \
  "Compare DataSphere 1 and QuantumSoft 2 pricing and Q1 2025 growth" \
  "What does the compliance policy say about distributing reports?" \
  "Summarize last quarter's regional sales performance"; do
  echo "--- $q ---"
  curl -s -X POST "$SERVICE_URL/research" \
    -H "X-API-Key: $API_KEY" -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"task\":\"$q\"}" | head -c 400; echo
done
```

### Tear down when you're done verifying

```bash
gcloud run services delete research-backend --region us-central1 --quiet
```

Not strictly required (the 9pm sweep will get it anyway), but if you're
finished for the day, deleting it early keeps CPU-allocated billing to a
minimum — Cloud Run bills while `--min-instances` keeps an instance warm,
and `0` (used above) means it should scale to zero between requests, but
delete it explicitly if you want to be certain.

### Redeploy on Friday morning

Run the **exact block under "Cloud Run — deploy"** above again — that's
the whole point of writing it down verbatim. Nothing about the command
changes; only the fact that the 9am sweep deleted last night's service.

---

## 3. Environment variables this deploy needs

See `.env.example` for the full annotated list. The ones that matter for
this runbook specifically:

| Variable | Needed for | One-line meaning |
|---|---|---|
| `OPENAI_API_KEY` | Compose + Cloud Run | LLM + embeddings calls the pipeline makes. |
| `API_KEY` | Compose + Cloud Run | Layer-1 auth: every request's `X-API-Key` header must match this. |
| `JWT_SECRET` | Compose + Cloud Run | Layer-2 auth: signs/verifies the bearer token from `/auth/login`. |
| `DEMO_USERNAME` / `DEMO_PASSWORD` | Compose + Cloud Run | The one demo identity `/auth/login` accepts. |
| `BLOCK_ON_INJECTION` | Compose + Cloud Run | `true` (default) = guardrail blocks unsafe prompts before the pipeline runs. |
| `CHROMA_SERVER_HOST` | Compose only | Set by `docker-compose.yml` to `vectorstore`; leave blank for Cloud Run (embedded/local mode) or local CLI use. |
| `REDIS_URL` | Compose only | Set by `docker-compose.yml` to `redis://redis:6379/0`; falls back to in-memory automatically if unset/unreachable. |
| `TAVILY_API_KEY` | Optional | Web search; falls back to keyless DuckDuckGo if unset. |

---

## What's verified vs. what's still open

**Done and tested in this pass** (see `README.md` "Milestone 6" section
for the full evidence list): Docker Compose 4-service stack, required
JWT+API-key on every business route (regression-tested in
`tests/test_api_security.py`), guardrail pipeline wired to `/research*`
(regression-tested in `tests/test_guardrails.py` against a 20-row
dataset), Cloud Run deploy path documented and Dockerfile build-tested
locally.

**Not done in this pass** — flagged here rather than hidden, same
disclosure rule as the rest of this program: the 500-user Locust load
test (M6 Step 6), the AIF360 bias audit (Step 5), the Model Card / NIST
AI RMF worksheet (Step 5), and the shared 50-prompt red-team run (Step
4) haven't actually been *executed* against a live deployment yet. The
trainer's shared files (`redteam_prompts.csv`, `loan_approval_data.csv`)
and adapted runner scripts (`scripts/redteam_runner.py`,
`scripts/locustfile.py`, `scripts/bias_audit.py`) are now in this repo —
see the README's "What's honestly not done yet" table for exact run
commands. `model_card_template.md` and `nist_ai_rmf_worksheet.md` still
need to be pulled in and filled with the real output of those three runs.
