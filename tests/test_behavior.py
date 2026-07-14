from core.models import RealizedTrade
from services.behavior import disposition_effect, DispositionResult, MIN_SAMPLE


def _t(net_pnl, opened, closed):
    """RealizedTrade with only the fields disposition_effect reads meaningfully."""
    return RealizedTrade(
        symbol="X", segment="equity_delivery", mode="PAPER", qty=1,
        buy_price=100.0, sell_price=100.0 + net_pnl, gross_pnl=net_pnl, charges=0.0,
        net_pnl=net_pnl, rr_predicted=None, rr_achieved=None,
        opened_at=opened, closed_at=closed)


def _hours_apart(base_day, open_h, hold_h):
    o = f"2026-07-{base_day:02d}T{open_h:02d}:00:00"
    close_h = open_h + hold_h
    c = f"2026-07-{base_day:02d}T{close_h:02d}:00:00"
    return o, c


def test_disposition_present_when_losers_held_longer():
    trades = []
    for d in (1, 2, 3):
        o, c = _hours_apart(d, 9, 1)
        trades.append(_t(+50.0, o, c))
    for d in (4, 5, 6):
        o, c = _hours_apart(d, 9, 5)
        trades.append(_t(-40.0, o, c))
    r = disposition_effect(trades)
    assert isinstance(r, DispositionResult)
    assert r.insufficient is False
    assert r.present is True
    assert r.n_wins == 3 and r.n_losses == 3
    assert r.avg_hold_win_hours == 1.0
    assert r.avg_hold_loss_hours == 5.0
    assert r.hold_ratio == 5.0
    assert r.avg_win == 50.0
    assert r.avg_loss == 40.0
    assert "detected" in r.verdict.lower()


def test_no_disposition_when_winners_held_longer():
    trades = []
    for d in (1, 2, 3):
        o, c = _hours_apart(d, 9, 5)
        trades.append(_t(+50.0, o, c))
    for d in (4, 5, 6):
        o, c = _hours_apart(d, 9, 1)
        trades.append(_t(-40.0, o, c))
    r = disposition_effect(trades)
    assert r.present is False
    assert "no disposition" in r.verdict.lower()


def test_insufficient_when_too_few_losses():
    trades = []
    for d in (1, 2, 3):
        o, c = _hours_apart(d, 9, 1)
        trades.append(_t(+50.0, o, c))
    o, c = _hours_apart(4, 9, 5)
    trades.append(_t(-40.0, o, c))
    r = disposition_effect(trades)
    assert r.insufficient is True
    assert r.present is False
    assert "enough" in r.verdict.lower()


def test_empty_list_is_insufficient():
    r = disposition_effect([])
    assert r.insufficient is True
    assert r.n_wins == 0 and r.n_losses == 0


def test_hold_hours_math():
    trades = [_t(+10.0, *(_hours_apart(d, 9, 4))) for d in (1, 2, 3)]
    trades += [_t(-10.0, *(_hours_apart(d, 9, 2))) for d in (4, 5, 6)]
    r = disposition_effect(trades)
    assert r.avg_hold_win_hours == 4.0
    assert r.avg_hold_loss_hours == 2.0


def test_bad_timestamp_trade_skipped():
    good = [_t(+50.0, *(_hours_apart(d, 9, 1))) for d in (1, 2, 3)]
    good += [_t(-40.0, *(_hours_apart(d, 9, 5))) for d in (4, 5, 6)]
    bad = _t(+50.0, "not-a-date", "also-bad")
    r = disposition_effect(good + [bad])
    assert r.n_wins == 3
    assert r.insufficient is False


def test_zero_pnl_trade_excluded():
    trades = [_t(+50.0, *(_hours_apart(d, 9, 1))) for d in (1, 2, 3)]
    trades += [_t(-40.0, *(_hours_apart(d, 9, 5))) for d in (4, 5, 6)]
    trades.append(_t(0.0, *(_hours_apart(7, 9, 3))))
    r = disposition_effect(trades)
    assert r.n_wins == 3 and r.n_losses == 3


def test_zero_win_hold_ratio_guard():
    trades = [_t(+50.0, f"2026-07-0{d}T09:00:00", f"2026-07-0{d}T09:00:00")
              for d in (1, 2, 3)]
    trades += [_t(-40.0, *(_hours_apart(d, 9, 5))) for d in (4, 5, 6)]
    r = disposition_effect(trades)
    assert r.avg_hold_win_hours == 0.0
    assert r.hold_ratio == 0.0
    assert r.present is True
