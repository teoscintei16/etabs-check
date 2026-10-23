"""Reguli 8 (actiunea seismica), 20 (forte statice echivalente) si 12 (baza seismica)."""
from __future__ import annotations

from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .util import col, sname, yes

G = 9.81
_NEED_SPECTRUM = ("ag", "gamma_I", "beta0", "Tb", "Tc", "Td", "q")
_NAMES = {"ag": "ag", "gamma_I": "γI", "beta0": "β0", "Tb": "TB", "Tc": "TC", "Td": "TD", "q": "q"}


def spectrum_shape(T: float, beta0: float, q: float, Tb: float, Tc: float, Td: float) -> float:
    """Sd(T)/(ag·γI·g) conform P100-1 (spectrul de proiectare, cu factorul de comportare q)."""
    if T <= Tb:
        return 1.0 + (beta0 / q - 1.0) * T / Tb if Tb > 0 else beta0 / q
    if T <= Tc:
        return beta0 / q
    if T <= Td:
        return beta0 / q * Tc / T
    return beta0 / q * Tc * Td / T ** 2


def spectrum(ctx, T: float) -> float:
    """Sd(T) in m/s² cu parametrii proiectului (γI inclus)."""
    p = ctx.project
    shape = max(spectrum_shape(T, p["beta0"], p["q"], p["Tb"], p["Tc"], p["Td"]), float(p.get("beta_lim") or 0.0))
    return p["ag"] * G * p["gamma_I"] * shape


def _missing_info(ctx, names, what):
    miss = ctx.missing(*names)
    if miss:
        return Finding(INFO, f"{what} nu poate fi verificat: completează în Setări parametrii proiectului ({', '.join(_NAMES.get(m, m) for m in miss)}).")
    return None


def _rs_cases(ctx):
    df = ctx.snap.table("Load Case Definitions - Response Spectrum")
    if df.empty:
        return []
    df = df.copy()
    df["Name"] = df["Name"].replace("", None).ffill()
    out = []
    for name, grp in df.groupby("Name", sort=False):
        head = grp.iloc[0]
        comps = []
        ld, fn, sf = col(grp, "LoadName"), col(grp, "Function"), col(grp, "TransAccSF")
        for _, r in grp.iterrows():
            if str(r[ld]).strip():
                comps.append((str(r[ld]).strip(), str(r[fn]).strip(), float(r[sf]) if r[sf] == r[sf] else 0.0))
        out.append({"name": str(name), "head": head, "components": comps})
    return out


@check("r8_spectru", 8, "Spectrul de răspuns: forma P100-1 și factorul de scară (inclusiv g)",
       params=[Param("spectru_toleranta_pct", 3.0, "Abatere admisă față de spectrul calculat", "%")])
