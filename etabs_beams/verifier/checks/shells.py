"""Coji (placi inclinate) si coaste: arii de tip Slab inclinate > 15° fata de orizontala nu sunt planseu (nu au diafragma), iar barele care
le urmaresc muchiile (coaste, grinzi de picior si frontale) nu sunt grinzi de cadru: nu cer zone rigide, eliberari sau panta mica."""
from __future__ import annotations

import math
import re

import numpy as np

from ...models import COLUMN
from ..elements import build_area_elements
from ..registry import Finding
from .util import sname

TILT_MIN_DEG = 15.0


def _key(x, y, z) -> tuple[float, float, float]:
    return round(float(x), 3), round(float(y), 3), round(float(z), 3)


def _surfaces(ctx) -> tuple[set[str], set[tuple[float, float, float]]]:
    """(numele ariilor Slab inclinate, coordonatele nodurilor lor)."""
    cache = ctx.snap.cache
    if "shell_surfaces" in cache:
        return cache["shell_surfaces"]
    names: set[str] = set()
    pts: set[tuple[float, float, float]] = set()
    cache["shell_surfaces"] = (names, pts)
    asg = ctx.snap.table("Area Assignments - Section Properties")
    e = build_area_elements(ctx.snap.table, cache)
    if asg.empty or e.empty:
        return names, pts
    slab = {sname(r["UniqueName"]) for _, r in asg[asg["PropType"].astype(str) == "Slab"].iterrows()}
    e = e[e["ObjName"].isin(slab)]
    if e.empty:
        return names, pts
    p = [np.stack([e[f"X{k}"], e[f"Y{k}"], e[f"Z{k}"]], axis=1).astype(float) for k in range(1, 5)]
    tri = np.isnan(p[3][:, 0])
    n = np.where(tri[:, None], np.cross(p[1] - p[0], p[2] - p[0]), np.cross(p[2] - p[0], np.where(tri[:, None], p[2], p[3]) - p[1]))
    length = np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    tilted = np.abs(n[:, 2]) / length < math.cos(math.radians(TILT_MIN_DEG))
    flags = e.assign(_t=tilted).groupby("ObjName")["_t"].mean()
    names.update(flags[flags > 0.5].index)
    for k in range(4):
        sel = tilted & ~(np.isnan(p[k][:, 0]))
        for row in p[k][sel]:
            pts.add(_key(*row))
    return names, pts


def inclined_slabs(ctx) -> set[str]:
    """Numele ariilor de tip Slab inclinate (coji): nu sunt planseu."""
    return _surfaces(ctx)[0]


def shell_ribs(ctx) -> set[str]:
    """Barele (nestalpi) cu ambele capete pe noduri ale cojilor: coaste si grinzi de bordura ale cojilor."""
    cache = ctx.snap.cache
    if "shell_ribs" in cache:
        return cache["shell_ribs"]
    ribs: set[str] = set()
    cache["shell_ribs"] = ribs
    names, pts = _surfaces(ctx)
    if not names:
        return ribs
    for f in ctx.snap.model.frames.values():
        if f.orientation != COLUMN and _key(*f.start) in pts and _key(*f.end) in pts:
            ribs.add(f.name)
    return ribs


def shell_stories(ctx) -> set[str]:
    """Nivelurile care contin numai coji (placi inclinate) si niciun alt perete/placa orizontala: ETABS nu leaga masa lor de nivel."""
    asg = ctx.snap.table("Area Assignments - Section Properties")
    if asg.empty or not inclined_slabs(ctx):
        return set()
    inc = inclined_slabs(ctx)
    flat = asg.assign(_inc=[sname(n) in inc for n in asg["UniqueName"]])
    by = flat.groupby(flat["Story"].astype(str))["_inc"].all()
    return set(by[by].index)


def shell_points(ctx) -> set[tuple[float, float, float]]:
    return _surfaces(ctx)[1]


_COUNT = re.compile(r"^\d+")


def without_ribs(ctx, finding: Finding) -> Finding | None:
    """Constatarea fara barele-coaste; None daca nu mai ramane nimic. Numarul de la inceputul mesajului se actualizeaza."""
    ribs = shell_ribs(ctx)
    if not ribs:
        return finding
    kept = [o for o in finding.objects if not (o[0] == "frame" and sname(o[1]) in ribs)]
    if len(kept) == len(finding.objects):
        return finding
    if not kept:
        return None
    finding.message = _COUNT.sub(str(len(kept)), finding.message, count=1)
    finding.objects = kept
    finding.total = len(kept)
    return finding
