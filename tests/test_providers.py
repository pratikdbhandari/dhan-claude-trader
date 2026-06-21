from services.providers import parse_signal, load_providers, call_provider, make_client
from core.models import ProviderSignal, SignalType


def test_parse_valid_json():
    txt = ('{"signal":"BUY","confidence":72,"entry":100,"stop_loss":98,'
           '"target":104,"reasoning":"trend up","risk_reward_ratio":2.0}')
    sig = parse_signal(txt, provider="groq")
    assert isinstance(sig, ProviderSignal)
    assert sig.signal is SignalType.BUY and sig.confidence == 72
    assert sig.error is False and sig.provider == "groq"


def test_parse_json_embedded_in_text():
    txt = 'Here you go: {"signal":"SELL","confidence":60,"reasoning":"weak"} thanks'
    sig = parse_signal(txt, provider="claude")
    assert sig.signal is SignalType.SELL and sig.error is False


def test_parse_garbage_returns_none():
    assert parse_signal("not json at all", provider="x") is None


def test_load_providers_returns_list():
    provs = load_providers()
    names = {p["name"] for p in provs}
    assert {"claude", "groq", "cerebras", "mistral"}.issubset(names)


_SPEC = {"name": "groq", "model": "m"}


def test_call_provider_success():
    client = lambda prompt: '{"signal":"BUY","confidence":80,"reasoning":"ok"}'
    sig = call_provider(_SPEC, "p", client=client)
    assert sig.signal is SignalType.BUY and sig.error is False
    assert sig.latency_ms is not None


def test_call_provider_retries_then_holds():
    calls = {"n": 0}

    def flaky(prompt):
        calls["n"] += 1
        return "garbage"
    sig = call_provider(_SPEC, "p", client=flaky)
    assert sig.signal is SignalType.HOLD and sig.error is True
    assert calls["n"] == 2


def test_call_provider_exception_holds():
    def boom(prompt):
        raise RuntimeError("api 500")
    sig = call_provider(_SPEC, "p", client=boom)
    assert sig.signal is SignalType.HOLD and sig.error is True
    assert "api 500" in sig.reasoning


def test_make_client_openai_kind_uses_base_url():
    captured = {}

    class FakeOpenAI:
        def __init__(self, api_key, base_url):
            captured["base_url"] = base_url

        class chat:  # noqa
            pass
    spec = {"name": "groq", "kind": "openai", "model": "m",
            "base_url": "https://api.groq.com/openai/v1"}
    client = make_client(spec, api_key="k", _openai_cls=FakeOpenAI)
    assert callable(client)
    assert captured["base_url"] == "https://api.groq.com/openai/v1"


def test_make_client_anthropic_kind():
    captured = {}

    class FakeAnthropic:
        def __init__(self, api_key):
            captured["ok"] = True
    spec = {"name": "claude", "kind": "anthropic", "model": "m", "base_url": None}
    client = make_client(spec, api_key="k", _anthropic_cls=FakeAnthropic)
    assert callable(client) and captured["ok"] is True
