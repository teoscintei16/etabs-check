"""Reguli 2 (rezemare), 3 (diafragme), 17 (temperatura), 18 (constructie etapizata), 23 (truss/tension-only), 24 (presiuni)."""
from __future__ import annotations

import re

from ...models import BRACE
from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .frames import _end_released, _releases
from .util import col, sname, yes


def _joints(ctx):
    j = ctx.snap.table("Objects and Elements - Joints")
    if j.empty:
        return j
    j = j[j["ObjType"].astype(str) == "Joint"].drop_duplicates("ObjName").copy()
    j["_n"] = [sname(x) for x in j["ObjName"]]
    return j


def _names(df) -> set[str]:
    c = col(df, "UniqueName") if not df.empty else None
    return {sname(x) for x in df[c]} if c else set()


@check("r2_rezemare", 2, "Rezemarea la bază: noduri nerezemate, bază articulată, arcuri (ks) și unități",
       params=[Param("ks_min", 1000.0, "Coeficient de pat minim plauzibil", "kN/m³"),
               Param("ks_max", 500000.0, "Coeficient de pat maxim plauzibil", "kN/m³")])
def r2_rezemare(ctx):
    t = ctx.snap.table
    out = []
    tw = t("Tower and Base Story Definitions")
    j = _joints(ctx)
    restr, springs = t("Joint Assignments - Restraints"), t("Joint Assignments - Springs")
    rn, sn = _names(restr), _names(springs)
    area_spr = t("Area Assignments - Area Springs")
    area_joints: set[str] = set()
    floor_joints: set[str] = set()                 # noduri ale placilor (radier): rezemate prin placa, nu individual
    el = t("Objects and Elements - Areas")
    if not el.empty:
        jc = [c for c in el.columns if c.startswith("ElmJt")]
        spring_areas = _names(area_spr) if not area_spr.empty else set()
        for _, r in el[el["ObjType"].astype(str) == "Floor"].iterrows():
            js = {sname(r[c]) for c in jc if str(r[c]).strip() and not str(r[c]).startswith("~")}
            floor_joints |= js
            if sname(r["ObjName"]) in spring_areas:
                area_joints |= js
    if not j.empty and not tw.empty:
        base_ids = ({str(r["BSName"]) for _, r in tw.iterrows()} | {f"{r['Tower']}-{r['BSName']}" for _, r in tw.iterrows()})
        base = ", ".join(sorted({str(x) for x in tw["BSName"]}))
        bj = j[j["Story"].astype(str).isin(base_ids)]
        free = bj[~bj["_n"].isin(rn | sn | area_joints | floor_joints)]
        if len(free):
            out.append(Finding(ERROR, f"{len(free)} noduri de la baza modelului („{base}”) nu au nici reazem, nici arc: "
                                      "elementele conectate la ele „zboară”.",
                               [("joint", r["_n"], {"label": str(r["ObjLabel"]), "story": str(r["Story"])}) for _, r in free.iterrows()]))
        out.append(Finding(INFO, f"La baza modelului („{base}”): {len(rn)} noduri cu reazeme, {len(sn)} noduri cu arcuri punctuale, "
                                 f"{len(area_joints)} noduri sub arcuri de suprafață, {len(floor_joints & set(bj['_n']))} noduri aparțin plăcilor "
                                 f"(din {len(bj)} noduri la bază)."))
    if not restr.empty:
        tr = [c for c in ("UX", "UY", "UZ") if c in restr.columns]
        ro = [c for c in ("RX", "RY", "RZ") if c in restr.columns]
        pinned = restr[restr[tr].apply(lambda r: all(yes(v) for v in r), axis=1) & ~restr[ro].apply(lambda r: any(yes(v) for v in r), axis=1)]
        if len(pinned) == len(restr) and not sn and not area_joints:
            out.append(Finding(WARNING, "Toate reazemele de la bază sunt articulate (translații blocate, rotiri libere) și nu există arcuri: "
                                        "o structură în cadre devine instabilă.", [("joint", sname(r["UniqueName"]), {"label": str(r["Label"]), "story": str(r["Story"])})
                                                                                   for _, r in pinned.head(200).iterrows()]))
    if ctx.basement_stories() == [] and not restr.empty:                 # doar suprastructura: trebuie incastrata la baza
        cols = [c for c in ("UX", "UY", "UZ", "RX", "RY", "RZ") if c in restr.columns]
        partial = restr[~restr[cols].apply(lambda r: all(yes(v) for v in r), axis=1)]
        if len(partial):
            out.append(Finding(ERROR, f"Model doar cu suprastructura: {len(partial)} reazeme de la bază nu sunt încastrate (nu blochează toate cele 6 grade de libertate).",
                               [("joint", sname(r["UniqueName"]), {"label": str(r["Label"]), "story": str(r["Story"])}) for _, r in partial.head(200).iterrows()]))
    sp = t("Spring Property Definitions - Area Springs")
    if not sp.empty:
        lo, hi = ctx.p("ks_min"), ctx.p("ks_max")
        for _, r in sp.iterrows():
            k3 = float(r.get("StiffU3") or 0)
            if k3 and not (lo <= k3 <= hi):
                out.append(Finding(WARNING, f"Arcul de suprafață „{r['Name']}” are ks vertical = {k3:g} kN/m³, în afara intervalului {lo:g}–{hi:g}: "
                                            "posibile unități greșite (kN/m în loc de kN/m³).", [("spring", str(r["Name"]))]))
            if float(r.get("StiffU1") or 0) or float(r.get("StiffU2") or 0):
                out.append(Finding(INFO, f"Arcul „{r['Name']}” are rigiditate pe X/Y: se justifică doar dacă e necesar (altfel pot apărea artefacte).",
                                   [("spring", str(r["Name"]))]))
            nl = str(r.get("NonlinOpt3", ""))
            if "compression" not in nl.lower():
                out.append(Finding(INFO, f"Arcul „{r['Name']}” nu e „Compression Only” (radier cu coeficient de pat: recomandat compresiune numai).",
                                   [("spring", str(r["Name"]))]))
        if area_spr.empty:
            out.append(Finding(INFO, f"Proprietăți de arc de suprafață definite ({', '.join(map(str, sp['Name']))}), dar neasignate niciunei arii."))
    return out


