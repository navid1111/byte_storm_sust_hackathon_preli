# Implementation Plan: QueueStorm Investigator

**Spec**: [`spec.md`](./spec.md)
**Branch**: `001-queuestorm-investigator`
**Created**: 2026-06-26

This plan turns the spec into a concrete, time-boxed engineering approach for the 4.5-hour window. It
records the technical decisions, the architecture, the data model, and the contract tests — the *HOW*.

---

## 1. Guiding Strategy (priority order from the rubric)

The rubric is explicit about what to do first. We follow it exactly:

1. **Schema & endpoints correct first** — without valid JSON + reachable endpoints, the judge cannot
   score anything (15 pts gated, everything else depends on it).
2. **Evidence-based reasoning** over complaint + transaction history — the largest score (35 pts).
3. **Safety guardrails** before polishing text — unsafe replies can erase a high score (20 pts + can
   disqualify).
4. **Reliability & reachability** under the judge harness — timeouts/crashes lose a correct service (10 pts).
5. **Clear README + sample output + deployment** — documentation and reproducibility (10 pts) + Stage 2.

**Design principle:** *A simple, reliable, safe rule-based API will outscore a complex but unreliable
LLM one.* The deterministic core is the product; the LLM is an optional, fail-safe enhancement.

## 2. Architecture Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **FastAPI + Uvicorn** (existing stack) | Already in repo; async, fast, Pydantic-native schema validation gives us 400/422 handling for free. |
| D2 | **Pydantic v2 models** for request & response | Enum exactness and type correctness are 15 pts; Pydantic enforces them at the boundary and auto-returns 422 on validation errors. |
| D3 | **Deterministic rule engine as the default brain** | No LLM credits are provided; rules are reproducible, instant (<5 s p95 → full latency credit), and cost-free. Most reasoning (verdict, case_type, routing, severity) is deterministic from structured signals. |
| D4 | **Optional LLM layer behind a feature flag** (`LLM_ENABLED`, off by default) | Hybrid rule+AI is *recommended* by the manual. LLM only assists language understanding / reply drafting, never overrides safety. Hard fallback to rules on any error/timeout. |
| D5 | **Safety as a post-processing gate** on all generated text | S1–S3 are checked on `customer_reply` / `recommended_next_action`. A regex/keyword sanitizer runs *after* drafting so even an LLM reply is scrubbed. Rule-templated replies are safe by construction. |
| D6 | **Prompt-injection neutralization** | Complaint text is treated strictly as data — never concatenated into a system instruction without delimiting; rule core ignores it entirely for control flow (S4). |
| D7 | **Keep existing Prometheus + Grafana** | Differentiator for tie-breaker #5 (monitoring). `/metrics` already exposed; not on the judge's required path, no latency impact on `/analyze-ticket`. |
| D8 | **Single-process, stateless, no DB** | Each request is self-contained; statelessness = trivial reliability, horizontal scalability, and reproducibility. |
| D9 | **Replace the placeholder `GET /` & default app** | Current `main.py` returns "Hello World"; we repurpose into the investigator service while keeping CORS + instrumentation. |

## 3. Target Project Structure

