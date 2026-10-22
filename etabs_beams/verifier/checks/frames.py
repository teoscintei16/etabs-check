"""Reguli 11/25 (eliberari), 13 (zone rigide), 14 (axe locale), 15 (elemente Null)."""
from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from ...geometry import end_on_beam_hits
from ...models import COLUMN, NULL
from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .util import col, frame_objects, sname, yes

_REL = ("P", "V2", "V3", "T", "M2", "M3")


def _releases(ctx) -> dict[str, dict[str, bool]]:
    """{nume_unic: {'PI': bool, 'TJ': bool, ...}} din tabelul de eliberari / partial fixity."""
    df = ctx.snap.table("Frame Assignments - Releases and Partial Fixity")
    out: dict[str, dict[str, bool]] = {}
    if df.empty:
        return out
    uc = col(df, "UniqueName")
    for _, r in df.iterrows():
        d = {}
        for q in _REL:
            for end in ("I", "J"):
                c = col(df, f"{q}{end}")
                d[f"{q}{end}"] = yes(r[c]) if c else False
                s = col(df, f"{q}{end} Spring")
                d[f"{q}{end}_spring"] = bool(s and r[s] not in ("", 0, 0.0) and r[s] == r[s])
        out[sname(r[uc])] = d
    return out


def _end_released(rel: dict | None, end: str) -> bool:
    if not rel:
        return False
    return any(rel.get(f"{q}{end}") or rel.get(f"{q}{end}_spring") for q in ("T", "M2", "M3"))


@check("r11_grinzi_secundare", 11, "Grinzi secundare pe interiorul altor grinzi: eliberare / partial fixity")
def r11_grinzi_secundare(ctx):
    model = ctx.snap.model
    rel = _releases(ctx)
    hits = end_on_beam_hits(model, model.beam_names)
    no_release, ends = [], []
    for f_name, node, _g in hits:
        f = model.frames[f_name]
        end = "I" if node == f.p1 else "J"
        if not _end_released(rel.get(f_name), end):
            no_release.append(f_name)
            ends.append({"name": f_name, "end": end})
    if not no_release:
        return []
    uniq = list(dict.fromkeys(no_release))
    return [Finding(INFO, f"{len(uniq)} grinzi secundare se reazemă pe interiorul altor grinzi fără eliberare sau partial fixity "
                          "la capătul respectiv: torsiunea de compatibilitate poate încărca grinda principală "
                          "(recomandat: partial fixity la beton armat).", frame_objects(uniq),
                    fix={"id": "release_secondary", "label": f"Eliberează M3 la {len(ends)} capete", "args": {"ends": ends, "k": 0.0}})]


@check("r25_eliberari", 25, "Eliberări care creează mecanisme (torsiune eliberată la ambele capete)")
def r25_eliberari(ctx):
    rel = _releases(ctx)
    df = ctx.snap.table("Frame Assignments - Releases and Partial Fixity")
    meta = {}
    if not df.empty:
        uc, lc, sc = col(df, "UniqueName"), col(df, "Label"), col(df, "Story")
        meta = {sname(r[uc]): {"label": str(r[lc]) if lc else "", "story": str(r[sc]) if sc else ""} for _, r in df.iterrows()}

    def objs(names):
        return [("frame", n, meta.get(n, {})) for n in names]

    tors, allrel = [], []
    for name, r in rel.items():
        if r["TI"] and r["TJ"]:
            tors.append(name)
        if all(r[f"{q}{e}"] for q in _REL for e in ("I", "J")):
            allrel.append(name)
    out = []
    if tors:
        out.append(Finding(ERROR, f"{len(tors)} bare au torsiunea eliberată la ambele capete: pot deveni mecanism "
                                  "(rotire liberă în jurul axei proprii, „Ill-conditioned matrix”). Eliberează torsiunea "
                                  "doar la un capăt sau folosește partial fixity.", objs(tors)))
    if allrel:
        out.append(Finding(ERROR, f"{len(allrel)} bare au toate gradele de libertate eliberate la ambele capete.", objs(allrel)))
    return out


@check("r13_zone_rigide", 13, "Zone rigide la intersecții stâlp–grindă (factor de zonă rigidă)",
       params=[Param("factor_rigid_min", 0.5, "Factor minim de zonă rigidă recomandat", "")])
