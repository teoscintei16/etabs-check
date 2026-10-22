"""CLI:  python -m etabs_beams detect [filtre] -o beams.json"""
from __future__ import annotations

import argparse
import collections
import sys

from .api import check_model, detect, list_sections
from .connection import EtabsSession
from .export import write_json
from .models import Tolerances
from .selector import BeamSelector


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
    d = sub.add_parser("detect", help="detecteaza grinzile continue din ETABS-ul pornit")
    d.add_argument("-o", "--output", help="fisier JSON de iesire")
    d.add_argument("--section", action="append", default=[], help="doar sectiuni (sablon *, ?); repetabil")
    d.add_argument("--exclude-section", action="append", default=[], help="fara aceste sectiuni; repetabil")
    d.add_argument("--story", action="append", default=[], help="doar etaje; repetabil")
    d.add_argument("--exclude-story", action="append", default=[])
    d.add_argument("--frame", action="append", default=[], help="nume sau eticheta de grinda; repetabil")
    d.add_argument("--min-length", type=float)
    d.add_argument("--match", choices=("any", "all"), default="any",
                   help="any: lant ales daca un membru satisface sectiunea; all: toti membrii")
    d.add_argument("--continuity", choices=("any", "continuous", "single_span"), default="any")
    d.add_argument("--belt-section", action="append", default=[],
                   help="sectiune (sablon) care simuleaza centura de perete, ex. 'dummy*'; repetabil")
    d.add_argument("--no-belts", action="store_true", help="nu intreba: nu exista centuri")
    d.add_argument("--only-belts", action="store_true", help="extrage doar centurile (nu grinzile)")
    d.add_argument("--with-belts", action="store_true", help="include si centurile in JSON")
    d.add_argument("--wall-min-length", type=float, default=0.80,
                   help="[m] perete in planul grinzii mai lung de aceasta valoare => fara continuitate")
    d.add_argument("--angle-tol", type=float, default=10.0)
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        from .server import serve
        serve(a.port)
        return 0
    if a.cmd == "check":
        return _run_check(a)
    session = EtabsSession.attach()
    belt_secs = list(a.belt_section)
    if not belt_secs and not a.no_belts and sys.stdin.isatty():
        belt_secs = _ask_belt_sections(session)

    sel = BeamSelector(sections=a.section, exclude_sections=a.exclude_section, stories=a.story,
                       exclude_stories=a.exclude_story, frames=a.frame, min_length=a.min_length,
                       match=a.match, continuity=a.continuity)
    tol = Tolerances(angle_deg=a.angle_tol, belt_sections=belt_secs, wall_min_length=a.wall_min_length)
    bm = detect(session, tol, sel)
    print(f"\nModel: {session.filename}")
    print(f"Grinzi: {len(bm.model.beam_names)} | lanturi: {len(bm.chains)} | selectate: {len(bm.selected)} "
          f"| portiuni pe perete lung: {len(bm.on_wall)}")
    if bm.belts:
        print(f"Centuri: {len(bm.model.belt_names)} bare -> {len(bm.belts)} centuri")
    print("Reazeme (selectate):", dict(collections.Counter(s.kind for c in bm.selected for s in c.supports)))
    print("Tipuri:", dict(collections.Counter(c.continuity for c in bm.selected)))
    codes = collections.Counter(w["code"] for w in bm.model.warnings)
    if codes:
        print("Avertismente:", dict(codes))
    if a.output:
        include = ("belts",) if a.only_belts else (("beams", "belts") if a.with_belts else ("beams",))
        write_json(bm, a.output, session.filename, include)
        print("Scris:", a.output)


if __name__ == "__main__":
    sys.exit(main() or 0)
