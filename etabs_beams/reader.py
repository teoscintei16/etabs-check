"""Citirea modelului din ETABS (apeluri in bloc) -> ModelData. Unitati: cele curente (kN, m)."""
from __future__ import annotations

import math

from .classify import classify
from .connection import EtabsSession, ok
from .models import BEAM, COLUMN, Frame, ModelData, SectionInfo, Tolerances, WallInfo, warn

OBJ_FRAME, OBJ_AREA = 2, 5


def _section_info(sap, name: str) -> SectionInfo:
    if not name:
        return SectionInfo(name)
    try:
        kind_code = sap.PropFrame.GetTypeOAPI(name)[0]
    except Exception:
        kind_code = None
    try:
        if kind_code == 9:        # Circle
            v = ok(sap.PropFrame.GetCircle(name))
            return SectionInfo(name, "circle", depth=v[2], width=v[2])
        v = ok(sap.PropFrame.GetRectangle(name))
        return SectionInfo(name, "rect", depth=v[2], width=v[3])    # T3, T2
    except Exception:
        return SectionInfo(name)


def _read_walls(sap, md: ModelData, coords: dict) -> None:
    """Toate shell-urile verticale (pereti) cu poligonul lor."""
    thick_cache: dict[str, float] = {}
    names = ok(sap.AreaObj.GetNameList())[1]
    for a in names:
        try:
            if sap.AreaObj.GetDesignOrientation(a)[0] != 1:        # 1 = Wall
                continue
            prop = ok(sap.AreaObj.GetProperty(a))[0]
            if prop not in thick_cache:
                thick_cache[prop] = ok(sap.PropArea.GetWall(prop))[3]
            pts = ok(sap.AreaObj.GetPoints(a))[1]
        except Exception as e:
            warn(md.warnings, "wall_read_failed", f"Perete {a}: {e}", [("wall", a)])
            continue
        xyz = [coords[p] for p in pts]
        best, d = 0.0, (1.0, 0.0)
        for i in range(len(xyz)):
            for j in range(i + 1, len(xyz)):
                L = math.dist(xyz[i][:2], xyz[j][:2])
                if L > best:
                    best, d = L, ((xyz[j][0] - xyz[i][0]) / L, (xyz[j][1] - xyz[i][1]) / L)
        if best <= 1e-9:
            continue          # shell orizontal sau degenerat
        zs = [p[2] for p in xyz]
        lab, story = ok(sap.AreaObj.GetLabelFromName(a))[:2]
        md.walls[a] = WallInfo(a, thick_cache[prop], d, xyz, list(pts), min(zs), max(zs), lab, story)


def read_model(session: EtabsSession, tol: Tolerances | None = None) -> ModelData:
    """Citeste geometria, reazemele si clasifica grinzile. Apelati in `with session.units():`."""
    tol = tol or Tolerances()
    sap = session.model
    md = ModelData(units="kN_m")

    # 1. toate barele intr-un apel
    r = ok(sap.FrameObj.GetAllFrames())
    (n, names, props, stories, pn1, pn2, x1, y1, z1, x2, y2, z2, ang) = r[:13]
    offs, card = r[13:19], r[19]
    for i in range(n):
        orient = sap.FrameObj.GetDesignOrientation(names[i])[0]
        md.frames[names[i]] = Frame(
            name=names[i], label="", story=stories[i], section=props[i], p1=pn1[i], p2=pn2[i],
            start=(x1[i], y1[i], z1[i]), end=(x2[i], y2[i], z2[i]), angle=ang[i], orientation=orient,
            cardinal=card[i], offsets=tuple(o[i] for o in offs))

    # 2. detalii doar pentru bare relevante (grinzi candidate)
    for f in md.frames.values():
        if f.orientation != COLUMN and f.section:
            f.label = ok(sap.FrameObj.GetLabelFromName(f.name))[0]
            ii, jj = ok(sap.FrameObj.GetReleases(f.name))[:2]
            f.release_i = bool(ii[4] or ii[5])
            f.release_j = bool(jj[4] or jj[5])
            try:
                st = ok(sap.FrameObj.GetOutputStations(f.name))
                f.output_stations = (st[0], st[1], st[2])
            except Exception:
                pass
            try:
                f.curved = sap.FrameObj.GetTypeOAPI(f.name)[0] == "Curved"
            except Exception:
                pass
    classify(md, tol)

    # 3. sectiuni (grinzi + stalpi)
    used = {md.frames[b].section for b in md.beam_names}
    used |= {f.section for f in md.frames.values() if f.orientation == COLUMN}
    for s in used:
        md.sections[s] = _section_info(sap, s)

    # 4. puncte, pereti, conectivitate
    n, pnames, px, py, pz = ok(sap.PointObj.GetAllPoints())[:5]
    coords = {pnames[i]: (px[i], py[i], pz[i]) for i in range(n)}
    _read_walls(sap, md, coords)
    by_point: dict[str, list[str]] = {}
    for w in md.walls.values():
        for p in w.point_names:
            by_point.setdefault(p, []).append(w.name)

    nodes = {p for b in md.beam_names + md.belt_names for p in (md.frames[b].p1, md.frames[b].p2)}
    for p in nodes:
        n_, types, onames, _ = ok(sap.PointObj.GetConnectivity(p))
        md.node_frames[p] = [o for t, o in zip(types, onames) if t == OBJ_FRAME]
        md.node_areas[p] = by_point.get(p, [])
        if any(ok(sap.PointObj.GetRestraint(p))[0]):
            md.restrained.add(p)
    return md
