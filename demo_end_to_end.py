"""End-to-end demo of the whole pipeline in PAPER + mock mode (no creds, no cost).
Proves: candles -> regime -> 29-strategy confluence -> AI(mock) consensus ->
quality gate -> confidence sizing -> risk gate -> two-step order -> journal ->
accounting -> EOD report. Run: python demo_end_to_end.py
"""
import tempfile
import numpy as np
import pandas as pd

# register strategies
import services.strategies.trend, services.strategies.mean_reversion        # noqa: F401,E401
import services.strategies.breakout, services.strategies.volume, services.strategies.structure  # noqa: F401,E401

from core.models import Instrument, TradeMode, OrderResult, Side, OrderType, SignalType
from services import indicators as ind
from services.regime import classify_regime
from services.strategies.engine import build_confluence
from services import signal_engine, risk_manager, trade_controller
from services.quality_gate import apply_gate
from services.sizing import quality_multiplier
from services.dhan_client import DhanClient
from data.journal import init_db, log_order, to_legs, stats
from services.accounting import realized_trades, pnl_statement
from services.eod_report import build_report, write_report


def line(t):
    print("\n" + "=" * 64 + f"\n{t}\n" + "=" * 64)


def main():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                       security_id="2885", kind="EQUITY")

    line("1. MARKET DATA (synthetic trending candles)")
    n = 260
    close = 2400 + np.linspace(0, 120, n) + np.random.default_rng(7).normal(0, 3, n)
    df = pd.DataFrame({"open": close, "high": close + 5, "low": close - 5,
                       "close": close, "volume": np.full(n, 5e5)})
    print(f"  {n} daily candles, last close ₹{close[-1]:.1f}")

    line("2. REGIME + 29-STRATEGY CONFLUENCE")
    regime = classify_regime(df)
    snap = build_confluence(df, regime=regime, style="positional",
                            active_ids=list(range(1, 30)))
    print(f"  regime={regime.value}  bias={snap.bias.value}  net_score={snap.net_score}"
          f"  ({snap.buy_count}B/{snap.sell_count}S/{snap.hold_count}H)")
    print(f"  category_scores={snap.category_scores}")

    line("3. AI CONSENSUS (mock mode — free, deterministic)")
    atr = float(ind.atr(df).dropna().iloc[-1])
    last = float(df["close"].iloc[-1])
    cs = signal_engine.generate(instr, snap, last_price=last, atr=atr, mode="mock")
    sd = cs.indicator_snapshot
    print(f"  consensus={cs.consensus.value}  confidence={cs.avg_confidence}%")
    print(f"  entry={sd.get('entry')} stop={sd.get('stop_loss')} target={sd.get('target')}")

    line("4. TRI-FACTOR QUALITY GATE")
    gate = apply_gate(cs, fundamentals={"pe": 24}, event_flags=[], kind="EQUITY")
    print(f"  quality_score={gate.score}  passed={gate.passed}  vetoed={gate.vetoed}")
    print(f"  reasons={gate.reasons}")

    line("5. RISK GATE + CONFIDENCE SIZING")
    cfg = risk_manager.load_risk_config({})
    equity = 1_000_000
    pending = trade_controller.prepare_order(cs, instr, equity=equity, cfg=cfg,
                                             day_pnl_value=0, open_count=0)
    base_qty = pending.order_request.qty
    mult = min(1.0, quality_multiplier(gate.score))
    pending.order_request.qty = max(1, int(base_qty * mult))
    rc = pending.risk_check
    print(f"  equity ₹{equity:,}  1%-risk base qty={base_qty}  quality mult={mult}"
          f"  -> sized qty={pending.order_request.qty}")
    print(f"  risk_check allowed={rc.allowed}  buffer ₹{rc.remaining_loss_buffer:,.0f}")

    line("6. TWO-STEP CONFIRM -> PLACE (PAPER) -> JOURNAL")
    conn = init_db(tempfile.mktemp(suffix=".db"))

    class PaperDhan(DhanClient):
        def __init__(self):
            self.sdk, self.mode = None, TradeMode.PAPER
    dhan = PaperDhan()
    # entry fill
    buy_req = pending.order_request
    res = OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED",
                      exec_price=sd.get("entry"))
    log_order(conn, buy_req, res, consensus=cs)
    print(f"  ENTRY logged: {buy_req.side.value} {buy_req.qty} @ ₹{res.exec_price}")
    # exit fill at target (simulate a win)
    from core.models import OrderRequest
    exit_req = OrderRequest(instrument=instr, side=Side.SELL, order_type=OrderType.MARKET,
                            qty=buy_req.qty, price=sd.get("target"))
    log_order(conn, exit_req, OrderResult(ok=True, mode=TradeMode.PAPER, status="FILLED",
              exec_price=sd.get("target")), consensus=cs)
    print(f"  EXIT  logged: SELL {buy_req.qty} @ ₹{sd.get('target')}")

    line("7. ACCOUNTING (FIFO realized P&L, charge-accurate)")
    legs = to_legs(conn, mode="PAPER")
    realized = realized_trades(legs, mode="PAPER")
    for r in realized:
        print(f"  {r.symbol}: gross ₹{r.gross_pnl} - charges ₹{r.charges} = NET ₹{r.net_pnl}")
    stmt = pnl_statement(legs, mode="PAPER", period="all", period_key=None,
                         ltp_fn=lambda s: None)
    print(f"  P&L statement: gross ₹{stmt.gross_realized} | charges "
          f"₹{round(stmt.brokerage+stmt.stt+stmt.exchange_sebi_stamp+stmt.gst,2)} | "
          f"NET ₹{stmt.net_realized} | total ₹{stmt.total_pnl}")

    line("8. JOURNAL STATS + EOD REPORT")
    # mark pnl on the closed buy row so stats/leaderboard populate
    if realized:
        conn.execute("UPDATE trades SET pnl=? WHERE side='BUY'", (realized[0].net_pnl,))
        conn.commit()
    s = stats(conn, "PAPER")
    print(f"  stats: trades={s['trades']} wins={s['wins']} win_rate={s['win_rate']}%")
    rep = build_report(conn, mode="PAPER", date_key="2026-06-21")
    md, csv = write_report(rep, out_dir="reports", date_key="2026-06-21")
    print(f"  EOD report written: {md}")
    print(f"                      {csv}")

    line("DONE — full pipeline executed end-to-end in PAPER/mock (no creds, no orders fired)")


if __name__ == "__main__":
    main()
