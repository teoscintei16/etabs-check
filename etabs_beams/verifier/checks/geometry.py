"""Regula 5: geometrie curata si mesh."""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .util import col, sname, yes


@check("r5_noduri", 5, "Noduri duplicate/prea apropiate și coordonate cu zecimale parazite",
       params=[Param("dist_noduri_min", 0.02, "Distanța minimă între noduri distincte", "m"),
               Param("zecimale_parazite_max", 1e-4, "Abatere maximă de la grila de 1 mm considerată „parazită”", "m")])
def r5_noduri(ctx):
    j = ctx.snap.table("Objects and Elements - Joints")
    if j.empty:
        return []
    j = j[j["ObjType"].astype(str) == "Joint"].drop_duplicates("ObjName")
    pc = ctx.snap.table("Point Object Connectivity")            # punctele create automat de ETABS (IsAuto = Yes) au coordonate oarecare: nu sunt greseli de desen
    if not pc.empty and "IsAuto" in pc.columns:
        j = j[~j["ObjName"].map(sname).isin({sname(n) for n, a in zip(pc["UniqueName"], pc["IsAuto"]) if str(a).strip().lower() == "yes"})]
    j = j.reset_index(drop=True)
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
        rows = []
        for i in bad:
            for k, ax in enumerate("XYZ"):
                if 1e-9 < dev[i, k] <= tol:
                    rows.append({"name": names[int(i)], "label": str(j.loc[i, "ObjLabel"]), "story": str(j.loc[i, "Story"]), "axis": ax,
                                 "current": float(xyz[i, k]), "value": float(round(xyz[i, k], 3)) + 0.0})
        zero = sum(1 for r in rows if r["value"] == 0)
        out.append(Finding(WARNING, f"{len(bad)} noduri au coordonate cu zecimale parazite (abatere ≤ {tol:g} m față de grila de 1 mm), "
                                    f"tipic după desen din AutoCAD ({zero} valori aproape de 0, {len(rows) - zero} de rotunjit).", [obj(int(i)) for i in bad],
                           {"valori": [f"{r['name']} {r['axis']}={r['current']!r}" for r in rows[:30]]},
                           fix={"id": "move_nodes", "label": f"Corectează {len(rows)} coordonate", "args": {"rows": rows}}))
    return out


@check("r5_mesh", 5, "Setările de mesh pentru plăci și pereți",
       params=[Param("mesh_max", 0.5, "Dimensiunea maximă aproximativă a elementelor (standard)", "m")])
def r5_mesh(ctx):
    out = []
    lim = ctx.p("mesh_max")

    def fx(scope, label):
        return {"id": "apply_mesh_standard", "label": label, "args": {"scope": scope, "mesh_max": lim}}

    fl = ctx.snap.table("Analysis Options - Automatic Mesh Settings for Floors")
    if not fl.empty:
        r = fl.iloc[0]
        c = col(fl, "MaxMeshSize")
        bad = []
        if str(r.get("MeshOpt", "")).strip().lower() != "rectangular":
            bad.append(f"opțiunea de mesh este „{r.get('MeshOpt')}” (standard: Rectangular)")
        for f, label in (("Localized", "Use Localized Meshing"), ("MergeJoints", "Merge Joints")):
            if f in fl.columns and not yes(r[f]):
                bad.append(f"„{label}” este dezactivat")
        if c and abs(float(r[c]) - lim) > 1e-9:
            bad.append(f"dimensiunea maximă este {float(r[c]):g} m (standard: {lim:g} m)")
        if bad:
            out.append(Finding(WARNING, "Setările globale de mesh ale plăcilor diferă de standard: " + "; ".join(bad) + ".",
                               [("mesh", "Floors")], fix=fx("floor_global", "Aplică standardul plăcilor")))
    wl = ctx.snap.table("Analysis Options - Automatic Rectangular Mesh Options for Walls")
    c = col(wl, "MaxMeshSize") if not wl.empty else None
    if c and abs(float(wl.iloc[0][c]) - lim) > 1e-9:
        out.append(Finding(WARNING, f"Dimensiunea maximă a mesh-ului pentru pereți este {float(wl.iloc[0][c]):g} m (standard: {lim:g} m).",
                           [("mesh", "Walls")], fix=fx("wall_global", "Aplică dimensiunea standard (pereți)")))
    for key, what, scope in (("Area Assignments - Floor Auto Mesh Options", "plăci", "floor_areas"),
                             ("Area Assignments - Wall Auto Mesh Options", "pereți", "wall_areas")):
        df = ctx.snap.table(key)
        if df.empty:
            continue
        mo, rs = col(df, "MeshOption"), col(df, "Restraints")
        want = "auto rectangular" if scope == "wall_areas" else "default"       # pereti: mesh rectangular automat (altfel panoul ramane un singur element)
        odd = df[(df[mo].astype(str).str.lower() != want) | (~df[rs].map(yes) if rs else False)]
        if len(odd):
            objs = [("area", sname(r["UniqueName"]), {"label": str(r["Label"]), "story": str(r["Story"]), "mesh": str(r[mo])})
                    for _, r in odd.iterrows()]
            out.append(Finding(INFO, f"{len(odd)} arii ({what}) au opțiuni de mesh diferite de standard (opțiune „{'Auto Rectangular' if scope == 'wall_areas' else 'Default'}” și "
                                     f"„Add Restraints” activ; acum: {', '.join(sorted(set(odd[mo].astype(str))))}).", objs,
                               fix=fx(scope, f"Aplică standardul la {len(odd)} {what}")))
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
