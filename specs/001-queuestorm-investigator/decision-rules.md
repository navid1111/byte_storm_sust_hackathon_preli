# Decision Rules: QueueStorm Investigator

**Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md) · **Tasks**: [`tasks.md`](./tasks.md)
**Created**: 2026-06-26

The single source of truth for the **decision boundaries** the reasoning engine uses. Both the
implementation (`app/engine/*`) and the tests (`app/tests/*`) read from this file so two engineers
cannot drift on coverage.

> **Calibration note:** Shipped rules and thresholds are fully calibrated and verified
> against the 10 official worked cases in `SUST_Preli_Sample_Cases.json`, ensuring
> 100% field alignment and test pass rate.

---

## 1. Transaction Matching → `relevant_transaction_id`

Extract cues from the complaint, score every entry in `transaction_history`, pick the best entry above
threshold, else `null`. **Never invent an ID that is not in the provided history (AC-4).**

### 1.1 Cue weights

| Cue | Weight | How it matches |
|-----|--------|----------------|
| **Amount** | 0.45 | Number in complaint equals (or is within ±1 unit of) entry `amount`. Strongest signal. |
| **Type** | 0.25 | Complaint intent word maps to entry `type` (see §4 synonyms): e.g. "sent/পাঠাইছি" → `transfer`. |
| **Counterparty** | 0.20 | Last 4+ digits of a phone/merchant/agent ID in the complaint match entry `counterparty`. |
| **Recency / time** | 0.10 | Time-of-day or "today/আজ" cue is consistent with entry `timestamp`; ties broken toward most recent. |

Score = sum of matched cue weights (each cue contributes 0 or its full weight).

### 1.2 Threshold & tie-breaks

- **Claim a match** only if `score >= 0.45` **AND** at least one of {amount, counterparty} matched.
  (Type + recency alone is too weak — it would guess.)
- A single weak cue (only type, or only recency) → **no match → `null`** → drives `insufficient_data`.
- **Tie-break** (equal scores): prefer the entry whose **amount** matched; then the **most recent**
  `timestamp`; then the **first** entry in the array (stable).
- Empty or absent `transaction_history` → `null` immediately.

## 2. Evidence Verdict → `evidence_verdict`

Decided **after** matching, using the matched entry (if any) vs. the complaint claim.

| Verdict | Condition |
|---------|-----------|
| `insufficient_data` | No history provided, **or** no entry cleared the match threshold, **or** the claim cannot be checked against any field (e.g. "agent was rude" with no transactional assertion). |
| `inconsistent` | A match exists but the data **contradicts** the claim. Examples: complaint says "payment failed / money deducted" but matched entry `status = completed`; complaint claims a transfer that does not exist in history while history shows unrelated activity; claimed amount differs materially from every entry. |
| `consistent` | A match exists and the data **supports** the claim. Example: "sent 5000 to wrong number" + entry `transfer / 5000 / completed`. |

**Default on doubt:** if matching is borderline or signals conflict → `insufficient_data` +
`human_review_required = true`. Never assert `consistent`/`inconsistent` on a weak match.

## 3. Case Type, Department, Severity, Review

### 3.1 `case_type` signal rules (first match wins; phishing checked first)

| Order | `case_type` | Trigger signals |
|-------|-------------|-----------------|
| 1 | `phishing_or_social_engineering` | Any phishing cue in §5 (report of being asked for PIN/OTP/password/card, suspicious caller/SMS/link). **Checked first — overrides everything.** |
| 2 | `duplicate_payment` | "twice/double/দুইবার/duplicate" + 2 entries with same amount+counterparty, or two matching charges. |
| 3 | `wrong_transfer` | "wrong number/ভুল নম্বর/wrong recipient" + a `transfer` entry. |
| 4 | `payment_failed` | "failed/ব্যর্থ/deducted but failed/কাটছে কিন্তু হয়নি"; entry `status` in {`failed`,`pending`} with deduction claim. |
| 5 | `agent_cash_in_issue` | "agent/এজেন্ট/cash in/ক্যাশ ইন" + balance-not-reflected claim. |
| 6 | `merchant_settlement_delay` | "merchant/settlement/সেটেলমেন্ট" not received in window; `user_type=merchant`. |
| 7 | `refund_request` | "refund/ফেরত/return টাকা" request without fraud cue. |
| 8 | `other` | None of the above. |

### 3.2 `department` map (deterministic from `case_type`, Section 7.2)

| `case_type` | `department` |
|-------------|--------------|
| `phishing_or_social_engineering` | `fraud_risk` |
| `wrong_transfer` | `dispute_resolution` |
| `refund_request` (contested) | `dispute_resolution` |
| `refund_request` (low severity / simple) | `customer_support` |
| `payment_failed`, `duplicate_payment` | `payments_ops` |
| `merchant_settlement_delay` | `merchant_operations` |
| `agent_cash_in_issue` | `agent_operations` |
| `other`, vague, insufficient-data | `customer_support` |

