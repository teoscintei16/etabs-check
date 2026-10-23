"""Rulare de la cap la cap a unui model mare: creator -> verificator „pre” -> (optional) analiza -> verificator „post”.

Folosit de opera.py si burj.py. Cere ETABS deschis din creator (python -m etabs_creator) si verificatorul pornit (python -m etabs_beams serve)."""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import harness as h  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def show(results: dict, label: str) -> None:
    probs = h.problems(results)
    print(f"\n== {label}: {len(probs)} probleme (eroare/avertisment/eșec)", flush=True)
    for p in probs:
        print(f"  [{p['severity']}] {p['check']}: {p['message'][:200]}" + (f"  → fix {p['fix']['id']}" if p["fix"] else ""), flush=True)


def run(spec: dict, name: str, doc: str) -> int:
    ap = argparse.ArgumentParser(description=doc)
    ap.add_argument("--analyze", action="store_true", help="ruleaza analiza si verificarile „post”")
    ap.add_argument("--no-calibrate", action="store_true", help="fara calibrarea fortelor statice (nu ruleaza analiza la construire)")
    ap.add_argument("--name", default=name)
    a = ap.parse_args()
    t0 = time.time()
    res = h.build({**spec, "name": a.name, "calibrate_static": not a.no_calibrate})
    print(f"construit în {res['seconds']} s: {res['objects']}\n" + "\n".join("  " + n for n in res["notes"]), flush=True)
    show(h.run_check("pre"), "verificator „pre”")
    if a.analyze:
        print("\nanaliză …", flush=True)
        print(h.analyze(timeout=3600), flush=True)
        show(h.run_check("post"), "verificator „post”")
    print(f"\ntotal {round(time.time() - t0)} s")
    return 0
