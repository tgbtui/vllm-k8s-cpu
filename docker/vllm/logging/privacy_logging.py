"""Privacy-preserving logging for vLLM.

Prompts and generated text must never reach stdout/stderr. The fact of a request
(request id, token counts, params size) is still logged.

Wired in via VLLM_LOGGING_CONFIG_PATH -> logging_config.json (handler filter).
"""
import logging
import re

# vLLM RequestLogger messages (vllm/entrypoints/logger.py), e.g.
#   "Received request cmpl-1: prompt: '...', params: ..., prompt_token_ids: [...] ..."
#   "Generated response cmpl-1: output: '...', output_token_ids: [...] ..."
_REQ = re.compile(r"^(?P<verb>Received request|Generated response)\s+(?P<rid>[^\s:]+)")
# Any leftover "key: value" dumps that may carry user text / tokens / embeddings.
_SENSITIVE = re.compile(
    r"(prompt|output|prompt_token_ids|output_token_ids|prompt_embeds|text|content|messages)"
    r"\s*[:=]\s*(\[[^\]]*\]|'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|\S+)",
    re.IGNORECASE,
)
_LEN = re.compile(r"(?:prompt_token_ids|output_token_ids)\s*[:=]\s*\[([^\]]*)\]")


class PrivacyFilter(logging.Filter):
    """Replace request/response dumps with a content-free line; scrub the rest."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # malformed format args -> do not leak raw args
            record.msg, record.args = "<unprintable log record redacted>", None
            return True

        m = _REQ.match(msg)
        if m:
            tokens = _LEN.search(msg)
            n = len([t for t in tokens.group(1).split(",") if t.strip()]) if tokens else None
            what = "request received" if m["verb"] == "Received request" else "response generated"
            msg = f"{what} id={m['rid']}" + (f" tokens={n}" if n is not None else "") + " [content redacted]"
        else:
            msg = _SENSITIVE.sub(lambda s: f"{s.group(1)}=<redacted>", msg)

        record.msg, record.args = msg, None
        return True
