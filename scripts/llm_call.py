#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm_call — OPTIONAL helper: ask Claude one plain question from a script.

Order of attempts
-----------------
1. The Anthropic API, if the environment variable ``ANTHROPIC_API_KEY`` is set
   (you pay per use from your own API credit).
2. Otherwise (no key, no credit, no network) the ``claude -p`` command, which
   uses your normal Claude Code login.

Set ``LLM_CALL_API=0`` to skip step 1. Set ``LLM_CALL_LOG`` to a file path to
get one JSON line per call (which path was used, token counts).

This is for plain text in, text out. A job that needs tools, files or skills
should call ``claude -p`` itself. Stdlib only; nothing here is required by
the rest of the toolkit.

    from llm_call import complete
    print(complete("Summarize in one sentence: ...", max_tokens=200))
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_MODEL = "claude-haiku-5-5"
API_URL = "https://api.anthropic.com/v1/messages"


class LLMCallError(RuntimeError):
    """Every enabled path failed."""


def _http_post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _run_cli(prompt: str, model: str, timeout: float) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise LLMCallError("claude command not found")
    p = subprocess.run([exe, "-p", prompt, "--model", model], capture_output=True,
                       text=True, timeout=timeout, encoding="utf-8", errors="replace")
    out = (p.stdout or "").strip()
    if p.returncode != 0 or not out:
        raise LLMCallError(f"claude -p failed (exit {p.returncode})")
    return out


def _log(row: dict) -> None:
    path = os.environ.get("LLM_CALL_LOG", "").strip()
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}) + "\n")
    except OSError:
        pass


def complete(prompt: str, model: str = DEFAULT_MODEL, max_tokens: int = 1024,
             system: Optional[str] = None, timeout: float = 120,
             allow_cli: bool = True) -> str:
    """Return the answer text. Raises LLMCallError if every path fails."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    use_api = os.environ.get("LLM_CALL_API", "1").strip().lower() not in ("0", "false", "no", "off")
    err = "LLM_CALL_API=0" if not use_api else ("ANTHROPIC_API_KEY not set" if not key else "")
    if use_api and key:
        body = {"model": model, "max_tokens": max_tokens,
                "thinking": {"type": "disabled"},
                "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        try:
            r = _http_post(API_URL, {"x-api-key": key, "anthropic-version": "2023-06-01",
                                     "content-type": "application/json"}, body, timeout)
            text = "".join(b.get("text", "") for b in r.get("content", [])
                           if b.get("type") == "text").strip()
            if text:
                u = r.get("usage") or {}
                _log({"path": "api", "model": model, "in": u.get("input_tokens", 0),
                      "out": u.get("output_tokens", 0)})
                return text
            err = "empty API answer"
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
        except Exception as e:  # network, timeout, bad JSON
            err = type(e).__name__
    if not allow_cli:
        raise LLMCallError(f"API path failed and claude -p is disabled: {err}")
    prompt_cli = f"{system}\n\n{prompt}" if system else prompt
    try:
        text = _run_cli(prompt_cli, model, timeout)
    except Exception as e:
        raise LLMCallError(f"all paths failed ({err}; {e})") from e
    _log({"path": "cli", "model": model, "api_error": err})
    return text


if __name__ == "__main__":
    import sys
    print(complete(" ".join(sys.argv[1:]) or "reply with exactly: PONG", max_tokens=50))