def r8_spectru(ctx):
    cases = _rs_cases(ctx)
    if not cases:
        return [Finding(INFO, "Nu există cazuri de tip spectru de răspuns.")]
    out = []
    note = _missing_info(ctx, _NEED_SPECTRUM, "Spectrul")
    if note:
        out.append(note)
        return out
    fdf = ctx.snap.table("Functions - Response Spectrum - User Defined")
    funcs = {}
    if not fdf.empty:
        f = fdf.copy()
        f["Name"] = f["Name"].replace("", None).ffill()
        for n, g in f.groupby("Name", sort=False):
            funcs[str(n)] = list(zip(g["Period"].astype(float), g["Value"].astype(float)))
    tol = ctx.p("spectru_toleranta_pct") / 100.0
    p = ctx.project
    seen = set()
    for c in cases:
        comps = c["components"]
        main = max(comps, key=lambda x: abs(x[2])) if comps else None      # componenta principala (100%); cealalta e 30%, verificata in r8_caz_spectru
        for load, fname, sf in ([main] if main else []):
            if fname not in funcs:
                out.append(Finding(WARNING, f"Funcția „{fname}” a cazului „{c['name']}” nu e o funcție definită de utilizator; spectrul nu poate fi comparat.",
                                   [("loadcase", c["name"])]))
                continue
            pts = funcs[fname]
            if fname not in seen:
                seen.add(fname)
                bad = []
                for T, v in pts:
                    exp = spectrum(ctx, T)
                    if exp > 0 and abs(v / exp - 1.0) > tol:
                        bad.append({"T": T, "functie": round(v, 4), "calculat": round(exp, 4), "abatere_pct": round((v / exp - 1) * 100, 1)})
                if bad:
                    out.append(Finding(WARNING, f"Funcția spectrală „{fname}” nu coincide cu spectrul P100-1 calculat din parametrii proiectului "
                                                f"(în {len(bad)} din {len(pts)} puncte).", [("function", fname)],
                                       {"puncte": bad[:12], "parametri": {k: p[k] for k in _NEED_SPECTRUM}}))
            # factorul de scara: ordonata efectiva la platou trebuie sa fie ag·g·γI·β0/q
            peak = max(v for _t, v in pts) if pts else 0.0
            eff = peak * sf
            exp_peak = p["ag"] * G * p["gamma_I"] * max(1.0, p["beta0"] / p["q"])      # ordonata maxima a spectrului [m/s²]
            if sf and exp_peak and abs(eff / exp_peak - 1.0) > 0.1:
                ratio = eff / exp_peak
                plateau = exp_peak
                if abs(ratio * G - 1.0) < 0.1 or abs(ratio / G - 1.0) < 0.1:
                    msg = "factorul g (9.81) lipsește sau e aplicat de două ori"
                elif 1.1 < ratio <= 3.0:                       # amplificare voita (ex. P100-1: Fb dinamic >= 0,85 Fb static); corectitudinea o verifica r20_fb_static_dinamic
                    out.append(Finding(INFO, f"Cazul „{c['name']}” (direcția {load}): spectrul e amplificat ×{ratio:.2f} față de P100-1 (ordonata efectivă {eff:.3f} m/s²): "
                                             "acceptabil dacă amplificarea aduce forța tăietoare dinamică la ≥ 0,85 din cea statică (vezi regula 20).",
                                       [("loadcase", c["name"])], {"scale_factor": sf, "raport": round(ratio, 4)}))
                    continue
                else:
                    msg = "ordonata efectivă diferă de cea așteptată"
                out.append(Finding(ERROR, f"Cazul „{c['name']}” (direcția {load}): {msg} — ordonata efectivă maximă {eff:.3f} m/s² față de {plateau:.3f} m/s² așteptat.",
                                   [("loadcase", c["name"])], {"scale_factor": sf, "raport": round(ratio, 4)}))
    return out


@check("r8_caz_spectru", 8, "Cazul de spectru: combinare modală, direcțională, amortizare, excentricitate",
       params=[Param("amortizare", 0.05, "Amortizare așteptată", "")])
