"""Read-only Dhan connectivity self-test. Verifies every live READ endpoint + our
parsers against your real account WITHOUT placing any order. Run before going live:

    python scripts_connectivity_check.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

from core.models import Instrument, TradeMode
from services.dhan_client import DhanClient
from services import instruments
from services.connectivity import run_checks, verdict


def main():
    cid = os.getenv("DHAN_CLIENT_ID", "")
    if not cid or cid == "your_dhan_client_id":
        print("✗ DHAN_CLIENT_ID is missing or still the placeholder. "
              "Fill real creds in .env first.")
        return
    print("Read-only connectivity self-test (NO orders are placed)\n" + "-" * 60)

    client = DhanClient(client_id=cid, access_token=os.getenv("DHAN_ACCESS_TOKEN"),
                        mode=TradeMode.PAPER)
    try:
        idx = instruments.build_index(instruments.download_master())
    except Exception:
        idx = {}

    eq = instruments.resolve(Instrument(symbol="RELIANCE", exchange_segment="NSE_EQ",
                                        security_id=None, kind="EQUITY"), idx)
    index = instruments.resolve(Instrument(symbol="NIFTY", exchange_segment="IDX_I",
                                           security_id=None, kind="INDEX"), idx)

    checks = run_checks(client, equity_instr=eq, index_instr=index)
    for c in checks:
        mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "–"}[c.status]
        print(f"  {mark} {c.name:<42} {c.detail}")
    print("-" * 60)
    print(verdict(checks))


if __name__ == "__main__":
    main()
