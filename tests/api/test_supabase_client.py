from api.supabase_client import list_push_tokens, register_push_token


class FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


def test_register_push_token_upserts_via_post(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return FakeResponse()

    register_push_token("user-1", "device-token-abc", post=fake_post)
    assert len(calls) == 1
    url, payload, headers = calls[0]
    assert url == "https://project.supabase.co/rest/v1/push_tokens"
    assert payload == {"user_id": "user-1", "token": "device-token-abc"}
    assert headers["Prefer"] == "resolution=merge-duplicates"
    assert headers["apikey"] == "service-key"


def test_list_push_tokens_returns_token_list(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")

    def fake_get(url, headers, timeout):
        assert url == "https://project.supabase.co/rest/v1/push_tokens?select=token"
        return FakeResponse(json_data=[{"token": "t1"}, {"token": "t2"}])

    tokens = list_push_tokens(get=fake_get)
    assert tokens == ["t1", "t2"]


def test_list_push_tokens_returns_empty_list_when_no_rows(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    tokens = list_push_tokens(get=lambda url, headers, timeout: FakeResponse(json_data=[]))
    assert tokens == []