```
app/
  main.py                 # FastAPI app: wiring, middleware, instrumentation, routes
  api/
    routes.py             # GET /health, POST /analyze-ticket
    errors.py             # exception handlers → 400/422/500 with non-sensitive messages
  models/
    request.py            # TicketRequest, TransactionEntry (Pydantic)
    response.py           # TicketAnalysis (Pydantic) + enums (CaseType, Department, ...)
  engine/
    investigator.py       # orchestrates: match → verdict → classify → route → severity → review
    matcher.py            # complaint ↔ transaction matching (relevant_transaction_id)
    verdict.py            # consistent / inconsistent / insufficient_data logic
    classifier.py         # case_type detection (keyword + signal rules, en/bn/banglish)
    router.py             # department + severity + human_review_required
    reply.py              # agent_summary, recommended_next_action, customer_reply templates
    safety.py             # S1–S3 sanitizer + prompt-injection guard (S4)
    llm.py                # optional LLM client (flagged), with rule fallback
  config.py               # env-driven settings (LLM_ENABLED, provider keys, timeouts)
  tests/
    test_health.py
    test_schema_contract.py
    test_reasoning.py
    test_safety.py
    test_robustness.py    # malformed / empty / multilingual / injection
    fixtures/             # sample cases (from SUST_Preli_Sample_Cases.json when available)
  requirements.txt
  Dockerfile
  .env.example
samples/
  sample_output.json      # required deliverable: output from a public sample case
README.md                 # setup, MODELS section, safety logic, limitations
specs/001-queuestorm-investigator/{spec.md,plan.md,tasks.md}
```

## 4. Reasoning Pipeline (the core 35 points)

Input → ordered stages, each deterministic and independently testable:

1. **Normalize** — lowercase, strip, detect language signal; treat complaint as opaque data.
2. **Match** (`matcher.py`) → `relevant_transaction_id`
   - Extract cues from complaint: amount, recipient/number, time-of-day, transaction type words
     (English + Bangla + Banglish synonyms: *taka/টাকা*, *pathaisi/sent*, *refund/ফেরত*, etc.).
   - Score each history entry on amount match, type match, counterparty/recipient match, recency.
   - Best scoring entry above threshold → its ID; else `null`. **Never invent an ID** (AC-4).
