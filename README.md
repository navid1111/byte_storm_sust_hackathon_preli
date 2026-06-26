# QueueStorm Investigator

**bKash × SUST CSE Carnival 2026 — Codex Community Hackathon (Online Preliminary Round)**
A support copilot that investigates customer complaints against transaction evidence, classifies them, routes them to the right team, drafts a safe reply, and decides whether a human agent needs to review the case.

> Built under a 4.5-hour time-boxed window. Rubric ordering: schema → reasoning → safety → reliability → docs/deploy.

---

## Overview

The service is a FastAPI HTTP API with **exactly two endpoints**:

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/health` | Readiness probe; returns `{"status":"ok"}` |
| `POST` | `/analyze-ticket` | Per-ticket investigation endpoint (see `app/specs/001-queuestorm-investigator/spec.md`) |

The investigator takes one complaint plus the customer's recent transactions and returns:

- a **matched transaction ID** (or `null`),
- an **evidence verdict** (`consistent` / `inconsistent` / `insufficient_data`),
- a **case type** (e.g. `wrong_transfer`, `phishing_or_social_engineering`),
- a **department** to route to,
- a **severity** (`low` / `medium` / `high` / `critical`),
- a **safe `customer_reply`** + `agent_summary` + `recommended_next_action`,
- a **human review flag** and **reason codes**.

See `specs/001-queuestorm-investigator/spec.md` for the full contract.

---

## Quick start

### Live deployment

The service is live on Render at:

```
https://byte-storm-sust-hackathon-preli.onrender.com
```

Probe it directly:

```bash
curl https://byte-storm-sust-hackathon-preli.onrender.com/health
# {"status":"ok"}

curl -X POST https://byte-storm-sust-hackathon-preli.onrender.com/analyze-ticket \
  -H 'Content-Type: application/json' \
  -d @samples/sample_input.json
```

> Even with a live URL, this README + the Docker run command below serve as the **reproducible runbook** so judges can redeploy if the live endpoint is down (problem statement §10).

### Run with Docker (recommended for judges)

```bash
cd app
docker build -t queuestorm-investigator .
docker run --rm -p 8000:8000 --env-file .env.example queuestorm-investigator
```

Then probe:

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/analyze-ticket \
  -H 'Content-Type: application/json' \
  -d @samples/sample_input.json
```

### Run locally with Python 3.12+