def r8_caz_spectru(ctx):
    out = []
    cases = _rs_cases(ctx)
    auto = ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Coefficient")
    from .combos import seismic_info
    ecc_static = bool(not auto.empty and col(auto, "EccRatio") and (auto[col(auto, "EccRatio")].astype(float) > 0).any()) or \
        any(v[1] in ("+", "-") for v in seismic_info(ctx)[0].values())
    for c in cases:
        h = c["head"]
        mc, dc, ecc = "ModalCombo", "DirCombo", "EccenRatio"
        obj = [("loadcase", c["name"])]
        if mc in h and str(h[mc]).strip() not in ("CQC", "GMC"):
            out.append(Finding(WARNING, f"Cazul „{c['name']}” combină modurile prin „{h[mc]}” (recomandat CQC/GMC pentru moduri apropiate).", obj))
        if dc in h and str(h[dc]).strip() not in ("SRSS", "Absolute", "ABS"):
            out.append(Finding(WARNING, f"Cazul „{c['name']}” folosește combinarea direcțională „{h[dc]}”.", obj))
        if ecc in h and float(h[ecc] or 0) == 0 and not ecc_static:
            out.append(Finding(WARNING, f"Cazul „{c['name']}” are excentricitate accidentală 0 și nu există tipare statice cu excentricitate: "
                                        "torsiunea accidentală lipsește.", obj))
        ratios = sorted(abs(s) for _l, _f, s in c["components"] if s)
        if len(ratios) == 2 and ratios[1] and not (0.25 <= ratios[0] / ratios[1] <= 0.35):
            out.append(Finding(WARNING, f"Cazul „{c['name']}”: raportul factorilor pe cele două direcții este {ratios[0] / ratios[1]:.2f}, "
                                        "nu 0.30 (regula 100% + 30%).", obj))
    damp = ctx.snap.table("Functions - Response Spectrum - User Defined")
    dc2 = col(damp, "DampRatio") if not damp.empty else None
    if dc2:
        vals = {float(x) for x in damp[dc2].dropna() if str(x) != ""}
        bad = [v for v in vals if abs(v - ctx.p("amortizare")) > 1e-9]
        if bad:
            out.append(Finding(WARNING, f"Amortizarea din funcțiile spectrale diferă de {ctx.p('amortizare'):g}: {', '.join(f'{b:g}' for b in bad)}."))
    return out


@check("r20_forte_statice", 20, "Forțe statice echivalente: ambele direcții, excentricități ±, coeficient seismic",
       params=[Param("coef_tol_pct", 5.0, "Depășirea admisă a coeficientului seismic față de platou", "%")])
def r20_forte_statice(ctx):
    df = ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Coefficient")
    if df.empty and not ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Loads").empty:
        return _r20_user_loads(ctx)
    if df.empty:
        return [Finding(INFO, "Nu există tipare seismice automate de tip „User Coefficient” (tiparele cu încărcări definite de utilizator se verifică la regula 29 și prin forța de bază din modelul rulat).")]
    out = []
    tx = [str(r["Name"]) for _, r in df.iterrows() if yes(r.get("XDir")) or yes(r.get("XDirPlusE")) or yes(r.get("XDirMinusE"))]
    ty = [str(r["Name"]) for _, r in df.iterrows() if yes(r.get("YDir")) or yes(r.get("YDirPlusE")) or yes(r.get("YDirMinusE"))]
    for lab, names, cols in (("X", tx, ("XDirPlusE", "XDirMinusE")), ("Y", ty, ("YDirPlusE", "YDirMinusE"))):
        if not names:
            out.append(Finding(ERROR, f"Nu există nicio forță statică echivalentă pe direcția {lab}."))
            continue
        sub = df[df["Name"].isin(names)]
        for c, sign in zip(cols, "+−"):
            if not any(yes(v) for v in sub[c]):
                out.append(Finding(WARNING, f"Pe direcția {lab} lipsește tiparul cu excentricitate accidentală {sign}.",
                                   [("loadpattern", n) for n in names]))
    ecc = ctx.proj("ecc")
    if ecc is not None:
        bad = [str(r["Name"]) for _, r in df.iterrows() if abs(float(r["EccRatio"]) - float(ecc)) > 1e-9 and
               (yes(r.get("XDirPlusE")) or yes(r.get("XDirMinusE")) or yes(r.get("YDirPlusE")) or yes(r.get("YDirMinusE")))]
        if bad:
            out.append(Finding(WARNING, f"Excentricitatea accidentală din tipare diferă de {float(ecc):g}: {', '.join(bad)}.",
                               [("loadpattern", n) for n in bad]))
    if not ctx.missing(*_NEED_SPECTRUM, "lambda_mfse"):
        p = ctx.project
        cmax = p["lambda_mfse"] * p["gamma_I"] * p["ag"] * p["beta0"] / p["q"]
        tol = 1 + ctx.p("coef_tol_pct") / 100.0
        high = [(str(r["Name"]), float(r["C"])) for _, r in df.iterrows() if float(r["C"]) > cmax * tol]
        if high:
            out.append(Finding(ERROR, f"Coeficientul seismic depășește valoarea de platou λ·γI·ag·β0/q = {cmax:.3f}: "
                                      + ", ".join(f"{n} ({c:g})" for n, c in high) + ".", [("loadpattern", n) for n, _c in high],
                               {"coeficient_platou": round(cmax, 4)}))
        else:
            out.append(Finding(INFO, f"Coeficienții seismici (max {float(df['C'].max()):g}) nu depășesc valoarea de platou {cmax:.3f}; "
                                     "compararea cu T1 se face după rulare."))
    return out


