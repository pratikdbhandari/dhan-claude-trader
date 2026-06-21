from services.charges import compute, reconcile

def test_reconcile_overrides_provided_fields_and_recomputes_total():
    base = compute("equity_delivery", "BUY", qty=10, price=100, mode="LIVE")
    out = reconcile(base, {"brokerage": 5.0, "stt": 1.25})
    assert out.brokerage == 5.0
    assert out.stt == 1.25
    assert out.stamp == base.stamp
    assert out.total == round(5.0 + 1.25 + base.exchange_txn + base.sebi
                              + base.stamp + base.gst, 2)

def test_reconcile_with_empty_actuals_is_noop():
    base = compute("futures", "SELL", qty=50, price=300, mode="LIVE")
    out = reconcile(base, {})
    assert out == base
