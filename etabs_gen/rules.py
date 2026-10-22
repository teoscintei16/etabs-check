"""Pasii „de reguli” aplicati dupa geometrie, astfel incat modelul generat sa treaca verificarile: fisurare, zone rigide, mesh,
sursa de masa, moduri, spectru, forte statice, combinatii. Fiecare pas intoarce un sumar scurt (text) pentru raport."""
from __future__ import annotations

import math

from .connect import GenError, ok
from .seismic import SeismicParams, combos, seismic_coefficient, spectrum_points
from .tables import read_table, update_rows, upsert_entities

QUAKE = 5
RS_FUNCTION = "SPECTRU_P100"


def seismic_params(spec) -> SeismicParams:
    return SeismicParams(ag=spec.ag, gamma_I=spec.gamma_I, beta0=spec.beta0, Tb=spec.Tb, Tc=spec.Tc, Td=spec.Td, q=spec.q, lam=spec.lam,
                         ecc=spec.ecc, damping=spec.damping, psi2=spec.psi2, orth=spec.orth)


# ---------------------------------------------------------------- fisurare, zone rigide
def apply_cracking(sap, spec, names: dict[str, str]) -> str:
    """Modificatori de rigiditate pe sectiuni (EC8 / P100-1): I redus si J redus (torsiunea fisurata), arii cu m11/m22/m12 reduse."""
    for key, i_f, j_f in (("column", spec.crack_col_I, spec.crack_col_J), ("beam", spec.crack_beam_I, spec.crack_beam_J)):
        ok(sap.PropFrame.SetModifiers(names[key], [1.0, 1.0, 1.0, j_f, i_f, i_f, 1.0, 1.0]), "PropFrame.SetModifiers")
    s = spec.crack_slab
    ok(sap.PropArea.SetModifiers(names["slab"], [1.0, 1.0, 1.0, s, s, s, 1.0, 1.0, 1.0, 1.0]), "PropArea.SetModifiers")
    return (f"fisurare: stâlpi I×{spec.crack_col_I:g}/J×{spec.crack_col_J:g}, grinzi I×{spec.crack_beam_I:g}/J×{spec.crack_beam_J:g}, "
            f"plăci m×{spec.crack_slab:g}")


def apply_rigid_zones(sap, frames: list[str], factor: float) -> str:
    """Factorul zonei rigide pe toate barele (cu decalaje automate din conectivitate). FrameObj.SetEndLengthOffset ignora RZ cand
    AutoOffset=True, deci se scrie tabelul „End Length Offsets” (intreg, intr-o singura aplicare)."""
    n = update_rows(sap, "Frame Assignments - End Length Offsets", {f: {"RigidFact": f"{factor:g}"} for f in frames}, "UniqueName")
    return f"zone rigide ×{factor:g} la {n} bare"


# ---------------------------------------------------------------- mesh
def apply_mesh(sap, mesh_max: float) -> str:
    size = f"{mesh_max:g}"
    update_rows(sap, "Analysis Options - Automatic Mesh Settings for Floors", {None: {"MeshOpt": "Rectangular", "Localized": "Yes", "MergeJoints": "Yes", "MaxMeshSize": size}}, None)
    update_rows(sap, "Analysis Options - Automatic Rectangular Mesh Options for Walls", {None: {"MaxMeshSize": size}}, None)
    for key in ("Area Assignments - Floor Auto Mesh Options", "Area Assignments - Wall Auto Mesh Options"):
        try:
            _v, _f, rows = read_table(sap, key)
        except GenError:
            continue                                            # tabel inexistent (ex. fara pereti)
        if rows:
            update_rows(sap, key, {r["UniqueName"]: {"MeshOption": "Default", "Restraints": "Yes"} for r in rows}, "UniqueName")
    return f"mesh: plăci Rectangular/Localized/Merge, {size} m; arii „Default” + Add Restraints"


# ---------------------------------------------------------------- sursa de masa, moduri
def apply_mass_source(sap, spec, has_perm: bool) -> str:
    """Masa din elemente + tiparul permanent (x1) + utila (xψ2). Dead nu apare: are deja greutate proprie (altfel s-ar dubla)."""
    pats = ([("Permanenta", "1")] if has_perm else []) + [("Live", f"{spec.psi2:g}")]
    rows = [dict(Name="MsSrc1", IsDefault="Yes", IncLateral="Yes", IncVertical="No", LumpMass="Yes", SourceSelf="Yes", SourceAdded="Yes",
                 SourceLoads="Yes", MoveMass="No", LoadPattern=pats[0][0], Multiplier=pats[0][1])]
    rows += [dict(Name="MsSrc1", LoadPattern=p, Multiplier=m) for p, m in pats[1:]]
    upsert_entities(sap, "Mass Source Definition", "Name", rows)
    return "masă: elemente + " + " + ".join(f"{m}×{p}" for p, m in pats)