def _r20_user_loads(ctx):
    """Forte seismice date de utilizator pe niveluri: complet pe X/Y, ± excentricitate, valoarea excentricitatii, forta totala."""
    from collections import defaultdict

    from .combos import pattern_tower, user_load_patterns
    ul = ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Loads").copy()
    ul["Name"] = ul["Name"].replace("", None).ffill()
    info = user_load_patterns(ctx)
    out = []
    by_tower: dict[str, dict] = defaultdict(dict)
    totals = {}
    for n, (ax, ecc) in info.items():
        g = ul[ul["Name"] == n]
        tot = float(g["Fx" if ax == "X" else "Fy"].fillna(0).sum())
        totals[n] = tot
        by_tower[pattern_tower(n) or ""][(ax, ecc)] = n
    want = {("X", "+"), ("X", "-"), ("Y", "+"), ("Y", "-")}
    for tw, d in sorted(by_tower.items()):
        lack = want - set(d)
        if lack:
            out.append(Finding(WARNING, f"{tw or 'Modelul'}: lipsesc tipare seismice cu forțe definite de utilizator pentru " +
                               ", ".join(f"{a}{e}" for a, e in sorted(lack)) + " (direcție × excentricitate).", [("loadpattern", n) for n in d.values()]))
    ecc = ctx.proj("ecc")
    if ecc is not None:
        bad = []
        for n in info:
            vals = [abs(float(x)) for x in ul[ul["Name"] == n]["EccRatio"] if x == x and str(x) != ""]
            if vals and abs(vals[0] - float(ecc)) > 1e-9:
                bad.append((n, vals[0]))
        if bad:
            out.append(Finding(WARNING, f"Excentricitatea accidentală din tipare diferă de {float(ecc):g}: " + ", ".join(f"{n} ({v:g})" for n, v in bad) + ".",
                               [("loadpattern", n) for n, _v in bad]))
    out.append(Finding(INFO, f"{len(info)} tipare seismice cu forțe date pe niveluri; forța totală pe tipar: " +
                             "; ".join(f"{n} {abs(v):.0f} kN" for n, v in sorted(totals.items())[:12]) + ("…" if len(totals) > 12 else "") + "."))
    return out


def _stories_top_down(ctx) -> list[str]:
    st = ctx.snap.table("Story Definitions")
    return [str(s) for s in st["Story"]] if not st.empty else []


