"""Verificari pe model rulat (tab-ul „Model rulat”): moduri, mase, CM-CR, torsiune, reactiuni, forte de baza, rigiditate de etaj."""
from __future__ import annotations

import math
import re

import numpy as np

from ..registry import ERROR, INFO, WARNING, Finding, Param, check
from .combos import expand, load_combos, seismic_info
from .seismic import G, spectrum
from .util import col, sname, yes

POST = "post"
_SEVERE = re.compile(r"ill[- ]?condition|lost accuracy|unstable|instabil|mechanism|singular|zero stiffness|not converge|did not converge|negative stiffness|"
                     r"eigen.*(?:fail|error)|insufficient", re.I)


def _finished(ctx) -> set[str]:
    """Cazurile si combinatiile cu rezultate."""
    ex = ctx.snap.extras
    done = {n for n, s in ex.case_status.items() if s == 4}
    return done | set(ex.combos)


def _material_rows(ctx):
    """„Material List by Story” fara randurile de total (Story = Sum/Total, ObjectType = All)."""
    wt = ctx.snap.table("Material List by Story")
    if wt.empty:
        return wt
    return wt[~wt["Story"].astype(str).isin(["Sum", "Total"]) & (wt["ObjectType"].astype(str) != "All")]


def _seismic_cases(ctx):
    """({nume: (directie, ecc)} doar cazuri cu rezultate)."""
    seis, _types = seismic_info(ctx)
    fin = _finished(ctx)
    return {n: v for n, v in seis.items() if n in fin}


# ---------------------------------------------------------------- 10: masa participanta
@check("r10_masa_participanta", 10, "Masă modală participantă ≥ 90 % pe X și Y; primele moduri de translație", phase=POST,
       params=[Param("masa_min_pct", 90.0, "Masa modală participantă minimă", "%")])
def r10_masa_participanta(ctx):
    mp = ctx.snap.table("Modal Participating Mass Ratios")
    if mp.empty:
        return [Finding(WARNING, "Nu există rezultate modale (tabela maselor participante este goală).")]
    lim = ctx.p("masa_min_pct") / 100.0
    out = []
    for case, g in mp.groupby("Case", sort=False):
        g = g.sort_values("Mode")
        msg = []
        for ax in ("UX", "UY"):
            last = float(g[f"Sum{ax}"].iloc[-1])
            reach = g[g[f"Sum{ax}"] >= lim]
            if reach.empty:
                out.append(Finding(ERROR, f"Cazul modal „{case}”: masa participantă pe {ax[1]} este doar {last * 100:.1f} % după {len(g)} moduri "
                                          f"(minim {lim * 100:g} %). Crește numărul de moduri.", [("loadcase", str(case))],
                                   {"moduri": int(len(g)), f"suma_{ax}": round(last, 4)}))
            else:
                msg.append(f"{ax[1]}: {lim * 100:g} % la modul {int(reach['Mode'].iloc[0])}")
        first = g.head(3)
        tors = [int(r["Mode"]) for _, r in first.iterrows() if float(r["RZ"]) > max(float(r["UX"]), float(r["UY"])) and float(r["RZ"]) > 0.1]
        if tors:
            out.append(Finding(WARNING, f"Cazul „{case}”: modul(urile) {', '.join(map(str, tors))} dintre primele trei sunt predominant de torsiune "
                                        "(structură sensibilă la torsiune).", [("loadcase", str(case))]))
        if msg:
            out.append(Finding(INFO, f"Cazul „{case}”: " + "; ".join(msg) + f". T1 = {float(g['Period'].iloc[0]):.3f} s."))
    return out


