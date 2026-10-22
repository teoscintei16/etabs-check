"""Regula 1 (materiale) si 19 (unitati)."""
from __future__ import annotations

import re

from ..registry import ERROR, INFO, WARNING, Finding, Param, check

_CLASS = re.compile(r"^(?:(?P<factor>[0-9]*\.?[0-9]+)\s*\*\s*)?C(?P<fck>\d+)/\d+", re.I)

_UNITS = {1: "lb, in, F", 2: "lb, ft, F", 3: "kip, in, F", 4: "kip, ft, F", 5: "kN, mm, C", 6: "kN, m, C",
          7: "kgf, mm, C", 8: "kgf, m, C", 9: "N, mm, C", 10: "N, m, C", 11: "Ton, mm, C", 12: "Ton, m, C",
          13: "kN, cm, C", 14: "kgf, cm, C", 15: "N, cm, C", 16: "Ton, cm, C"}


def ecm_gpa(fck: float) -> float:
    """Ecm (EN 1992-1-1, tabelul 3.1) aproximat: 22*((fck+8)/10)^0.3 [GPa]."""
    return 22.0 * ((fck + 8.0) / 10.0) ** 0.3


def _materials(ctx):
    gen = ctx.snap.table("Material Properties - General")
    mech = ctx.snap.table("Material Properties - Basic Mechanical Properties")
    if gen.empty or mech.empty:
        return None
    return gen.merge(mech, on="Material", how="inner")


@check("r1_materiale", 1, "Materiale: modul de elasticitate, greutate, clasă de beton",
       params=[Param("ecm_tolerance_pct", 5.0, "Abatere admisă a lui E față de clasa de beton", "%"),
               Param("beton_greutate_min", 23.0, "Greutate specifică minimă beton", "kN/m³"),
               Param("beton_greutate_max", 26.0, "Greutate specifică maximă beton", "kN/m³")])
def r1_materiale(ctx):
    df = _materials(ctx)
    if df is None:
        return [Finding(INFO, "Tabelele de materiale nu au putut fi citite.")]
    out = []
    zero_w = df[df["Type"].isin(["Concrete", "Steel"]) & (df["UnitWeight"].fillna(0) <= 0)]
    if len(zero_w):
        out.append(Finding(ERROR, "Materiale (beton/oțel) cu greutate specifică zero.",
                           [("material", m) for m in zero_w["Material"]]))
    bad_e = df[df["Type"].isin(["Concrete", "Steel", "Rebar"]) & (df["E1"].fillna(0) <= 0)]
    if len(bad_e):
        out.append(Finding(ERROR, "Materiale cu modul de elasticitate zero sau lipsă.",
                           [("material", m) for m in bad_e["Material"]]))
    tol = ctx.p("ecm_tolerance_pct") / 100.0
    off, data = [], {}
    for _, r in df[df["Type"] == "Concrete"].iterrows():
        name = str(r["Material"]).strip()
        m = _CLASS.match(name)
        factor = float(m.group("factor")) if (m and m.group("factor")) else 1.0
        if not m:
            m = _CLASS.match(str(r.get("Grade", "")).strip())
        if not m or not r["E1"]:
            continue
        expected = factor * ecm_gpa(float(m.group("fck"))) * 1e6          # kN/m2
        dev = r["E1"] / expected - 1.0
        if abs(dev) > tol:
            off.append(("material", name))
            data[name] = {"E": float(r["E1"]), "E_asteptat": round(expected), "abatere_pct": round(dev * 100, 1)}
    if off:
        out.append(Finding(WARNING, "Modulul de elasticitate nu corespunde clasei de beton din nume "
                                    "(inclusiv factorul de fisurare din prefix, ex. 0.5*C35/45).", off, data))
    lo, hi = ctx.p("beton_greutate_min"), ctx.p("beton_greutate_max")
    w = df[(df["Type"] == "Concrete") & (df["UnitWeight"] > 0) & ~df["UnitWeight"].between(lo, hi)]
    if len(w):
        out.append(Finding(WARNING, f"Beton cu greutate specifică în afara intervalului {lo:g}–{hi:g} kN/m³.",
                           [("material", m) for m in w["Material"]]))
    return out