@check("r12_baza_seismica", 12, "Baza seismică: nivelul de la care acționează forțele (±0.00 la subsoluri rigide)")
def r12_baza_seismica(ctx):
    out = []
    tw = ctx.snap.table("Tower and Base Story Definitions")
    if tw.empty:
        return [Finding(INFO, "Definițiile turnurilor/nivelului de bază nu au putut fi citite.")]
    base = ", ".join(f"{r['Tower']}: {r['BSName']} (cota {r['BSElev']})" for _, r in tw.iterrows())
    bs = ctx.basement_stories()
    if bs == []:
        return [Finding(INFO, f"Model fără subsol (suprastructură încastrată la bază): baza seismică rămâne la nivelul de bază ({base}); verificarea nu se aplică.")]
    if bs is None:
        return [Finding(INFO, f"Nivel de bază în model: {base}. Pentru a verifica baza seismică, indică în Setări dacă există subsol și care sunt nivelurile lui.")]
    stories = ctx.stories()
    ground = ctx.ground_story()
    expected = stories[stories.index(ground) + 1] if ground in stories and stories.index(ground) + 1 < len(stories) else None
    if expected is None:
        return [Finding(WARNING, "Nu există niveluri sub parter, deși ai indicat subsoluri.")]
    pat = ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Coefficient")
    if pat.empty:
        ul = ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Loads")
        if not ul.empty:                                         # tipare cu forte date pe niveluri: nu trebuie sa existe forte in subsol
            u = ul.copy()
            u["Name"] = u["Name"].replace("", None).ffill()
            ids = ctx.story_ids(bs)
            low = u[u["Story"].astype(str).isin(ids) & ((u["Fx"].fillna(0).abs() > 0) | (u["Fy"].fillna(0).abs() > 0))]
            if len(low):
                names = sorted(set(low["Name"].astype(str)))
                return [Finding(ERROR, f"Cu subsoluri rigide, forțele seismice nu trebuie aplicate în subsol, dar tiparele {', '.join(names)} au forțe la "
                                       f"{', '.join(sorted(set(low['Story'].astype(str)))[:8])}.", [("loadpattern", n) for n in names])]
            return [Finding(INFO, f"Tiparele seismice cu forțe date pe niveluri nu au forțe în subsol ({', '.join(bs)}).")]
        return [Finding(INFO, "Nu există tipare seismice automate; baza seismică a cazurilor de spectru se verifică manual.")]
    bad = [str(r["Name"]) for _, r in pat.iterrows() if str(r["BotStory"]) != expected]
    if bad:
        out.append(Finding(ERROR, f"Cu subsoluri rigide, forțele seismice trebuie aplicate de la nivelul „{expected}” (sub parterul „{ground}”), "
                                  f"dar tiparele {', '.join(bad)} au baza la „{pat.iloc[0]['BotStory']}”: masa subsolurilor intră în forța tăietoare de bază.",
                           [("loadpattern", n) for n in bad], {"nivel_asteptat": expected}))
    else:
        out.append(Finding(INFO, f"Tiparele seismice au baza la „{expected}” (sub parterul „{ground}”)."))
    return out


# ---------------------------------------------------------------- regula 29: seism pe turnuri
@check("r29_seism_pe_turnuri", 29, "Acțiunea seismică definită separat și coerent pe fiecare turn")
def r29_seism_pe_turnuri(ctx):
    from collections import defaultdict

    from .combos import pattern_tower, seismic_info
    from .loads import has_loads, pattern_usage
    towers = ctx.towers()
    if len(towers) < 2:
        return []                                                          # regula se aplica doar la modele cu mai multe turnuri
    seis, _types = seismic_info(ctx)
    static = {n: v for n, v in seis.items() if v[0] in ("X", "Y")}
    by_tower: dict[str, set] = defaultdict(set)
    for n, (ax, ecc) in static.items():
        tw = pattern_tower(n)
        if tw:
            by_tower[tw].add((ax, ecc))
    out = []
    missing = [t for t in towers if t not in by_tower]
    if missing:
        out.append(Finding(WARNING, f"Turnuri fără tipare seismice statice (de forma Tn_XP / Tn_XN / Tn_YP / Tn_YN): {', '.join(missing)}. "
                                    "Dacă sunt turnuri care se calculează separat, le lipsește acțiunea seismică.", data={"turnuri": missing}))
    want = {("X", "+"), ("X", "-"), ("Y", "+"), ("Y", "-")}
    for tw in sorted(by_tower):
        lack = want - by_tower[tw]
        if lack:
            out.append(Finding(WARNING, f"Turnul {tw} are setul seismic incomplet: lipsește " +
                               ", ".join(f"{a}{'+' if e == '+' else '−'}" for a, e in sorted(lack)) + " (direcție × excentricitate).",
                               [("loadpattern", n) for n in static if pattern_tower(n) == tw]))
    usage = pattern_usage(ctx)
    empty = [n for n in static if not has_loads(usage.get(n))]
    if empty:
        out.append(Finding(WARNING, f"{len(empty)} tipare seismice nu au nicio încărcare asignată: {', '.join(sorted(empty)[:12])}"
                                    f"{'…' if len(empty) > 12 else ''}.", [("loadpattern", n) for n in sorted(empty)]))
    rs = [n for n, v in seis.items() if v[0] == "RS"]
    if rs:
        out.append(Finding(INFO, f"Cazurile de spectru ({', '.join(rs)}) sunt globale, nu pe turn: excentricitatea accidentală și rezultatele pe turn se verifică separat."))
    return out