# ---------------------------------------------------------------- 25: mesaje de analiza
@check("r25_mesaje_analiza", 25, "Mesaje de analiză: instabilități, „Ill-conditioned matrix”, pierderi de precizie", phase=POST)
def r25_mesaje_analiza(ctx):
    m = ctx.snap.table("Analysis Messages")
    if m.empty:
        return [Finding(INFO, "Nu există mesaje de analiză salvate.")]
    typ, msg = col(m, "Type"), col(m, "Message")
    out = []
    severe = m[m[msg].astype(str).str.contains(_SEVERE)]
    if len(severe):
        out.append(Finding(ERROR, f"{len(severe)} mesaje de analiză indică instabilitate sau pierdere de precizie.",
                           data={"mesaje": sorted({str(x)[:160] for x in severe[msg]})[:8]}))
    other = m[m[typ].astype(str).str.lower().isin(["warning", "error"]) & ~m.index.isin(severe.index)]
    if len(other):
        out.append(Finding(WARNING, f"{len(other)} avertismente/erori de analiză.", data={"mesaje": sorted({str(x)[:160] for x in other[msg]})[:8]}))
    return out


# ---------------------------------------------------------------- 6: mase pe etaj
@check("r6_mase_etaj", 6, "Mase pe etaj: niveluri fără masă și salturi bruște",
       params=[Param("salt_masa_pct", 40.0, "Variația maximă a masei între etaje consecutive", "%")], phase=POST)
def r6_mase_etaj(ctx):
    ms = ctx.snap.table("Mass Summary by Story")
    if ms.empty:
        return [Finding(WARNING, "Tabela maselor pe etaj este goală.")]
    mat = _material_rows(ctx)
    with_elements = set(mat["Story"].astype(str)) if not mat.empty else None         # niveluri care au elemente (un turn mai scund nu are etaje sus)
    ms = ms.copy()
    ms["Story"] = ms["Story"].astype(str)
    ms["_plain"] = [ctx.plain_story(x) for x in ms["Story"]]
    ms["_tower"] = [ctx.tower_of(x) or "" for x in ms["Story"]]
    is_base = ms["_plain"].str.lower().eq("base")
    skip = ms["_plain"].str.lower().isin(["total", "sum"])
    total_all = float(ms[~skip]["UX"].astype(float).sum())
    base_mass = float(ms[is_base]["UX"].astype(float).sum())
    out = []
    lim = ctx.p("salt_masa_pct") / 100.0
    zero, jumps = [], []
    for tower, g in ms[~is_base & ~skip].groupby("_tower", sort=False):
        st, mx = list(g["Story"]), g["UX"].astype(float).tolist()
        zero += [s for s, v in zip(st, mx) if v <= 0 and (with_elements is None or s in with_elements)]
        for i in range(len(st) - 1):
            if mx[i] > 0 and mx[i + 1] > 0 and abs(mx[i + 1] / mx[i] - 1.0) > lim:
                jumps.append((st[i], st[i + 1], mx[i], mx[i + 1]))
    if zero:
        out.append(Finding(ERROR, f"{len(zero)} niveluri cu elemente nu au masă: {', '.join(zero[:20])}{'…' if len(zero) > 20 else ''}. "
                                  "Verifică diafragmele și sursa de masă.", data={"niveluri": zero}))
    if jumps:
        out.append(Finding(WARNING, f"{len(jumps)} salturi de masă între etaje consecutive (> {lim * 100:g} %): "
                                    + "; ".join(f"{a}→{b}: {x:.0f}→{y:.0f}" for a, b, x, y in jumps[:6]) + ".",
                           data={"salturi": [{"de_la": a, "la": b, "masa_a": round(x, 1), "masa_b": round(y, 1)} for a, b, x, y in jumps]}))
    note = f"Masa totală (UX) = {total_all:.0f} (→ greutate ≈ {total_all * G:.0f} kN), din care la nivelul de bază „Base” {base_mass:.0f}"
    if not mat.empty:
        note += f"; greutatea elementelor structurale din „Material List by Story” = {float(mat['Weight'].astype(float).sum()):.0f} kN"
    out.append(Finding(INFO, note + "."))
    return out


# ---------------------------------------------------------------- 21: CM-CR si torsiune
@check("r21_cm_cr", 21, "Excentricitatea CM–CR pe etaj (față de latura clădirii)",
       params=[Param("ecc_max_pct", 15.0, "Excentricitate CM–CR maximă admisă", "% din latură")], phase=POST)