3. **Verdict** (`verdict.py`) → `evidence_verdict`
   - `insufficient_data` if history empty / no plausible match / cues unverifiable.
   - `inconsistent` if matched transaction contradicts the claim (e.g. complaint says "money
     deducted but failed" yet status is `completed`; or claims a transfer that does not exist).
   - `consistent` if the matched transaction supports the claim.
4. **Classify** (`classifier.py`) → `case_type` (Section 7.1 keywords + transaction `type`/`status`
   signals; phishing/social-engineering detection takes precedence on suspicious cues).
5. **Route** (`router.py`) → `department` (deterministic map from `case_type` + user_type, Section 7.2),
   `severity` (amount thresholds + status + fraud signals), `human_review_required`
   (disputes / suspicious / high-value / ambiguous verdict → true, AC-8).
6. **Draft** (`reply.py`) → `agent_summary`, `recommended_next_action`, `customer_reply`
   (safe templates per case_type; optional LLM polish if `LLM_ENABLED`).
7. **Sanitize** (`safety.py`) → enforce S1–S3 on all text; attach `reason_codes`, `confidence`.
8. **Validate** → Pydantic response model guarantees schema/enum exactness before returning 200.

## 5. Data Model (Pydantic v2)

- **Enums** (str-based, exact values): `EvidenceVerdict`, `CaseType`, `Severity`, `Department`,
  `Language`, `Channel`, `UserType`, `TransactionType`, `TransactionStatus`.
- `TransactionEntry`: all fields optional-tolerant on parse (judge may send partials) but typed.
- `TicketRequest`: `ticket_id` + `complaint` required; rest optional. Empty/whitespace complaint →
  422 via validator (AC-9).
- `TicketAnalysis`: all Section 6 required fields; `confidence: float | None`, `reason_codes:
  list[str]`. Response is the single source of truth for schema correctness.

## 6. Safety Implementation (20 points + disqualifier)

- **Templated-by-default replies** are safe by construction — no template asks for credentials or
  promises a refund.
- **Sanitizer gate** runs on every outbound text field regardless of source:
  - S1: block/scrub any phrasing requesting PIN/OTP/password/card; replace with a security-awareness
    note ("we will never ask for your PIN or OTP").
  - S2: rewrite refund/reversal/unblock *confirmations* into authority-safe language ("any eligible
    amount will be returned through official channels", "your case has been escalated for review").
  - S3: strip third-party contact directives; direct to official support only.
- **Prompt-injection guard (S4):** complaint is never executed as instruction; if LLM is used, it is
  passed as clearly delimited untrusted data with a fixed system prompt, and its output is re-sanitized.
- **Fail-safe defaults:** on any uncertainty → `human_review_required = true`, conservative reply.

## 7. Robustness & Reliability (10 points)

- Global exception handlers → 400 (malformed/missing), 422 (semantic), 500 (internal, non-sensitive
  message). Never leak stack traces/secrets (AC-13).
- Hard internal time budget well under 30 s; LLM calls wrapped with a timeout + rule fallback.
- Stateless and side-effect-free → no crash surface from concurrent judge calls.
- `/health` is trivial and dependency-free so it answers within 60 s of boot (AC-1).

## 8. Deployment

- **Primary:** Live HTTPS URL (Render / Railway / Fly / Poridhi Lab / EC2) exposing `/health` +
  `/analyze-ticket`, no login. Bind `0.0.0.0`, documented port.
- **Fallback:** Docker image < 500 MB (`python:3.12-slim`, no model weights baked in). `docker build`
  + `docker run -p 8000:8000 --env-file judging.env` documented in README/runbook.
- **Secrets:** env vars only; `.env.example` lists names. No secrets in repo/image/logs.
- The existing `docker-compose.yaml` (app + Prometheus + Grafana) stays for local/monitoring; the
  judge only needs the `app` service.

## 9. Testing Strategy (contract-first)

| Test file | Covers | Acceptance criteria |
|-----------|--------|---------------------|
| `test_health.py` | `/health` shape & speed | AC-1 |
| `test_schema_contract.py` | required fields, enum exactness, ticket_id echo, types | AC-2, AC-3 |
| `test_reasoning.py` | matching, verdict, classify, route on worked sample cases | AC-4, AC-5, AC-7, AC-8 |
| `test_safety.py` | S1/S2/S3 never violated; injection neutralized | AC-6, AC-11 |
| `test_robustness.py` | malformed/empty/missing/multilingual → no crash, correct codes | AC-9, AC-10 |

Run with `pytest`; gate in existing CI (`.github/workflows/ci.yml`). When
`SUST_Preli_Sample_Cases.json` is obtained, load its 10 cases as parametrized fixtures and assert
functional equivalence (same `relevant_transaction_id`, `evidence_verdict`, `case_type`, `department`,
comparable `severity`, safe `customer_reply`).

## 10. Optional LLM Layer (flagged, default off)

- `LLM_ENABLED=false` by default → fully deterministic, zero external dependency, zero cost.
- When enabled: provider via env (`LLM_PROVIDER`, `*_API_KEY`, `MODEL_NAME`); used **only** for (a)
  Banglish/Bangla intent disambiguation and (b) reply fluency — **never** for safety decisions or
  enum selection. Output always passes through the same Pydantic validation + safety sanitizer.
- Rationale captured in README MODELS section (model, where it runs, why, cost note).

## 11. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Sample cases JSON missing → reasoning calibration blind spots | Build from spec examples now; swap in real fixtures the moment the file is available. |
| Enum drift (plural/casing) → schema violation | Single enum source of truth in Pydantic; contract tests assert exact values. |
| LLM latency/cost/quota under judging | Default off; timeout + rule fallback; never on the critical path. |
| Over-confident refund language → −10 / disqualify | Safety sanitizer rewrites all confirmation language; default `human_review_required=true` on doubt. |
| Live URL down during judging | Repo ships a runbook + Docker fallback (required even with live URL). |
| Image bloat > 1 GB | `slim` base, no baked models, `--no-cache-dir`, `.dockerignore`. |

## 12. Out-of-Scope Reminders

No frontend, no real payment integration, no auth, no persistence, no GPU/large local models, no
autonomous financial action. Keep it simple, reliable, safe.
