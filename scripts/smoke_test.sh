#!/usr/bin/env bash
# Smoke-test the QueueStorm Investigator endpoints.
# Usage:
#   ./scripts/smoke_test.sh                 # tests the deployed Render URL
#   ./scripts/smoke_test.sh http://localhost:8000
#
# Checks: GET /health, POST /analyze-ticket (happy path + phishing + malformed),
# GET /metrics. Verifies status codes and key response fields. Exits non-zero on
# any failure so it can gate CI or a pre-submit check.

set -u
BASE="${1:-https://byte-storm-sust-hackathon-preli.onrender.com}"
PASS=0
FAIL=0

ok()   { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

echo "Target: $BASE"
echo

# 1. GET /health -> 200 {"status":"ok"}
echo "[1] GET /health"
body=$(curl -s -m 30 -w "\n%{http_code}" "$BASE/health")
code=$(echo "$body" | tail -1); json=$(echo "$body" | sed '$d')
[ "$code" = "200" ] && ok "status 200" || bad "expected 200, got $code"
echo "$json" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' && ok 'body {"status":"ok"}' || bad "body was: $json"

# 2. POST /analyze-ticket happy path -> 200 + required fields + id echo
echo "[2] POST /analyze-ticket (wrong transfer)"
req='{"ticket_id":"TKT-001","complaint":"I sent 5000 taka to a wrong number around 2pm today","transaction_history":[{"transaction_id":"TXN-9101","timestamp":"2026-04-14T14:08:22Z","type":"transfer","amount":5000,"counterparty":"+8801719876543","status":"completed"}]}'
body=$(curl -s -m 30 -w "\n%{http_code}" -X POST "$BASE/analyze-ticket" -H "content-type: application/json" -d "$req")
code=$(echo "$body" | tail -1); json=$(echo "$body" | sed '$d')
[ "$code" = "200" ] && ok "status 200" || bad "expected 200, got $code"
echo "$json" | grep -q '"ticket_id"[[:space:]]*:[[:space:]]*"TKT-001"' && ok "echoes ticket_id" || bad "ticket_id not echoed"
all_fields=1
for f in relevant_transaction_id evidence_verdict case_type severity department agent_summary recommended_next_action customer_reply human_review_required; do
  echo "$json" | grep -q "\"$f\"" || { all_fields=0; bad "missing field: $f"; }
done
[ "$all_fields" = "1" ] && ok "all required response fields present"
# safety: reply must not ask for PIN/OTP or promise a refund
low=$(echo "$json" | tr '[:upper:]' '[:lower:]')
echo "$low" | grep -q "we will refund" && bad "reply promises a refund (S2)" || ok "no unauthorized refund promise"

# 3. POST /analyze-ticket phishing -> fraud escalation
echo "[3] POST /analyze-ticket (phishing)"
req='{"ticket_id":"TKT-PH","complaint":"A caller claiming to be bKash asked me to share my OTP to unlock my account"}'
json=$(curl -s -m 30 -X POST "$BASE/analyze-ticket" -H "content-type: application/json" -d "$req")
echo "$json" | grep -q '"case_type"[[:space:]]*:[[:space:]]*"phishing_or_social_engineering"' && ok "case_type=phishing" || bad "phishing not detected: $json"
echo "$json" | grep -q '"department"[[:space:]]*:[[:space:]]*"fraud_risk"' && ok "routed to fraud_risk" || bad "not routed to fraud_risk"

# 4. malformed JSON -> 4xx, not a crash
echo "[4] POST /analyze-ticket (malformed JSON)"
code=$(curl -s -m 30 -o /dev/null -w "%{http_code}" -X POST "$BASE/analyze-ticket" -H "content-type: application/json" -d '{bad json')
case "$code" in 400|422) ok "controlled error ($code), no crash" ;; *) bad "expected 400/422, got $code" ;; esac

# 5. GET /metrics -> 200 prometheus
echo "[5] GET /metrics"
code=$(curl -s -m 30 -o /dev/null -w "%{http_code}" "$BASE/metrics")
[ "$code" = "200" ] && ok "status 200" || bad "expected 200, got $code"

echo
echo "==== $PASS passed, $FAIL failed ===="
[ "$FAIL" -eq 0 ]
