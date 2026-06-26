# QueueStorm Investigator — System Architecture

**Project:** bKash × SUST CSE Carnival 2026 — Codex Community Hackathon (Online Preliminary Round)
**Team:** Navid (backend + evidence reasoning core) · Shadman (safety + reliability + deployment) · Jyoti (fixtures + tests + docs)

This document describes how the system is put together: the request lifecycle, every component in the
engine, the design decisions behind them, and how safety, deployment, and observability fit in. It is
the single reference for *how the pieces connect* — `decision-rules.md` remains the source of truth for
the actual thresholds and cue tables.

---

## 1. Purpose & Scope

QueueStorm Investigator is a stateless FastAPI service with two endpoints (`GET /health`,
`POST /analyze-ticket`) that turns a customer complaint + transaction history into a fully-reasoned,
safety-checked ticket analysis: matched transaction, evidence verdict, case type, routing, severity,
human-review flag, and safe drafted text. The reasoning core is a **deterministic rule engine**; an
LLM is an optional, fail-safe enhancement layered on top — never a decision-maker.

---

## 2. High-Level Architecture

```mermaid
graph TD
    Client([Judge / Client]) -->|POST /analyze-ticket| API[FastAPI Routes<br/>app/api/routes.py]
    Client -->|GET /health| API

    API --> ReqModel[Pydantic Request Models<br/>TicketRequest / TransactionEntry]
    ReqModel --> Orchestrator[investigator.py<br/>analyze]

    subgraph "Engine Pipeline (engine/)"
        Orchestrator --> Lexicon[lexicon.py<br/>normalize + cue lookup]
        Lexicon --> Matcher[matcher.py<br/>relevant_transaction_id]
        Matcher --> Verdict[verdict.py<br/>evidence_verdict]
        Verdict --> Classifier[classifier.py<br/>case_type]
        Classifier --> Router[router.py<br/>severity / department / human_review]
        Router --> Reply[reply.py<br/>safe-by-construction templates]
        Reply --> Safety[safety.py<br/>S1-S3 sanitizer]
        Safety -.->|if LLM_ENABLED| LLM[llm.py<br/>Gemini fluency polish]
        LLM -.->|re-sanitize| Safety
    end

    Safety --> RespModel[Pydantic Response Model<br/>TicketAnalysis]
    RespModel --> API
    API --> Client

    API -.-> Metrics[/metrics<br/>Prometheus instrumentator]

    style Client fill:#4F46E5,stroke:#312E81,color:#fff
    style API fill:#F59E0B,stroke:#78350F,color:#fff
    style Safety fill:#EF4444,stroke:#7F1D1D,color:#fff
    style LLM fill:#9CA3AF,stroke:#374151,color:#fff
```

**Key property:** the pipeline is a straight line, not a graph with branches back into the model layer.
Every stage takes the previous stage's typed output and produces a typed output for the next. Nothing
downstream of `safety.py` can re-introduce unsafe text, because the sanitizer runs again after the
optional LLM step.

---

## 3. Request Lifecycle

1. **Ingress** — `main.py` wires CORS, Prometheus instrumentation, and routes. `routes.py` exposes
   `GET /health` and `POST /analyze-ticket`.
2. **Parse & validate** — the request body is parsed into `TicketRequest` (Pydantic v2). Invalid
   JSON → 400; semantic violations (e.g. empty `complaint`) → 422. `extra="ignore"` is set so unknown
   top-level fields from the judge harness don't break parsing.
3. **Orchestrate** — `investigator.analyze(ticket)` runs the pipeline in a fixed order:
   `match → verdict → classify → route (severity → department → human_review) → draft → sanitize →
   (optional LLM polish → re-sanitize) → assemble`.
4. **Match** — `matcher.match()` scores every `transaction_history` entry against cues pulled from the
   complaint and returns the best entry above threshold, or `None`. An ID is **never invented**.
