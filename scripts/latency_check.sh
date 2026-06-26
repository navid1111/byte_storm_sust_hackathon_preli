#!/usr/bin/env bash
# Latency check for the QueueStorm Investigator /analyze-ticket endpoint.
#
# Hits the endpoint N times with concurrency C using the public sample request
# (samples/sample_input.json), measures per-request latency, and asserts
# p95 < 5000 ms (rubric AC-12).
#
# Usage:
#   # Start uvicorn first (in another shell):
#   uvicorn app.main:app --host 0.0.0.0 --port 8000
#
#   # Then run:
#   ./scripts/latency_check.sh                          # localhost
#   ./scripts/latency_check.sh https://your.host        # any reachable URL
#
# Env overrides:
#   N=100   total requests (default 100)
#   C=10    concurrency     (default 10)
#   WARM=10 warmup requests discarded before measurement (default 10)
#   FILE=samples/sample_input.json   request body (default)

set -u

BASE="${1:-http://localhost:8000}"
N="${N:-100}"
C="${C:-10}"
WARM="${WARM:-10}"
FILE="${FILE:-samples/sample_input.json}"
P95_LIMIT_MS="${P95_LIMIT_MS:-5000}"

if [ ! -f "$FILE" ]; then
  echo "ERROR: request body file not found: $FILE" >&2
  exit 2
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl is required" >&2
  exit 2
fi

# Prefer python3 for percentile computation (more portable than `python`).
PY="${PY:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "ERROR: $PY is required (set PY=python to override)" >&2
  exit 2
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "Target: $BASE"
echo "Sending $WARM warmup + $N measured requests with concurrency $C"
echo

# Warmup (results discarded to avoid cold-start skew)
for _ in $(seq 1 "$WARM"); do
  curl -s -o /dev/null -X POST "$BASE/analyze-ticket" \
    -H "content-type: application/json" --data-binary "@$FILE" || true
done

# Use xargs -P for concurrency; each worker writes its measured ms to a file.
seq 1 "$N" | xargs -n1 -P "$C" -I{} bash -c '
  start=$("'"$PY"'" -c "import time;print(int(time.time()*1000))")
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "'"$BASE"'/analyze-ticket" \
    -H "content-type: application/json" --data-binary "@'"$FILE"'")
  end=$("'"$PY"'" -c "import time;print(int(time.time()*1000))")
  echo "$((end - start)) $code" >> "'"$WORK"'/latencies.txt"
'

# Drop non-2xx (we want to measure real responses, not timeouts)
total=$(wc -l < "$WORK/latencies.txt" | tr -d ' ')
ok=$(awk '$2 ~ /^2/ {n++} END{print n+0}' "$WORK/latencies.txt")
fail=$((total - ok))

if [ "$ok" -eq 0 ]; then
  echo "ERROR: zero successful (2xx) responses out of $total attempts." >&2
  echo "Latency cannot be measured. Check that $BASE/analyze-ticket is reachable." >&2
  exit 3
fi

awk '$2 ~ /^2/ {print $1}' "$WORK/latencies.txt" > "$WORK/ok.txt"

# Compute percentiles using the configured python interpreter.
"$PY" - "$WORK/ok.txt" "$P95_LIMIT_MS" "$ok" "$fail" <<'PY'
import sys, statistics
path, limit, ok, fail = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
with open(path) as f:
    samples = sorted(int(x) for x in f if x.strip())
if not samples:
    print("ERROR: no 2xx samples to measure", file=sys.stderr); sys.exit(3)

def pct(p):
    if not samples: return 0
    k = max(0, min(len(samples)-1, int(round((p/100.0) * (len(samples)-1)))))
    return samples[k]

p50, p95, p99 = pct(50), pct(95), pct(99)
mx = samples[-1]
avg = int(round(statistics.mean(samples)))

print(f"sent={ok+fail}  ok={ok}  fail={fail}")
print(f"p50={p50}ms  p95={p95}ms  p99={p99}ms  max={mx}ms  avg={avg}ms")

if p95 < limit:
    print(f"PASS  p95 ({p95}ms) < {limit}ms")
    sys.exit(0)
else:
    print(f"FAIL  p95 ({p95}ms) >= {limit}ms", file=sys.stderr)
    sys.exit(1)
PY
status=$?

echo
exit $status