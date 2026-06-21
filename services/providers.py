"""AI provider adapters: load registry, parse strict-JSON into ProviderSignal,
call a provider with retry/HOLD fallback, and build real clients."""
from __future__ import annotations
import json
import re
import time
from pathlib import Path
from typing import Optional
from core.models import ProviderSignal, SignalType

_PROVIDERS_PATH = Path(__file__).resolve().parent.parent / "providers.json"


def load_providers() -> list[dict]:
    return json.loads(_PROVIDERS_PATH.read_text())["providers"]


def parse_signal(text: str, provider: str) -> Optional[ProviderSignal]:
    """Parse the first JSON object in text into a ProviderSignal. None on failure."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        d = json.loads(match.group(0))
        return ProviderSignal(
            provider=provider,
            signal=SignalType(d["signal"].upper()),
            confidence=int(d.get("confidence", 0)),
            entry=d.get("entry"), stop_loss=d.get("stop_loss"),
            target=d.get("target"),
            risk_reward_ratio=d.get("risk_reward_ratio"),
            reasoning=str(d.get("reasoning", "")),
            error=False)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def call_provider(spec: dict, prompt: str, client) -> ProviderSignal:
    """client(prompt) -> str. Parse -> retry once -> HOLD fallback. Never raises."""
    name = spec["name"]
    start = time.time()
    last_err = ""
    for _attempt in range(2):
        try:
            text = client(prompt)
            sig = parse_signal(text, provider=name)
            if sig is not None:
                sig.latency_ms = int((time.time() - start) * 1000)
                return sig
            last_err = "unparseable response"
        except Exception as e:                 # noqa: BLE001
            last_err = str(e)
    return ProviderSignal(
        provider=name, signal=SignalType.HOLD, confidence=0,
        entry=None, stop_loss=None, target=None, risk_reward_ratio=None,
        reasoning=f"parse/api error: {last_err}", error=True,
        latency_ms=int((time.time() - start) * 1000))


def make_client(spec: dict, api_key: str, _openai_cls=None, _anthropic_cls=None):
    """Return client(prompt)->str for a real provider. SDK classes injectable for tests."""
    kind = spec.get("kind", "openai")
    model = spec["model"]
    if kind == "anthropic":
        if _anthropic_cls is None:
            from anthropic import Anthropic as _anthropic_cls   # noqa: N806
        sdk = _anthropic_cls(api_key=api_key)

        def call(prompt: str) -> str:
            resp = sdk.messages.create(
                model=model, max_tokens=512,
                messages=[{"role": "user", "content": prompt}])
            return resp.content[0].text
        return call

    if _openai_cls is None:
        from openai import OpenAI as _openai_cls               # noqa: N806
    sdk = _openai_cls(api_key=api_key, base_url=spec.get("base_url"))

    def call(prompt: str) -> str:
        resp = sdk.chat.completions.create(
            model=model, max_tokens=512,
            messages=[{"role": "user", "content": prompt}])
        return resp.choices[0].message.content
    return call
