"""Start the AI Banking System dashboard (demo / educational only).

Usage (from the project root -- the folder containing this file):
    macOS / Linux:  python3 run.py
                    python3 run.py --port 8080
                    python3 run.py --reset
    Windows:        py run.py
                    py run.py --port 8080
                    py run.py --reset

No other installs or setup steps are required: Python 3.10+ standard
library only. Data lives in data/ under the project root; --reset
deletes data/ and reseeds it. Demo data is seeded ONLY when the
databases are empty, so restarting never duplicates demo data.

DEMO / EDUCATIONAL ONLY: not a real bank, not PCI-DSS / SOC 2
compliant. AI scores are illustrative, not regulated decisions.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.seed import list_bank_accounts, seed_data
from api.server import build_state, serve


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI Banking System demo server")
    parser.add_argument("--port", type=int, default=8000,
                        help="port to serve on (default: 8000)")
    parser.add_argument("--reset", action="store_true",
                        help="delete data/ and reseed demo data")
    args = parser.parse_args(argv)

    data_dir = ROOT / "data"
    if args.reset and data_dir.exists():
        shutil.rmtree(data_dir)
        print("Reset: removed data/", flush=True)

    state = build_state(data_dir)
    if seed_data(state):
        print("Seeded demo data (fictitious demo customers/accounts only).", flush=True)
    else:
        print("Existing data found (%d account(s)); not reseeding."
              % len(list_bank_accounts(state.bank)), flush=True)

    print("Demo users: admin/admin123, manager/manager123,"
          " teller/teller123, customer/customer123", flush=True)
    print("DEMO / EDUCATIONAL ONLY - not a real bank.", flush=True)
    serve(state, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
