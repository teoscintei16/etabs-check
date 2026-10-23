"""Testeaza reparatiile cu un click ale verificatorului pe modele cu defecte intentionate (create de creator).

Pentru fiecare defect: construieste modelul → verificatorul trebuie sa-l semnaleze cu reparatia asteptata → previzualizare → aplicare →
reverificare (defectul a disparut si nu a aparut nimic nou) → anulare (defectul reapare). Orice blocaj (eroare ETABS, model ramas blocat,
defect ramas, regresie) se raporteaza.

Utilizare:  python scripts/fix_roundtrip.py [--only modes_few,dof_off] [--list]
Cere: instanta ETABS deschisa din creator (python -m etabs_creator) si verificatorul pornit (python -m etabs_beams serve)."""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import harness as h  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

FRAME = dict(structure="cadre", stories=4, bays=3, travei=3, calibrate_static=False)
WALLS = dict(structure="pereti_izolati", stories=4, bays=3, travei=3, walls=True, calibrate_static=False)
TOWERS = dict(structure="turnuri", bays=7, travei=3, towers="0,0,3,3,3;4,0,3,3,3", walls=True, wall_lines_x="first,last", wall_bays_x="middle",
              wall_lines_y="none", wall_bays_y="none", calibrate_static=False)

# defect: (specificatia de baza, verificarile urmarite, reparatiile asteptate)
CASES = {
    "modes_few": (FRAME, ["r10_moduri"], {"set_modal_modes"}),
    "ritz_no_accel": (FRAME, ["r10_ritz"], {"ritz_add_accel"}),
    "selfwt_none": (FRAME, ["r22_greutate_proprie"], {"set_selfwt"}),
    "selfwt_double": (FRAME, ["r22_greutate_proprie"], {"set_selfwt"}),
    "dof_off": (FRAME, ["r21_dof_diafragme"], {"set_dof_all"}),
    "pattern_type_wrong": (FRAME, ["r7_tipare"], {"set_load_types"}),
    "no_rigid_zones": (FRAME, ["r13_zone_rigide"], {"set_rigid_factor"}),
    "slab_no_diaphragm": (FRAME, ["r3_diafragme"], {"assign_diaphragm"}),
    "parasitic_nodes": (FRAME, ["r5_noduri"], {"move_nodes"}),
    "secondary_beams": (FRAME, ["r11_grinzi_secundare"], {"release_secondary"}),
    "mesh_nonstandard": (WALLS, ["r5_mesh"], {"apply_mesh_standard"}),
    "pier_same_labels": (TOWERS, ["r28_pier_pe_corpuri"], {"rename_piers"}),
}


def key(p: dict) -> tuple:
    return p["check"], p["message"][:60]


def fixes_for(results: dict, checks: list[str], wanted: set[str]) -> list[dict]:
    out = []
    for cid in checks:
        for f in results.get(cid, {}).get("findings", []):
            if f.get("fix") and f["fix"]["id"] in wanted and not f["waived"]:
                out.append(f["fix"])
    return out


def apply_like_gui(fix: dict) -> tuple[dict, dict]:
    """Previzualizeaza si aplica o reparatie ca GUI-ul: intrarile cu valorile propuse, randurile editabile toate bifate."""
    pv = h.call(h.CHECK, "/api/v/fix/preview", {"fix": fix["id"], "args": fix["args"]})
    args = dict(fix["args"])
    for i in pv.get("inputs") or []:
        args[i["key"]] = i["value"]
    if pv.get("rows"):
        args[pv["rows"]["key"]] = [{**r, "include": True} for r in pv["rows"]["items"]]
    done = h.call(h.CHECK, "/api/v/fix/apply", {"fix": fix["id"], "args": args, "analyze": False})
    return pv, done


def run_case(name: str) -> dict:
    spec, checks, wanted = CASES[name]
    out = {"case": name, "ok": False, "notes": []}
    t0 = time.time()
    h.build({"name": f"fix_{name}", **spec, "defects": ""})
    base = h.problems(h.run_check("pre"))
    h.build({"name": f"fix_{name}", **spec, "defects": name})
    before_results = h.run_check("pre")
    before = h.problems(before_results)
    offered = fixes_for(before_results, checks, wanted)
    if not offered:
        out["notes"].append(f"defectul nu a fost semnalat cu reparația {sorted(wanted)} (probleme: {[p['check'] for p in before if p['check'] in checks]})")
        return out
    applied = []
    for fix in offered:
        try:
            pv, done = apply_like_gui(fix)
        except RuntimeError as e:
            out["notes"].append(f"BLOCAJ la aplicarea {fix['id']}: {e}")
            return out
        applied.append(done["id"])
        out["notes"].append(f"{fix['id']}: {len(pv.get('changes', []))} modificări, avertismente: {len(pv.get('warnings', []))}")
    after_results = h.run_check("pre")
    after = h.problems(after_results)
    still = fixes_for(after_results, checks, wanted)
    if still:
        out["notes"].append(f"DEFECTUL A RĂMAS după reparare: {[f['label'] for f in still]}")
        return out
    new = [p for p in after if key(p) not in {key(b) for b in before} and key(p) not in {key(b) for b in base}]
    if new:
        out["notes"].append("REGRESII după reparare: " + "; ".join(f"{p['check']}: {p['message'][:90]}" for p in new))
        return out
    st = h.call(h.CHECK, "/api/status")
    out["notes"].append(f"reparat; model {'analizat' if st.get('analyzed') else 'neanalizat'}")
    for fid in reversed(applied):
        try:
            h.call(h.CHECK, f"/api/v/fix/undo/{fid}", {})
        except RuntimeError as e:
            out["notes"].append(f"BLOCAJ la anulare: {e}")
            return out
    back = fixes_for(h.run_check("pre"), checks, wanted)
    if not back:
        out["notes"].append("ANULAREA NU A RESTAURAT defectul")
        return out
    out["notes"].append("anulare ok (defectul reapare)")
    out["ok"] = True
    out["seconds"] = round(time.time() - t0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(CASES))
        return 0
    names = [n for n in (a.only.split(",") if a.only else CASES) if n]
    bad = 0
    for n in names:
        try:
            r = run_case(n)
        except RuntimeError as e:
            r = {"case": n, "ok": False, "notes": [f"EROARE: {e}"]}
        bad += not r["ok"]
        print(f"{'OK  ' if r['ok'] else 'FAIL'} {n:20s} " + " | ".join(r["notes"]), flush=True)
    print(f"\n{len(names) - bad}/{len(names)} reparații funcționează de la cap la cap.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