def r21_cm_cr(ctx):
    t = ctx.snap.table("Centers Of Mass And Rigidity")
    if t.empty:
        return [Finding(ERROR, "Lipsește tabelul „Centers of Mass and Rigidity”: fără diafragme și analiză 3D nu se pot calcula CM și CR.")]
    out = []
    mat = _material_rows(ctx)
    if not mat.empty:                                          # nivelurile care au planseu (turnurile mai scunde nu au etaje sus)
        fl = mat[(mat["ObjectType"].astype(str) == "Floor") & (mat["Weight"].astype(float) > 0)]
        stories = [x for x in dict.fromkeys(fl["Story"].astype(str)) if ctx.plain_story(x).lower() != "base"]
    else:
        stories = [ctx.story_id(tw, st) for tw in ctx.towers() for st in ctx.stories()]
    have = {str(x) for x in t["Story"]}
    miss = [x for x in stories if x not in have]
    if miss and stories:
        out.append(Finding(WARNING, f"CM/CR sunt disponibile doar pentru {len(stories) - len(miss)} din {len(stories)} niveluri cu planșeu (lipsesc: {', '.join(miss[:12])}"
                                    f"{'…' if len(miss) > 12 else ''}): la niveluri fără diafragmă nu se poate evalua torsiunea."))
    j = ctx.snap.table("Objects and Elements - Joints")
    dims = {}
    if not j.empty:
        j = j[j["ObjType"].astype(str) == "Joint"]
        for s, g in j.groupby(j["Story"].astype(str)):
            dims[s] = (float(g["GlobalX"].max() - g["GlobalX"].min()), float(g["GlobalY"].max() - g["GlobalY"].min()))
    bad, rows, nan = [], [], []
    for _, r in t.iterrows():
        s = str(r["Story"])
        if not all(r[c] == r[c] for c in ("XCM", "YCM", "XCR", "YCR")):
            nan.append(s)
            continue
        lx, ly = dims.get(s, (0.0, 0.0))
        ex = abs(float(r["XCM"]) - float(r["XCR"])) / lx if lx else 0.0
        ey = abs(float(r["YCM"]) - float(r["YCR"])) / ly if ly else 0.0
        rows.append({"etaj": s, "ex_pct": round(ex * 100, 1), "ey_pct": round(ey * 100, 1)})
        if max(ex, ey) * 100 > ctx.p("ecc_max_pct"):
            bad.append(s)
    if nan:
        out.append(Finding(WARNING, f"Centrul de rigiditate nu a fost calculat la: {', '.join(nan)}."))
    if bad:
        out.append(Finding(WARNING, f"Excentricitatea CM–CR depășește {ctx.p('ecc_max_pct'):g} % din latura clădirii la: {', '.join(bad)}.", data={"niveluri": rows}))
    elif rows:
        out.append(Finding(INFO, f"Excentricitatea CM–CR este sub {ctx.p('ecc_max_pct'):g} % la nivelurile evaluate ({len(rows)}).", data={"niveluri": rows}))
    return out


@check("r21_torsiune_etaj", 21, "Torsiunea de etaj: raportul deplasare maximă / medie la seism",
       params=[Param("torsiune_warn", 1.2, "Raport maxim/mediu peste care structura e neregulată la torsiune", ""),
               Param("torsiune_err", 1.5, "Raport maxim/mediu peste care torsiunea e excesivă", "")], phase=POST)
