"""Regula 2: continuitatea verticala a elementelor verticale (stalpi si pereti) pana la baza, fara sa reazeme pe placi sau grinzi."""
from __future__ import annotations

import math

from ...models import COLUMN
from ..registry import ERROR, INFO, WARNING, Finding, Param, check


def _on_segment(px: float, py: float, a, b, tol: float) -> bool:
    """Punctul (px, py) se afla pe segmentul a-b din plan (distanta <= tol)."""
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) <= tol


def _wall_edges(w):
    """(segment de jos, cota de jos, segment de sus, cota de sus) ale unui perete: din cele 4 varfuri, cele cu cota minima si maxima."""
    pts = w.points
    zmin, zmax = min(p[2] for p in pts), max(p[2] for p in pts)
    low = [p for p in pts if abs(p[2] - zmin) < 1e-6]
    high = [p for p in pts if abs(p[2] - zmax) < 1e-6]
    if len(low) < 2 or len(high) < 2:
        return None
    return (low[0], low[-1]), zmin, (high[0], high[-1]), zmax


@check("r2_continuitate_verticala", 2, "Continuitatea verticală a stâlpilor și pereților până la bază",
       params=[Param("continuitate_tol", 0.05, "Toleranța de poziție la verificarea reazemului", "m")])
def r2_continuitate_verticala(ctx):
    """Un stalp sau perete care nu e la baza trebuie sa aiba dedesubt un stalp sau perete (nu o placa sau o grinda): altfel reazema pe element orizontal."""
    model, tol = ctx.snap.model, ctx.p("continuitate_tol")
    cols = [f for f in model.frames.values() if f.orientation == COLUMN and abs(f.end[2] - f.start[2]) > 1e-6]
    walls = [(w, e) for w in model.walls.values() if (e := _wall_edges(w))]
    if not cols and not walls:
        return []
    base = min([min(f.start[2], f.end[2]) for f in cols] + [e[1] for _w, e in walls])
    below_walls = [(e[0], e[3]) for _w, e in walls]                           # (segment de sus, cota de sus) al peretilor
    below_cols = [(max(f.start[2], f.end[2]), f.start[0], f.start[1]) if f.start[2] > f.end[2] else (f.end[2], f.end[0], f.end[1]) for f in cols]

    def supported_point(x, y, z):
        if any(abs(zt - z) < tol and math.hypot(cx - x, cy - y) <= tol for zt, cx, cy in below_cols):
            return True
        return any(abs(zt - z) < tol and _on_segment(x, y, seg[0], seg[1], tol) for seg, zt in below_walls)

    bad_cols = []
    for f in cols:
        lo = f.start if f.start[2] <= f.end[2] else f.end
        if lo[2] - base > tol and not supported_point(lo[0], lo[1], lo[2]):
            bad_cols.append(f)
    bad_walls, partial = [], []
    for w, (low, zlow, _high, _zh) in walls:
        if zlow - base <= tol:
            continue
        a, b = low
        samples = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        hits = sum(1 for x, y in samples if supported_point(x, y, zlow))
        if hits == 0:
            bad_walls.append(w)
        elif hits < len(samples):
            partial.append(w)
    out = []
    if bad_cols or bad_walls:
        objs = [("frame", f.name, {"label": f.label, "story": f.story, "section": f.section}) for f in bad_cols] + \
               [("wall", w.name, {"label": w.label, "story": w.story}) for w in bad_walls]
        out.append(Finding(ERROR, f"{len(bad_cols)} stâlpi și {len(bad_walls)} pereți nu au continuitate până la bază: reazemă pe o placă sau o grindă, nu pe un element "
                                  "vertical (stâlp sau perete) dedesubt. Elementele verticale trebuie duse până la fundație.", objs,
                           {"stalpi": len(bad_cols), "pereti": len(bad_walls), "cota_bazei_m": round(base, 3)}))
    if partial:
        out.append(Finding(WARNING, f"{len(partial)} pereți reazemă doar parțial pe pereți sau stâlpi dedesubt (restul marginii de jos e pe placă sau grindă).",
                           [("wall", w.name, {"label": w.label, "story": w.story}) for w in partial]))
    if not out:
        out.append(Finding(INFO, f"Toți stâlpii și pereții au continuitate verticală până la baza modelului (cota {base:g} m)."))
    return out
