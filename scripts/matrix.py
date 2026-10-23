"""Matrice de modele generate de creator, verificate de verificator (nerulat + rulat). Afiseaza ce nu e „ok” la fiecare.

Utilizare:  python scripts/matrix.py [--no-post] [--only cerc,cadre] [--list]
Cere: instanta ETABS deschisa din creator (python -m etabs_creator) si verificatorul pornit (python -m etabs_beams serve)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import harness as h  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

WALLS_X = dict(walls=True, wall_lines_x="first,last", wall_bays_x="middle", wall_lines_y="none", wall_bays_y="none")
MATRIX = {
    "cadre": dict(structure="cadre", stories=5, bays=3, travei=3),
    "cadre_rigid": dict(structure="cadre", stories=5, bays=3, travei=3, diaphragm="rigid"),
    "pereti_izolati": dict(structure="pereti_izolati", stories=5, walls=True),
    "pereti_cuplati": dict(structure="pereti_cuplati", stories=6, walls=True, wall_lines_x="first,last", wall_bays_x="first,last",
                           wall_lines_y="none", wall_bays_y="none", coupling_bays_x="all"),
    "dual": dict(structure="dual", stories=8, bays=4, travei=3, **WALLS_X),
    "nucleu_C": dict(structure="nucleu", stories=6, bays=4, travei=4, walls=True, wall_lines_x="none", wall_bays_x="none",
                     wall_lines_y="none", wall_bays_y="none", core_shape="C"),
    "nucleu_H": dict(structure="nucleu", stories=6, bays=4, travei=4, walls=True, wall_lines_x="none", wall_bays_x="none",
                     wall_lines_y="none", wall_bays_y="none", core_shape="H"),
    "L_cu_gol": dict(structure="neregulat", stories=6, bays=4, travei=3, shape="L", cut_bays=2, cut_travei=1, void_cells="1,1"),
    "retragere": dict(structure="neregulat", stories=8, bays=4, travei=3, shape="setback", setback_story=4, setback_bays=2),
    "subsol_pereti": dict(structure="pereti_izolati", stories=5, basement=2, walls=True),
    "podium": dict(structure="turnuri", stories=5, bays=6, travei=4, towers="1,0,4,4,5", basement=2, walls=True,
                   wall_lines_x="first,last", wall_bays_x="middle", wall_lines_y="first,last", wall_bays_y="middle"),
    "doua_turnuri": dict(structure="turnuri", bays=9, travei=3, towers="0,0,3,3,6;5,0,4,3,9", basement=2, **WALLS_X),
    "cerc": dict(structure="cerc", stories=5, free_shape="circle"),
    "semicerc": dict(structure="semicerc", stories=4, free_shape="semicircle", free_radius=14),
    "spline": dict(structure="spline", stories=4, free_shape="spline"),
    "trapez_pereti": dict(structure="trapez", stories=5, walls=True, free_shape="trapezoid", free_wall_edges="all"),
    "piramida": dict(structure="piramida", stories=8, walls=True, free_shape="polygon", free_sides=4, free_radius=14, taper=0.7, free_wall_edges="all"),
    "lobi_atriu_subsol": dict(structure="cerc", stories=5, basement=2, walls=True, free_shape="lobed", free_radius=14, atrium=0.3, free_wall_edges="alternate"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-post", action="store_true", help="doar verificarile pe modelul nerulat")
    ap.add_argument("--only", default="", help="nume separate prin virgula")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-calibrate", action="store_true", help="fara analiza de calibrare a fortelor statice (mai rapid)")
    a = ap.parse_args()
    if a.list:
        print("\n".join(MATRIX))
        return 0
    names = [n for n in (a.only.split(",") if a.only else MATRIX) if n]
    report: dict[str, dict] = {}
    for name in names:
        spec = {"name": name, **MATRIX[name]}
        if a.no_calibrate:
            spec["calibrate_static"] = False
        t0 = time.time()
        try:
            res = h.build(spec)
            pre = h.problems(h.run_check("pre"))
            post = []
            if not a.no_post:
                h.analyze()
                post = h.problems(h.run_check("post"))
        except RuntimeError as e:
            print(f"\n### {name}: EȘUAT — {e}")
            report[name] = {"error": str(e)}
            continue
        report[name] = {"objects": res["objects"], "pre": pre, "post": post, "seconds": round(time.time() - t0)}
        print(f"\n### {name}  ({report[name]['seconds']} s)  {res['objects']}")
        for phase, items in (("nerulat", pre), ("rulat", post)):
            for p in items:
                print(f"  [{phase}] [{p['severity']}] {p['check']}{' (are reparatie)' if p['fix'] else ''}: {p['message'][:170]}")
    os.makedirs(os.path.join(os.path.dirname(__file__), "out"), exist_ok=True)
    with open(os.path.join(os.path.dirname(__file__), "out", "matrix.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
