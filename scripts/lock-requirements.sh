#!/usr/bin/env bash
# Resolve ALL vLLM CPU dependencies (incl. transitive) for the pinned tag into a hashed requirements.txt.
set -euo pipefail
VLLM_VERSION="${VLLM_VERSION:-0.27.0}"
OUT="$(cd "$(dirname "$0")/.." && pwd)/docker/vllm/requirements.txt"
docker run --rm -v "$(dirname "$OUT"):/out" -e VLLM_VERSION="$VLLM_VERSION" ubuntu:24.04 bash -euc '
  apt-get update -qq && apt-get install -y -qq git python3 python3-venv ca-certificates >/dev/null
  python3 -m venv /t && /t/bin/pip install -q uv
  git clone -q --depth 1 --branch "v${VLLM_VERSION}" https://github.com/vllm-project/vllm.git /src
  cd /src
  /t/bin/uv pip compile requirements/cpu.txt --generate-hashes --python-version 3.12 \
      --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match \
      -o /out/requirements.txt
'
echo "Locked -> $OUT"
