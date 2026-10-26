# syntax=docker/dockerfile:1
# vLLM (CPU-only) >= 0.27.0, rootless, pinned deps, privacy logging.
ARG VLLM_VERSION=0.27.0

############################ builder: compile vLLM CPU wheel ############################
FROM ubuntu:24.04 AS builder
ARG VLLM_VERSION
# arm64 only: force the BF16 ISA at compile time (empty = auto-detect, vLLM default)
ARG VLLM_CPU_ARM_BF16=""
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git curl gcc-12 g++-12 libnuma-dev cmake ninja-build \
        python3 python3-dev python3-venv \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 10 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-12 10 \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "v${VLLM_VERSION}" https://github.com/vllm-project/vllm.git /src
WORKDIR /src
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir -U pip wheel
# Build-requirements path differs between vLLM versions: pick whichever exists in the tag.
RUN f=$(ls requirements/build/cpu.txt requirements/cpu-build.txt 2>/dev/null | head -1) && echo "build reqs: $f" \
 && /venv/bin/pip install --no-cache-dir -r "$f" --extra-index-url https://download.pytorch.org/whl/cpu
# Newer tags ship an optional Rust frontend; build it best-effort if the script exists.
RUN if [ -x tools/build_rust.sh ]; then \
      apt-get update && apt-get install -y --no-install-recommends cargo rustc \
      && (PATH=/venv/bin:$PATH tools/build_rust.sh || echo "WARN: rust frontend build skipped"); \
    fi
RUN if [ -n "${VLLM_CPU_ARM_BF16}" ]; then export VLLM_CPU_ARM_BF16; fi; \
    VLLM_TARGET_DEVICE=cpu /venv/bin/python setup.py bdist_wheel --dist-dir=/wheels

############################ runtime ############################
FROM ubuntu:24.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnuma1 libtcmalloc-minimal4 python3 python3-venv python3-dev g++ \
    && rm -rf /var/lib/apt/lists/*

# Reproducibility: every Python dependency (incl. transitive) pinned + hashed.
COPY docker/vllm/requirements.txt /tmp/requirements.txt
RUN grep -q -- '--hash=' /tmp/requirements.txt || \
    { echo "requirements.txt is not locked. Run scripts/lock-requirements.sh first." >&2; exit 1; }
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -U pip==25.2 \
 && /opt/venv/bin/pip install --no-cache-dir --require-hashes --no-deps \
        --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.txt
COPY --from=builder /wheels /wheels
RUN /opt/venv/bin/pip install --no-cache-dir --no-deps /wheels/vllm-*.whl && rm -rf /wheels /tmp/requirements.txt

# Privacy logging + entrypoint
COPY docker/vllm/logging/ /opt/vllm-privacy/
COPY docker/vllm/entrypoint.sh /usr/local/bin/entrypoint.sh

# Rootless: unprivileged user, fixed UID/GID
RUN groupadd -g 10001 vllm && useradd -u 10001 -g 10001 -m -s /usr/sbin/nologin vllm \
 && chmod 0755 /usr/local/bin/entrypoint.sh
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/opt/vllm-privacy \
    VLLM_LOGGING_CONFIG_PATH=/opt/vllm-privacy/logging_config.json \
    VLLM_CONFIGURE_LOGGING=1 \
    VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1 \
    HF_HUB_OFFLINE=1 \
    VLLM_CACHE_ROOT=/tmp/vllm-cache HOME=/home/vllm
USER 10001:10001
WORKDIR /home/vllm
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
