"""Regula 22 (greutate proprie)."""
from __future__ import annotations

import re

from ..registry import ERROR, INFO, WARNING, Finding, check
from .util import col, sname, yes


@check("r22_greutate_proprie", 22, "Multiplicatorul greutății proprii: 1 la un singur tipar Dead, 0 în rest")
def r22_greutate_proprie(ctx):
    lp = ctx.snap.table("Load Pattern Definitions")
    if lp.empty:
        return [Finding(INFO, "Tabela cu tiparele de încărcare nu a putut fi citită.")]
    sw = lp[lp["SelfWtMult"].fillna(0) != 0]
    names = [("loadpattern", n) for n in sw["Name"]]
    dead = [str(n) for n, t in zip(lp["Name"], lp["Type"]) if str(t) == "Dead"]
    primary_dead = next((n for n in dead if n.lower() in ("dead", "g", "permanent", "permanenta")), dead[0] if dead else None)

    def fx(target: dict, label: str) -> dict:
        return {"id": "set_selfwt", "label": label, "args": {"set": target}}

    out = []
    if sw.empty:
        out.append(Finding(ERROR, "Niciun tipar nu include greutatea proprie (multiplicator 0 peste tot): "
                                  "structura „plutește” fără greutatea elementelor.",
                           fix=fx({primary_dead: 1.0}, f"Setează 1 la „{primary_dead}”") if primary_dead else None))
    elif len(sw) > 1:
        keep = next((str(n) for n, t in zip(sw["Name"], sw["Type"]) if str(t) == "Dead" and str(n) == primary_dead), None)             or next((str(n) for n, t in zip(sw["Name"], sw["Type"]) if str(t) == "Dead"), None)
        target = {str(n): 0.0 for n in sw["Name"] if str(n) != keep} if keep else None
        if target is not None:
            target[keep] = 1.0
        out.append(Finding(ERROR, "Greutatea proprie este inclusă în mai multe tipare (risc de dublare): "
                                  "multiplicatorul trebuie să fie 1 doar la tiparul permanent principal.", names,
                           {n: float(m) for n, m in zip(sw["Name"], sw["SelfWtMult"])},
                           fix=fx(target, f"Păstrează doar „{keep}” (1), restul la 0") if target else None))
    else:
        row = sw.iloc[0]
        if row["Type"] != "Dead":
            out.append(Finding(WARNING, f"Greutatea proprie este în tiparul „{row['Name']}”, care nu este de tip Dead.", names))
        if abs(float(row["SelfWtMult"]) - 1.0) > 1e-9:
            out.append(Finding(WARNING, f"Multiplicatorul greutății proprii este {float(row['SelfWtMult']):g}, nu 1.", names,
                               fix=fx({str(row["Name"]): 1.0}, f"Setează 1 la „{row['Name']}”")))
    return out


# ---------------------------------------------------------------- regula 6
@check("r6_sursa_masa", 6, "Sursa de masă: greutate proprie, încărcări cu multiplicatori, fără dublări")
def r6_sursa_masa(ctx):
    ms = ctx.snap.table("Mass Source Definition")
    lp = ctx.snap.table("Load Pattern Definitions")
    if ms.empty:
        return [Finding(ERROR, "Nu există nicio sursă de masă definită.")]
    sw = {str(r["Name"]): float(r["SelfWtMult"] or 0) for _, r in lp.iterrows()} if not lp.empty else {}
    typ = {str(r["Name"]): str(r["Type"]) for _, r in lp.iterrows()} if not lp.empty else {}
    out = []
    ms = ms.copy()
    ms["Name"] = ms["Name"].replace("", None).ffill()
    for name, grp in ms.groupby("Name", sort=False):
        head = grp.iloc[0]
        obj = [("masssource", str(name))]
        pats = ([(str(p), float(m)) for p, m in zip(grp["LoadPattern"], grp["Multiplier"]) if str(p).strip() and m == m and str(m) != ""]
                if {"LoadPattern", "Multiplier"} <= set(grp.columns) else [])          # masa doar din elemente: tabelul nu are aceste coloane
        lateral, self_mass = yes(head["IncLateral"]), yes(head["SourceSelf"])
        use_loads = yes(head["SourceLoads"])
        if not lateral:
            out.append(Finding(ERROR, f"Sursa de masă „{name}” nu include masa laterală.", obj))
        if not self_mass and not (use_loads and pats):
            out.append(Finding(ERROR, f"Sursa de masă „{name}” nu include nici masa elementelor, nici încărcări: masa seismică lipsește.", obj))
        if use_loads and not pats:
            out.append(Finding(WARNING, f"Sursa de masă „{name}” folosește încărcări, dar lista de tipare e goală.", obj))
        if self_mass:
            dbl = [p for p, _m in pats if sw.get(p, 0) != 0]
            if dbl:
                out.append(Finding(ERROR, f"Sursa de masă „{name}” include masa proprie ȘI tipare cu greutate proprie "
                                          f"({', '.join(dbl)}): greutatea elementelor se dublează.",
                                   obj + [("loadpattern", p) for p in dbl]))
        bad_m = [p for p, m in pats if m < 0 or m > 1.0 + 1e-9]
        if bad_m:
            out.append(Finding(WARNING, f"Multiplicatori în afara intervalului [0, 1] în „{name}”: {', '.join(bad_m)}.",
                               [("loadpattern", p) for p in bad_m]))
        wrong = [p for p, _m in pats if typ.get(p) in ("Seismic", "Quake", "Wind")]
        if wrong:
            out.append(Finding(WARNING, f"Tipare seismice/de vânt incluse în masă în „{name}”: {', '.join(wrong)}.",
                               [("loadpattern", p) for p in wrong]))
        perm = [p for p, m in pats if typ.get(p) in ("Dead", "Super Dead") and abs(m - 1.0) > 1e-9 and sw.get(p, 0) == 0]
        if perm:
            out.append(Finding(WARNING, f"Încărcări permanente cu multiplicator diferit de 1 în „{name}”: {', '.join(perm)}.",
                               [("loadpattern", p) for p in perm]))
    modal = []
    for key in ("Modal Case Definitions - Eigen", "Modal Case Definitions - Ritz"):
        df = ctx.snap.table(key)
        c = col(df, "MassSource") if not df.empty else None
        if c:
            modal += [(str(r["Name"]), str(r[c])) for _, r in df.iterrows()]
    if len({m for _n, m in modal}) > 1:
        out.append(Finding(WARNING, "Cazurile modale folosesc surse de masă diferite: " + ", ".join(f"{n}→{m}" for n, m in modal) + ".",
                           [("loadcase", n) for n, _m in modal]))
    return out


