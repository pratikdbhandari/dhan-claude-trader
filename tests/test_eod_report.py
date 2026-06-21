import json
from data.journal import init_db
from services.eod_report import build_report, write_report


def _insert_closed(conn, symbol, side, pnl, providers, rr_pred=2.0, rr_ach=1.5):
    cj = json.dumps({"providers": providers})
    conn.execute("""INSERT INTO trades (created_at, mode, symbol, side, qty,
        entry, exec_price, exit_price, pnl, rr_predicted, rr_achieved,
        exec_status, consensus_json, product_type, kind)
        VALUES ('2026-06-21','PAPER',?,?,1,100,100,110,?,?,?,'FILLED',?,'INTRADAY','EQUITY')""",
        (symbol, side, pnl, rr_pred, rr_ach, cj))
    conn.commit()


def _conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def test_build_report_summary(tmp_path):
    conn = _conn(tmp_path)
    _insert_closed(conn, "X", "BUY", 100, [{"provider": "groq", "signal": "BUY"}])
    _insert_closed(conn, "Y", "BUY", -50, [{"provider": "groq", "signal": "BUY"}])
    rep = build_report(conn, mode="PAPER")
    assert rep["summary"]["trades"] == 2
    assert rep["summary"]["wins"] == 1
    assert rep["summary"]["win_rate"] == 50.0


def test_leaderboard_scores_providers(tmp_path):
    conn = _conn(tmp_path)
    # winning trade (BUY, +pnl): groq said BUY (correct), mistral said SELL (wrong)
    _insert_closed(conn, "X", "BUY", 100,
                   [{"provider": "groq", "signal": "BUY"},
                    {"provider": "mistral", "signal": "SELL"}])
    # losing trade (BUY, -pnl): winning dir = SELL; groq BUY wrong, mistral SELL correct
    _insert_closed(conn, "Y", "BUY", -40,
                   [{"provider": "groq", "signal": "BUY"},
                    {"provider": "mistral", "signal": "SELL"}])
    rep = build_report(conn, mode="PAPER")
    lb = {r["provider"]: r for r in rep["leaderboard"]}
    assert lb["groq"]["calls"] == 2 and lb["groq"]["correct"] == 1
    assert lb["groq"]["accuracy"] == 50.0
    assert lb["mistral"]["correct"] == 1


def test_write_report_creates_files(tmp_path):
    conn = _conn(tmp_path)
    _insert_closed(conn, "X", "BUY", 100, [{"provider": "groq", "signal": "BUY"}])
    rep = build_report(conn, mode="PAPER", date_key="2026-06-21")
    md, csv_path = write_report(rep, out_dir=str(tmp_path / "reports"),
                                date_key="2026-06-21")
    assert md.endswith("EOD_2026-06-21_PAPER.md")
    from pathlib import Path
    md_text = Path(md).read_text(encoding="utf-8")
    assert "Provider Leaderboard" in md_text and "groq" in md_text
    assert "symbol,side,qty" in Path(csv_path).read_text(encoding="utf-8")


def test_empty_journal_still_writes(tmp_path):
    conn = _conn(tmp_path)
    rep = build_report(conn, mode="PAPER", date_key="2026-06-21")
    assert rep["summary"]["trades"] == 0
    md, csv_path = write_report(rep, out_dir=str(tmp_path / "reports"))
    from pathlib import Path
    assert Path(md).exists() and Path(csv_path).exists()
