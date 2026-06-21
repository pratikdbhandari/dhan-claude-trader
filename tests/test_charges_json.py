import json
from pathlib import Path

REQUIRED = {"brokerage_flat", "brokerage_pct", "stt_buy", "stt_sell",
            "exchange_txn", "sebi", "stamp_buy", "gst"}

def test_all_segments_have_required_keys():
    data = json.loads(Path("charges.json").read_text())
    for seg in ("equity_delivery", "equity_intraday", "futures", "options"):
        assert seg in data, f"missing segment {seg}"
        assert REQUIRED.issubset(data[seg].keys()), f"{seg} missing keys"
