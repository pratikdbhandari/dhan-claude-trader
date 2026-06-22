"""Settings 'Test All' self-checks: Dhan (read-only), AI providers (tiny ping),
and data sources (yfinance + news). Returns ✓/✗ Check rows. Pure-ish: all external
callers are injectable for tests."""
from __future__ import annotations
from services.connectivity import Check, run_checks, _run


def test_dhan(client, equity_instr, index_instr=None) -> list[Check]:
    return run_checks(client, equity_instr=equity_instr, index_instr=index_instr)


def test_providers(provider_specs: list[dict], key_lookup,
                   client_factory=None) -> list[Check]:
    """Ping each enabled provider that has a key. key_lookup(env_name)->str|None.
    client_factory(spec, api_key)->callable(prompt)->str (defaults to real make_client)."""
    from services.providers import make_client, call_provider
    factory = client_factory or make_client
    out: list[Check] = []
    for spec in provider_specs:
        if not spec.get("enabled", True):
            continue
        key = key_lookup(spec.get("key_env", ""))
        if not key:
            out.append(Check(f"AI {spec['name']}", "SKIP", "no key set"))
            continue

        def _do(spec=spec, key=key):
            client = factory(spec, key)
            sig = call_provider(spec, 'Reply with JSON {"signal":"HOLD","confidence":0,'
                                '"reasoning":"ping"}', client=client)
            return (not sig.error), ("responded" if not sig.error else sig.reasoning)
        out.append(_run(f"AI {spec['name']}", _do))
    return out


def test_data_sources(*, ticker_factory=None, news_fetch=None) -> list[Check]:
    out: list[Check] = []

    def _yf():
        from services.fundamentals import get_fundamentals
        d = get_fundamentals("RELIANCE", ticker_factory=ticker_factory)
        return (isinstance(d, dict)), f"fundamentals keys={list(d.keys())}"
    out.append(_run("yfinance fundamentals", _yf))

    def _news():
        from services import news
        h = news.get_headlines("NIFTY", fetch=news_fetch)
        return (isinstance(h, list)), f"{len(h)} headlines"
    out.append(_run("news RSS", _news))
    return out