@check("r19_unitati", 19, "Unități de măsură și ordine de mărime plauzibile")
def r19_unitati(ctx):
    out = []
    code = getattr(ctx.snap, "original_units", None)
    if code is not None and code != 6:
        out.append(Finding(INFO, f"Modelul este salvat în unitățile „{_UNITS.get(code, code)}”. "
                                 "Aplicația citește tot în kN, m, °C și restaurează unitățile după citire."))
    df = _materials(ctx)
    if df is None:
        return out
    # in kN/m2: beton ~ 1e6..5e7, otel ~ 1e8..3e8
    sus = df[((df["Type"] == "Concrete") & ~df["E1"].between(1e6, 5e7)) |
             ((df["Type"] == "Steel") & ~df["E1"].between(1e8, 3e8))]
    if len(sus):
        out.append(Finding(ERROR, "Modul de elasticitate cu ordin de mărime suspect (posibile unități greșite: "
                                  "MPa introdus în loc de kN/m²).", [("material", m) for m in sus["Material"]],
                           {m: float(e) for m, e in zip(sus["Material"], sus["E1"])}))
    return out


_FACTOR = re.compile(r"^([0-9]*\.?[0-9]+)\s*\*")


def _mod_cols(df):
    from .util import col
    return {k: col(df, *names) for k, names in {
        "A": ("Area Modifier", "AreaMod", "Area"), "J": ("J Modifier", "JMod", "J", "Torsion"),
        "I22": ("I22 Modifier", "I22Mod", "I22"), "I33": ("I33 Modifier", "I33Mod", "I33"),
        "name": ("Name", "UniqueName"), "As2": ("As2 Modifier", "As2")}.items()}


@check("r1_fisurare", 1, "Rigiditate fisurată: modificatori sau factor în materialul betonului; torsiunea J",
       params=[Param("fisurare_asteptata", 1, "Se așteaptă reducere de rigiditate pentru fisurare (1 = da, 0 = nu)", "")])
def r1_fisurare(ctx):
    t = ctx.snap.table
    defs, assign = t("Frame Property Modifier Definitions"), t("Frame Assignments - Property Modifiers")
    shell_defs, shell_assign = t("Shell Property Modifier Definitions"), t("Area Assignments - Stiffness Modifiers")
    have_mods = not (defs.empty and assign.empty and shell_defs.empty and shell_assign.empty)
    mats = t("Material Properties - General")
    factor_mats = []
    if not mats.empty:
        for _, r in mats[mats["Type"] == "Concrete"].iterrows():
            m = _FACTOR.match(str(r["Material"]).strip())
            if m and float(m.group(1)) < 1.0:
                factor_mats.append((str(r["Material"]), float(m.group(1))))
    out = []
    if not have_mods and not factor_mats:
        if ctx.p("fisurare_asteptata"):
            out.append(Finding(WARNING, "Nu există nicio reducere de rigiditate pentru fisurare: nici modificatori de secțiune, "
                                        "nici materiale de beton cu factor în nume (ex. 0.5*C35/45)."))
    elif have_mods and factor_mats:
        out.append(Finding(WARNING, "Fisurarea apare prin ambele metode (modificatori de secțiune ȘI materiale cu factor): "
                                    "verifică să nu se reducă rigiditatea de două ori.",
                           [("material", n) for n, _f in factor_mats]))
    else:
        how = ("materiale cu factor în nume: " + ", ".join(f"{n} (×{f:g})" for n, f in factor_mats)) if factor_mats             else "modificatori de secțiune"
        out.append(Finding(INFO, f"Rigiditatea fisurată este modelată prin {how}."))
    if not defs.empty:
        c = _mod_cols(defs)
        if c["J"] and (c["I22"] or c["I33"]):
            bad = []
            for _, r in defs.iterrows():
                inertia = [float(r[c[k]]) for k in ("I22", "I33") if c[k] and r[c[k]] == r[c[k]]]
                if inertia and min(inertia) < 1.0 and float(r[c["J"]]) >= 1.0:
                    bad.append(str(r[c["name"]]))
            if bad:
                out.append(Finding(WARNING, f"{len(bad)} definiții de modificatori reduc inerția la încovoiere, dar lasă rigiditatea la "
                                            "torsiune J = 1: grinzile pot atrage torsiune de compatibilitate excesivă.",
                                   [("section", n) for n in bad]))
    return out
