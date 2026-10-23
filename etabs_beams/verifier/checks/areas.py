"""Geometrie de arii (elemente de mesh), pier/spandrel, goluri, componente conexe (reguli 3, 4, 5, 14, 16, 26-28)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from ...geometry import end_on_beam_hits
from ..elements import build_area_elements
from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .shells import shell_points
from .util import col, sname


# ---------------------------------------------------------------- date comune
def area_elements(ctx) -> pd.DataFrame:
    """O linie pe element de arie (coordonate X1..4, Y1..4, Z1..4; nume de noduri J1..4)."""
    return build_area_elements(ctx.snap.table, ctx.snap.cache)


def _poly_arrays(e: pd.DataFrame, axes="XY"):
    n = np.where(e["X4"].isna().to_numpy(), 3, 4)
    return n


def _sides(e: pd.DataFrame) -> np.ndarray:
    """Lungimile laturilor (n x 4, NaN la triunghiuri) in 3D."""
    pts = [np.stack([e[f"X{k}"], e[f"Y{k}"], e[f"Z{k}"]], axis=1).astype(float) for k in range(1, 5)]
    tri = e["X4"].isna().to_numpy()
    p4 = np.where(tri[:, None], pts[0], pts[3])                    # triunghi: ultima latura = 3->1
    seq = [pts[0], pts[1], pts[2], p4]
    sides = np.stack([np.linalg.norm(seq[i] - seq[(i + 1) % 4], axis=1) for i in range(4)], axis=1)
    sides[tri, 3] = np.linalg.norm(pts[2][tri] - pts[0][tri], axis=1)
    sides[tri, 2] = np.linalg.norm(pts[1][tri] - pts[2][tri], axis=1)
    return sides


def _obj(row, extra=None):
    d = {"label": str(row["ObjLabel"]), "story": str(row["Story"]), "tip": str(row["ObjType"])}
    d.update(extra or {})
    return ("area", row["ObjName"], d)


# ---------------------------------------------------------------- regula 5: calitatea mesh-ului
@check("r5_calitate_mesh", 5, "Calitatea elementelor de mesh: raport de aspect",
       params=[Param("aspect_max", 4.0, "Raport de aspect maxim admis (latura mare / latura mică)", "")])
def r5_calitate_mesh(ctx):
    e = area_elements(ctx)
    if e.empty:
        return []
    s = _sides(e)
    ratio = np.nanmax(s, axis=1) / np.maximum(np.nanmin(np.where(s > 0, s, np.nan), axis=1), 1e-9)
    bad = e[ratio > ctx.p("aspect_max")].assign(_r=ratio[ratio > ctx.p("aspect_max")])
    if bad.empty:
        return []
    worst = bad.sort_values("_r", ascending=False).drop_duplicates("ObjName")
    objs = [_obj(r, {"raport_max": round(float(r["_r"]), 1)}) for _, r in worst.iterrows()]
    return [Finding(WARNING, f"{len(bad)} elemente de mesh (din {worst['ObjName'].nunique()} arii) au raportul de aspect > {ctx.p('aspect_max'):g}: "
                             "rezultate mai puțin stabile.", objs, {"cel_mai_rau": round(float(bad["_r"].max()), 1)})]


# ---------------------------------------------------------------- regula 14: sensul placilor
@check("r14_normale_placi", 14, "Sensul axei locale 3 a plăcilor (toate în același sens)")
def r14_normale_placi(ctx):
    e = area_elements(ctx)
    if e.empty:
        return []
    f = e[e["ObjType"].astype(str) == "Floor"].drop_duplicates("ObjName")
    if f.empty:
        return []
    xs = np.stack([f[f"X{k}"].to_numpy(dtype=float) for k in range(1, 5)], axis=1)
    ys = np.stack([f[f"Y{k}"].to_numpy(dtype=float) for k in range(1, 5)], axis=1)
    tri = np.isnan(xs[:, 3])
    xs[tri, 3], ys[tri, 3] = xs[tri, 2], ys[tri, 2]                      # triunghi: al patrulea nod repetat
    nz = (xs * np.roll(ys, -1, axis=1) - np.roll(xs, -1, axis=1) * ys).sum(axis=1)       # aria orientata (formula lui Gauss): robusta si la patrulatere concave
    up = nz > 0
    minority = up.sum() < len(f) / 2
    bad = f[(up if minority else ~up) & (np.abs(nz) > 1e-9)]
    if bad.empty or len(bad) == len(f):
        return []
    return [Finding(WARNING, f"{len(bad)} plăci au ordinea nodurilor inversă față de majoritate ({'în sus' if not minority else 'în jos'}): "
                             "axa locală 3 și sensul încărcărilor de suprafață sunt opuse.", [_obj(r) for _, r in bad.iterrows()])]


# ---------------------------------------------------------------- regula 3: goluri in placi
@check("r3_goluri", 3, "Goluri în plăci mai mari de 1 m² (cutia scărilor, lifturi, ghene)",
       params=[Param("gol_min", 1.0, "Suprafața minimă a golului raportat", "m²")])
def r3_goluri(ctx):
    e = area_elements(ctx)
    if e.empty:
        return []
    f = e[(e["ObjType"].astype(str) == "Floor") & e["Z3"].notna()]
    out, rows = [], []
    for story, g in f.groupby("Story", sort=False):
        pts = np.stack([g[[f"X{k}", f"Y{k}"]].to_numpy(dtype=float) for k in range(1, 5)], axis=1)
        tri = g["X4"].isna().to_numpy()
        pts[tri, 3] = pts[tri, 2]                                  # triunghi -> al patrulea nod repetat
        polys = shapely.polygons(pts)
        polys = polys[shapely.is_valid(polys) & (shapely.area(polys) > 0)]
        if len(polys) == 0:
            continue
        u = shapely.union_all(shapely.set_precision(polys, 1e-4))     # coverage_union ar fi mai rapid, dar da rezultate gresite la muchii neconforme
        for poly in (u.geoms if hasattr(u, "geoms") else [u]):
            for ring in poly.interiors:
                hole = shapely.Polygon(ring)
                if hole.area >= ctx.p("gol_min"):
                    c = hole.centroid
                    rows.append({"etaj": str(story), "suprafata_m2": round(hole.area, 2), "x": round(c.x, 2), "y": round(c.y, 2)})
    if not rows:
        return []
    rows.sort(key=lambda r: -r["suprafata_m2"])
    return [Finding(INFO, f"{len(rows)} goluri de peste {ctx.p('gol_min'):g} m² în plăci (pe {len({r['etaj'] for r in rows})} niveluri). "
                          "Verifică dacă sunt cele din arhitectură; un gol necesar care lipsește nu poate fi detectat automat.",
                    data={"goluri": rows[:40]})]


# ---------------------------------------------------------------- regula 4: pier / spandrel
def _wall_table(ctx) -> pd.DataFrame:
    sp = ctx.snap.table("Area Assignments - Section Properties")
    if sp.empty:
        return sp
    w = sp[sp["PropType"].astype(str) == "Wall"].copy()
    w["_n"] = [sname(x) for x in w["UniqueName"]]
    model = ctx.snap.loaded_model() or ctx.snap.model
    sloped = set(getattr(model, "sloped_walls", {}) or {})
    if sloped:                                                  # aria cu proprietate Wall dar inclinata nu e perete vertical: nu poate avea eticheta Pier
        w = w[~w["_n"].isin(sloped)]
    pl = ctx.snap.table("Area Assignments - Pier Labels")
    lab = {sname(r["UniqueName"]): str(r["PierName"]) for _, r in pl.iterrows()} if not pl.empty else {}
    w["_pier"] = w["_n"].map(lambda n: lab.get(n, ""))
    bs = ctx.basement_stories()
    if bs and ctx.proj("pier_ignora_infra") != "nu":        # pereti de infrastructura: ignorati la etichetele Pier
        w = w[~w["Story"].astype(str).isin(ctx.story_ids(bs))]
    return w


def _wall_obj(r, extra=None):
    d = {"label": str(r["Label"]), "story": str(r["Story"]), "section": str(r["SectProp"])}
    d.update(extra or {})
    return ("area", r["_n"], d)


@check("r4_pier_etichete", 4, "Etichete Pier pe pereți: fiecare perete etichetat, o etichetă per perete (nu pe felii)")
def r4_pier_etichete(ctx):
    w = _wall_table(ctx)
    if w.empty:
        return []
    out = []
    none = w[w["_pier"] == ""]
    if len(none):
        out.append(Finding(WARNING, f"{len(none)} pereți din {len(w)} nu au etichetă Pier: eforturile pe perete nu se pot extrage pe ansamblu.",
                           [_wall_obj(r) for _, r in none.iterrows()]))
    e = area_elements(ctx)
    if not e.empty:
        ew = e[e["ObjName"].isin(set(w["_n"]))]
        # adiacenta: obiecte de perete cu >= 2 noduri comune si acelasi plan (directie orizontala), pe acelasi nivel
        ang = {}
        for obj, g in ew.groupby("ObjName", sort=False):
            r = g.iloc[0]
            dx, dy = r["X2"] - r["X1"], r["Y2"] - r["Y1"]
            if abs(dx) + abs(dy) < 1e-9:
                dx, dy = r["X3"] - r["X1"], r["Y3"] - r["Y1"]
            ang[obj] = np.degrees(np.arctan2(dy, dx)) % 180.0
        a = ctx.snap.table("Objects and Elements - Areas")
        jc = [c for c in a.columns if c.startswith("ElmJt")]
        wa = a[a["ObjName"].map(sname).isin(set(w["_n"]))]
        owners: dict[str, set[str]] = {}
        for _, r in wa.iterrows():
            for c in jc:
                nm = str(r[c])
                if nm and nm != "nan":
                    owners.setdefault(nm, set()).add(sname(r["ObjName"]))
        pairs: dict[tuple[str, str], int] = {}
        for nm, objs in owners.items():
            if len(objs) > 1:
                ol = sorted(objs)
                for i in range(len(ol)):
                    for k in range(i + 1, len(ol)):
                        pairs[(ol[i], ol[k])] = pairs.get((ol[i], ol[k]), 0) + 1
        idx = {n: i for i, n in enumerate(w["_n"])}
        rows, cols = [], []
        story = dict(zip(w["_n"], w["Story"].astype(str)))
        for (p, q), cnt in pairs.items():
            if cnt >= 2 and story.get(p) == story.get(q) and p in ang and q in ang:
                d = abs(ang[p] - ang[q])
                if min(d, 180 - d) < 5.0:
                    rows.append(idx[p]); cols.append(idx[q])
        if rows:
            m = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(idx), len(idx)))
            _n, comp = connected_components(m, directed=False)
            w = w.assign(_c=comp)
            bad = []
            for c, g in w.groupby("_c"):
                labels = {x for x in g["_pier"]}
                if len(g) > 1 and len(labels) > 1:
                    bad += [_wall_obj(r, {"etichete_in_grup": sorted(labels - {""}) or ["(fără)"]}) for _, r in g.iterrows()]
            if bad:
                out.append(Finding(WARNING, f"{len(bad)} felii de perete (în plan comun, pe același nivel) au etichete Pier diferite sau lipsă: "
                                            "programul va da eforturi separate pe fiecare felie.", bad))
    return out


@check("r4_pier_continuitate", 4, "Continuitatea verticală a etichetelor Pier (fără etaje lipsă)")
def r4_pier_continuitate(ctx):
    w = _wall_table(ctx)
    st = ctx.snap.table("Story Definitions")
    if w.empty or st.empty:
        return []
    order = {s: i for i, s in enumerate(ctx.stories())}
    gaps = {}
    for lab, g in w[w["_pier"] != ""].groupby("_pier"):
        pos = sorted({order[ctx.plain_story(s)] for s in g["Story"].astype(str) if ctx.plain_story(s) in order})
        miss = [i for i in range(pos[0], pos[-1] + 1) if i not in pos] if pos else []
        if miss:
            names = {i: s for s, i in order.items()}
            gaps[lab] = [names[i] for i in miss]
    if not gaps:
        return []
    return [Finding(WARNING, f"{len(gaps)} etichete Pier lipsesc la unul sau mai multe niveluri intermediare (perete întrerupt sau etichetă lipsă): "
                             + ", ".join(sorted(gaps)[:12]) + ".", [("pier", k) for k in sorted(gaps)], {k: f"lipsește la {', '.join(v)}" for k, v in sorted(gaps.items())})]


@check("r4_grinzi_cuplare", 4, "Grinzi de cuplare între pereți fără etichetă Spandrel")
def r4_grinzi_cuplare(ctx):
    model = ctx.snap.model
    belts = set(model.belt_names)
    cand = []
    for n in model.beam_names:
        f = model.frames[n]
        if n in belts or not model.node_areas.get(f.p1) or not model.node_areas.get(f.p2):
            continue
        shared = set(model.node_areas[f.p1]) & set(model.node_areas[f.p2])
        if shared:
            continue                                               # grinda sta pe un singur perete (centura/grinda pe perete)
        cand.append(n)
    if not cand:
        return []
    sp = ctx.snap.table("Frame Assignments - Spandrel Labels")
    have = {sname(x) for x in sp[col(sp, "UniqueName")]} if not sp.empty else set()
    miss = [n for n in cand if n not in have]
    defs = ctx.snap.table("Spandrel Label Definitions")
    msg = f"{len(miss)} grinzi leagă doi pereți diferiți (posibile grinzi de cuplare / buiandrugi) fără etichetă Spandrel"
    if not defs.empty and sp.empty:
        msg += f"; etichete definite ({', '.join(map(str, defs['Name']))}) dar neasignate"
    return [Finding(INFO, msg + ".", [("frame", n) for n in miss])] if miss else []


@check("r4_centuri_capete", 4, "Centuri (dummy) la capetele pereților unde se descarcă grinzi reale")
def r4_centuri_capete(ctx):
    model = ctx.snap.model
    if not model.belt_names:
        return []
    belt_nodes = set()
    for b in model.belt_names:
        f = model.frames[b]
        belt_nodes |= {f.p1, f.p2}
    on_belts = {p for _f, p, _g in end_on_beam_hits(model, model.beam_names, targets=model.belt_names)}
    shell_pts = shell_points(ctx)                              # nodul peretelui pe care reazema o coaja: nu e o descarcare de grinda
    miss = []
    for n in model.beam_names:
        f = model.frames[n]
        for p, xyz in ((f.p1, f.start), (f.p2, f.end)):
            if model.node_areas.get(p) and p not in belt_nodes and p not in on_belts and tuple(round(float(v), 3) for v in xyz) not in shell_pts:
                miss.append(n)
                break
    if not miss:
        return []
    return [Finding(WARNING, f"{len(miss)} grinzi se descarcă într-un nod de perete unde nu există nicio centură (dummy): "
                             "momentele nu se transmit corect peretelui.", [("frame", n) for n in miss])]


# ---------------------------------------------------------------- regula 16: planșee deck
@check("r16_directii_deck", 16, "Planșee Deck/Ribbed: direcția de descărcare (axa locală) pe grupe")
def r16_directii_deck(ctx):
    sec = ctx.snap.table("Area Section Property Definitions - Summary")
    asg = ctx.snap.table("Area Assignments - Section Properties")
    if sec.empty or asg.empty:
        return []
    deck = set(sec[sec["Type"].astype(str).isin(["Deck", "Ribbed", "Waffle"])]["Name"].astype(str))
    d = asg[asg["SectProp"].astype(str).isin(deck)]
    if d.empty:
        return []
    ax = ctx.snap.table("Area Assignments - Local Axes")
    ang = {sname(r["UniqueName"]): float(r["Angle"]) for _, r in ax.iterrows()} if not ax.empty else {}
    groups: dict[tuple, list] = {}
    for _, r in d.iterrows():
        groups.setdefault((str(r["SectProp"]), ang.get(sname(r["UniqueName"]), 0.0) % 180), []).append(r)
    objs = [("area", sname(r["UniqueName"]), {"label": str(r["Label"]), "story": str(r["Story"]), "section": str(r["SectProp"]),
                                              "unghi_axa_1": ang.get(sname(r["UniqueName"]), 0.0)}) for _, r in d.iterrows()]
    return [Finding(INFO, f"{len(d)} plăci Deck/Ribbed, în {len(groups)} grupe de orientare (secțiune, unghi axă locală): "
                          + "; ".join(f"{s} la {a:g}°: {len(v)}" for (s, a), v in sorted(groups.items())) +
                          ". Confirmă în lista de control că direcția de descărcare este spre grinzile/pereții de reazem.", objs)]


# ---------------------------------------------------------------- reguli 26-28: corpuri independente
def _components(ctx):
    """(DataFrame noduri cu componenta, nume noduri->idx) pentru elementele de deasupra cotei +/-0.00 (sau toate)."""
    cache = ctx.snap.cache
    if "components" in cache:
        return cache["components"]
    stories = ctx.stories()
    ground = ctx.ground_story()
    keep = ctx.story_ids(stories[: stories.index(ground) + 1] if ground in stories else stories)
    a, f = ctx.snap.table("Objects and Elements - Areas"), ctx.snap.table("Objects and Elements - Frames")
    parts_a, parts_b = [], []
    if not a.empty:
        ak = a[a["Story"].astype(str).isin(keep)]
        j1 = ak["ElmJt1"].astype(str).to_numpy(dtype=object)
        for k in (2, 3, 4):
            jk = ak[f"ElmJt{k}"].astype(str).to_numpy(dtype=object)
            ok_ = (jk != "") & (jk != "nan")
            parts_a.append(j1[ok_])
            parts_b.append(jk[ok_])
    if not f.empty:
        fk = f[f["Story"].astype(str).isin(keep)]
        parts_a.append(fk["ElmJtI"].astype(str).to_numpy(dtype=object))
        parts_b.append(fk["ElmJtJ"].astype(str).to_numpy(dtype=object))
    if not parts_a or sum(len(x) for x in parts_a) == 0:
        cache["components"] = (pd.DataFrame(), {})
        return cache["components"]
    ea, eb = np.concatenate(parts_a), np.concatenate(parts_b)
    codes, names = pd.factorize(np.concatenate([ea, eb]))
    r, c = codes[: len(ea)], codes[len(ea):]
    idx = {n: i for i, n in enumerate(names)}
    _n, comp = connected_components(coo_matrix((np.ones(len(r)), (r, c)), shape=(len(names),) * 2), directed=False)
    j = ctx.snap.table("Objects and Elements - Joints").drop_duplicates("ElmName")
    jd = j.set_index(j["ElmName"].astype(str))[["GlobalX", "GlobalY", "GlobalZ", "Story"]]
    df = jd.reindex(names)
    df["comp"] = comp
    df.index.name = "joint"
    cache["components"] = (df, idx)
    return cache["components"]


@check("r26_corpuri", 26, "Corpuri independente (turnuri): componente conexe, diafragme și turnuri definite",
       params=[Param("rost_min", 0.10, "Distanța sub care două corpuri separate sunt considerate prea apropiate", "m"),
               Param("corp_min_elem", 200, "Număr minim de noduri pentru a socoti un corp (ignoră elemente izolate)", "noduri")])
def r26_corpuri(ctx):
    df, _idx = _components(ctx)
    if df.empty:
        return []
    out = []
    sizes = df.groupby("comp").size()
    big = sizes[sizes >= ctx.p("corp_min_elem")]
    small = sizes[sizes < ctx.p("corp_min_elem")]
    ground = ctx.ground_story()
    scope = f"deasupra nivelului „{ground}”" if ground else "pe tot modelul (setează parterul în Setări pentru a exclude infrastructura comună)"
    tw = ctx.snap.table("Story Definitions")
    towers = sorted({str(t) for t in tw["Tower"]}) if not tw.empty else []
    if len(big) > 1:
        out.append(Finding(INFO, f"{len(big)} corpuri independente {scope} (noduri: {', '.join(map(str, big.tolist()))}); "
                                 f"turnuri definite în model: {len(towers)} ({', '.join(towers)}).",
                           data={"corpuri": {int(k): int(v) for k, v in big.items()}}))
        if len(big) != len(towers):
            out.append(Finding(WARNING, f"Numărul de corpuri independente ({len(big)}) diferă de numărul de turnuri definite ({len(towers)})."))
    elif len(big) == 1:
        out.append(Finding(INFO, f"Un singur corp structural {scope}; turnuri definite: {len(towers)}."))
    if len(small):
        out.append(Finding(INFO, f"{len(small)} grupuri mici de elemente (< {int(ctx.p('corp_min_elem'))} noduri) nu sunt conectate la corpul principal "
                                 f"({int(small.sum())} noduri).", data={"grupuri": {int(k): int(v) for k, v in small.head(15).items()}}))
    # diafragme care leaga corpuri diferite
    dia = ctx.snap.table("Area Assignments - Diaphragms")
    a = ctx.snap.table("Objects and Elements - Areas")
    if not dia.empty and not a.empty and len(big) > 1:
        comp_of = df["comp"].to_dict()
        first = a.drop_duplicates("ObjName")
        obj_comp = {sname(r["ObjName"]): comp_of.get(str(r["ElmJt1"])) for _, r in first.iterrows()}
        d = dia[~dia["Diaphragm"].astype(str).isin(["None", ""])]
        per: dict[tuple, set] = {}
        for _, r in d.iterrows():
            c = obj_comp.get(sname(r["UniqueName"]))
            if c is not None and c in big.index:
                per.setdefault((str(r["Story"]), str(r["Diaphragm"])), set()).add(int(c))
        bad = [(s, dn, sorted(cs)) for (s, dn), cs in per.items() if len(cs) > 1]
        if bad:
            out.append(Finding(ERROR, f"{len(bad)} diafragme (nivel, nume) conțin plăci din corpuri independente diferite: forțele laterale se redistribuie între turnuri.",
                               [("diaphragm", f"{dn}@{s}") for s, dn, _c in bad], {f"{dn}@{s}": cs for s, dn, cs in bad}))
    return out


@check("r27_rosturi", 27, "Rosturi între corpuri: distanță minimă între noduri din corpuri diferite",
       params=[Param("rost_min_dist", 0.10, "Distanța sub care rostul e suspect", "m"),
               Param("corp_min_nod", 200, "Număr minim de noduri pentru a socoti un corp", "noduri")])
def r27_rosturi(ctx):
    df, _ = _components(ctx)
    if df.empty:
        return []
    sizes = df.groupby("comp").size()
    big = list(sizes[sizes >= ctx.p("corp_min_nod")].index)
    if len(big) < 2:
        return []
    res = []
    for story, g in df[df["comp"].isin(big)].dropna(subset=["GlobalX"]).groupby("Story"):
        if g["comp"].nunique() < 2:
            continue
        xyz = g[["GlobalX", "GlobalY", "GlobalZ"]].to_numpy(dtype=float)
        pairs = cKDTree(xyz).query_pairs(ctx.p("rost_min_dist"), output_type="ndarray")
        comps = g["comp"].to_numpy()
        for p, q in pairs:
            if comps[p] != comps[q]:
                res.append((str(story), float(np.linalg.norm(xyz[p] - xyz[q])), g.index[p], g.index[q]))
    if not res:
        return []
    return [Finding(WARNING, f"{len(res)} perechi de noduri din corpuri independente diferite sunt la mai puțin de {ctx.p('rost_min_dist') * 100:g} cm: "
                             "rostul seismic e prea îngust sau neconectat corect.",
                    data={"exemple": [{"etaj": s, "distanta_m": round(d, 4), "noduri": [a, b]} for s, d, a, b in sorted(res, key=lambda t: t[1])[:10]]})]


@check("r28_pier_pe_corpuri", 28, "Etichetele Pier nu se repetă între corpuri independente")
def r28_pier_pe_corpuri(ctx):
    df, _ = _components(ctx)
    pl = ctx.snap.table("Area Assignments - Pier Labels")
    a = ctx.snap.table("Objects and Elements - Areas")
    if df.empty or pl.empty or a.empty:
        return []
    sizes = df.groupby("comp").size()
    big = set(sizes[sizes >= 200].index)
    if len(big) < 2:
        return []
    comp_of = df["comp"].to_dict()
    first = a.drop_duplicates("ObjName")
    obj_comp = {sname(r["ObjName"]): comp_of.get(str(r["ElmJt1"])) for _, r in first.iterrows()}
    obj_story = {sname(r["ObjName"]): str(r["Story"]) for _, r in first.iterrows()}
    per: dict[str, set] = {}
    members: list[tuple[str, str, int]] = []              # (arie, eticheta, corp)
    for _, r in pl.iterrows():
        c = obj_comp.get(sname(r["UniqueName"]))
        if c in big:
            per.setdefault(str(r["PierName"]), set()).add(int(c))
            members.append((sname(r["UniqueName"]), str(r["PierName"]), int(c)))
    dup = {k: sorted(v) for k, v in per.items() if len(v) > 1}
    if not dup:
        return []
    # prefix per corp: turnul dominant al corpului (daca e unic intre corpuri), altfel C<n>
    from collections import Counter
    towers_of: dict[int, Counter] = {}
    for name, _p, c in members:
        t = ctx.tower_of(obj_story.get(name, ""))
        if t:
            towers_of.setdefault(c, Counter())[t] += 1
    main = {c: cnt.most_common(1)[0][0] for c, cnt in towers_of.items()}
    prefix = {c: (main[c] if c in main and list(main.values()).count(main[c]) == 1 else f"C{c}") for c in {m[2] for m in members}}
    renames = [{"name": n, "pier": f"{prefix[c]}_{p}"} for n, p, c in members if p in dup]
    return [Finding(WARNING, f"{len(dup)} etichete Pier sunt folosite în mai multe corpuri independente: " + ", ".join(sorted(dup)[:12]) +
                    ". Fiecare turn trebuie să aibă etichete diferite.", [("pier", k) for k in sorted(dup)], {k: f"corpuri {v}" for k, v in dup.items()},
                    fix={"id": "rename_piers", "label": f"Prefixează {len(renames)} arii cu turnul/corpul", "args": {"renames": renames}})]
