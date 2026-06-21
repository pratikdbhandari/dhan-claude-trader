from data.segments import to_segment


def test_equity_intraday_vs_delivery():
    assert to_segment("INTRADAY", "EQUITY") == "equity_intraday"
    assert to_segment("CNC", "EQUITY") == "equity_delivery"


def test_fut_and_opt():
    assert to_segment("INTRADAY", "FUT") == "futures"
    assert to_segment("INTRADAY", "OPT") == "options"
    assert to_segment("NRML", "OPTION") == "options"