def r21_torsiune_etaj(ctx):
    sc = list(_seismic_cases(ctx))
    if not sc:
        return [Finding(INFO, "Nu există cazuri seismice cu rezultate pentru evaluarea torsiunii.")]
    t = ctx.snap.results_table("Story Max Over Avg Drifts", cases=sc)
    if t.empty:
        return [Finding(INFO, "Tabela „Story Max Over Avg Drifts” nu are rezultate pentru cazurile seismice.")]
    from .combos import pattern_tower
    keep = [pattern_tower(str(r["OutputCase"])) in (None, ctx.tower_of(str(r["Story"]))) for _, r in t.iterrows()]   # un caz Tn_* conteaza doar pe turnul Tn
    t = t[keep]
    if t.empty:
        return [Finding(INFO, "Nu există rezultate de torsiune pe turnurile încărcate.")]
    mx = t.loc[t["Ratio"].astype(float).idxmax()]
    worst = t.sort_values("Ratio", ascending=False).head(5)
    data = [{"etaj": str(r["Story"]), "caz": str(r["OutputCase"]), "directie": str(r["Direction"]), "raport": round(float(r["Ratio"]), 3)} for _, r in worst.iterrows()]
    r = float(mx["Ratio"])
    if r > ctx.p("torsiune_err"):
        return [Finding(ERROR, f"Raportul deplasare maximă / medie ajunge la {r:.2f} (etaj {mx['Story']}, {mx['OutputCase']}): torsiune excesivă.", data={"cele_mai_mari": data})]
    if r > ctx.p("torsiune_warn"):
        return [Finding(WARNING, f"Raportul deplasare maximă / medie ajunge la {r:.2f} (etaj {mx['Story']}, {mx['OutputCase']}): structură neregulată la torsiune.", data={"cele_mai_mari": data})]
    return [Finding(INFO, f"Raport maxim/mediu al derivelor: {r:.2f} (sub {ctx.p('torsiune_warn'):g}).", data={"cele_mai_mari": data})]


# ---------------------------------------------------------------- 22: reactiuni Dead si q topit
def _gravity_combo(ctx):
    combos = load_combos(ctx)
    seis, types = seismic_info(ctx)
    best = None
    for n, (t, _it) in combos.items():
        if t.lower().startswith("env"):
            continue
        e = expand(combos, n)
        if not e or any(k in seis for k in e) or not any(types.get(k) in ("Dead", "Super Dead") for k in e):
            continue
        if max(abs(v) for v in e.values()) <= 1.0 + 1e-9:
            tot = sum(abs(v) for v in e.values())
            if best is None or tot > best[1]:
                best = (n, tot)
    return best[0] if best else None


@check("r22_reactiuni_dead", 22, "Reacțiunea verticală din greutatea proprie față de greutatea elementelor", phase=POST,
       params=[Param("dead_tol_pct", 10.0, "Abatere admisă a reacțiunii față de greutatea estimată", "%")])
def r22_reactiuni_dead(ctx):
    lp = ctx.snap.table("Load Pattern Definitions")
    wt = _material_rows(ctx)
    if lp.empty or wt.empty:
        return [Finding(INFO, "Lipsesc datele pentru estimarea greutății (tipare sau „Material List by Story”).")]
    sw = [str(r["Name"]) for _, r in lp.iterrows() if float(r["SelfWtMult"] or 0) != 0]
    if not sw or sw[0] not in _finished(ctx):
        return [Finding(INFO, "Cazul cu greutate proprie nu are rezultate.")]
    if ctx.multi_tower():                                   # lista de materiale repeta infrastructura comuna pe fiecare turn: suma ar fi dublata
        br0 = ctx.snap.results_table("Base Reactions", cases=[sw[0]])
        fz0 = float(br0.iloc[0]["FZ"]) if not br0.empty else float("nan")
        return [Finding(INFO, f"Model cu mai multe turnuri: reacțiunea din „{sw[0]}” = {fz0:.0f} kN. Compararea cu „Material List by Story” nu se face "
                              "(lista repetă infrastructura comună pe fiecare turn).")]
    br = ctx.snap.results_table("Base Reactions", cases=[sw[0]])
    if br.empty:
        return []
    fz = float(br.iloc[0]["FZ"])
    est = float(wt["Weight"].astype(float).sum())
    ratio = fz / est if est else float("nan")
    tol = ctx.p("dead_tol_pct") / 100.0
    data = {"FZ_kN": round(fz, 1), "greutate_estimata_kN": round(est, 1), "raport": round(ratio, 3)}
    if abs(ratio - 1.0) <= tol:
        return [Finding(INFO, f"Reacțiunea din „{sw[0]}” ({fz:.0f} kN) coincide cu greutatea elementelor ({est:.0f} kN), raport {ratio:.2f}.", data=data)]
    why = " (aproape dublă: greutate dublată?)" if abs(ratio - 2.0) < 0.2 else (" (aproape zero: multiplicator 0?)" if ratio < 0.3 else "")
    return [Finding(ERROR, f"Reacțiunea din „{sw[0]}” ({fz:.0f} kN) diferă de greutatea elementelor ({est:.0f} kN): raport {ratio:.2f}{why}.", data=data)]


