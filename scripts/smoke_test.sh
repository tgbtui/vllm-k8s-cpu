#!/usr/bin/env bash
set -uo pipefail
URL="${URL:-http://localhost:8000}"; NS="${NS:-vllm}"; MODEL="${MODEL:-qwen2.5-1.5b-instruct}"
: "${KEY:?set KEY=<VLLM_API_KEY>}"
CANARY="CANARY-$RANDOM-SECRET-PROMPT"
ok(){ echo "PASS: $1"; }; bad(){ echo "FAIL: $1"; FAILED=1; }; FAILED=0
body="{\"model\":\"$MODEL\",\"max_tokens\":16,\"messages\":[{\"role\":\"user\",\"content\":\"$CANARY say hi\"}]}"
[[ $(curl -s -o /dev/null -w '%{http_code}' $URL/health) == 200 ]] && ok "health 200" || bad "health"
[[ $(curl -s -o /dev/null -w '%{http_code}' $URL/v1/chat/completions -H 'Content-Type: application/json' -d "$body") == 401 ]] && ok "no token -> 401" || bad "no token must be 401"
resp=$(curl -s $URL/v1/chat/completions -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "$body")
echo "$resp" | grep -q '"choices"' && ok "with token -> completion" || bad "completion: $resp"
sleep 2
logs=$(kubectl -n $NS logs deploy/vllm -c vllm 2>&1)
grep -q "$CANARY" <<<"$logs" && bad "PROMPT LEAKED into logs" || ok "prompt not in logs"
grep -qi "redacted\|POST /v1/chat/completions" <<<"$logs" && ok "request fact is logged" || bad "no request log"
kubectl -n $NS rollout restart deploy/vllm >/dev/null && kubectl -n $NS rollout status deploy/vllm --timeout=15m >/dev/null
kubectl -n $NS logs deploy/vllm -c model-downloader 2>&1 | grep -q "already cached" && ok "restart: model taken from PVC, no download" || bad "restart did re-download"
exit $FAILED
