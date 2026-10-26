#!/usr/bin/env python3
"""Load test for OpenAI-compatible vLLM endpoint (stdlib only).
Measures TTFT, end-to-end latency, throughput for short/long prompts. Prints a Markdown table.

  python scripts/loadtest.py --url http://localhost:8000 --api-key $KEY --model qwen2.5-1.5b-instruct \
      --concurrency 4 --requests 16
"""
import argparse, http.client, json, statistics as st, threading, time, urllib.parse

def one(u, key, model, prompt, max_tokens):
    c = (http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection)(u.netloc, timeout=900)
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens,
                       "temperature": 0, "stream": True, "stream_options": {"include_usage": True}})
    t0 = time.perf_counter(); ttft = None; toks = 0
    c.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    r = c.getresponse()
    if r.status != 200:
        raise RuntimeError(f"HTTP {r.status}")
    for line in r:
        if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
            continue
        d = json.loads(line[6:])
        if d.get("choices") and d["choices"][0]["delta"].get("content") and ttft is None:
            ttft = time.perf_counter() - t0
        if d.get("usage"):
            toks = d["usage"]["completion_tokens"]
    return ttft or 0.0, time.perf_counter() - t0, toks

def run(args, name, prompt):
    u = urllib.parse.urlparse(args.url); res, err = [], 0
    q = list(range(args.requests)); lock = threading.Lock()
    def worker():
        nonlocal err
        while True:
            with lock:
                if not q: return
                q.pop()
            try: res.append(one(u, args.api_key, args.model, prompt, args.max_tokens))
            except Exception: err += 1
    t0 = time.perf_counter()
    ts = [threading.Thread(target=worker) for _ in range(args.concurrency)]
    [t.start() for t in ts]; [t.join() for t in ts]
    wall = time.perf_counter() - t0
    p = lambda xs, k: sorted(xs)[min(len(xs) - 1, int(len(xs) * k))] if xs else 0
    tt, lat = [r[0] for r in res], [r[1] for r in res]
    return (f"| {name} | {args.concurrency} | {len(res)}/{err} | {st.mean(tt) if tt else 0:.2f} | {p(tt,.95):.2f} | "
            f"{st.mean(lat) if lat else 0:.2f} | {p(lat,.95):.2f} | {sum(r[2] for r in res)/wall:.1f} | {len(res)/wall:.2f} |")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000"); ap.add_argument("--api-key", required=True)
    ap.add_argument("--model", default="qwen2.5-1.5b-instruct")
    ap.add_argument("--concurrency", type=int, default=4); ap.add_argument("--requests", type=int, default=16)
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--long-words", type=int, default=1500, help="approx size of the long prompt (words)")
    a = ap.parse_args()
    short = "Explain in two sentences what Kubernetes is."
    long_ = "Summarize the following text in one sentence.\n" + " ".join(f"word{i % 97}" for i in range(a.long_words))
    print("| prompt | conc | ok/err | TTFT avg, s | TTFT p95, s | latency avg, s | latency p95, s | throughput, tok/s | req/s |")
    print("|---|---|---|---|---|---|---|---|---|")
    print(run(a, "short (~12 tok)", short)); print(run(a, f"long (~{a.long_words*2} tok)", long_))
