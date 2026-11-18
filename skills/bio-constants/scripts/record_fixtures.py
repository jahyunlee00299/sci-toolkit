"""Record live public responses as test fixtures (run by hand; polite 1 req/s)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from biodb import http, pdb, uniprot  # noqa: E402
import fixture_transport as ft  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
http.TRANSPORT = ft.recorder(http._wire)
for a in ["P33160", "P61889", "P04637-2", "P69905", "P00533", "A0A0G3HLV0", "A0A0G3I6S6",
          "P0AES4", "P01922", "P12345-2"]:
    try:
        uniprot.fetch(a)
        print("ok", a)
    except Exception as e:  # noqa: BLE001
        print("recorded-with-error", a, e)
for p in ["2NAD", "9ZZZ"]:
    try:
        pdb.fetch(p)
        print("ok", p)
    except Exception as e:  # noqa: BLE001
        print("recorded-with-error", p, e)
