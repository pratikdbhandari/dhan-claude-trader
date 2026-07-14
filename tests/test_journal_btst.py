from core.models import Instrument, OrderRequest, OrderResult, OrderType, Side, TradeMode
from data.journal import init_db, log_order, open_btst_book, list_trades


def _buy(sym="RELIANCE", qty=5):
    return OrderRequest(instrument=Instrument(symbol=sym, exchange_segment="NSE_EQ",
                                              security_id="1", kind="EQUITY"),
                        side=Side.BUY, order_type=OrderType.MARKET, qty=qty, price=100.0,
                        product_type="CNC")


def _sell(sym="RELIANCE", qty=5):
    return OrderRequest(instrument=Instrument(symbol=sym, exchange_segment="NSE_EQ",
                                              security_id="1", kind="EQUITY"),
                        side=Side.SELL, order_type=OrderType.MARKET, qty=qty, price=103.0,
                        product_type="CNC")


def _res(mode=TradeMode.PAPER):
    return OrderResult(ok=True, mode=mode, status="FILLED", dhan_order_id="O1",
                       exec_price=100.0)


def test_btst_columns_roundtrip(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy(), _res(), strategy_tag="BTST",
              planned_exit_date="2026-07-15", plan_target=103.0, plan_stop=98.0)
    row = list_trades(conn)[0]
    assert row["strategy_tag"] == "BTST"
    assert row["planned_exit_date"] == "2026-07-15"
    assert row["plan_target"] == 103.0
    assert row["plan_stop"] == 98.0


def test_non_btst_order_has_null_tag(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy(), _res())
    row = list_trades(conn)[0]
    assert row["strategy_tag"] is None


def test_btst_buy_logs_delivery_product(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy(), _res(), strategy_tag="BTST")
    row = list_trades(conn)[0]
    assert row["product_type"] == "CNC"        # accounting segments as delivery


def test_open_btst_book_lists_unclosed_buys(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy("RELIANCE"), _res(), strategy_tag="BTST",
              planned_exit_date="2026-07-15", plan_target=103.0, plan_stop=98.0)
    log_order(conn, _buy("TCS"), _res(), strategy_tag="BTST",
              planned_exit_date="2026-07-15", plan_target=50.0, plan_stop=45.0)
    book = open_btst_book(conn, mode="PAPER")
    syms = {b["symbol"] for b in book}
    assert syms == {"RELIANCE", "TCS"}
    reliance = next(b for b in book if b["symbol"] == "RELIANCE")
    assert reliance["plan_target"] == 103.0
    assert reliance["planned_exit_date"] == "2026-07-15"


def test_open_btst_book_excludes_closed_positions(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    log_order(conn, _buy("RELIANCE"), _res(), strategy_tag="BTST",
              planned_exit_date="2026-07-15", plan_target=103.0, plan_stop=98.0)
    log_order(conn, _sell("RELIANCE"), _res(), strategy_tag="BTST")
    book = open_btst_book(conn, mode="PAPER")
    assert book == []
