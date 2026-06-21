"""RSS news headlines. Pure-ish: fetch() is injectable so tests pass XML directly.
Network/parse failures degrade to an empty list (never raise)."""
from __future__ import annotations
import logging
import xml.etree.ElementTree as ET
from urllib.request import urlopen

log = logging.getLogger(__name__)

FEEDS = [
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
]


def _default_fetch(url: str) -> str:
    with urlopen(url, timeout=5) as r:        # noqa: S310
        return r.read().decode("utf-8", "ignore")


def get_headlines(symbol: str, hours: int = 24, fetch=None, feeds=None) -> list[str]:
    fetch = fetch or _default_fetch
    feeds = feeds if feeds is not None else FEEDS
    titles: list[str] = []
    for url in feeds:
        try:
            xml = fetch(url)
            root = ET.fromstring(xml)
            for item in root.iter("item"):
                t = item.findtext("title")
                if t:
                    titles.append(t.strip())
        except Exception as e:                # noqa: BLE001
            log.warning("news feed failed %s: %s", url, e)
            continue
    return titles
