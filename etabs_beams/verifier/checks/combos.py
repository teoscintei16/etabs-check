"""Regula 9: combinatii de incarcari (acoperire ULS, combinatii seismice, SLS)."""
from __future__ import annotations

import re
from collections import defaultdict
from itertools import product

from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .loads import has_loads, pattern_usage
from .util import col, yes


SEISMIC_NAME = re.compile(r"^(?:T(?P<tower>\d+)[_-])?(?P<dir>[XY])(?P<sgn>[PN])$", re.I)


def pattern_tower(name: str) -> str | None:
    """„T2_XP” -> „T2” (turnul din numele tiparului seismic) sau None."""
    m = SEISMIC_NAME.match(name)
    return f"T{m.group('tower')}" if m and m.group("tower") else None


def load_combos(ctx) -> dict[str, tuple[str, list[tuple[str, float]]]]:
    lc = ctx.snap.table("Load Combination Definitions")
    if lc.empty:
        return {}
    lc = lc.copy()
    for c in ("Name", "Type"):
        lc[c] = lc[c].replace("", None).ffill()
    out = {}
    for n, g in lc.groupby("Name", sort=False):
        out[str(n)] = (str(g["Type"].iloc[0]), [(str(a), float(b)) for a, b in zip(g["LoadName"], g["SF"]) if str(a).strip()])
    return out


def expand(combos, name: str, k: float = 1.0, _stack=()) -> dict[str, float]:
    """Dezvolta combinatiile imbricate pana la tiparele/cazurile de baza (combinatiile Envelope nu se dezvolta)."""
    if name in _stack:
        return {}
    out: dict[str, float] = defaultdict(float)
    typ, items = combos[name]
    for load, sf in items:
        if load in combos:
            if combos[load][0].lower().startswith("env"):
                continue
            for a, b in expand(combos, load, k * sf, _stack + (name,)).items():
                out[a] += b
        else:
            out[load] += k * sf
    return dict(out)


def user_load_patterns(ctx) -> dict[str, tuple[str, str]]:
    """{tipar: (axa, excentricitate)} din „Auto Seismic - User Loads”: axa = directia cu forta totala nenula, ecc = semnul EccRatio."""
    df = ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Loads")
    out: dict[str, tuple[str, str]] = {}
    if df.empty:
        return out
    df = df.copy()
    df["Name"] = df["Name"].replace("", None).ffill()
    for name, g in df.groupby("Name", sort=False):
        fx = float(g["Fx"].fillna(0).abs().sum()) if "Fx" in g.columns else 0.0
        fy = float(g["Fy"].fillna(0).abs().sum()) if "Fy" in g.columns else 0.0
        ecc = [float(x) for x in g["EccRatio"] if x == x and str(x) != ""] if "EccRatio" in g.columns else []
        sign = "0" if not ecc or abs(ecc[0]) < 1e-12 else ("+" if ecc[0] > 0 else "-")
        out[str(name)] = ("X" if fx >= fy else "Y", sign)
    return out


def seismic_info(ctx):
    """({tipar/caz: (directie, excentricitate)}, {tipare Dead/Live/...: tip}) din tabele."""
    seis: dict[str, tuple[str, str]] = {}
    auto = ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Coefficient")
    if not auto.empty:
        for _, r in auto.iterrows():
            for d in ("X", "Y"):
                for key, ecc in ((f"{d}Dir", "0"), (f"{d}DirPlusE", "+"), (f"{d}DirMinusE", "-")):
                    if yes(r.get(key)):
                        seis[str(r["Name"])] = (d, ecc)
    for n, (ax, ecc) in user_load_patterns(ctx).items():            # tipare cu incarcari definite de utilizator
        seis.setdefault(n, (ax, ecc))
    lp = ctx.snap.table("Load Pattern Definitions")
    types = {str(r["Name"]): str(r["Type"]) for _, r in lp.iterrows()} if not lp.empty else {}
    for n, t in types.items():
        if t in ("Seismic", "Quake") and n not in seis:
            m = SEISMIC_NAME.match(n)                      # tipare cu incarcari definite de utilizator: Tn_XP / Tn_XN / Tn_YP / Tn_YN
            seis[n] = (m.group("dir"), "+" if m.group("sgn") == "P" else "-") if m else ("?", "0")
    cs = ctx.snap.table("Load Case Definitions - Summary")
    if not cs.empty:
        for _, r in cs.iterrows():
            if "response spectrum" in str(r["Type"]).lower():
                seis[str(r["Name"])] = ("RS", "0")
    return seis, types


