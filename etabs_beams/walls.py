"""Zone de perete in planul unei grinzi (hibrid: shell-uri + centuri/dummy). Logica pura."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .models import ModelData, Tolerances, warn


@dataclass
class Zone:
    a: float                       # abscise pe axa lantului (necropate la lantul propriu)
    b: float
    source: str                    # "shell" | "belt"
    shell_len: float | None = None  # lungimea 2 (din shell-uri)
    belt_len: float | None = None   # lungimea 1 (din centura)
    walls: list = field(default_factory=list)         # shell-urile (nume arie) din zona
    belt_frames: list = field(default_factory=list)   # barele de centura din zona

    @property
    def length(self) -> float:
        return self.b - self.a


def _wall_arrays(model: ModelData):
    arr = getattr(model, "_wall_arrays", None)
    if arr is not None and arr[0] == len(model.walls):
        return arr
    names = list(model.walls)
    n = np.array([[-model.walls[k].direction[1], model.walls[k].direction[0]] for k in names]).reshape(-1, 2)
    c = np.array([n[i][0] * model.walls[k].points[0][0] + n[i][1] * model.walls[k].points[0][1]
                  for i, k in enumerate(names)])
    zmax = np.array([model.walls[k].zmax for k in names])
    zmin = np.array([model.walls[k].zmin for k in names])
    d = np.array([model.walls[k].direction for k in names]).reshape(-1, 2)
    along = [[p[0] * d[i][0] + p[1] * d[i][1] for p in model.walls[k].points] for i, k in enumerate(names)]
    tmin = np.array([min(a) for a in along])
    tmax = np.array([max(a) for a in along])
    thick = np.array([model.walls[k].thickness for k in names])
    arr = (len(names), names, n, c, zmax, zmin, d, tmin, tmax, thick)
    model._wall_arrays = arr
    return arr


def _merge(intervals, gap):
    out: list[list[float]] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _axis(p0, p1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    Lxy = math.hypot(dx, dy)
    if Lxy < 1e-9:
        return None
    L3 = math.dist(p0, p1)
    return (dx / Lxy, dy / Lxy), L3 / Lxy


def _coplanar(model: ModelData, p0, p1, tol: Tolerances, above: bool = False):
    """Shell-uri sub axa p0->p1, in planul ei: [(nume, t_min, t_max)] cu t = abscisa pe axa."""
    ax = _axis(p0, p1)
    if ax is None or not model.walls:
        return []
    (ux, uy), scale = ax
    W, names, n, c, zmax, zmin = _wall_arrays(model)[:6]
    zmid = (p0[2] + p1[2]) / 2
    sin = np.abs(n[:, 0] * ux + n[:, 1] * uy)
    dist = np.abs(n[:, 0] * p0[0] + n[:, 1] * p0[1] - c)
    ok_ = (sin <= tol.wall_parallel_sin) & (dist <= tol.wall_plane_tol) & (np.abs((zmin if above else zmax) - zmid) <= tol.wall_top_tol)
    out = []
    for i in np.nonzero(ok_)[0]:
        ts = [((p[0] - p0[0]) * ux + (p[1] - p0[1]) * uy) * scale for p in model.walls[names[i]].points]
        out.append((names[i], min(ts), max(ts)))
    return out


def shell_intervals(model: ModelData, p0, p1, tol: Tolerances, above: bool = False):
    """Intervale (in abscise pe axa p0->p1) ocupate de pereti sub axa (sau deasupra, above=True);
    shell-urile alaturate se unesc."""
    iv = [(a, b) for _, a, b in _coplanar(model, p0, p1, tol, above)]
    return [tuple(x) for x in _merge(iv, tol.wall_gap_tol)] if iv else []


def _zone_half_thickness(model: ModelData, p0, p1, tol: Tolerances, a, b) -> float:
    return max((model.walls[n].thickness / 2 for n, lo, hi in _coplanar(model, p0, p1, tol)
                if min(b, hi) - max(a, lo) > 0), default=0.0)


def belt_intervals(model: ModelData, p0, p1, tol: Tolerances):
    """Centuri (lanturi de dummy) coliniare cu axa: [(a, b, [bare], [id_centura])], unite cand sunt lipite."""
    ax = _axis(p0, p1)
    if ax is None or not model.belt_segments:
        return []
    (ux, uy), scale = ax
    nx, ny = -uy, ux
    zmid = (p0[2] + p1[2]) / 2
    iv = []
    for s, e, frames, cid in model.belt_segments:
        if abs(s[2] - zmid) > tol.wall_top_tol or abs(e[2] - zmid) > tol.wall_top_tol:
            continue
        ds = abs((s[0] - p0[0]) * nx + (s[1] - p0[1]) * ny)
        de = abs((e[0] - p0[0]) * nx + (e[1] - p0[1]) * ny)
        if ds > tol.wall_plane_tol or de > tol.wall_plane_tol:
            continue
        t1 = ((s[0] - p0[0]) * ux + (s[1] - p0[1]) * uy) * scale
        t2 = ((e[0] - p0[0]) * ux + (e[1] - p0[1]) * uy) * scale
        iv.append((min(t1, t2), max(t1, t2), list(frames), [cid]))
    out: list[list] = []
    for a, b, fr, ids in sorted(iv, key=lambda x: x[0]):
        if out and a <= out[-1][1] + tol.wall_gap_tol:
            out[-1][1] = max(out[-1][1], b)
            out[-1][2] += fr
            out[-1][3] += ids
        else:
            out.append([a, b, fr, ids])
    return [tuple(x) for x in out]


def _junction_extra(model: ModelData, pt, z, u, tol: Tolerances) -> float:
    """Cu cat se prelungeste un shell dincolo de centura la o jonctiune: jumatate din grosimea
    peretelui care il intersecteaza (perpendicular sau oblic) exact in punctul `pt`; 0 daca nu e jonctiune."""
    if not model.walls:
        return 0.0
    W, names, n, c, zmax, zmin = _wall_arrays(model)[:6]
    ux, uy = u
    best = 0.0
    for i in range(W):
        w = model.walls[names[i]]
        cosang = abs(n[i][0] * ux + n[i][1] * uy)          # 1 = perete perpendicular pe axa
        if cosang < 0.5:
            continue
        if abs(n[i][0] * pt[0] + n[i][1] * pt[1] - c[i]) > tol.wall_plane_tol:
            continue                                        # punctul nu e in planul peretelui transversal
        if not (w.zmin - tol.wall_top_tol <= z <= w.zmax + tol.wall_top_tol):
            continue
        ts = [(p[0] - pt[0]) * (-n[i][1]) + (p[1] - pt[1]) * n[i][0] for p in w.points]
        if min(ts) - tol.wall_plane_tol <= 0.0 <= max(ts) + tol.wall_plane_tol:
            best = max(best, w.thickness / 2 / cosang)
    return best


def chain_zones(model: ModelData, p0, p1, tol: Tolerances, check: bool = True, ref=()) -> list[Zone]:
    """Zone de perete pe axa p0->p1.

    Lungimea din shell-uri (L2) se compara cu cea din centuri (L1). Daca shell-ul depaseste centura la capete
    cu jumatate din grosimea peretelui (al zonei sau transversal, la jonctiune), se foloseste centura. Orice alta
    diferenta -> avertisment (cu id-urile peretilor/centurilor/grinzilor) si se foloseste shell-ul.
    `ref`: grinzile (nume) pentru care se calculeaza, trecute in avertismente."""
    cop = _coplanar(model, p0, p1, tol)
    shells = [tuple(x) for x in _merge([(a, b) for _, a, b in cop], tol.wall_gap_tol)] if cop else []
    belts = belt_intervals(model, p0, p1, tol) if model.belt_segments else []
    ax = _axis(p0, p1)
    zones: list[Zone] = []
    used = set()
    for a, b in shells:
        wl = sorted({n for n, lo, hi in cop if min(b, hi) - max(a, lo) > 0})
        over = [i for i, (c, d, _, _) in enumerate(belts) if min(b, d) - max(a, c) > -tol.wall_length_tol]
        z = Zone(a, b, "shell", shell_len=b - a, walls=wl)
        if over:
            used.update(over)
            c, d = min(belts[i][0] for i in over), max(belts[i][1] for i in over)
            bf = sorted({f for i in over for f in belts[i][2]})
            z.belt_len, z.belt_frames = d - c, bf
            da, db = c - a, b - d           # >0: shell mai lung decat centura la capatul respectiv
            if abs(da) > tol.wall_length_tol or abs(db) > tol.wall_length_tol:
                (ux, uy), scale = ax
                pt = lambda t: (p0[0] + t / scale * ux, p0[1] + t / scale * uy)
                own = _zone_half_thickness(model, p0, p1, tol, a, b)      # centura retrasa cu t/2 la capete

                def explained(delta, t_end):
                    if abs(delta) <= tol.wall_length_tol:
                        return True
                    if delta <= 0:
                        return False
                    cand = (own, _junction_extra(model, pt(t_end), p0[2], (ux, uy), tol))
                    return any(abs(delta - r) <= tol.wall_length_tol for r in cand if r > 0)

                ok_a, ok_b = explained(da, a), explained(db, b)
                if ok_a and ok_b:
                    z = Zone(c, d, "belt", shell_len=b - a, belt_len=d - c, walls=wl, belt_frames=bf)
                elif check:
                    _warn_once(model, "wall_length_mismatch",
                               f"Perete: lungime din shell-uri {b - a:.3f} m vs centura {d - c:.3f} m, "
                               f"diferenta nu se explica prin grosimea peretilor "
                               f"(la x={p0[0]:.2f}, y={p0[1]:.2f}, z={p0[2]:.2f}); se foloseste shell-ul",
                               _abs_key(p0, p1, a, b),
                               [("wall", w) for w in wl] + [("frame", f) for f in bf]
                               + [("frame", f) for f in ref],
                               {"shell_length": round(b - a, 4), "belt_length": round(d - c, 4),
                                "difference_start": round(da, 4), "difference_end": round(db, 4),
                                "x": round(p0[0], 3), "y": round(p0[1], 3), "z": round(p0[2], 3)})
        zones.append(z)
    for i, (c, d, bf, bids) in enumerate(belts):
        if i not in used:
            zones.append(Zone(c, d, "belt", belt_len=d - c, belt_frames=sorted(set(bf))))
            if check:
                _warn_once(model, "belt_without_wall",
                           f"Centura de {d - c:.3f} m fara perete (shell) dedesubt "
                           f"(la x={p0[0]:.2f}, y={p0[1]:.2f}, z={p0[2]:.2f}); se foloseste centura",
                           _abs_key(p0, p1, c, d),
                           [("frame", f) for f in sorted(set(bf))] + [("frame", f) for f in ref],
                           {"belt_length": round(d - c, 4), "x": round(p0[0], 3), "y": round(p0[1], 3),
                            "z": round(p0[2], 3)})
    zones.sort(key=lambda z: z.a)
    return zones


def _abs_key(p0, p1, a, b):
    ax = _axis(p0, p1)
    (ux, uy), scale = ax
    pt = lambda t: (round(p0[0] + t / scale * ux, 1), round(p0[1] + t / scale * uy, 1))
    return tuple(sorted((pt(a), pt(b))))      # fara cota: acelasi perete pe mai multe etaje = un singur avertisment


def _warn_once(model: ModelData, code: str, msg: str, key, objects=(), data=None) -> None:
    seen = model.__dict__.setdefault("_seen_warn", set())
    k = (code, key)
    if k in seen:
        return
    seen.add(k)
    warn(model.warnings, code, msg, objects, data)


def walls_at_point(model: ModelData, xyz, tol: Tolerances) -> list[str]:
    """Pereti (shell) pe a caror suprafata/muchie se afla punctul `xyz`, chiar daca nu au nod comun cu el."""
    if not model.walls:
        return []
    W, names, n, c, zmax, zmin, d, tmin, tmax, thick = _wall_arrays(model)
    x, y, z = xyz
    dist = np.abs(n[:, 0] * x + n[:, 1] * y - c)
    lim = np.maximum(tol.wall_plane_tol, thick / 2 + 0.02)
    t = d[:, 0] * x + d[:, 1] * y
    ok_ = ((dist <= lim) & (t >= tmin - tol.wall_plane_tol) & (t <= tmax + tol.wall_plane_tol)
           & (z >= zmin - tol.wall_top_tol) & (z <= zmax + tol.wall_top_tol))
    return [names[i] for i in np.nonzero(ok_)[0]]