_Q_RANGES = {"rezidential_cadre": (5.0, 6.5), "rezidential_pereti": (5.5, 7.5), "birouri_cadre": (6.0, 8.0),
             "birouri_pereti": (6.5, 9.0), "incarcari_grele": (8.5, 10.5)}


@check("r22_q_topit", 22, "Încărcarea medie pe m² de planșeu („q topit”: încărcări aplicate, fără greutatea proprie)", phase=POST,
       params=[Param("q_avertisment", 1, "Semnalează ca avertisment când q iese din interval (0 = doar informativ)", "")])
def r22_q_topit(ctx):
    name = _gravity_combo(ctx)
    wt = _material_rows(ctx)
    lp = ctx.snap.table("Load Pattern Definitions")
    if not name or wt.empty or lp.empty or name not in _finished(ctx):
        return [Finding(INFO, "Nu pot calcula „q topit”: lipsește o combinație gravitațională (factori ≤ 1) cu rezultate sau lista de materiale.")]
    sw = [str(r["Name"]) for _, r in lp.iterrows() if float(r["SelfWtMult"] or 0) != 0]
    combos = load_combos(ctx)
    e_sw = sum(expand(combos, name).get(n, 0.0) for n in sw)                # cat din greutatea proprie intra in combinatie
    stories = ctx.stories()
    ground = ctx.ground_story()
    floors = wt.drop_duplicates("Story")
    floors = floors[~floors["Story"].astype(str).map(ctx.plain_story).str.lower().eq("base")]
    cases = [n for n in sw if n in _finished(ctx)]
    if ground in stories:
        above = stories[: stories.index(ground) + 1]
        both = ctx.snap.results_table("Story Forces", cases=cases, combos=[name])          # un singur export pentru ambele (e lent)
        ftot = both[both["OutputCase"].astype(str) == name] if not both.empty else both
        fsw = both[both["OutputCase"].astype(str).isin(cases)] if not both.empty else both

        def p_bottom(df, sid):
            row = df[(df["Story"].astype(str) == sid) & (df["Location"].astype(str).str.lower() == "bottom")] if not df.empty else df
            return abs(float(row.iloc[0]["P"])) if len(row) else None

        total = own = area = 0.0
        used = []
        for tw in ctx.towers() or [""]:
            gid = ctx.story_id(tw, ground) if tw else ground
            tt, oo = p_bottom(ftot, gid), p_bottom(fsw, gid)
            if tt is None or oo is None:
                continue
            ids = [ctx.story_id(tw, s) if tw else s for s in above]
            total, own = total + tt, own + oo
            area += float(floors[floors["Story"].astype(str).isin(ids)]["FloorArea"].astype(float).sum())
            used.append(tw)
        scope = f"suprastructura (de la „{ground}” în sus{', turnurile ' + ', '.join(used) if len(used) > 1 else ''})"
        if not used:
            return []
    else:
        btot = ctx.snap.results_table("Base Reactions", combos=[name])
        bsw = ctx.snap.results_table("Base Reactions", cases=cases) if cases else btot.iloc[0:0]
        total = abs(float(btot.iloc[0]["FZ"])) if not btot.empty else None
        own = abs(float(bsw.iloc[0]["FZ"])) if not bsw.empty else None
        area = float(floors["FloorArea"].astype(float).sum())
        scope = "întreaga structură (setează subsolurile în Setări pentru a izola suprastructura)"
    if total is None or own is None or not area:
        return []
    applied = total - e_sw * own
    q = applied / area
    kind = ctx.proj("tip_cladire")
    base = (f"Combinația „{name}”, {scope}: încărcări aplicate (fără greutatea proprie) {applied:.0f} kN pe {area:.0f} m² de planșeu → "
            f"q = {q:.2f} kN/m².")
    data = {"q": round(q, 2), "total_kN": round(total, 1), "greutate_proprie_kN": round(own, 1), "arie_m2": round(area, 1)}
    if kind in _Q_RANGES and ground in stories:
        lo, hi = _Q_RANGES[kind]
        if lo * 0.9 <= q <= hi * 1.1:
            return [Finding(INFO, base + f" În intervalul tipic {lo:g}–{hi:g} kN/m² pentru „{kind}”.", data=data)]
        sev = WARNING if ctx.p("q_avertisment") else INFO
        return [Finding(sev, base + f" În afara intervalului tipic {lo:g}–{hi:g} kN/m² pentru „{kind}”: verifică încărcările de planșeu "
                                    "(finisaje, compartimentări, utile, zăpadă) — posibil dublate sau lipsă.", data=data)]
    return [Finding(INFO, base + " Alege tipul clădirii și subsolurile în Setări pentru a compara cu intervalul tipic.", data=data)]