def r13_zone_rigide(ctx):
    df = ctx.snap.table("Frame Assignments - End Length Offsets")
    if df.empty:
        return []
    model = ctx.snap.model
    rf, uc, oo = col(df, "RigidFact"), col(df, "UniqueName"), col(df, "OffsetOpt")
    lo = ctx.p("factor_rigid_min")
    beams, cols = [], []
    for _, r in df.iterrows():
        n = sname(r[uc])
        f = model.frames.get(n)
        if f is None or not f.section or n in model.belt_names or f.orientation == NULL:
            continue
        auto_no_zone = str(r[oo]).lower().startswith("auto") and (r[rf] if r[rf] == r[rf] else 0) < lo
        if auto_no_zone:
            (cols if f.orientation == COLUMN else beams).append(n)
    out = []
    if beams or cols:
        out.append(Finding(WARNING,
                           f"{len(beams)} grinzi și {len(cols)} stâlpi nu au zone rigide la capete (factor < {lo:g}): "
                           "deschiderea grinzii se calculează din axul stâlpului, structura devine prea flexibilă.",
                           frame_objects(beams + cols), {"grinzi": len(beams), "stalpi": len(cols)},
                           fix={"id": "set_rigid_factor", "label": f"Setează zone rigide ({len(beams) + len(cols)} bare)",
                                "args": {"frames": beams + cols, "factor": 0.75}}))
    return out


@check("r14_axe_locale_stalpi_arii", 14, "Axe locale consecvente: stâlpi și arii cu aceeași secțiune")
def r14_axe_locale_stalpi_arii(ctx):
    model = ctx.snap.model
    out = []
    by_sec: dict[str, list] = defaultdict(list)
    for f in model.frames.values():
        if f.orientation == COLUMN and f.section:
            by_sec[f.section].append(f)
    minority, detail = [], {}
    for sec, fr in by_sec.items():
        cnt = Counter(round(f.angle % 180, 3) for f in fr)
        if len(cnt) > 1:
            major = cnt.most_common(1)[0][0]
            minority += [f.name for f in fr if round(f.angle % 180, 3) != major]
            detail[sec] = {str(k): v for k, v in cnt.items()}
    if minority:
        out.append(Finding(WARNING, f"{len(minority)} stâlpi au axele locale rotite diferit față de ceilalți stâlpi cu aceeași "
                                    "secțiune: extragerea tabelară a momentelor (M2/M3) nu va fi uniformă.",
                           frame_objects(minority), detail))
    ax, sp = ctx.snap.table("Area Assignments - Local Axes"), ctx.snap.table("Area Assignments - Section Properties")
    if not ax.empty and not sp.empty:
        ang = {sname(r["UniqueName"]): r["Angle"] for _, r in ax.iterrows()}
        total = Counter(sp["SectProp"])
        rotated = Counter()
        odd = []
        for _, r in sp.iterrows():
            u = sname(r["UniqueName"])
            if abs(ang.get(u, 0) or 0) > 1e-6:
                rotated[r["SectProp"]] += 1
                odd.append(("area", u, {"label": str(r["Label"]), "story": str(r["Story"]), "section": str(r["SectProp"])}))
        mixed = {s for s in rotated if 0 < rotated[s] < total[s]}
        odd = [o for o in odd if o[2]["section"] in mixed]
        if odd:
            out.append(Finding(WARNING, f"{len(odd)} arii au axele locale rotite, deși alte arii cu aceeași secțiune au axele implicite "
                                        "(posibil amestec haotic de orientări).", odd,
                               {s: f"{rotated[s]} din {total[s]} rotite" for s in mixed}))
    return out


@check("r15_null_masa", 15, "Elementele Null / ajutătoare nu adaugă masă")
def r15_null_masa(ctx):
    df = ctx.snap.table("Frame Assignments - Additional Mass")
    if df.empty:
        return []
    model = ctx.snap.model
    uc = col(df, "UniqueName")
    nulls = [sname(n) for n in df[uc] if sname(n) in model.frames and (not model.frames[sname(n)].section)]
    if not nulls:
        return []
    return [Finding(WARNING, f"{len(nulls)} bare Null/ajutătoare au masă adițională asignată: ele nu trebuie să adauge masă structurii.",
                    frame_objects(nulls))]