def _diaphragm_proposals(ctx, asg, dsg, miss):
    """Diafragma fiecarei placi fara diafragma = cea mai frecventa dintre placile cu diafragma de la acelasi nivel (si turn)."""
    from collections import Counter
    story_of = {sname(r["UniqueName"]): str(r["Story"]) for _, r in asg.iterrows()}
    by_story: dict[str, Counter] = {}
    if not dsg.empty:
        for _, r in dsg.iterrows():
            d = str(r["Diaphragm"]).strip()
            if d not in ("None", ""):
                by_story.setdefault(story_of.get(sname(r["UniqueName"]), ""), Counter())[d] += 1
    assign, unknown = [], []
    for _, r in miss.iterrows():
        name = sname(r["UniqueName"])
        c = by_story.get(str(r["Story"]))
        if c:
            assign.append({"name": name, "diaphragm": c.most_common(1)[0][0]})
        else:
            unknown.append(name)
    return assign, unknown


@check("r3_diafragme", 3, "Diafragme și tipul elementelor de placă",
       params=[Param("fara_diafragma_exceptii", "radier", "Secțiuni de placă fără diafragmă acceptate (text din nume)", "", "text")])
def r3_diafragme(ctx):
    t = ctx.snap.table
    out = []
    dia = t("Diaphragm Definitions")
    if not dia.empty:
        rigid = [str(r["Name"]) for _, r in dia.iterrows() if str(r["Rigidity"]).lower().startswith("rigid")]
        if rigid:
            out.append(Finding(INFO, f"Diafragme rigide: {', '.join(rigid)}. Se recomandă semi-rigide; rigidul se justifică prin compararea deformațiilor.",
                               [("diaphragm", n) for n in rigid]))
    sec = t("Area Section Property Definitions - Summary")
    if not sec.empty:
        mem = sec[(sec["Type"].astype(str) == "Slab") & (sec["AnalType"].astype(str).str.lower() == "membrane")]
        if len(mem):
            out.append(Finding(WARNING, "Plăci modelate ca „Membrane”: nu preiau încovoiere (valabil doar pentru plăci rezemate pe grinzi, nu pentru dale).",
                               [("section", str(n)) for n in mem["Name"]]))
    asg, dsg = t("Area Assignments - Section Properties"), t("Area Assignments - Diaphragms")
    if not asg.empty:
        slabs = asg[asg["PropType"].astype(str) == "Slab"]
        have = {sname(r["UniqueName"]) for _, r in dsg.iterrows() if str(r["Diaphragm"]).strip() not in ("None", "")} if not dsg.empty else set()
        skip = str(ctx.p("fara_diafragma_exceptii")).strip().lower()
        miss = slabs[~slabs["UniqueName"].map(sname).isin(have)]
        tw = t("Tower and Base Story Definitions")
        base_story = ({str(r["BSName"]) for _, r in tw.iterrows()} | {f"{r['Tower']}-{r['BSName']}" for _, r in tw.iterrows()}) if not tw.empty else set()
        miss = miss[~miss["Story"].astype(str).isin(base_story)]          # placile nivelului de baza (radier) nu au diafragma
        if skip:
            miss = miss[~miss["SectProp"].astype(str).str.lower().str.contains(re.escape(skip))]
        if len(miss):
            assign, unknown = _diaphragm_proposals(ctx, asg, dsg, miss)
            extra = f" Pentru {len(unknown)} nu există o diafragmă de referință la același nivel." if unknown else ""
            out.append(Finding(ERROR, f"{len(miss)} plăci nu sunt asignate niciunei diafragme (rămân fără legătură rigidă/semi-rigidă în plan): "
                                      "fără diafragmă nu se transmit forțele laterale și nu se pot calcula CM/CR." + extra,
                               [("area", sname(r["UniqueName"]), {"label": str(r["Label"]), "story": str(r["Story"]), "section": str(r["SectProp"])})
                                for _, r in miss.iterrows()],
                               fix={"id": "assign_diaphragm", "label": f"Asignează diafragma la {len(assign)} plăci", "args": {"assign": assign}} if assign else None))
    return out