# ---------------------------------------------------------------- 2: reactiuni de intindere la baza
@check("r2_reactiuni_intindere", 2, "Reacțiuni de întindere la reazeme sub încărcări gravitaționale", phase=POST,
       params=[Param("intindere_min", 1.0, "Reacțiune de întindere neglijabilă sub această valoare", "kN")])
def r2_reactiuni_intindere(ctx):
    name = _gravity_combo(ctx)
    if not name or name not in _finished(ctx):
        return []
    jr = ctx.snap.results_table("Joint Reactions", combos=[name])
    if jr.empty:
        return []
    neg = jr[jr["FZ"].astype(float) < -ctx.p("intindere_min")]
    if neg.empty:
        return []
    return [Finding(WARNING, f"{len(neg)} reazeme au reacțiune de întindere sub „{name}” (min {float(neg['FZ'].min()):.0f} kN): "
                             "verifică arcurile/pilonii (compresiune-numai) și modelarea bazei.",
                    [("joint", sname(r["UniqueName"]), {"label": str(r["Label"]), "story": str(r["Story"]), "FZ": float(r["FZ"])}) for _, r in neg.iterrows()])]


# ---------------------------------------------------------------- 20 / 8: forta de baza
def _t1(ctx, axis: str) -> float | None:
    mp = ctx.snap.table("Modal Participating Mass Ratios")
    if mp.empty:
        return None
    r = mp.loc[mp[f"U{axis}"].astype(float).idxmax()]
    return float(r["Period"])


@check("r20_fb_static_dinamic", 20, "Forța tăietoare de bază: statică față de calcul manual (T1, spectru) și față de cea dinamică", phase=POST,
       params=[Param("fb_tol_pct", 20.0, "Abatere admisă între Fb static din model și calculul manual", "%"),
               Param("dyn_static_min", 0.85, "Raport minim Fb dinamic / Fb static", "")])
