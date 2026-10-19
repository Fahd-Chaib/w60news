"""Free open-source LLM router (OpenAI-compatible APIs: Groq, Cerebras, ...).

Providers from config.yaml are tried in order. A rate-limited (429) or failing
provider hands over to the next one, so the bot keeps working on free tiers.
"""
from __future__ import annotations

import json
import logging
import re
import time

import requests

from .config import env

log = logging.getLogger("newsbot.llm")


def _extract_json(text: str):
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    text = text[min(starts):] if starts else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # tolerate trailing chatter after the JSON object
        depth, end = 0, None
        for i, ch in enumerate(text):
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end:
            return json.loads(text[:end])
        raise


def _call(provider: dict, cfg, system: str, prompt: str, max_tokens: int, extras: bool):
    key = env(provider["key_env"])
    if not key:
        raise PermissionError(f"{provider['key_env']} not set")
    body = {
        "model": provider["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }
    if extras:
        body["response_format"] = {"type": "json_object"}
        if cfg.get_path("llm.reasoning_effort"):
            body["reasoning_effort"] = cfg.get_path("llm.reasoning_effort")
    r = requests.post(f"{provider['base_url'].rstrip('/')}/chat/completions", json=body, timeout=180,
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    if r.status_code == 429:
        wait = float(r.headers.get("retry-after", "0") or 0)
        raise TimeoutError(f"rate limited (retry-after {wait:.0f}s)")
    if r.status_code == 400 and extras:
        raise ValueError(r.text[:300])  # parameter not supported → retry without extras
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"].get("content") or ""
    usage = data.get("usage", {})
    log.info("LLM %s/%s : %s tokens", provider["name"], provider["model"], usage.get("total_tokens", "?"))
    return content


def ask_json(cfg, system: str, prompt: str, max_tokens: int = 4000, retries: int = 2):
    providers = cfg.get_path("llm.providers", [])
    errors = []
    for attempt in range(retries):
        for p in providers:
            for extras in (True, False):
                try:
                    return _extract_json(_call(p, cfg, system, prompt, max_tokens, extras))
                except ValueError as exc:  # unsupported params or bad JSON → try plain mode
                    errors.append(f"{p['name']}: {exc}")
                    continue
                except PermissionError as exc:
                    errors.append(f"{p['name']}: {exc}")
                    break
                except (TimeoutError, requests.RequestException, KeyError) as exc:
                    errors.append(f"{p['name']}: {exc}")
                    log.warning("LLM %s unavailable (%s) — trying next provider", p["name"], exc)
                    break
        time.sleep(20 * (attempt + 1))
    raise RuntimeError("No LLM provider answered: " + " | ".join(errors[-6:]))