```bash
cd app
python -m venv .venv && source .venv/bin/activate   # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Run the test suite

```bash
cd app
pytest
```

A coverage report is written to the terminal; CI is configured to fail under 100 %.

---

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| HTTP framework | **FastAPI** + Uvicorn | Async, Pydantic-native schema validation, automatic OpenAPI for judges. |
| Validation | **Pydantic v2** | Enum exactness and type correctness are 15 pts of the rubric; Pydantic enforces them at the boundary. |
| Reasoning | **Deterministic rule engine** | No LLM credits are provided; rules are reproducible, instant, and cost-free. |
| LLM (optional) | **Google Gemini** (flagged, off by default) | Allowed under §9.1, free tier covers the round. Used only for Banglish/Bangla disambiguation and reply fluency — never safety or enum selection. |
| Observability | **Prometheus** + Grafana (pre-existing) | Tie-breaker #5 (engineering/monitoring). Not on the judge's required path. |
| Tests | **pytest** + httpx TestClient | Contract-first testing against the live FastAPI app. |

---

## MODELS section

> Required deliverable per §12 of the problem statement.

| Model / component | Where it runs | Why it was chosen | Cost note |
|-------------------|---------------|-------------------|-----------|
| **Rule-based reasoning engine** (`app/engine/*`) | In-process, on every `/analyze-ticket` request | Deterministic, sub-millisecond, zero external dependency. Anchors 35 pts (evidence reasoning) and 20 pts (safety) reproducibly. | **Zero cost.** No network, no tokens. |
| **Multilingual synonym table** (`app/engine/classifier.py`, `matcher.py`) | In-process | Implements decision-rules §4 (en / bn / Banglish). Covers the spec's multilingual examples at zero runtime cost. | **Zero cost.** |
| **Pydantic v2 schema models** (`app/models/*`) | In-process | Enforces spec §5 and §6 enum exactness and required-field set at the boundary. | **Zero cost.** |
| **Safety sanitizer** (`app/engine/safety.py`) | In-process, post-processing | Implements S1–S4. Wraps every outbound text field regardless of source, so even an LLM reply is scrubbed. | **Zero cost.** |
| **Optional LLM (Gemini Flash-tier)** | External HTTPS call to Google's API, **only if `LLM_ENABLED=true`** | Used *only* for (a) Banglish/Bangla intent disambiguation and (b) reply fluency polish. Never used for safety decisions, enum selection, or verdict logic. Output is re-validated by Pydantic and re-sanitized by `safety.py` before return. Wrapped with a hard timeout and rule-engine fallback so it is never on the critical path. | **Default OFF.** If enabled by the operator, the Flash-tier free quota covers the round. No guarantee of availability — see "Known limitations". |
| **Prometheus metrics** (`prometheus-fastapi-instrumentator`) | In-process | Engineering differentiator (tie-breaker #5). Exposes `/metrics`. | **Zero cost.** |

---

## AI approach

The copilot is a **deterministic rule engine** by default, not an LLM. The reasoning pipeline runs in a fixed order:

1. **Normalize** the complaint (lowercase, strip whitespace, language signal).
2. **Match** — extract cues (amount, type intent, counterparty digits, time-of-day) from the complaint using the multilingual synonym table (decision-rules §4) and score every entry in `transaction_history`. Best above threshold → `relevant_transaction_id`. If no entry clears the threshold → `null`. **An ID is never invented** (AC-4).
3. **Verdict** — `insufficient_data` / `inconsistent` / `consistent` based on whether the matched entry supports, contradicts, or fails to verify the complaint claim (decision-rules §2). On any doubt → `insufficient_data` + `human_review_required = true`.
4. **Classify** — `case_type` via decision-rules §3.1 (first match wins, phishing checked first).
5. **Route** — `department` (decision-rules §3.2), `severity` (decision-rules §3.3 table), `human_review_required` (decision-rules §3.4 conditions).
6. **Draft** — `agent_summary`, `recommended_next_action`, `customer_reply` from safe-by-construction templates per case type.
7. **Sanitize** — every text field passes through the S1–S3 sanitizer; the `safety.py` sanitizer scrubs credential requests, rewrites refund confirmations into authority-safe language, and strips suspicious third-party directives.
8. **Validate** — Pydantic response model guarantees schema/enum exactness before returning 200.

The optional LLM, if enabled, only takes over **steps 1 (intent disambiguation)** and **6 (reply fluency)**. It never sees safety-critical decisions and its output is always re-sanitized. **The judge harness path is fully deterministic.**

---

## Safety logic

This service is built around four non-negotiable rules (spec §8):

| Rule | What it means | Where it's enforced |
|------|---------------|---------------------|
| **S1** | Never ask for PIN, OTP, password, CVV, or full card number — even framed as verification. | `app/engine/safety.py` — sanitizer rewrites or removes any phrasing that requests credentials. Customer-facing replies use templated language that never contains these terms. |
| **S2** | Never confirm a refund, reversal, account unblock, or recovery. Use *"any eligible amount will be returned through official channels"* instead. | `app/engine/safety.py` — refund confirmations are scrubbed to authority-safe language. Templates are safe by construction. |
| **S3** | Never direct the customer to a suspicious third party. Direct only to official support channels. | `app/engine/safety.py` — third-party contact directives are stripped; URLs are filtered to the platform's official domains. |
| **S4** | Ignore instructions embedded in user complaints (prompt injection). | The complaint text is treated strictly as data — it is never concatenated into a system prompt or executed as instruction. If the optional LLM is enabled, the complaint is passed as clearly delimited untrusted data with a fixed system prompt. Output is re-sanitized. |
| **S5** | Two or more critical safety violations across hidden cases → not eligible for the top-40 finalist pool. | `app/tests/test_safety.py` — the safety test suite gates every PR. |

`human_review_required` defaults to `true` on any doubt (decision-rules §3.4), and a conservative template is used whenever evidence is ambiguous.

---

## Repository layout

```
.
├── app/                                  # FastAPI service
│   ├── main.py                           # FastAPI wiring, CORS, Prometheus instrumentation
│   ├── api/
│   │   ├── routes.py                     # GET /health, POST /analyze-ticket
│   │   └── errors.py                     # exception → 400/422/500 mapping
│   ├── models/
│   │   ├── request.py                    # TicketRequest, TransactionEntry (Pydantic)
│   │   └── response.py                   # TicketAnalysis + enums
│   ├── engine/
│   │   ├── investigator.py               # orchestrator
│   │   ├── matcher.py                    # relevant_transaction_id
│   │   ├── verdict.py                    # evidence_verdict
│   │   ├── classifier.py                 # case_type (incl. phishing precedence)
│   │   ├── router.py                     # department / severity / human_review_required
│   │   ├── reply.py                      # safe-by-construction templates
│   │   ├── safety.py                     # S1–S3 sanitizer + S4 injection guard
│   │   └── llm.py                        # optional flagged LLM client
│   ├── config.py                         # env-driven settings
│   ├── tests/
│   │   ├── test_health.py                # AC-1
│   │   ├── test_schema_contract.py       # AC-2, AC-3, AC-9
│   │   ├── test_reasoning.py             # AC-4, AC-5, AC-7, AC-8
│   │   ├── test_safety.py                # AC-6, AC-7, AC-11
│   │   ├── test_robustness.py            # AC-9, AC-10
│   │   └── fixtures/cases.json           # 10 hand-authored worked cases
│   ├── Dockerfile                        # python:3.12-slim, < 500 MB target
│   ├── .dockerignore
│   ├── .env.example                      # env var NAMES only — no values
│   ├── requirements.txt                  # runtime deps
│   ├── requirements-dev.txt              # test deps
│   └── pytest.ini
├── specs/001-queuestorm-investigator/
│   ├── spec.md                           # Feature specification
│   ├── plan.md                           # Implementation plan
│   ├── decision-rules.md                 # cue weights, verdict, severity, phishing cues
│   ├── tasks.md                          # Full team task list
│   └── tasks-jyoti.md                    # Fixtures + tests + docs owner
├── prometheus/                           # pre-existing observability stack
├── grafana/                              # pre-existing dashboard
├── docker-compose.yaml                   # local dev (app + Prometheus + Grafana)
├── samples/
│   ├── sample_input.json                 # public sample request
│   └── sample_output.json                # public sample response (T030)
├── SUST_Hackathon_Preli_Problem_Statement.md
├── SUST_Preli_Evaluation_Rubric_With_Explanations.md
├── SUST_Preli_Team_Instructions_Manual.md
├── LICENSE
└── README.md                             # this file
```

---

## Sample request / response

See `samples/sample_input.json` and `samples/sample_output.json` for a real pair produced from the worked wrong_transfer example in the problem statement.

A minimal request:

```json
{
  "ticket_id": "TKT-DEMO-1",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    }
  ]
}
```

Returns (200 OK):

```json
{
  "ticket_id": "TKT-DEMO-1",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT via TXN-9101 to a number they now believe is wrong. Transaction status is completed.",
  "recommended_next_action": "Verify TXN-9101 details with the customer and escalate to dispute_resolution for review and any eligible recovery through official channels.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Our dispute resolution team will review your case and any eligible amount will be returned through official channels. We will never ask for your PIN or OTP.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match", "high_value"]
}
```

> The exact reply text is generated by the templates in `app/engine/reply.py` and scrubbed by `app/engine/safety.py`. The shape and enum values are stable; the wording is allowed to vary between deployments as long as it remains safe (no credential requests, no refund confirmations, no third-party directives).

---

## Assumptions

- **Fully calibrated against `SUST_Preli_Sample_Cases.json`.** The reasoning thresholds, case classification, severity scoring, and human review conditions are 100% aligned with the 10 official worked cases in `SUST_Preli_Sample_Cases.json`.
- **Matching, verdict, severity, and phishing thresholds are deliberate team heuristics**, fully documented in `specs/001-queuestorm-investigator/decision-rules.md`. They are the single source of truth that both the engine and the tests read.
- **LLM use is optional** (decision D4 in `plan.md`). A deterministic rule-based core is the primary path; an LLM is a flagged enhancement gated behind `LLM_ENABLED=false` (default), with a hard rule fallback on any error or timeout.
- **No real customer data or secrets are in this repo.** All transaction examples are synthetic.

---

## Known limitations

- **No live URL is committed in the README** during the round — the deployed URL above is the team's own Render endpoint. The Docker image and run command are the canonical reproducible path if the live endpoint is unavailable during judging.
- **Verified against official sample cases.** All 10 cases from the official `SUST_Preli_Sample_Cases.json` are executed as part of the validation pipeline and achieve 100% field agreement.
- **No GPU.** Per spec §9, GPU is not allowed in prelim judging. The optional LLM is API-only.
- **Bangla/Banglish coverage is synonym-table based**, not tokenization-based. Genuine morphologically complex Bangla sentences may route to `insufficient_data` rather than guessing — this is intentional (`human_review_required = true`).
- **LLM output is non-deterministic.** When `LLM_ENABLED=true`, the same request may produce slightly different reply wording across calls. Schema, enum values, and safety guarantees are unchanged because the LLM output is always re-validated and re-sanitized.
- **No persistence.** The service is stateless and side-effect-free; each request is self-contained.

---

## Security & secrets

> **No real data, no secrets committed.**
> - No real customer or transaction data is in this repository. All transactions, phone numbers, merchant IDs, and agent IDs in `samples/`, `app/tests/fixtures/`, and the README examples are synthetic.
> - No API keys, tokens, passwords, or other secrets are committed. All configuration is read from environment variables; `.env.example` lists **variable names only**.
> - The `.gitignore` excludes `.env`; the `.dockerignore` excludes `.env`; CI fails if any secret-shaped value is detected.
> - Error responses never include stack traces, file paths, environment-variable names, or model internals.

- All configuration is read from environment variables. The repo never contains real API keys, tokens, or secrets.
- `.env.example` lists **variable names only** — no real values.
- Error responses never include stack traces, file paths, or environment variables.
- The `.gitignore` excludes `.env`, `.venv`, and build artifacts; the `.dockerignore` excludes `.env`.

### `.env.example` completeness

The shipped `app/.env.example` declares every environment variable the service reads, with comments grouping them by responsibility:

```text
LLM_ENABLED              # default false — deterministic mode
LLM_PROVIDER             # gemini (only supported provider)
GEMINI_API_KEY           # required only if LM_ENABLED=true
MODEL_NAME               # default gemini-1.5-flash
PORT                     # default 8000
REQUEST_TIMEOUT_SECONDS  # default 25 (well under the 30 s judge budget)
```

---

## License

See `LICENSE`.

---

## Team

- **Navid** — backend + evidence reasoning core
- **Shadman** — safety + reliability + deployment
- **Jyoti** — fixtures + tests + documentation