def r20_fb_static_dinamic(ctx):
    from collections import defaultdict

    from .combos import pattern_tower
    seis = _seismic_cases(ctx)
    static = {n: v for n, v in seis.items() if v[0] in ("X", "Y")}
    dyn = [n for n, v in seis.items() if v[0] == "RS"]
    if not static and not dyn:
        return [Finding(INFO, "Nu există cazuri seismice cu rezultate.")]
    br = ctx.snap.results_table("Base Reactions", cases=list(static) + dyn)
    if br.empty:
        return []
    fx = {str(r["OutputCase"]): (abs(float(r["FX"])), abs(float(r["FY"]))) for _, r in br.iterrows()}
    out = []
    auto = ctx.snap.table("Load Pattern Definitions - Auto Seismic - User Coefficient")
    weight = {str(r["Name"]): float(r["WeightUsed"]) for _, r in auto.iterrows()} if not auto.empty else {}
    coef = {str(r["Name"]): float(r["C"]) for _, r in auto.iterrows()} if not auto.empty else {}
    have_params = not ctx.missing("ag", "gamma_I", "beta0", "Tb", "Tc", "Td", "q", "lambda_mfse")
    groups = defaultdict(list)                                        # (turn, axa) -> tipare
    for n, v in static.items():
        groups[(pattern_tower(n) or "", v[0])].append(n)
    single = len({tw for tw, _ in groups}) <= 1
    per_group, per_axis = {}, {"X": 0.0, "Y": 0.0}
    for (tw, ax), names in sorted(groups.items()):
        vals = [fx[n][0 if ax == "X" else 1] for n in names if n in fx]
        if not vals:
            continue
        vb = max(vals)
        per_group[(tw, ax)] = vb
        per_axis[ax] += vb
        t1 = _t1(ctx, ax)
        if single and have_params and t1 and weight.get(names[0]):
            c_exp = ctx.project["lambda_mfse"] * spectrum(ctx, t1) / G
            fb_exp = c_exp * weight[names[0]]
            dev = vb / fb_exp - 1.0 if fb_exp else float("nan")
            data = {"Fb_model_kN": round(vb, 1), "Fb_manual_kN": round(fb_exp, 1), "T1_s": t1, "c_manual": round(c_exp, 4), "C_model": coef.get(names[0])}
            if abs(dev) * 100 > ctx.p("fb_tol_pct"):
                out.append(Finding(WARNING, f"Direcția {ax}: Fb static din model = {vb:.0f} kN, calcul manual (T1 = {t1:.3f} s) = {fb_exp:.0f} kN, abatere {dev * 100:+.0f} %: "
                                            "perioada fundamentală sau coeficientul seismic nu corespund.", [("loadpattern", n) for n in names], data))
            else:
                out.append(Finding(INFO, f"Direcția {ax}: Fb static = {vb:.0f} kN, calcul manual {fb_exp:.0f} kN (abatere {dev * 100:+.0f} %).", data=data))
    if not single and per_group:
        out.append(Finding(INFO, "Forța tăietoare de bază statică pe turn: " + "; ".join(f"{tw or '—'} {ax}: {v:.0f} kN" for (tw, ax), v in sorted(per_group.items())) +
                                 ". Compararea cu calculul manual se face pe modele cu un singur turn."))
    if per_group and single and not have_params and weight:
        out.append(Finding(INFO, "Comparația cu calculul manual a forței de bază cere parametrii proiectului (ag, γI, β0, TB, TC, TD, q) în Setări."))
    from .seismic import _rs_cases
    primary = {}
    for c in _rs_cases(ctx):
        if c["components"]:
            ld = max(c["components"], key=lambda x: abs(x[2]))[0].upper()
            primary[c["name"]] = "X" if ld in ("U1", "UX") else "Y" if ld in ("U2", "UY") else None
    for n in dyn:
        if n not in fx:
            continue
        for ax, k in (("X", 0), ("Y", 1)):
            if primary.get(n) == ax and per_axis[ax] > 0:
                ratio = fx[n][k] / per_axis[ax]
                sumtxt = " (suma turnurilor)" if not single else ""
                if ratio < ctx.p("dyn_static_min"):
                    out.append(Finding(WARNING, f"Fb dinamic „{n}” pe {ax} este {ratio:.2f} din Fb static{sumtxt} (< {ctx.p('dyn_static_min'):g}): forțele dinamice trebuie amplificate.",
                                       [("loadcase", n)], {"Fb_dinamic": round(fx[n][k], 1), "Fb_static": round(per_axis[ax], 1)}))
                else:
                    out.append(Finding(INFO, f"Fb dinamic „{n}” pe {ax} = {fx[n][k]:.0f} kN ({ratio:.2f} din Fb static{sumtxt} {per_axis[ax]:.0f} kN)."))
    return out


# ---------------------------------------------------------------- 28: rigiditate de etaj (soft story)
@check("r28_rigiditate_etaj", 28, "Rigiditatea de etaj: niveluri „moi” față de cele de deasupra", phase=POST,
       params=[Param("soft_ratio", 0.7, "Raport minim între rigiditatea unui etaj și a celui de deasupra", "")])