@check("r17_temperatura", 17, "Efecte de temperatură pentru clădiri lungi",
       params=[Param("lungime_max", 45.0, "Lungimea peste care se cere ΔT (fără rosturi)", "m")])
def r17_temperatura(ctx):
    j = _joints(ctx)
    if j.empty:
        return []
    L = max(float(j["GlobalX"].max() - j["GlobalX"].min()), float(j["GlobalY"].max() - j["GlobalY"].min()))
    lp = ctx.snap.table("Load Pattern Definitions")
    temps = [str(r["Name"]) for _, r in lp.iterrows() if str(r["Type"]) == "Temperature"] if not lp.empty else []
    used = set()
    for key in ("Area Load Assignments - Temperature", "Frame Loads Assignments - Temperature", "Joint Loads Assignments - Temperature"):
        df = ctx.snap.table(key)
        c = col(df, "LoadPattern") if not df.empty else None
        if c:
            used |= {str(x) for x in df[c]}
    if temps:
        empty = [n for n in temps if n not in used]
        if empty:
            return [Finding(WARNING, f"Tiparele de temperatură nu au încărcări asignate: {', '.join(empty)}.", [("loadpattern", n) for n in empty])]
        return [Finding(INFO, f"Există încărcări de temperatură ({', '.join(temps)}); lungimea clădirii este {L:.1f} m.")]
    if L > ctx.p("lungime_max"):
        return [Finding(WARNING, f"Clădirea are {L:.1f} m în plan (> {ctx.p('lungime_max'):g} m) și nu are caz de temperatură. "
                                 "Dacă există rosturi de dilatare, justifică această constatare.", data={"lungime_m": round(L, 1)})]
    return []