5. **Verdict** — `verdict.decide()` compares the matched entry's status against the complaint's claim
   and returns `consistent` / `inconsistent` / `insufficient_data`.
6. **Classify** — `classifier.classify()` walks a fixed precedence list (phishing checked first) and
   returns exactly one `case_type`.
7. **Route** — `router.py` derives `severity` from case type + amount + verdict, then `department`
   from case type + severity, then `human_review_required` from all of the above.
8. **Draft** — `reply.draft()` fills a per-case-type template (already safe by construction) with the
   matched transaction ID and verdict caveat.
9. **Sanitize** — `safety.py` scrubs `customer_reply` and `recommended_next_action` for S1 (credential
   requests), S2 (refund/reversal confirmations), and S3 (third-party directives / unofficial URLs).
10. **Optional LLM polish** — if `LLM_ENABLED=true`, `llm.polish_reply()` rewrites only the wording of
    `customer_reply` for fluency/language matching. Output is **re-sanitized** before use; any error,
    timeout, or missing key falls back silently to the rule-drafted text.
11. **Assemble & validate** — the result is packed into `TicketAnalysis`. Pydantic guarantees schema
    and enum exactness before the 200 response leaves the process.

---

## 4. Layered Breakdown

### 4.1 API layer (`app/api/`)
| File | Responsibility |
|---|---|
| `routes.py` | `GET /health` (dependency-free, answers cold or warm); `POST /analyze-ticket` (delegates entirely to `investigator.analyze`) |
| `errors.py` | Maps exceptions → 400 / 422 / 500 with non-sensitive messages (no stack traces, no file paths, no env var names) |

### 4.2 Models layer (`app/models/`)
| File | Responsibility |
|---|---|
| `request.py` | `TicketRequest`, `TransactionEntry` — required vs. optional fields, type coercion, `extra="ignore"` |
| `response.py` | `TicketAnalysis` + all enums (`CaseType`, `EvidenceVerdict`, `Severity`, `Department`, …) — the single source of truth for schema correctness |

### 4.3 Engine layer (`app/engine/`)
| File | Responsibility | Notes |
|---|---|---|
| `lexicon.py` | Normalization (lowercase, whitespace, Bangla-digit→ASCII) + EN/Bangla/Banglish synonym tables (`TRANSFER_CUES`, `WRONG_NUMBER_CUES`, `FAILED_CUES`, `PHISHING_CUES`, …) + amount/digit-tail extraction | Also strips literal "ignore instructions" phrasing as a first-line S4 guard before the text ever reaches matching logic |
| `matcher.py` | Weighted scoring: amount 0.45, type 0.25, counterparty 0.20, recency 0.10; `MATCH_THRESHOLD = 0.45`, gated by requiring a *strong* cue (amount or counterparty) on top of the threshold; deterministic tie-break (score → amount-match → recency → array order) | `MatchResult` dataclass carries `transaction_id`, `entry`, `score`, `cues` downstream for reason codes |
| `verdict.py` | `insufficient_data` (no match) / `inconsistent` (status `completed` but claim says failed/not-received) / `consistent` (status supports the claim, or any concrete match) | Conservative by design — ambiguity defaults to `insufficient_data`, never to a guess |
| `classifier.py` | Fixed precedence: phishing → duplicate → wrong_transfer → payment_failed → agent_cash_in → merchant_settlement → refund_request → other | `is_agent` / `is_merchant` guards prevent a cash-in or settlement complaint from being misread as a generic payment failure |
| `router.py` | `severity()` (amount thresholds: ≥25,000 BDT high-value, ≥1,000 BDT mid-value; phishing always critical), `department()` (case-type map, refund splits by severity), `human_review_required()` (true on phishing, non-consistent verdict, high/critical severity, or specific case types) | Pure functions — no I/O, fully unit-testable |
| `reply.py` | Per-`case_type` template tuples `(agent_summary, recommended_next_action, customer_reply)`, safe by construction (no template asks for credentials or confirms a refund) | Interpolates `transaction_id` and an evidence caveat into `agent_summary` |
| `safety.py` | S1 credential-request regex scrub, S2 refund/reversal-confirmation rewrite list, S3 third-party/URL strip (allow-lists `support`/`help`/`official` domains) | Runs on *every* outbound text field regardless of source — including LLM output |
| `llm.py` | Optional Gemini client; lazy-imported SDK; fixed system prompt instructing the model to rewrite tone/language only, never meaning; hard try/except fallback to the original text on any failure | Disabled unless `LLM_ENABLED=true` **and** `GEMINI_API_KEY` is set |
| `investigator.py` | Orchestrator — the only file that calls every other engine module, in order | Computes `reason_codes` (case type + match cues + verdict) and a simple `confidence` heuristic from match score and verdict |

