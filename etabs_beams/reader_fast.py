"""Citirea modelului din tabele ETABS (rapid): un singur apel GetAllFrames + tabele in bloc, fara apeluri COM pe obiect."""
from __future__ import annotations

from .classify import classify
from .connection import ok
from .models import BEAM, BRACE, COLUMN, NULL, OTHER, Frame, ModelData, Tolerances
from .reader import _section_info
from .verifier.checks.util import col, sname, yes
from .verifier.elements import build_walls

_ORIENT = {"beam": BEAM, "column": COLUMN, "brace": BRACE, "null": NULL, "other": OTHER}


def read_model_fast(session, table, cache: dict, tol: Tolerances | None = None) -> ModelData:
    """Echivalentul lui `reader.read_model`, dar din tabele. Apelati in `with session.units():`.

    Diferenta: barele curbe nu sunt detectate (se considera drepte)."""
    tol = tol or Tolerances()
    sap = session.model
    md = ModelData(units="kN_m")

    r = ok(sap.FrameObj.GetAllFrames())
    (n, names, props, stories, pn1, pn2, x1, y1, z1, x2, y2, z2, ang) = r[:13]
    offs, card = r[13:19], r[19]
    summ = table("Frame Assignments - Summary")
    orient, label, stations = {}, {}, {}
    if not summ.empty:
        for _, s in summ.iterrows():
            u = sname(s["UniqueName"])
            orient[u] = _ORIENT.get(str(s["Type"]).strip().lower(), OTHER)
            label[u] = str(s["Label"])
            mx, mn = s.get("MaxStaSpcg"), s.get("MinNumSta")
            if mx == mx and mx not in ("", None):
                stations[u] = (1, float(mx), 0)
            elif mn == mn and mn not in ("", None):
                stations[u] = (2, 0.0, int(mn))
    rel = table("Frame Assignments - Releases and Partial Fixity")
    rel_i, rel_j = set(), set()
    if not rel.empty:
        uc = col(rel, "UniqueName")
        for _, q in rel.iterrows():
            u = sname(q[uc])
            if any(yes(q[c]) for c in ("M2I", "M3I") if c in rel.columns):
                rel_i.add(u)
            if any(yes(q[c]) for c in ("M2J", "M3J") if c in rel.columns):
                rel_j.add(u)
    for i in range(n):
        nm = names[i]
        md.frames[nm] = Frame(
            name=nm, label=label.get(nm, ""), story=stories[i], section=props[i], p1=pn1[i], p2=pn2[i],
            start=(x1[i], y1[i], z1[i]), end=(x2[i], y2[i], z2[i]), angle=ang[i], orientation=orient.get(nm, BEAM),
            release_i=nm in rel_i, release_j=nm in rel_j, cardinal=card[i], offsets=tuple(o[i] for o in offs),
            output_stations=stations.get(nm, ()))
    classify(md, tol)

    used = {md.frames[b].section for b in md.beam_names}
    used |= {f.section for f in md.frames.values() if f.orientation == COLUMN}
    for s in used:
        md.sections[s] = _section_info(sap, s)

    md.walls = build_walls(table, cache)
    by_point: dict[str, list[str]] = {}
    for w in md.walls.values():
        for p in w.point_names:
            by_point.setdefault(p, []).append(w.name)
    nodes = {p for b in md.beam_names + md.belt_names for p in (md.frames[b].p1, md.frames[b].p2)}
    at: dict[str, list[str]] = {}
    for f in md.frames.values():                                # bare conectate in nod (capetele obiectelor)
        for p in (f.p1, f.p2):
            if p in nodes:
                at.setdefault(p, []).append(f.name)
    for p in nodes:
        md.node_frames[p] = at.get(p, [])
        md.node_areas[p] = by_point.get(p, [])
    rs = table("Joint Assignments - Restraints")
    if not rs.empty:
        cols = [c for c in ("UX", "UY", "UZ", "RX", "RY", "RZ") if c in rs.columns]
        for _, q in rs.iterrows():
            if any(yes(q[c]) for c in cols):
                md.restrained.add(sname(q["UniqueName"]))
    return md