@check("r29_rezultate_turnuri", 29, "Rezultate seismice distincte între turnuri (nu identice, nu nule)", phase="post")
def r29_rezultate_turnuri(ctx):
    from collections import defaultdict

    from .combos import pattern_tower, seismic_info
    from .results import _finished
    if len(ctx.towers()) < 2:
        return []
    seis, _t = seismic_info(ctx)
    fin = _finished(ctx)
    static = [n for n, v in seis.items() if v[0] in ("X", "Y") and pattern_tower(n) and n in fin]
    if not static:
        return []
    br = ctx.snap.results_table("Base Reactions", cases=static)
    if br.empty:
        return []
    shear = {str(r["OutputCase"]): (abs(float(r["FX"])), abs(float(r["FY"]))) for _, r in br.iterrows()}
    out = []
    by_dir = defaultdict(list)
    for n in static:
        if n in shear:
            by_dir[(seis[n][0], seis[n][1])].append((pattern_tower(n), n, shear[n][0 if seis[n][0] == "X" else 1]))
    mass = {}
    ms = ctx.snap.table("Mass Summary by Story")
    if not ms.empty:
        for _, r in ms.iterrows():
            tw = ctx.tower_of(str(r["Story"]))
            if tw:
                mass[tw] = mass.get(tw, 0.0) + float(r["UX"])
    dup, zero, twins = [], [], []
    for (ax, ecc), rows in by_dir.items():
        for i in range(len(rows)):
            if rows[i][2] < 1e-3:
                zero.append(rows[i][1])
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if a[2] > 1e-3 and abs(a[2] - b[2]) / max(a[2], b[2]) < 1e-6:
                    ma, mb = mass.get(a[0], 0.0), mass.get(b[0], 0.0)
                    if ma and mb and abs(ma - mb) / max(ma, mb) < 0.02:           # turnuri practic identice ca masa: forte egale = normal
                        twins.append((a[0], b[0]))
                    else:
                        dup.append((a[1], b[1], a[2]))
    if dup:
        out.append(Finding(WARNING, f"{len(dup)} perechi de tipare seismice din turnuri diferite dau exact aceeași forță de bază: " +
                           "; ".join(f"{a} = {b} ({v:.0f} kN)" for a, b, v in dup[:5]) + ". Turnurile au mase diferite, deci posibil același set de încărcări copiat pe mai multe turnuri.",
                           [("loadpattern", n) for a, b, _v in dup for n in (a, b)]))
    if twins:
        pairs = sorted({tuple(sorted(p)) for p in twins})
        out.append(Finding(INFO, "Turnuri cu masă practic identică și forță seismică identică: " + ", ".join(f"{a}–{b}" for a, b in pairs) + " (normal pentru turnuri gemene)."))
    if zero:
        out.append(Finding(WARNING, f"Tipare seismice cu forță de bază nulă: {', '.join(sorted(set(zero))[:12])}.", [("loadpattern", n) for n in sorted(set(zero))]))
    return out
