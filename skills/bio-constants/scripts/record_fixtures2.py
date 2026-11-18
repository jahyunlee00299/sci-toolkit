"""Record Phase 2 public responses (Rhea, eQuilibrator web page) as fixtures."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from biodb import http, rhea, thermo  # noqa: E402
import fixture_transport as ft  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
http.TRANSPORT = ft.recorder(http._wire)
for kw in ({"rhea_id": "RHEA:21432"}, {"ec": "1.1.1.37"}, {"ec": "7.1.1.1"},
           {"ec": "1.17.1.9"}, {"rhea_id": "RHEA:21433"}, {"ec": "9.9.9.9"}):
    try:
        rhea.fetch(**kw)
        print("ok", kw)
    except Exception as e:  # noqa: BLE001
        print("recorded-with-error", kw, e)
rx = "(S)-malate + NAD+ = oxaloacetate + NADH"
for c in (thermo.Conditions(7.5, 0.25, 298.15, 3.0), thermo.Conditions(7.0, 0.10, 298.15, 3.0)):
    r = thermo.web_dg(rx, c)
    print("ok", c.tag(), r["dg"], r["err"])