@check("r9_acoperire", 9, "Toate încărcările apar în combinațiile ULS gravitaționale",
       params=[Param("sf_uls_min", 1.3, "Factor minim care identifică o combinație ULS (γG ≈ 1.35)", "")])
def r9_acoperire(ctx):
    combos = load_combos(ctx)
    if not combos:
        return []
    seis, types = seismic_info(ctx)
    check_types = ("Dead", "Super Dead", "Live", "Reduce Live", "Roof Live", "Snow", "Wind")
    wanted = [n for n, t in types.items() if t in check_types and n not in seis]
    uls = []
    for n, (t, items) in combos.items():
        if t.lower().startswith("env"):
            continue
        e = expand(combos, n)
        if e and not any(k in seis for k in e) and max(abs(v) for v in e.values()) >= ctx.p("sf_uls_min"):
            uls.append(n)
    if not uls:
        return [Finding(ERROR, "Nu există nicio combinație ULS gravitațională (cu factori ≈ 1.35 / 1.5).")]
    covered = set()
    for n in uls:
        covered |= {k for k, v in expand(combos, n).items() if abs(v) > 1e-9}
    missing = [n for n in wanted if n not in covered]
    if not missing:
        return [Finding(INFO, f"Toate tiparele gravitaționale apar în cel puțin o combinație ULS ({len(uls)} combinații).")]
    usage = pattern_usage(ctx)
    loaded = [n for n in missing if has_loads(usage.get(n))]
    empty = [n for n in missing if not has_loads(usage.get(n))]
    out = []

    def describe(n):
        u = usage[n]
        parts = []
        if u["arii"]:
            via = f" (prin seturile {', '.join(u['seturi'])})" if u["seturi"] else ""
            parts.append(f"{u['arii']} plăci/arii{via}")
        if u["bare"]:
            parts.append(f"{u['bare']} încărcări pe bare")
        if u["noduri"]:
            parts.append(f"{u['noduri']} încărcări în noduri")
        return f"{n}: " + ", ".join(parts)

    if loaded:
        out.append(Finding(ERROR, f"{len(loaded)} tipare au încărcări asignate, dar nu apar în nicio combinație ULS gravitațională, "
                                  "deci nu sunt luate în calcul la dimensionare: " + "; ".join(describe(n) for n in loaded) + ".",
                           [("loadpattern", n) for n in loaded], {"combinatii_uls": uls, "utilizare": {n: usage[n] for n in loaded}}))
    if empty:
        out.append(Finding(INFO, f"{len(empty)} tipare nu apar în ULS, dar nici nu au încărcări asignate: {', '.join(empty)}.",
                           [("loadpattern", n) for n in empty]))
    return out


@check("r9_seismice", 9, "Combinații seismice: ortogonale (±0.3), excentricitate, partea gravitațională",
       params=[Param("ortogonal", 0.3, "Factorul componentei ortogonale", "")])