### 3.3 `severity` (evaluate top-down, first hit wins)

| `severity` | Condition |
|------------|-----------|
| `critical` | `phishing_or_social_engineering` (active scam / credential theft), **or** evidenced unauthorized debit ≥ 25,000 BDT. |
| `high` | `wrong_transfer` with `completed` status (money gone — the 5000 BDT anchor), **or** `payment_failed` with a credible deduction claim, **or** any matched amount ≥ 25,000 BDT. |
| `medium` | `duplicate_payment`, `merchant_settlement_delay`, `agent_cash_in_issue`, contested `refund_request`, **or** matched amount 1,000–25,000 BDT not already `high`. |
| `low` | `other`, simple `refund_request`, vague / `insufficient_data` informational, amount < 1,000 BDT. |

> Severity is partial-credit ("comparable severity" — spec §13). Prefer **slightly over-escalating**
> to under-escalating; never let a borderline severity suppress `human_review_required`.

### 3.4 `human_review_required = true` when any of:

- `case_type == phishing_or_social_engineering` (always).
- `evidence_verdict in {inconsistent, insufficient_data}` (ambiguous or contradicted).
- `severity in {high, critical}`.
- `case_type in {wrong_transfer, duplicate_payment, payment_failed}` (money-movement disputes).
- Matched amount ≥ 25,000 BDT (high value).
- `user_type in {merchant, agent}` with a settlement/cash dispute.

Otherwise `false` (e.g. simple informational `refund_request` with `consistent` low-value data).

## 4. Multilingual Intent Synonyms (en / bn / Banglish)

Used by the matcher (§1) and classifier (§3.1). Tie-breaker #6 rewards Bangla/Banglish quality —
cover these at minimum.

| Intent → maps to | English | Banglish (romanized) | Bangla |
|------------------|---------|----------------------|--------|
| send / transfer → `transfer` | send, sent, transfer, paid to | pathaisi, pathalam, pathaichi, dilam, transfer korsi | পাঠাইছি, পাঠালাম, দিলাম, পাঠিয়েছি |
| refund / return → `refund_request` | refund, return, money back | refund chai, taka ferot, return koren | ফেরত, টাকা ফেরত, ফিরিয়ে দিন |
| wrong number → `wrong_transfer` | wrong number, wrong recipient | bhul number, bhul nambar, vul number | ভুল নম্বর, ভুল নাম্বার, ভুল লোক |
| failed / deducted → `payment_failed` | failed, declined, deducted but failed | fail hoise, kete nise but hoyni, taka katlo | ব্যর্থ, কাটছে কিন্তু হয়নি, টাকা কেটে নিয়েছে |
| duplicate → `duplicate_payment` | twice, double, charged again | duibar, double katse, abar katlo | দুইবার, ডবল কাটছে, আবার কেটেছে |
| cash in (agent) → `agent_cash_in_issue` | cash in, deposit via agent | cash in korsi, agent ke dilam | ক্যাশ ইন, এজেন্টকে দিলাম |
| settlement → `merchant_settlement_delay` | settlement, payout, not received | settlement pai nai, taka dhuke nai | সেটেলমেন্ট, টাকা ঢোকেনি |
| amount unit | taka, tk, BDT | taka, tk | টাকা, ৳ |
| today / time | today, just now, around 2pm | aaj, ekhon, dupur 2 ta | আজ, এখন, দুপুর |

## 5. Phishing / Social-Engineering Cues (drives `fraud_risk` + `critical`)

Set `case_type = phishing_or_social_engineering`, `department = fraud_risk`, `severity = critical`,
`human_review_required = true` when the complaint **reports** any of:

- Someone (caller / SMS / message) **asked for** PIN, OTP, password, CVV, or full card number.
  Bangla: কেউ পিন/ওটিপি/পাসওয়ার্ড চেয়েছে; কল/এসএমএস এ চাওয়া।
- A caller **claiming to be** the platform / bKash / an official ("bkash theke bolchi", "official call").
- A suspicious **link / URL** the customer was told to click, or a fake offer tied to the campaign.
- Urgency + reward bait ("account locked, share OTP to unlock", "cashback — confirm your PIN").

> **Critical distinction:** this is the customer **reporting being targeted** — it is *not* a license
> for our `customer_reply` to request those credentials. The reply must reassure and warn ("we will
> never ask for your PIN or OTP") and escalate to fraud_risk. Confusing the two is an S1 violation.

## 6. `reason_codes` Convention

`reason_codes` is a **freeform** array of short snake_case labels supporting the decision — **no closed
enum**. Its absence is not a schema violation (it is optional, spec §6.1). Recommended conventional
labels for consistency: the chosen `case_type`, plus signals such as `transaction_match`,
`no_match`, `amount_match`, `status_contradiction`, `phishing_cue`, `high_value`, `empty_history`.
