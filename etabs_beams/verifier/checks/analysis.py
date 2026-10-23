"""Reguli 10 (setari de analiza) si 21 (3D complet + diafragme pentru CM/CR)."""
from __future__ import annotations

import re

from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .util import col, header_rows, sname, yes

_DOF = ["UX", "UY", "UZ", "RX", "RY", "RZ"]


@check("r21_dof_diafragme", 21, "Analiză 3D completă și diafragme (necesare pentru centrele de masă/rigiditate)")
def r21_dof_diafragme(ctx):
    out = []
    dof = ctx.snap.table("Analysis Options - Active Degrees of Freedom")
    if dof.empty:
        out.append(Finding(INFO, "Gradele de libertate active nu au putut fi citite."))
    else:
        off = [d for d in _DOF if d in dof.columns and not yes(dof.iloc[0][d])]
        if off:
            out.append(Finding(ERROR, f"Gradele de libertate dezactivate: {', '.join(off)}. "
                                      "Pentru o clădire 3D trebuie active toate cele 6.", data={"dezactivate": off},
                               fix={"id": "set_dof_all", "label": "Activează toate gradele de libertate", "args": {}}))
    dia = ctx.snap.table("Diaphragm Definitions")
    assigned = len(ctx.snap.table("Area Assignments - Diaphragms")) + len(ctx.snap.table("Joint Assignments - Diaphragms"))
    if dia.empty:
        out.append(Finding(WARNING, "Nu există nicio diafragmă definită: centrele de rigiditate și masă nu pot fi calculate."))
    elif assigned == 0:
        out.append(Finding(WARNING, "Diafragmele sunt definite, dar nu sunt asignate niciunui nod sau plăci."))
    return out


def _count_stories(ctx) -> int:
    """Etajele care vibreaza: cele peste teren, la cel mai inalt turn (subsolul rigid nu se numara, daca utilizatorul l-a declarat)."""
    st = ctx.snap.table("Story Definitions")
    n = int(st.groupby("Tower").size().max()) if "Tower" in st.columns and len(st) else len(st)
    return max(n - len(ctx.basement_stories() or []), 0)


@check("r10_moduri", 10, "Număr suficient de moduri de vibrație (≥ 3 pe etaj)",
       params=[Param("moduri_per_etaj", 3, "Moduri cerute pe fiecare etaj", "buc")])
def r10_moduri(ctx):
    summary = ctx.snap.table("Load Case Definitions - Summary")
    modal = summary[summary["Type"].astype(str).str.startswith("Modal")] if not summary.empty else summary
    if modal.empty:
        return [Finding(ERROR, "Nu există niciun caz modal definit.")]
    stories = _count_stories(ctx)
    need = int(ctx.p("moduri_per_etaj") * stories)
    out = []
    for key, kind in (("Modal Case Definitions - Eigen", "Eigen"), ("Modal Case Definitions - Ritz", "Ritz")):
        df = ctx.snap.table(key)
        if df.empty:
            continue
        mx = col(df, "MaxModes")
        for _, r in header_rows(df).iterrows():
            have = int(r[mx]) if mx and r[mx] == r[mx] else 0
            if stories and have < need:
                out.append(Finding(ERROR,
                                   f"Cazul modal „{r['Name']}” ({kind}) cere {have} moduri, dar pentru {stories} etaje "
                                   f"sunt recomandate cel puțin {need} ({ctx.p('moduri_per_etaj'):g} pe etaj).",
                                   [("loadcase", str(r["Name"]))], {"moduri": have, "recomandat": need, "etaje": stories},
                                   fix={"id": "set_modal_modes", "label": f"Setează {need} moduri", "args": {"cases": [{"name": str(r["Name"]), "max": need}]}}
                                   if kind == "Eigen" else None))
    return out


_AXES = {"X": re.compile(r"^(Accel\s+)?(UX|U1)$", re.I), "Y": re.compile(r"^(Accel\s+)?(UY|U2)$", re.I), "Z": re.compile(r"^(Accel\s+)?(UZ|U3)$", re.I)}


def _ritz_fix(name, missing) -> dict:
    return {"id": "ritz_add_accel", "label": f"Adaugă accelerațiile {', '.join(missing)}", "args": {"cases": [{"name": str(name), "missing": list(missing)}]}}


@check("r10_ritz", 10, "Caz Ritz cu accelerații pe X, Y și Z ca vectori de pornire")
def r10_ritz(ctx):
    df = ctx.snap.table("Modal Case Definitions - Ritz")
    if df.empty:
        return []
    out = []
    ms = ctx.snap.table("Mass Source Definition")
    iv = col(ms, "IncVertical") if not ms.empty else None
    vertical = bool(iv) and any(yes(v) for v in ms[iv])             # fara masa verticala, vectorul de pornire pe Z ar fi nul (ETABS il elimina)
    ltype, lname = col(df, "LoadType"), col(df, "LoadName")
    df = df.copy()
    df["Name"] = df["Name"].replace("", None).ffill()
    for name, grp in df.groupby("Name"):
        accel = [str(n).strip() for t, n in zip(grp[ltype], grp[lname]) if "accel" in str(t).lower()] if ltype and lname else []
        miss = [ax for ax, rx in _AXES.items() if (vertical or ax != "Z") and not any(rx.match(a) for a in accel)]
        if "X" in miss or "Y" in miss:
            out.append(Finding(ERROR, f"Cazul Ritz „{name}” nu include accelerația pe {', '.join(m for m in miss if m != 'Z')} "
                                      "ca vector de încărcare de pornire.", [("loadcase", str(name))], {"lipsa": miss},
                               fix=_ritz_fix(name, miss)))
        elif "Z" in miss:
            out.append(Finding(WARNING, f"Cazul Ritz „{name}” nu include accelerația pe Z.", [("loadcase", str(name))], fix=_ritz_fix(name, miss)))
    return out


@check("r10_pdelta", 10, "Efecte de ordinul II (P-Delta) activate")
def r10_pdelta(ctx):
    t = ctx.snap.table
    pd_opt = t("P-Delta Option Definition")
    auto = str(pd_opt.iloc[0].get("AutoMethod", "None")) if not pd_opt.empty else "None"
    sources = []
    if auto not in ("None", "", "nan"):
        sources.append(f"opțiunea globală P-Delta ({auto})")
    for key, c in (("Load Case Definitions - Linear Static", "StiffType"), ("Modal Case Definitions - Eigen", "StiffType"),
                   ("Modal Case Definitions - Ritz", "StiffType")):
        df = t(key)
        cc = col(df, c) if not df.empty else None
        if cc and df[cc].astype(str).str.contains("P-Delta", case=False).any():
            sources.append("rigiditate P-Delta în cazuri")
            break
    nl = t("Load Case Definitions - Nonlinear Static")
    g = col(nl, "GeoNonlin") if not nl.empty else None
    if g and nl[g].astype(str).str.contains("P-Delta", case=False).any():
        sources.append("neliniaritate geometrică P-Delta în cazuri neliniare")
    if not sources:
        return [Finding(WARNING, "Efectele P-Delta nu sunt activate nicăieri (opțiune globală, rigiditate sau cazuri neliniare).")]
    return [Finding(INFO, "P-Delta activ prin: " + "; ".join(dict.fromkeys(sources)) + ".")]
