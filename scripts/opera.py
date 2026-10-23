"""Construieste si verifica modelul â€žOperaâ€ (podium + sali + coji sferice): creator -> verificator â€žpreâ€ -> (optional) analiza -> â€žpostâ€.

Utilizare:  python scripts/opera.py [--analyze] [--no-calibrate] [--name opera]
Cere: ETABS deschis din creator (python -m etabs_creator) si verificatorul pornit (python -m etabs_beams serve)."""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import harness as h  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

OPERA = dict(structure="opera", opera=True, stories=2, bays=12, travei=15, span_x=10.0, span_y=12.0, story_height=6.0, basement=1,
             basement_height=6.0, column_b=1.2, column_h=1.2, beam_b=0.6, beam_h=1.2, slab_t=0.25, concrete="C40/50", wall_t=0.5,
             basement_wall_t=0.6, mesh_max=2.0, modes_per_story=25, modal_type="ritz", diaphragm="rigid", dead_extra=3.0, live=5.0, soil_pressure=25.0)


def show(results: dict, label: str) -> None:
    probs = h.problems(results)
    print(f"\n== {label}: {len(probs)} probleme (eroare/avertisment/eÈ™ec)", flush=True)
    for p in probs:
        print(f"  [{p['severity']}] {p['check']}: {p['message'][:170]}" + (f"  â†’ fix {p['fix']['id']}" if p["fix"] else ""), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--no-calibrate", action="store_true")
    ap.add_argument("--name", default="opera")
    a = ap.parse_args()
    t0 = time.time()
    res = h.build({**OPERA, "name": a.name, "calibrate_static": not a.no_calibrate})
    print(f"construit Ã®n {res['seconds']} s: {res['objects']}\n" + "\n".join("  " + n for n in res["notes"]), flush=True)
    show(h.run_check("pre"), "verificator â€žpreâ€")
    if a.analyze:
        print("\nanalizÄƒ â€¦", flush=True)
        print(h.analyze(), flush=True)
        show(h.run_check("post"), "verificator â€žpostâ€")
    print(f"\ntotal {round(time.time() - t0)} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
