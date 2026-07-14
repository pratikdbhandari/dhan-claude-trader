import json
from core.models import Instrument
from web import deps


def test_load_watchlist_reads_file(tmp_path):
    p = tmp_path / "watchlist.json"
    p.write_text(json.dumps({"instruments": [
        {"symbol": "RELIANCE", "exchange_segment": "NSE_EQ", "security_id": "2885",
         "lot_size": 1, "kind": "EQUITY"}]}))
    wl = deps.load_watchlist(path=p)
    assert wl == [Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                             security_id="2885", lot_size=1, kind="EQUITY")]


def test_get_equity_paper_uses_account_capital(monkeypatch, tmp_path):
    from core import config_store
    monkeypatch.setattr(config_store, "SETTINGS_PATH", tmp_path / "s.json")
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, tmp_path / "s.json"))
    monkeypatch.setenv("ACCOUNT_CAPITAL", "150000")
    assert deps.get_equity("PAPER", None) == 150000.0


def test_style_for():
    assert deps.style_for("INDEX") == "intraday"
    assert deps.style_for("EQUITY") == "positional"
