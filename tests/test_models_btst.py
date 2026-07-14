from core.models import (BtstCandidate, Instrument, OrderRequest, OrderType,
                         Side)


def test_order_request_defaults_product_type_intraday():
    req = OrderRequest(instrument=Instrument(symbol="X", exchange_segment="NSE_EQ"),
                       side=Side.BUY, order_type=OrderType.MARKET, qty=1)
    assert req.product_type == "INTRADAY"


def test_order_request_accepts_cnc():
    req = OrderRequest(instrument=Instrument(symbol="X", exchange_segment="NSE_EQ"),
                       side=Side.BUY, order_type=OrderType.MARKET, qty=1,
                       product_type="CNC")
    assert req.product_type == "CNC"


def test_btst_candidate_fields():
    instr = Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ", security_id="1")
    c = BtstCandidate(instrument=instr, entry=100.0, target=103.0, stop=98.0,
                      net_score=0.4, close_strength=0.8, volume_ratio=1.5,
                      reasons=["strong close"], gap_risk="overnight gap risk")
    assert c.instrument.symbol == "RELIANCE"
    assert c.ai_reasoning == ""
    assert c.target > c.entry > c.stop