def r28_rigiditate_etaj(ctx):
    from .combos import pattern_tower
    seis = _seismic_cases(ctx)
    pick = {}
    for n, v in sorted(seis.items(), key=lambda kv: (kv[1][1] != "+", kv[0])):      # tiparul cu excentricitate + e reprezentativ
        if v[0] in ("X", "Y"):
            pick.setdefault((pattern_tower(n), v[0]), n)
    cases = list(pick.values())
    st = ctx.snap.table("Story Definitions")
    if not cases or st.empty:
        return [Finding(INFO, "Nu există cazuri seismice statice cu rezultate pentru calculul rigidității de etaj.")]
    stories = ctx.stories()
    h = {}
    for _, r in st.iterrows():
        h[ctx.story_id(str(r["Tower"]), str(r["Story"]))] = float(r["Height"])
    drifts = ctx.snap.results_table("Story Drifts", cases=cases)
    forces = ctx.snap.results_table("Story Forces", cases=cases)
    if drifts.empty or forces.empty:
        return []
    out, soft = [], []
    for case in cases:
        for ax in ("X", "Y"):
            d = drifts[(drifts["OutputCase"].astype(str) == case) & (drifts["Direction"].astype(str) == ax)]
            f = forces[(forces["OutputCase"].astype(str) == case) & (forces["Location"].astype(str).str.lower() == "bottom")]
            col_v = "VX" if ax == "X" else "VY"
            dd = {str(r["Story"]): abs(float(r["Drift"])) * h.get(str(r["Story"]), 0.0) for _, r in d.iterrows()}
            vv = {str(r["Story"]): abs(float(r[col_v])) for _, r in f.iterrows()}
            from .combos import pattern_tower
            own = pattern_tower(case)
            for tw in ([own] if own else (ctx.towers() or [""])):          # un tipar Tn_* incarca doar turnul Tn
                order = [ctx.story_id(tw, s) if tw else s for s in stories]
                k = {s: vv[s] / dd[s] for s in order if s in dd and s in vv and dd[s] > 1e-12 and vv[s] > 0}
                for i, s in enumerate(order[1:], 1):
                    above = order[i - 1]
                    if s in k and above in k and k[above] > 0 and k[s] / k[above] < ctx.p("soft_ratio"):
                        soft.append({"etaj": s, "caz": case, "directie": ax, "raport": round(k[s] / k[above], 2)})
    if soft:
        soft.sort(key=lambda r: r["raport"])
        out.append(Finding(WARNING, f"{len(soft)} situații de etaj „moale” (rigiditate < {ctx.p('soft_ratio'):g} din etajul de deasupra), de exemplu etajul "
                                    f"{soft[0]['etaj']} ({soft[0]['caz']}, {soft[0]['directie']}): {soft[0]['raport']}.", data={"etaje": soft[:12]}))
    return out


# ---------------------------------------------------------------- 3: diafragme rigide
@check("r3_diafragme_rigide_rezultate", 3, "Diafragme rigide: deplasările din planșeu (maxim / medie)", phase=POST,
       params=[Param("diafragma_raport", 1.2, "Raport maxim/mediu peste care ipoteza rigidă e discutabilă", "")])
def r3_diafragme_rigide_rezultate(ctx):
    dia = ctx.snap.table("Diaphragm Definitions")
    rigid = {str(r["Name"]) for _, r in dia.iterrows() if str(r["Rigidity"]).lower().startswith("rigid")} if not dia.empty else set()
    if not rigid:
        return []
    sc = list(_seismic_cases(ctx))
    t = ctx.snap.results_table("Diaphragm Max Over Avg Drifts", cases=sc) if sc else ctx.snap.table("Diaphragm Max Over Avg Drifts")
    if t.empty:
        return []
    t = t[t["Item"].astype(str).str.contains("|".join(re.escape(x) for x in rigid))]
    bad = t[t["Ratio"].astype(float) > ctx.p("diafragma_raport")]
    if bad.empty:
        return []
    return [Finding(WARNING, f"{len(bad)} rezultate arată deplasări neuniforme în diafragmele rigide ({', '.join(sorted(rigid))}), raport maxim "
                             f"{float(bad['Ratio'].max()):.2f}: ipoteza de diafragmă rigidă trebuie justificată (sau folosește semi-rigid).",
                    data={"exemple": [{"etaj": str(r["Story"]), "item": str(r["Item"]), "raport": round(float(r["Ratio"]), 2)} for _, r in bad.head(6).iterrows()]})]