def r9_seismice(ctx):
    combos = load_combos(ctx)
    seis, types = seismic_info(ctx)
    if not combos or not seis:
        return []
    k2 = ctx.p("ortogonal")
    sc = {}
    for n, (t, items) in combos.items():
        if t.lower().startswith("env"):
            continue
        e = expand(combos, n)
        s = {k: v for k, v in e.items() if k in seis and abs(v) > 1e-9}
        if s:
            sc[n] = (s, {k: v for k, v in e.items() if k not in seis and abs(v) > 1e-9})
    out = []
    if not sc:
        return [Finding(ERROR, "Există acțiune seismică, dar nicio combinație de încărcări nu o conține.")]
    # partea gravitationala identica
    grav_sets = {tuple(sorted((k, round(v, 6)) for k, v in g.items())) for _s, g in sc.values()}
    if len(grav_sets) > 1:
        out.append(Finding(WARNING, f"Partea gravitațională diferă între combinațiile seismice ({len(grav_sets)} variante): ψ2 nu e consecvent.",
                           [("combo", n) for n in sc]))
    # psi2 vs mass source
    ms = ctx.snap.table("Mass Source Definition")
    if not ms.empty and grav_sets:
        ms = ms.copy()
        mmap = {str(p): float(m) for p, m in zip(ms["LoadPattern"], ms["Multiplier"]) if str(p).strip() and m == m and str(m) != ""}
        diff = []
        for gs in sorted(grav_sets):                   # fiecare varianta de parte gravitationala se compara cu masa
            g0 = dict(gs)
            for p in sorted(set(g0) | set(mmap)):
                a, b = g0.get(p), mmap.get(p)
                if abs((a or 0) - (b or 0)) > 1e-6 and types.get(p) not in ("Seismic", "Quake") and not (p == "Dead" and b is None):
                    if (p, a, b) not in diff:
                        diff.append((p, a, b))
        if diff:
            out.append(Finding(WARNING, "Factorii de încărcări gravitaționale din combinațiile seismice diferă de multiplicatorii sursei de masă: "
                                        + "; ".join(f"{p}: combinație {a if a is not None else '—'} / masă {b if b is not None else '—'}" for p, a, b in diff) + ".",
                               [("loadpattern", p) for p in dict.fromkeys(d[0] for d in diff)]))
    # excentricitate accidentala: ± pe fiecare directie
    used = defaultdict(set)
    for s, _g in sc.values():
        for k in s:
            d, e = seis[k]
            if d in ("X", "Y"):
                used[d].add(e)
    for d in ("X", "Y"):
        if d in used and not {"+", "-"} <= used[d] and "0" not in used[d]:
            out.append(Finding(WARNING, f"Pe direcția {d} combinațiile folosesc doar o singură excentricitate accidentală ({', '.join(sorted(used[d]))})."))
    # ortogonale
    prim = [(k, sgn) for k, (d, _e) in seis.items() if d in ("X", "Y") for sgn in (1, -1)]
    present = set()
    pure = set()
    for n, (s, _g) in sc.items():
        items = sorted(s.items(), key=lambda kv: -abs(kv[1]))
        k1, v1 = items[0]
        if seis[k1][0] not in ("X", "Y"):
            continue
        if len(items) == 1:
            pure.add((k1, 1 if v1 > 0 else -1))
        elif len(items) == 2 and seis[items[1][0]][0] in ("X", "Y") and seis[items[1][0]][0] != seis[k1][0] \
                and abs(abs(items[1][1]) / abs(v1) - k2) < 0.03:
            present.add(((k1, 1 if v1 > 0 else -1), (items[1][0], 1 if items[1][1] > 0 else -1)))
    expected = {(p, (q, t)) for p in prim for q in [k for k, (d, _e) in seis.items() if d in ("X", "Y") and d != seis[p[0]][0]] for t in (1, -1)}
    miss_pure = [p for p in prim if p not in pure]
    miss_orth = expected - present
    if miss_pure:
        out.append(Finding(WARNING, f"{len(miss_pure)} combinații seismice pure (±E pe o direcție) lipsesc: " +
                           ", ".join(f"{'+' if s > 0 else '−'}{k}" for k, s in miss_pure[:8]) + ("…" if len(miss_pure) > 8 else "") + "."))
    if miss_orth:
        out.append(Finding(INFO if len(present) else WARNING,
                           f"Combinații cu componentă ortogonală {k2:g}·E: {len(present)} din {len(expected)} posibile "
                           "(componenta principală × excentricitate × semnul componentei ortogonale). Dacă alegi doar cazurile defavorabile, "
                           "poți justifica această constatare.", data={"lipsa": len(miss_orth), "exemple": [f"{'+' if a[1] > 0 else '−'}{a[0]} {'+' if b[1] > 0 else '−'}{k2:g}{b[0]}" for a, b in sorted(miss_orth)[:6]]}))
    return out


@check("r9_sls", 9, "Combinații SLS: caracteristică și cvasi-permanentă")
def r9_sls(ctx):
    combos = load_combos(ctx)
    seis, types = seismic_info(ctx)
    if not combos:
        return []
    char = quasi = None
    for n, (t, _it) in combos.items():
        if t.lower().startswith("env"):
            continue
        e = expand(combos, n)
        if not e or any(k in seis for k in e):
            continue
        vals = [abs(v) for v in e.values() if abs(v) > 1e-9]
        if vals and all(abs(v - 1.0) < 1e-9 for v in vals) and len(vals) > 1:
            char = char or n
        elif vals and max(vals) <= 1.0 + 1e-9 and any(v < 1.0 - 1e-9 for v in vals) and all(
                abs(abs(e[k]) - 1.0) < 1e-9 for k in e if types.get(k) in ("Dead", "Super Dead") and abs(e[k]) > 1e-9):
            quasi = quasi or n
    out = []
    if not char:
        out.append(Finding(WARNING, "Nu există combinație SLS caracteristică (toți factorii 1.0)."))
    if not quasi:
        out.append(Finding(WARNING, "Nu există combinație SLS cvasi-permanentă (G + ψ2·Q)."))
    if char and quasi:
        out.append(Finding(INFO, f"SLS: caracteristică „{char}”, cvasi-permanentă „{quasi}”. Combinația frecventă (G + ψ1·Q + ψ2·Q) nu se detectează automat."))
    return out
