import services.selftest as selftest
from services.connectivity import Check


def test_providers_skips_when_no_key():
    specs = [{"name": "groq", "key_env": "GROQ_API_KEY", "enabled": True,
              "kind": "openai", "model": "m"}]
    rows = selftest.test_providers(specs, key_lookup=lambda e: None)
    assert rows[0].status == "SKIP"


def test_providers_pings_with_fake_factory():
    specs = [{"name": "groq", "key_env": "GROQ_API_KEY", "enabled": True,
              "kind": "openai", "model": "m"}]

    def fake_factory(spec, api_key):
        return lambda prompt: '{"signal":"HOLD","confidence":0,"reasoning":"ping"}'
    rows = selftest.test_providers(specs, key_lookup=lambda e: "key",
                          client_factory=fake_factory)
    assert rows[0].status == "PASS"


def test_providers_reports_failure():
    specs = [{"name": "groq", "key_env": "GROQ_API_KEY", "enabled": True,
              "kind": "openai", "model": "m"}]

    def boom_factory(spec, api_key):
        def c(prompt):
            raise RuntimeError("401")
        return c
    rows = selftest.test_providers(specs, key_lookup=lambda e: "key",
                          client_factory=boom_factory)
    assert rows[0].status == "FAIL"


def test_data_sources_with_fakes():
    class FakeTicker:
        info = {"trailingPE": 20}
    rows = selftest.test_data_sources(ticker_factory=lambda s: FakeTicker(),
                             news_fetch=lambda url: "<rss><channel></channel></rss>")
    assert all(isinstance(r, Check) for r in rows)
    assert {r.name for r in rows} == {"yfinance fundamentals", "news RSS"}
    assert all(r.status == "PASS" for r in rows)
