import json, logging, os, sys, io, logging.config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "docker", "vllm", "logging"))
cfgp = os.path.join(os.path.dirname(__file__), "..", "docker", "vllm", "logging", "logging_config.json")

def test_no_prompt_or_response_leak():
    cfg = json.load(open(cfgp)); cfg["handlers"]["stdout"]["stream"] = (buf := io.StringIO())
    logging.config.dictConfig(cfg)
    log = logging.getLogger("vllm.entrypoints.logger")
    log.info("Received request %s: prompt: %r, params: %s, prompt_token_ids: %s, prompt_embeds shape: %s, lora_request: %s.",
             "cmpl-1", "MY SECRET PROMPT", "SamplingParams(n=1)", [1, 2, 3], None, None)
    log.info("Generated response %s%s: output: %r, output_token_ids: %s, finish_reason: %s",
             "cmpl-1", "", "SECRET ANSWER", [4, 5], "stop")
    logging.getLogger("vllm.other").warning("debug dump messages=[{'content': 'SECRET'}] text='SECRET'")
    out = buf.getvalue()
    assert "SECRET" not in out
    assert "request received id=cmpl-1 tokens=3" in out and "response generated id=cmpl-1 tokens=2" in out
