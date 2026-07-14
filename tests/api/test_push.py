from api.push import send_push


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_send_push_returns_true_on_success(monkeypatch):
    monkeypatch.setenv("FCM_PROJECT_ID", "test-project")
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return FakeResponse(200)

    result = send_push("device-token", "title", "body", data={"pending_id": "abc"},
                       get_access_token=lambda: "fake-access-token", post=fake_post)
    assert result is True
    assert len(calls) == 1
    url, payload, headers = calls[0]
    assert url == "https://fcm.googleapis.com/v1/projects/test-project/messages:send"
    assert payload["message"]["token"] == "device-token"
    assert payload["message"]["notification"] == {"title": "title", "body": "body"}
    assert payload["message"]["data"] == {"pending_id": "abc"}
    assert headers["Authorization"] == "Bearer fake-access-token"


def test_send_push_returns_false_on_http_error(monkeypatch):
    monkeypatch.setenv("FCM_PROJECT_ID", "test-project")

    def fake_post(url, json, headers, timeout):
        return FakeResponse(500)

    result = send_push("device-token", "title", "body",
                       get_access_token=lambda: "fake-access-token", post=fake_post)
    assert result is False


def test_send_push_returns_false_when_project_id_missing(monkeypatch):
    monkeypatch.delenv("FCM_PROJECT_ID", raising=False)
    result = send_push("device-token", "title", "body",
                       get_access_token=lambda: "fake-access-token", post=lambda **kw: None)
    assert result is False


def test_send_push_returns_false_when_token_fetch_raises(monkeypatch):
    monkeypatch.setenv("FCM_PROJECT_ID", "test-project")

    def raising_get_token():
        raise RuntimeError("credentials file not found")

    result = send_push("device-token", "title", "body",
                       get_access_token=raising_get_token, post=lambda **kw: None)
    assert result is False
