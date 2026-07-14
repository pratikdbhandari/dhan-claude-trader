import plotly.graph_objects as go

from services import charting


def test_fold_bars_returns_figure():
    folds = [{"expectancy": 12.0}, {"expectancy": -3.0}, {"expectancy": 8.0}]
    assert isinstance(charting.fold_bars(folds, colors=None), go.Figure)


def test_fold_bars_empty_safe():
    assert isinstance(charting.fold_bars([], colors=None), go.Figure)


def test_histogram_returns_figure():
    fig = charting.histogram([1.0, 2.0, 2.0, 3.0, 5.0], colors=None, title="dd")
    assert isinstance(fig, go.Figure)


def test_histogram_empty_safe():
    assert isinstance(charting.histogram([], colors=None), go.Figure)
