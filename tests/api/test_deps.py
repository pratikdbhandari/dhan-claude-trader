import json

from core.models import Instrument, TradeMode
from core import config_store
from services.dhan_client import DhanClient
from services.risk_manager import RiskConfig


def _isolate_config_store(monkeypatch, tmp_path):
    empty_path = tmp_path / "settings.local.json"
    monkeypatch.setattr(config_store, "SETTINGS_PATH", empty_path)
    monkeypatch.setattr(config_store.get_setting, "__defaults__", (None, empty_path))


def test_get_journal_returns_same_connection_each_call(monkeypatch, tmp_path):
    import api.deps as deps
    deps._journal_conn = None
    monkeypatch.chdir(tmp_path)
    conn1 = deps.get_journal()
    conn2 = deps.get_journal()
    assert conn1 is conn2
    deps._journal_conn = None


def test_get_dhan_client_reads_mode_from_config_store(monkeypatch, tmp_path):
    import api.deps as deps
    _isolate_config_store(monkeypatch, tmp_path)
    monkeypatch.setenv("TRADE_MODE", "PAPER")
    monkeypatch.setenv("DHAN_CLIENT_ID", "cid")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "token")
    client = deps.get_dhan_client()
    assert isinstance(client, DhanClient)
    assert client.mode is TradeMode.PAPER


def test_get_risk_config_reads_env_overrides(monkeypatch, tmp_path):
    import api.deps as deps
    _isolate_config_store(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_DAILY_LOSS", "5000")
    monkeypatch.setenv("MAX_RISK_PER_TRADE_PCT", "2.0")
    monkeypatch.setenv("MAX_OPEN_POSITIONS", "3")
    cfg = deps.get_risk_config()
    assert cfg == RiskConfig(max_daily_loss=5000.0, max_risk_per_trade_pct=2.0,
                             max_open_positions=3)


def test_load_watchlist_returns_resolved_instruments(tmp_path):
    import api.deps as deps
    wl_path = tmp_path / "watchlist.json"
    wl_path.write_text(json.dumps({"instruments": [
        {"symbol": "RELIANCE", "exchange_segment": "NSE_EQ", "security_id": "500325",
         "lot_size": 1, "kind": "EQUITY"},
    ]}))
    result = deps.load_watchlist(path=wl_path)
    assert result == [Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                                 security_id="500325", lot_size=1, kind="EQUITY")]


def test_get_equity_paper_mode_uses_account_capital(monkeypatch, tmp_path):
    import api.deps as deps
    _isolate_config_store(monkeypatch, tmp_path)
    monkeypatch.setenv("ACCOUNT_CAPITAL", "250000")
    equity = deps.get_equity("PAPER", dhan=None)
    assert equity == 250000.0


def test_get_equity_live_mode_reads_fund_limits(fake_dhan):
    import api.deps as deps
    fake_dhan.fund_limits = {"availabelBalance": 42000}
    equity = deps.get_equity("LIVE", dhan=fake_dhan)
    assert equity == 42000.0


def test_get_pending_store_returns_same_instance():
    import api.deps as deps
    assert deps.get_pending_store() is deps.get_pending_store()
