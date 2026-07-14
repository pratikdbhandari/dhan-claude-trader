import json
from web import charts


def test_fig_json_is_valid_json_with_data_and_layout():
    from core.models import RealizedTrade
    rt = RealizedTrade(symbol="X", segment="equity_delivery", mode="PAPER", qty=1,
                       buy_price=100, sell_price=110, gross_pnl=10, charges=0, net_pnl=10,
                       rr_predicted=None, rr_achieved=None,
                       opened_at="2026-07-01T09:00:00", closed_at="2026-07-01T15:00:00")
    from services import charting
    fig = charting.equity_curve([rt] * 3)
    s = charts.fig_json(fig)
    parsed = json.loads(s)
    assert "data" in parsed and "layout" in parsed
