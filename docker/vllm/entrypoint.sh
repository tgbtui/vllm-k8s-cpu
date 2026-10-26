#!/usr/bin/env bash
# All settings come from the ConfigMap (env). Secrets: VLLM_API_KEY (read by vLLM from env,
# so it never appears in `ps`), HF_TOKEN is NOT needed here (weights are fetched by the initContainer).
set -euo pipefail

: "${MODEL_DIR:?}" "${SERVED_MODEL_NAME:?}"
: "${VLLM_API_KEY:?API token must come from the k8s Secret}"

args=(
  serve "${MODEL_DIR}"
  --served-model-name "${SERVED_MODEL_NAME}"
  --host 0.0.0.0 --port "${PORT:-8000}"
  --dtype "${DTYPE:-bfloat16}"
  --max-model-len "${MAX_MODEL_LEN:-4096}"
  --max-num-seqs "${MAX_NUM_SEQS:-16}"
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS:-2048}"
)
[[ -n "${QUANTIZATION:-}" ]] && args+=(--quantization "${QUANTIZATION}")
[[ "${ENABLE_PREFIX_CACHING:-false}" == "true" ]] && args+=(--enable-prefix-caching)
# Never pass --enable-log-requests: it logs prompts. (Filter redacts anyway.)
# shellcheck disable=SC2206
[[ -n "${EXTRA_ARGS:-}" ]] && args+=(${EXTRA_ARGS})

# tcmalloc speeds up CPU inference (path depends on arch: x86_64 / aarch64)
tc="/usr/lib/$(uname -m)-linux-gnu/libtcmalloc_minimal.so.4"
[[ -f "$tc" ]] && export LD_PRELOAD="$tc${LD_PRELOAD:+:$LD_PRELOAD}"

exec vllm "${args[@]}"
