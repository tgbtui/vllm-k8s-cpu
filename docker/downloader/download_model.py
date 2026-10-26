#!/usr/bin/env python3
"""Download a Hugging Face model snapshot into MODEL_DIR (a PVC). Stdlib only.

Idempotent: if MODEL_DIR/.download_complete exists, exits immediately without any network access.
Env: MODEL_ID (required), MODEL_DIR (required), HF_TOKEN (optional), HF_REVISION (default main).
"""
import json, os, sys, urllib.request, urllib.parse

MODEL_ID = os.environ["MODEL_ID"]
MODEL_DIR = os.environ["MODEL_DIR"]
REV = os.environ.get("HF_REVISION", "main")
TOKEN = os.environ.get("HF_TOKEN", "")
HUB = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
MARKER = os.path.join(MODEL_DIR, ".download_complete")


def req(url):
    r = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})
    return urllib.request.urlopen(r, timeout=60)


def main():
    if os.path.exists(MARKER):
        print(f"[download] {MODEL_ID} already cached in {MODEL_DIR}; skipping network.")
        return
    os.makedirs(MODEL_DIR, exist_ok=True)
    with req(f"{HUB}/api/models/{MODEL_ID}/revision/{urllib.parse.quote(REV, safe='')}") as r:
        files = [s["rfilename"] for s in json.load(r)["siblings"]]
    # skip non-inference artifacts
    files = [f for f in files if not f.startswith(("onnx/", "original/")) and not f.endswith((".gguf", ".h5", ".msgpack", ".ot"))]
    for name in files:
        dst = os.path.join(MODEL_DIR, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        url = f"{HUB}/{MODEL_ID}/resolve/{urllib.parse.quote(REV, safe='')}/{urllib.parse.quote(name)}"
        print(f"[download] {name}", flush=True)
        with req(url) as r, open(dst + ".part", "wb") as f:
            while chunk := r.read(8 << 20):
                f.write(chunk)
        os.replace(dst + ".part", dst)
    open(MARKER, "w").write(f"{MODEL_ID}@{REV}\n")
    print("[download] done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never print the token
        print(f"[download] FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