@check("r18_constructie_etapizata", 18, "Construcție etapizată la clădiri înalte",
       params=[Param("etaje_min", 15, "Număr de etaje de la care se recomandă analiza etapizată", "etaje")])
def r18_constructie_etapizata(ctx):
    st_df = ctx.snap.table("Story Definitions")
    n = int(st_df.groupby("Tower").size().max()) if not st_df.empty and "Tower" in st_df.columns else len(st_df)       # cel mai inalt turn
    staged = ctx.snap.table("Load Case Definitions - Nonlinear Staged Construction")
    if n >= ctx.p("etaje_min") and staged.empty:
        return [Finding(WARNING, f"Clădirea are {n} niveluri și nu există caz de construcție etapizată: scurtarea axială cumulată a stâlpilor "
                                 "poate încărca fals grinzile din etajele superioare.")]
    if not staged.empty:
        return [Finding(INFO, "Există caz de construcție etapizată.")]
    return []


@check("r23_truss_tension", 23, "Contravântuiri și elemente tension-only: eliberări și cazuri neliniare")
def r23_truss_tension(ctx):
    out = []
    model = ctx.snap.model
    braces = [f.name for f in model.frames.values() if f.orientation == BRACE and f.section]
    if braces:
        rel = _releases(ctx)
        fixed = [b for b in braces if not (_end_released(rel.get(b), "I") and _end_released(rel.get(b), "J"))]
        if fixed:
            out.append(Finding(WARNING, f"{len(fixed)} contravântuiri nu au eliberări de moment la ambele capete: pot prelua încovoiere și rigidizează fals cadrele.",
                               [("frame", b) for b in fixed]))
    tl = ctx.snap.table("Frame Assignments - Tension and Compression Limits")
    if not tl.empty:
        nl = ctx.snap.table("Load Case Definitions - Nonlinear Static")
        if nl.empty and ctx.snap.table("Load Case Definitions - Nonlinear Staged Construction").empty:
            out.append(Finding(WARNING, f"{len(tl)} bare au limite de întindere/compresiune, dar nu există cazuri neliniare: "
                                        "comportamentul tension-only nu se activează în analiza liniară.",
                               [("frame", sname(x)) for x in tl[col(tl, "UniqueName")]]))
    return out


_SOIL = re.compile(r"pamant|pământ|soil|earth|impinger|împinger|hidrostat|water|\bapa\b|\bapă\b", re.I)


@check("r24_presiuni", 24, "Împingerea pământului / apei la pereții de subsol")
def r24_presiuni(ctx):
    below = ctx.basement_stories()
    if below == []:
        return [Finding(INFO, "Model fără subsol: verificarea presiunii pământului nu se aplică.")]
    if below is None:
        return [Finding(INFO, "Nu pot stabili dacă există subsoluri: indică în Setări dacă există subsol și nivelurile lui.")]
    lp = ctx.snap.table("Load Pattern Definitions")
    soil = [str(r["Name"]) for _, r in lp.iterrows() if _SOIL.search(str(r["Name"]))] if not lp.empty else []
    if not soil:
        return [Finding(WARNING, f"Există {len(below)} niveluri de subsol ({', '.join(below)}), dar niciun tipar de încărcare pentru presiunea pământului/apei.")]
    used = set()
    for key in ("Area Load Assignments - Non-uniform", "Area Load Assignments - Uniform", "Area Load Assignments - Uniform Load Sets",
                "Joint Loads Assignments - Force", "Frame Loads Assignments - Distributed"):
        df = ctx.snap.table(key)
        c = col(df, "LoadPattern") if not df.empty else None
        if c:
            used |= {str(x) for x in df[c]}
    empty = [n for n in soil if n not in used]
    if empty:
        return [Finding(WARNING, f"Tiparele de presiune ({', '.join(empty)}) nu au încărcări asignate.", [("loadpattern", n) for n in empty])]
    return [Finding(INFO, f"Tipare de presiune: {', '.join(soil)}. Sensul presiunii (spre interior) se verifică vizual.")]
