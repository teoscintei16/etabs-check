"""Regula 5: geometrie curata si mesh."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .util import col, sname


@check("r5_noduri", 5, "Noduri duplicate/prea apropiate și coordonate cu zecimale parazite",
       params=[Param("dist_noduri_min", 0.02, "Distanța minimă între noduri distincte", "m"),
               Param("zecimale_parazite_max", 1e-4, "Abatere maximă de la grila de 1 mm considerată „parazită”", "m")])
def r5_noduri(ctx):
    j = ctx.snap.table("Objects and Elements - Joints")
    if j.empty:
        return []
    j = j[j["ObjType"].astype(str) == "Joint"].drop_duplicates("ObjName").reset_index(drop=True)
    xyz = j[["GlobalX", "GlobalY", "GlobalZ"]].to_numpy(dtype=float)
    out = []
    names = [sname(n) for n in j["ObjName"]]

    def obj(i):
        return ("joint", names[i], {"label": str(j.loc[i, "ObjLabel"]), "story": str(j.loc[i, "Story"])})

    dmin = ctx.p("dist_noduri_min")
    pairs = cKDTree(xyz).query_pairs(dmin, output_type="ndarray")
    if len(pairs):
        d = np.linalg.norm(xyz[pairs[:, 0]] - xyz[pairs[:, 1]], axis=1)
        merge = float(ctx.snap.table("Preferences - Tolerance").iloc[0].get("MergeTol", 0.001) or 0.001) \
            if not ctx.snap.table("Preferences - Tolerance").empty else 0.001
        idx = sorted({int(i) for p in pairs for i in p})
        out.append(Finding(ERROR, f"{len(pairs)} perechi de noduri distincte la mai puțin de {dmin * 100:g} cm "
                                  f"(toleranța de unire din model: {merge * 1000:g} mm): nodurile nu sunt unite și elementele "
                                  "nu se conectează.", [obj(i) for i in idx],
                           {"distanta_minima_m": round(float(d.min()), 6), "perechi": int(len(pairs))}))
    tol = ctx.p("zecimale_parazite_max")
    dev = np.abs(xyz - np.round(xyz, 3))
    bad = np.where(((dev > 1e-9) & (dev <= tol)).any(axis=1))[0]
    if len(bad):
        out.append(Finding(WARNING, f"{len(bad)} noduri au coordonate cu zecimale parazite (abatere ≤ {tol:g} m față de grila de 1 mm), "
                                    "tipic după desen din AutoCAD.", [obj(int(i)) for i in bad]))
    return out


@check("r5_mesh", 5, "Setările de mesh pentru plăci și pereți",
       params=[Param("mesh_max", 1.0, "Dimensiunea maximă recomandată a elementelor", "m")])
def r5_mesh(ctx):
    out = []
    lim = ctx.p("mesh_max")
    for key, what in (("Analysis Options - Automatic Mesh Settings for Floors", "plăci"),
                      ("Analysis Options - Automatic Rectangular Mesh Options for Walls", "pereți")):
        df = ctx.snap.table(key)
        c = col(df, "MaxMeshSize") if not df.empty else None
        if c and float(df.iloc[0][c]) > lim:
            out.append(Finding(WARNING, f"Dimensiunea maximă a mesh-ului pentru {what} este {float(df.iloc[0][c]):g} m (> {lim:g} m).",
                               [("mesh", key)]))
    for key, normal in (("Area Assignments - Floor Auto Mesh Options", {"default"}),
                        ("Area Assignments - Wall Auto Mesh Options", {"auto rectangular", "default"})):
        df = ctx.snap.table(key)
        if df.empty:
            continue
        mo = col(df, "MeshOption")
        odd = df[~df[mo].astype(str).str.lower().isin(normal)]
        if len(odd):
            objs = [("area", sname(r["UniqueName"]), {"label": str(r["Label"]), "story": str(r["Story"]), "mesh": str(r[mo])})
                    for _, r in odd.iterrows()]
            out.append(Finding(INFO, f"{len(odd)} arii au o opțiune de mesh diferită de cea implicită "
                                     f"({', '.join(sorted(set(odd[mo].astype(str))))}).", objs))
    return out


@check("r5_arii_suprapuse", 5, "Arii suprapuse (aceleași noduri de element)")
def r5_arii_suprapuse(ctx):
    df = ctx.snap.table("Objects and Elements - Areas")
    if df.empty:
        return []
    cols = [c for c in df.columns if c.startswith("ElmJt")]
    keys = df[cols].astype(str).apply(lambda r: "|".join(sorted(x for x in r if x and x != "nan")), axis=1)
    g = df.assign(_k=keys).groupby("_k")["ObjName"].nunique()
    dup = set(g[g > 1].index)
    if not dup:
        return []
    rows = df[keys.isin(dup)].drop_duplicates("ObjName")
    objs = [("area", sname(r["ObjName"]), {"label": str(r["ObjLabel"]), "story": str(r["Story"]), "tip": str(r["ObjType"])})
            for _, r in rows.iterrows()]
    return [Finding(ERROR, f"{len(objs)} arii se suprapun (aceleași noduri de element la obiecte diferite): rigiditate și masă dublate.", objs)]