def apply_modal(sap, spec) -> str:
    n = spec.modes_per_story * spec.stories
    ok(sap.LoadCases.ModalEigen.SetNumberModes("Modal", n, 1), "SetNumberModes")
    return f"moduri: {n} ({spec.modes_per_story}/etaj)"


# ---------------------------------------------------------------- actiune seismica
def apply_seismic(sap, spec, top_story: str, base_story: str = "Base") -> tuple[list[str], list[str], list[str]]:
    """Functia spectrala P100-1, cazurile de spectru SPECX/SPECY (100% + 30%, CQC, SRSS, excentricitate) si 4 tipare statice cu
    excentricitate ±. Intoarce (tipare statice, cazuri spectru, note)."""
    p = seismic_params(spec)
    pts = spectrum_points(p)
    rows = [dict(Name=RS_FUNCTION, Period=f"{t:g}", Value=f"{v:g}", DampRatio=f"{p.damping:g}" if i == 0 else "") for i, (t, v) in enumerate(pts)]
    upsert_entities(sap, "Functions - Response Spectrum - User Defined", "Name", rows)
    rs = sap.LoadCases.ResponseSpectrum
    cases = []
    for name, main, other in (("SPECX", "U1", "U2"), ("SPECY", "U2", "U1")):
        ok(rs.SetCase(name), "ResponseSpectrum.SetCase")
        ok(rs.SetLoads(name, 2, [main, other], [RS_FUNCTION, RS_FUNCTION], [1.0, p.orth], ["Global", "Global"], [0.0, 0.0]), "ResponseSpectrum.SetLoads")
        ok(rs.SetModalCase(name, "Modal"), "SetModalCase")
        ok(rs.SetEccentricity(name, p.ecc), "SetEccentricity")
        cases.append(name)
    # tipare statice: cate unul pe directie × excentricitate; coeficientul C = λ·γI·ag·β0/q
    spec_rows, patterns = [], []
    for name, d, e in (("EXP", "X", "Plus"), ("EXN", "X", "Minus"), ("EYP", "Y", "Plus"), ("EYN", "Y", "Minus")):
        r = sap.LoadPatterns.Add(name, QUAKE, 0, True)
        if r not in (0,):
            raise GenError(f"Nu pot crea tiparul {name} (cod {r}).")
        flags = {f"{ax}Dir{kind}": "No" for ax in "XY" for kind in ("", "PlusE", "MinusE")}
        flags[f"{d}Dir{e}E"] = "Yes"
        spec_rows.append(dict(Name=name, IsAuto="No", EccRatio=f"{p.ecc:g}", TopStory=top_story, BotStory=base_story,
                              C=f"{seismic_coefficient(p):g}", K="1", **flags))
        patterns.append(name)
    upsert_entities(sap, "Load Pattern Definitions - Auto Seismic - User Coefficient", "Name", spec_rows)
    return patterns, cases, [f"spectru P100-1 ({len(pts)} puncte), C = {seismic_coefficient(p):g}, e = {p.ecc:g}"]


def apply_combinations(sap, spec, has_perm: bool, static: list[str], rs: list[str]) -> int:
    p = seismic_params(spec)
    items = combos(has_perm, static, rs, p, spec.gamma_g, spec.gamma_q)
    for name, parts in items:
        ok(sap.RespCombo.Add(name, 0), f"RespCombo.Add({name})")
        for load, sf in parts:
            kind = 0                                              # eCNameType.LoadCase (tiparele au cazuri liniare cu acelasi nume)
            ok(sap.RespCombo.SetCaseList(name, kind, load, float(sf)), f"RespCombo.SetCaseList({name}, {load})")
    return len(items)


def assert_finite(spec) -> None:
    for f in ("ag", "gamma_I", "beta0", "Tb", "Tc", "Td", "q", "lam"):
        v = getattr(spec, f)
        if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0):
            raise GenError(f"Parametrul seismic „{f}” trebuie să fie pozitiv.")
    if not (spec.Tb < spec.Tc < spec.Td):
        raise GenError("Trebuie TB < TC < TD.")
