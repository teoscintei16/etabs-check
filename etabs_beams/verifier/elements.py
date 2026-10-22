"""Elemente de arie (mesh) si pereti din tabelele ETABS, vectorizat (fara apeluri COM pe obiect)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..models import WallInfo
from .checks.util import sname


def build_area_elements(table, cache: dict) -> pd.DataFrame:
    """O linie pe element de arie: Story, ObjName, ObjLabel, ObjType, J1..J4 (nume noduri), X1..4, Y1..4, Z1..4 (NaN la triunghiuri)."""
    if "area_elems" in cache:
        return cache["area_elems"]
    j = table("Objects and Elements - Joints")
    a = table("Objects and Elements - Areas")
    if j.empty or a.empty:
        cache["area_elems"] = pd.DataFrame()
        return cache["area_elems"]
    jj = j.drop_duplicates("ElmName")
    jd = jj.set_index(jj["ElmName"].astype(str))[["GlobalX", "GlobalY", "GlobalZ"]]
    out = a[["Story", "ElmName", "ObjName", "ObjLabel", "ObjType"]].copy()
    out["ObjName"] = [sname(x) for x in out["ObjName"]]
    out["Story"] = out["Story"].astype(str)
    for k in range(1, 5):
        names = a[f"ElmJt{k}"].astype(str).replace({"": np.nan, "nan": np.nan})
        out[f"J{k}"] = names
        for ax, src in zip("XYZ", ("GlobalX", "GlobalY", "GlobalZ")):
            out[f"{ax}{k}"] = names.map(jd[src]).to_numpy(dtype=float)
    cache["area_elems"] = out
    return out


def build_walls(table, cache: dict) -> dict[str, WallInfo]:
    """Peretii (arii cu proprietate de tip Wall): grosime, directie in plan, poligon dreptunghic in plan si nodurile-obiect."""
    if "walls" in cache:
        return cache["walls"]
    sp, sec = table("Area Assignments - Section Properties"), table("Area Section Property Definitions - Summary")
    e = build_area_elements(table, cache)
    walls: dict[str, WallInfo] = {}
    sloped: dict[str, dict] = {}
    cache["sloped_walls"] = sloped
    if sp.empty or e.empty:
        cache["walls"] = walls
        return walls
    thick = {str(r["Name"]): float(r["TotalThick"]) for _, r in sec.iterrows()} if not sec.empty else {}
    w = sp[sp["PropType"].astype(str) == "Wall"]
    meta = {sname(r["UniqueName"]): r for _, r in w.iterrows()}
    ew = e[e["ObjName"].isin(meta)]
    xs = np.stack([ew[f"X{k}"].to_numpy() for k in range(1, 5)], axis=1)
    ys = np.stack([ew[f"Y{k}"].to_numpy() for k in range(1, 5)], axis=1)
    zs = np.stack([ew[f"Z{k}"].to_numpy() for k in range(1, 5)], axis=1)
    js = ew[["J1", "J2", "J3", "J4"]].to_numpy(dtype=object)
    idx = ew.groupby("ObjName", sort=False).indices
    for name, rows in idx.items():
        x, y, z = xs[rows].ravel(), ys[rows].ravel(), zs[rows].ravel()
        ok = ~np.isnan(x)
        x, y, z = x[ok], y[ok], z[ok]
        if len(x) < 3:
            continue
        c = np.array([x.mean(), y.mean()])
        pts = np.stack([x, y], axis=1) - c
        if np.abs(pts).max() < 1e-9:
            continue                                         # shell orizontal / degenerat
        u, s, vt = np.linalg.svd(pts, full_matrices=False)
        d = vt[0]
        if s[0] < 1e-9:
            continue
        if s[1] > 1e-3 * s[0] + 1e-6:                        # proiectia in plan nu e un segment: aria nu e verticala (rampa / perete inclinat)
            sloped[name] = _sloped_edges(x, y, z, meta[name], thick, js[rows])
            walls.update(_virtual_edges(name, sloped[name], thick.get(str(meta[name]["SectProp"]), 0.0)))
            continue
        t = pts @ d
        tmin, tmax = float(t.min()), float(t.max())
        zmin, zmax = float(z.min()), float(z.max())
        p0 = c + d * tmin
        p1 = c + d * tmax
        poly = [(float(p0[0]), float(p0[1]), zmin), (float(p1[0]), float(p1[1]), zmin),
                (float(p1[0]), float(p1[1]), zmax), (float(p0[0]), float(p0[1]), zmax)]
        names = sorted({str(j) for j in js[rows].ravel() if isinstance(j, str) and j != "nan" and not j.startswith("~")})
        r = meta[name]
        walls[name] = WallInfo(name, thick.get(str(r["SectProp"]), 0.0), (float(d[0]), float(d[1])), poly, names, zmin, zmax,
                               str(r["Label"]), str(r["Story"]))
    cache["walls"] = walls
    return walls


EDGE_BAND = 0.2            # m: grosimea benzii verticale care reprezinta o margine de perete inclinat


def _extreme_pair(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Capetele celui mai lung segment din plan dintre punctele date (la o cota)."""
    i = int(np.argmax(np.linalg.norm(pts - pts[0], axis=1)))
    j = int(np.argmax(np.linalg.norm(pts - pts[i], axis=1)))
    return pts[i], pts[j]


def _sloped_edges(x, y, z, row, thick, names) -> dict:
    """Marginea de jos si cea de sus ale unei arii inclinate: {"bottom": ((x, y), (x, y), z), "top": (...)}."""
    zlo, zhi = float(z.min()), float(z.max())
    out = {"label": str(row["Label"]), "story": str(row["Story"])}
    for key, zz in (("bottom", zlo), ("top", zhi)):
        sel = np.abs(z - zz) < 1e-6
        a, b = _extreme_pair(np.stack([x[sel], y[sel]], axis=1))
        out[key] = ((float(a[0]), float(a[1])), (float(b[0]), float(b[1])), zz)
    return out


def _virtual_edges(name: str, e: dict, thickness: float) -> dict[str, WallInfo]:
    """Doua pereti verticali subtiri (benzi de EDGE_BAND) pe marginile reale: grinzile/centurile de pe margine se potrivesc pe ele."""
    out = {}
    for key, tag, up in (("bottom", "B", True), ("top", "T", False)):
        a, b, zz = e[key]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        z0, z1 = (zz, zz + EDGE_BAND) if up else (zz - EDGE_BAND, zz)
        pts = [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)]
        out[f"{name}#{tag}"] = WallInfo(f"{name}#{tag}", thickness, (dx / L, dy / L), pts, [], z0, z1, e["label"], e["story"], virtual=True)
    return out
