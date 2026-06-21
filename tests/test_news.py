from services import news

SAMPLE = """<?xml version="1.0"?><rss><channel>
<item><title>Nifty hits record high</title></item>
<item><title>RBI holds repo rate</title></item>
</channel></rss>"""

def test_parses_titles_from_rss():
    out = news.get_headlines("NIFTY", hours=24, fetch=lambda url: SAMPLE)
    assert "Nifty hits record high" in out
    assert "RBI holds repo rate" in out

def test_network_error_returns_empty():
    def boom(url): raise OSError("no net")
    assert news.get_headlines("NIFTY", hours=24, fetch=boom) == []