### 4.4 Cross-cutting
| Concern | Where |
|---|---|
| Config | `config.py` — env-driven settings (`LLM_ENABLED`, `LLM_PROVIDER`, `GEMINI_API_KEY`, `MODEL_NAME`, `REQUEST_TIMEOUT_SECONDS`, `PORT`) |
| Observability | `prometheus-fastapi-instrumentator` wired in `main.py`, exposing `/metrics`; Prometheus + Grafana stack in `docker-compose.yaml` (not on the judge's required path) |
| Tests | `pytest` + `httpx.TestClient` against the live app — contract-first, one file per concern (`test_health`, `test_schema_contract`, `test_reasoning`, `test_safety`, `test_robustness`) |

---

## 5. Design Decisions

| # | Decision | Why |
|---|---|---|
| D1 | FastAPI + Uvicorn | Async, Pydantic-native validation, free OpenAPI docs for judges |
| D2 | Pydantic v2 for request & response | Enum exactness and required fields are enforced at the boundary, not by hand |
| D3 | Deterministic rule engine as the default brain | No LLM credits provided; rules are reproducible, sub-millisecond, zero cost |
| D4 | Optional LLM behind `LLM_ENABLED` (off by default) | Hybrid enhancement without sacrificing determinism on the judge's critical path |
| D5 | Safety as a post-processing gate on *all* text | One sanitizer covers both rule-drafted and LLM-drafted replies — no safety logic duplicated per source |
| D6 | Prompt-injection neutralization (S4) | Complaint text is data, never an instruction — true whether or not the LLM path is on |
| D7 | Keep existing Prometheus + Grafana | Engineering differentiator at zero cost to the required path |
| D8 | Single-process, stateless, no DB | Removes an entire class of reliability and concurrency bugs |
| D9 | Repurpose the placeholder app | Keeps existing CORS/instrumentation wiring instead of rebuilding it |

---

## 6. Data Model

- **Request:** `TicketRequest` (`ticket_id`, `complaint` required; `language`, `channel`, `user_type`,
  `transaction_history: list[TransactionEntry]` optional). Empty/whitespace `complaint` → 422.
- **Transaction entry:** `transaction_id`, `timestamp`, `type`, `amount`, `counterparty`, `status` —
  optional-tolerant on parse since the judge harness may send partial records.
- **Response:** `TicketAnalysis` — every field in the spec's §6 contract is required and enum-typed:
  `relevant_transaction_id`, `evidence_verdict`, `case_type`, `severity`, `department`,
  `agent_summary`, `recommended_next_action`, `customer_reply`, `human_review_required`,
  `confidence`, `reason_codes`.

---

## 7. Safety Architecture (S1–S5)

| Rule | Enforcement point | Mechanism |
|---|---|---|
| **S1** — never request PIN/OTP/password/CVV/card number | `safety.py`, both sanitizer functions | Regex match on credential terms (EN + Bangla); auto-redacted unless the sentence already contains a "we will never ask" warning |
| **S2** — never confirm a refund/reversal/unblock | `safety.py` | A list of refund/reversal confirmation patterns is rewritten to *"any eligible amount will be returned through official channels"* |
| **S3** — never direct to a suspicious third party | `safety.py` | Strips phrases like "send money to", "contact this number", "click this link"; filters URLs to an allow-list of official-support domain keywords |
| **S4** — ignore instructions embedded in the complaint | `lexicon.normalize()` (pre-strip) + `llm.py` system prompt (untrusted-context framing) | The complaint is never concatenated into a system prompt; the rule engine never branches on the literal text as control flow |
| **S5** — two+ critical violations across hidden cases disqualifies | `app/tests/test_safety.py` | Gates every PR before merge |

`human_review_required` defaults to `true` whenever evidence is ambiguous (`insufficient_data` /
`inconsistent`), so a low-confidence case is never auto-resolved.

---

## 8. Optional LLM Layer

- **Default:** off (`LLM_ENABLED=false`) — zero external dependency, zero cost, fully deterministic.
- **When enabled:** Gemini Flash-tier is used *only* to (a) disambiguate Banglish/Bangla intent during
  normalization and (b) polish the fluency of `customer_reply`. It never selects an enum and never
  makes a safety decision.
- **Guardrails:** fixed system prompt, complaint passed as clearly delimited untrusted context, hard
  request timeout (`REQUEST_TIMEOUT_SECONDS`, well under the 30 s judge budget), and a silent fallback
  to the original rule-drafted text on any exception. Output is re-validated by Pydantic and
  re-sanitized by `safety.py` before it leaves the process.

---

## 9. Deployment Architecture

- **Primary:** live HTTPS URL on Render (`https://byte-storm-sust-hackathon-preli.onrender.com`),
  cold-start tolerant (`/health` has no dependencies and no model warm-up).
- **Fallback:** `Dockerfile` on `python:3.12-slim`, target < 500 MB, no model weights baked in —
  `docker build && docker run -p 8000:8000 --env-file .env.example`.
- **Secrets:** environment variables only. `.env.example` lists variable *names* only; `.gitignore` /
  `.dockerignore` exclude `.env`.
- **Stateless:** no DB, no shared memory between requests — every request is self-contained, which is
  what makes the service trivially horizontally scalable and crash-resistant under concurrent judge
  calls.

---

## 10. Observability

`prometheus-fastapi-instrumentator` exposes `/metrics` from inside `main.py`. The pre-existing
`docker-compose.yaml` brings up `app` + `prometheus` + `grafana` on a private network for local
development, with an auto-provisioned FastAPI dashboard. This is a quality/engineering signal
(tie-breaker #5) and is explicitly **not** on the judge's required scoring path — `/analyze-ticket`
latency is unaffected whether or not the stack is running.

---

## 11. Testing Strategy

| Test file | Covers |
|---|---|
| `test_health.py` | `/health` shape & speed |
| `test_schema_contract.py` | Required fields, enum exactness, type correctness |
| `test_reasoning.py` | Matching, verdict, classification, routing against worked cases |
| `test_safety.py` | S1/S2/S3 never violated; injection neutralized |
| `test_robustness.py` | Malformed / empty / multilingual input → correct status codes, no crash |

All tests run against the live FastAPI app via `httpx.TestClient`, so they exercise the real pipeline
end-to-end rather than mocking engine internals.

---

## 12. Known Limitations

- Calibration against the official `SUST_Preli_Sample_Cases.json` is pending publication; thresholds
  are currently tuned against the one worked example in the problem statement plus 10 hand-authored
  fixtures.
- Bangla/Banglish coverage is synonym-table based, not tokenization-based — genuinely complex Bangla
  phrasing may fall through to `insufficient_data` rather than guess (intentional, triggers human
  review).
- LLM output is non-deterministic when enabled; schema, enums, and safety guarantees are unaffected
  because output is always re-validated and re-sanitized.
- No persistence, no auth, no real payment integration, no GPU — all out of scope by design (§12 of
  the problem statement).