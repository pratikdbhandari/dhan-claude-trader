from core.models import ChargeBreakdown, RealizedTrade, Holding, PnLStatement

def test_charge_breakdown_fields():
    c = ChargeBreakdown(brokerage=0, stt=1.0, exchange_txn=0.03, sebi=0.0,
                        stamp=0.15, gst=0.01, total=1.19)
    assert c.total == 1.19

def test_realized_and_holding_and_statement():
    r = RealizedTrade(symbol="X", segment="equity_delivery", mode="PAPER", qty=10,
                      buy_price=100, sell_price=110, gross_pnl=100, charges=2.33,
                      net_pnl=97.67, rr_predicted=None, rr_achieved=None,
                      opened_at="t0", closed_at="t1")
    h = Holding(symbol="X", segment="equity_delivery", mode="PAPER", qty=5,
                avg_cost=100, invested=500, ltp=None, current_value=None,
                unrealized_pnl=None)
    s = PnLStatement(mode="PAPER", period="all", gross_realized=100, brokerage=0,
                     stt=2.1, exchange_sebi_stamp=0.2, gst=0.03, net_realized=97.67,
                     unrealized=0.0, total_pnl=97.67)
    assert r.net_pnl == 97.67 and h.qty == 5 and s.total_pnl == 97.67