# ---------------------------------------------------------------- utilizarea tiparelor
def pattern_usage(ctx) -> dict[str, dict]:
    """Pentru fiecare tipar: cate arii (direct sau prin seturi de incarcari uniforme), bare si noduri il folosesc."""
    from collections import Counter, defaultdict
    t = ctx.snap.table
    usage: dict[str, dict] = defaultdict(lambda: {"arii": 0, "bare": 0, "noduri": 0, "seturi": []})
    sets_assign, shell = t("Area Load Assignments - Uniform Load Sets"), t("Shell Uniform Load Sets")
    if not sets_assign.empty and not shell.empty:
        per_set = Counter(str(x) for x in sets_assign["LoadSet"])
        for _, r in shell.iterrows():
            n = per_set.get(str(r["Name"]), 0)
            if n:
                u = usage[str(r["LoadPattern"])]
                u["arii"] += n
                u["seturi"].append(str(r["Name"]))
    ul = t("Load Pattern Definitions - Auto Seismic - User Loads")
    if not ul.empty:                                                 # forte seismice date pe niveluri/diafragme
        u2 = ul.copy()
        u2["Name"] = u2["Name"].replace("", None).ffill()
        for n, g in u2.groupby("Name"):
            usage[str(n)]["noduri"] += int(((g["Fx"].fillna(0) != 0) | (g["Fy"].fillna(0) != 0)).sum())
    for key, field in (("Area Load Assignments - Uniform", "arii"), ("Area Load Assignments - Non-uniform", "arii"),
                       ("Area Load Assignments - Temperature", "arii"), ("Frame Loads Assignments - Distributed", "bare"),
                       ("Frame Loads Assignments - Point", "bare"), ("Frame Loads Assignments - Temperature", "bare"),
                       ("Joint Loads Assignments - Force", "noduri"), ("Joint Loads Assignments - Ground Displacement", "noduri"),
                       ("Joint Loads Assignments - Temperature", "noduri")):
        df = t(key)
        c = col(df, "LoadPattern") if not df.empty else None
        if c:
            for p, n in Counter(str(x) for x in df[c]).items():
                usage[p][field] += n
    return dict(usage)


def has_loads(u: dict | None) -> bool:
    return bool(u and (u["arii"] or u["bare"] or u["noduri"]))


# ---------------------------------------------------------------- regula 7
_NAME_RULES = [
    (re.compile(r"zapad|snow", re.I), {"Snow"}, "zăpadă"),
    (re.compile(r"vant|wind", re.I), {"Wind"}, "vânt"),
    (re.compile(r"seism|quake|cutremur", re.I), {"Seismic", "Quake"}, "seism"),
    (re.compile(r"temperatur|termic", re.I), {"Temperature"}, "temperatură"),
    (re.compile(r"util|live|trafic|traffic|pompieri", re.I), {"Live", "Reduce Live", "Roof Live", "Other"}, "utilă"),
]


_PROPOSED = {"zăpadă": "Snow", "vânt": "Wind", "seism": "Quake", "temperatură": "Temperature", "utilă": "Live"}


@check("r7_tipare", 7, "Tipare de încărcare: tip corect și încărcări asignate")
def r7_tipare(ctx):
    t = ctx.snap.table
    lp = t("Load Pattern Definitions")
    if lp.empty:
        return []
    usage = pattern_usage(ctx)
    used = {p for p, u in usage.items() if has_loads(u)}
    out = []
    unused = []
    for _, r in lp.iterrows():
        n = str(r["Name"])
        auto = yes(r.get("IsAuto", "No")) or str(r.get("AutoLoad", "")).strip() not in ("", "None")
        if n not in used and not auto and float(r.get("SelfWtMult") or 0) == 0:
            unused.append(n)
    if unused:
        out.append(Finding(WARNING, f"{len(unused)} tipare de încărcare nu au nicio încărcare asignată: " + ", ".join(unused) + ".",
                           [("loadpattern", n) for n in unused]))
    wrong = []
    for _, r in lp.iterrows():
        n, ty = str(r["Name"]), str(r["Type"])
        for rx, ok_types, label in _NAME_RULES:
            if rx.search(n):
                if ty not in ok_types:
                    wrong.append((n, f"numele sugerează {label}, tipul este {ty}", _PROPOSED[label]))
                break
    if wrong:
        out.append(Finding(WARNING, f"{len(wrong)} tipare au un tip care nu corespunde numelui (ex. zăpadă sau încărcare utilă definite ca Dead).",
                           [("loadpattern", n) for n, _w, _t in wrong], {n: w for n, w, _t in wrong},
                           fix={"id": "set_load_types", "label": "Corectează tipul tiparelor",
                                "args": {"rows": [{"name": n, "type": t} for n, _w, t in wrong]}}))
    return out
