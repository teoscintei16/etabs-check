"""CLI:  python -m etabs_beams serve  |  check  (verificatorul de model; extragerea grinzilor e in proiectul etabs-beam-extract)"""
from __future__ import annotations

import argparse
import sys

from .api import check_model, list_sections
from .connection import EtabsSession
from .models import Tolerances


def _ask_belt_sections(session) -> list[str]:
    """Intreaba utilizatorul daca exista grinzi care simuleaza centurile peretilor si ce sectiuni au."""
    secs = list_sections(session)
    print("\nExista in model grinzi care simuleaza centurile peretilor (ex. 'dummy')? [d/N] ", end="", flush=True)
    if input().strip().lower() not in ("d", "da", "y", "yes"):
        return []
    print("Sectiuni disponibile (bare care nu sunt stalpi):")
    for i, (name, n) in enumerate(secs, 1):
        print(f"  {i:3d}. {name}  ({n} bare)")
    print("Alege sectiunile de centura (numere separate prin virgula): ", end="", flush=True)
    picks = [p.strip() for p in input().split(",") if p.strip().isdigit()]
    return [secs[int(p) - 1][0] for p in picks if 0 < int(p) <= len(secs)]


def _run_check(a) -> int:
    import json
    from .checker import format_report, report
    session = EtabsSession.attach()
    belt_secs = list(a.belt_section)
    if not belt_secs and not a.no_belts and sys.stdin.isatty():
        belt_secs = _ask_belt_sections(session)
    tol = Tolerances(belt_sections=belt_secs)
    md, issues, extras = check_model(session, tol)
    rep = report(md, issues, extras)
    print()
    print(format_report(rep, a.max_objects))
    if a.output:
        with open(a.output, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
        print("\nRaport scris:", a.output)
    return 0 if rep["ready"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="etabs_beams")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("serve", help="porneste GUI-ul local (backend + interfata web)")
    g.add_argument("--port", type=int, default=8765)
    c = sub.add_parser("check", help="verifica daca modelul ETABS este curat si pregatit")
    c.add_argument("-o", "--output", help="raport JSON")
    c.add_argument("--belt-section", action="append", default=[],
                   help="sectiune (sablon) de centura, ex. 'dummy*'; repetabil")
    c.add_argument("--no-belts", action="store_true", help="nu intreba: nu exista centuri")
    c.add_argument("--max-objects", type=int, default=12, help="obiecte afisate pe verificare in consola")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        from .server import serve
        serve(a.port)
        return 0
    if a.cmd == "check":
        return _run_check(a)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
