from services import providers, cost


class _Usage:
    def __init__(self, a, b, *, openai=False):
        if openai:
            self.prompt_tokens, self.completion_tokens = a, b
        else:
            self.input_tokens, self.output_tokens = a, b


class _AnthResp:
    def __init__(self):
        self.content = [type("C", (), {"text": "BUY"})()]
        self.usage = _Usage(1000, 500)


class _AnthSdk:
    def __init__(self, *a, **k):
        self.messages = self

    def create(self, **kw):
        return _AnthResp()


class _OpenAiResp:
    def __init__(self, with_usage=True):
        msg = type("M", (), {"content": "SELL"})()
        self.choices = [type("Ch", (), {"message": msg})()]
        self.usage = _Usage(2000, 800, openai=True) if with_usage else None


class _OpenAiSdk:
    def __init__(self, *a, with_usage=True, **k):
        self._wu = with_usage
        self.chat = self
        self.completions = self

    def create(self, **kw):
        return _OpenAiResp(self._wu)


def test_anthropic_client_logs_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(cost, "COST_PATH", str(tmp_path / "cost.jsonl"))
    monkeypatch.setattr(cost, "load_prices", lambda path=None: {
        "M": {"input_per_1k": 1.0, "output_per_1k": 2.0},
        "default": {"input_per_1k": 0.0, "output_per_1k": 0.0}})
    client = providers.make_client({"kind": "anthropic", "model": "M"}, "k",
                                   _anthropic_cls=_AnthSdk)
    text = client("prompt")
    assert text == "BUY"
    runs = cost.read_runs(path=str(tmp_path / "cost.jsonl"))
    assert len(runs) == 1 and runs[0]["in"] == 1000 and runs[0]["out"] == 500


def test_openai_client_logs_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(cost, "COST_PATH", str(tmp_path / "cost.jsonl"))
    monkeypatch.setattr(cost, "load_prices", lambda path=None: {
        "default": {"input_per_1k": 0.0, "output_per_1k": 0.0}})
    client = providers.make_client({"kind": "openai", "model": "M"}, "k",
                                   _openai_cls=_OpenAiSdk)
    assert client("prompt") == "SELL"
    runs = cost.read_runs(path=str(tmp_path / "cost.jsonl"))
    assert len(runs) == 1 and runs[0]["in"] == 2000 and runs[0]["out"] == 800


def test_missing_usage_skips_logging(tmp_path, monkeypatch):
    monkeypatch.setattr(cost, "COST_PATH", str(tmp_path / "cost.jsonl"))

    def _sdk(*a, **k):
        return _OpenAiSdk(with_usage=False)
    client = providers.make_client({"kind": "openai", "model": "M"}, "k",
                                   _openai_cls=_sdk)
    assert client("prompt") == "SELL"
    assert cost.read_runs(path=str(tmp_path / "cost.jsonl")) == []
