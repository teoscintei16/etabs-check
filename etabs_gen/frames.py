"""Model ETABS cu structura in cadre: x etaje, y deschideri (directia X), z travei (directia Y), plansee, rezemare, diafragme, incarcari."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .connect import KN_M_C, GenError, assert_safe_to_overwrite, ok
from .rules import (apply_combinations, apply_cracking, apply_mass_source, apply_mesh, apply_modal, apply_rigid_zones, apply_seismic,
                    assert_finite)

# clasa betonului -> (fck [kN/m2], Ecm [kN/m2]) conform EN 1992-1-1
CONCRETE = {"C20/25": (20e3, 30e6), "C25/30": (25e3, 31e6), "C30/37": (30e3, 33e6), "C35/45": (35e3, 34e6), "C40/50": (40e3, 35e6)}
SLAB_DIR_GRAVITY = 10                       # directia de incarcare „Gravity” din API
STEEL, CONCRETE_TYPE, SLAB, SHELL_THIN, SUPER_DEAD = 1, 2, 0, 1, 2


@dataclass
class FrameSpec:
    name: str = "cadre"
    stories: int = 5                        # x: numar de etaje
    bays: int = 3                           # y: deschideri (pe directia X)
    travei: int = 3                         # z: travei (pe directia Y)
    story_height: float = 3.0               # m
    bottom_height: float | None = None      # m (implicit = inaltimea etajului curent)
    span_x: float = 5.0                     # m, deschiderea
    span_y: float = 5.0                     # m, traveea
    column_b: float = 0.50                  # m, latimea stalpului
    column_h: float = 0.50                  # m, inaltimea sectiunii stalpului (directia Y locala)
    beam_b: float = 0.30
    beam_h: float = 0.60
    slab_t: float = 0.15
    concrete: str = "C25/30"
    dead_extra: float = 3.0                 # kN/m2 permanent suplimentar (finisaje + compartimentari)
    live: float = 2.0                       # kN/m2 utila
    diaphragm: str = "semirigid"            # semirigid | rigid
    # --- rigiditate fisurata (EC8 / P100-1): factori pe sectiuni
    crack_col_I: float = 0.7
    crack_col_J: float = 0.1
    crack_beam_I: float = 0.5
    crack_beam_J: float = 0.1
    crack_slab: float = 0.5                 # m11 = m22 = m12
    rigid_zone: float = 0.75                # factorul zonei rigide la capete
    mesh_max: float = 0.5                   # m, dimensiunea maxima aproximativa a elementelor
    modes_per_story: int = 3
    # --- actiunea seismica (P100-1): se completeaza de utilizator, valorile implicite sunt doar orientative
    ag: float = 0.20                        # in multipli de g
    gamma_I: float = 1.0
    beta0: float = 2.5
    Tb: float = 0.07
    Tc: float = 0.7
    Td: float = 3.0
    q: float = 3.5
    lam: float = 0.85
    ecc: float = 0.05
    damping: float = 0.05
    psi2: float = 0.3                       # ψ2 al utilei = multiplicatorul ei in sursa de masa
    orth: float = 0.3
    gamma_g: float = 1.35
    gamma_q: float = 1.5
    seismic: bool = True                    # False = fara actiune seismica (doar gravitational)

    def validate(self) -> "FrameSpec":
        if not (1 <= self.stories <= 60):
            raise GenError("Numărul de etaje trebuie să fie între 1 și 60.")
        if not (1 <= self.bays <= 30 and 1 <= self.travei <= 30):
            raise GenError("Deschiderile și traveile trebuie să fie între 1 și 30.")
        for f in ("story_height", "span_x", "span_y", "column_b", "column_h", "beam_b", "beam_h", "slab_t"):
            if getattr(self, f) <= 0:
                raise GenError(f"Valoarea „{f}” trebuie să fie pozitivă.")
        if self.concrete not in CONCRETE:
            raise GenError(f"Clasă de beton necunoscută: {self.concrete}")
        if self.diaphragm not in ("semirigid", "rigid"):
            raise GenError("Diafragma poate fi „semirigid” sau „rigid”.")
        for f in ("crack_col_I", "crack_col_J", "crack_beam_I", "crack_beam_J", "crack_slab", "rigid_zone"):
            if not 0 < getattr(self, f) <= 1:
                raise GenError(f"„{f}” trebuie să fie între 0 (exclusiv) și 1.")
        if self.mesh_max <= 0 or self.modes_per_story < 1:
            raise GenError("Dimensiunea mesh-ului și numărul de moduri pe etaj trebuie să fie pozitive.")
        if self.seismic:
            assert_finite(self)
        return self

    @property
    def bottom(self) -> float:
        return self.story_height if self.bottom_height is None else self.bottom_height


def _cm(v: float) -> str:
    return f"{v * 100:g}"


def section_names(spec: FrameSpec) -> dict[str, str]:
    return {"column": f"C{_cm(spec.column_b)}x{_cm(spec.column_h)}", "beam": f"B{_cm(spec.beam_b)}x{_cm(spec.beam_h)}",
            "slab": f"P{_cm(spec.slab_t)}", "material": spec.concrete}


def define_sections(sap, spec: FrameSpec) -> dict[str, str]:
    """Material beton + sectiuni de stalp, grinda si placa. Intoarce numele definite."""
    n = section_names(spec)
    fck, ecm = CONCRETE[spec.concrete]
    ok(sap.PropMaterial.SetMaterial(n["material"], CONCRETE_TYPE), "SetMaterial")
    ok(sap.PropMaterial.SetMPIsotropic(n["material"], ecm, 0.2, 1e-5), "SetMPIsotropic")
    ok(sap.PropMaterial.SetWeightAndMass(n["material"], 1, 25.0), "SetWeightAndMass")
    try:                                    # parametrii de rezistenta (nu sunt necesari analizei)
        ok(sap.PropMaterial.SetOConcrete_1(n["material"], fck, False, 1, 2, 2, 0.002, 0.005, -0.1))
    except GenError:
        pass
    ok(sap.PropFrame.SetRectangle(n["column"], n["material"], spec.column_h, spec.column_b), "SetRectangle (stâlp)")
    ok(sap.PropFrame.SetRectangle(n["beam"], n["material"], spec.beam_h, spec.beam_b), "SetRectangle (grindă)")
    ok(sap.PropArea.SetSlab(n["slab"], SLAB, SHELL_THIN, n["material"], spec.slab_t), "SetSlab")
    return n


def build_frame_model(sap, spec: FrameSpec, out_path: str | Path | None = None) -> dict:
    """Creeaza modelul in `sap` (cSapModel) si il salveaza la `out_path`. Intoarce un sumar cu numarul de obiecte."""
    spec = spec.validate()
    assert_safe_to_overwrite(sap)
    ok(sap.InitializeNewModel(KN_M_C), "InitializeNewModel")
    ok(sap.File.NewGridOnly(spec.stories, spec.story_height, spec.bottom, spec.bays + 1, spec.travei + 1, spec.span_x, spec.span_y), "NewGridOnly")
    ok(sap.SetPresentUnits(KN_M_C), "SetPresentUnits")
    sec = define_sections(sap, spec)

    xs = [i * spec.span_x for i in range(spec.bays + 1)]
    ys = [j * spec.span_y for j in range(spec.travei + 1)]
    zs = [0.0] + [spec.bottom + k * spec.story_height for k in range(spec.stories)]
    count = {"stalpi": 0, "grinzi": 0, "placi": 0}
    base_points: list[str] = []
    frames: list[str] = []

    for k in range(1, len(zs)):
        for x in xs:
            for y in ys:
                name = ok(sap.FrameObj.AddByCoord(x, y, zs[k - 1], x, y, zs[k], "", sec["column"]), "AddByCoord (stâlp)")[0]
                frames.append(name)
                count["stalpi"] += 1
                if k == 1:
                    base_points.append(ok(sap.FrameObj.GetPoints(name), "GetPoints")[0])
        for y in ys:
            for a, b in zip(xs, xs[1:]):
                frames.append(ok(sap.FrameObj.AddByCoord(a, y, zs[k], b, y, zs[k], "", sec["beam"]), "AddByCoord (grindă X)")[0])
                count["grinzi"] += 1
        for x in xs:
            for a, b in zip(ys, ys[1:]):
                frames.append(ok(sap.FrameObj.AddByCoord(x, a, zs[k], x, b, zs[k], "", sec["beam"]), "AddByCoord (grindă Y)")[0])
                count["grinzi"] += 1

    sap.Diaphragm.Delete("D1")                # NewGridOnly defineste deja o diafragma D1 (rigida): o redefinim cu tipul cerut
    ok(sap.Diaphragm.SetDiaphragm("D1", spec.diaphragm == "semirigid"), "SetDiaphragm")
    try:
        ok(sap.LoadPatterns.Add("Permanenta", SUPER_DEAD, 0, True), "LoadPatterns.Add")
    except GenError:
        pass                                  # exista deja
    for k in range(1, len(zs)):
        for a, b in zip(xs, xs[1:]):
            for c, d in zip(ys, ys[1:]):
                name = ok(sap.AreaObj.AddByCoord(4, [a, b, b, a], [c, c, d, d], [zs[k]] * 4, "", sec["slab"]), "AddByCoord (placă)")[-1]   # COM intoarce si tablourile X, Y, Z
                ok(sap.AreaObj.SetDiaphragm(name, "D1"), "AreaObj.SetDiaphragm")
                if spec.dead_extra:
                    ok(sap.AreaObj.SetLoadUniform(name, "Permanenta", spec.dead_extra, SLAB_DIR_GRAVITY), "SetLoadUniform (perm.)")
                if spec.live:
                    ok(sap.AreaObj.SetLoadUniform(name, "Live", spec.live, SLAB_DIR_GRAVITY), "SetLoadUniform (utilă)")
                count["placi"] += 1

    for p in base_points:
        ok(sap.PointObj.SetRestraint(p, [True] * 6), "SetRestraint")

    notes = [apply_cracking(sap, spec, sec), apply_rigid_zones(sap, frames, spec.rigid_zone), apply_mesh(sap, spec.mesh_max),
             apply_mass_source(sap, spec, bool(spec.dead_extra)), apply_modal(sap, spec)]
    static, cases = [], []
    if spec.seismic:
        top = ok(sap.Story.GetNameList(), "Story.GetNameList")[1][0]            # primul = nivelul cel mai de sus
        static, cases, extra = apply_seismic(sap, spec, top)
        notes += extra
    notes.append(f"{apply_combinations(sap, spec, bool(spec.dead_extra), static, cases)} combinații (ULS, SLS, seismice)")
    if hasattr(sap, "View"):
        sap.View.RefreshView(0, False)

    path = None
    if out_path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ok(sap.File.Save(str(path)), "File.Save")
    return {"spec": asdict(spec), "sections": sec, "objects": count, "base_nodes": len(base_points), "file": str(path) if path else None,
            "notes": notes, "project": project_params(spec) if spec.seismic else {}}


def project_params(spec: FrameSpec) -> dict:
    """Parametrii proiectului pentru Setarile verificatorului (aceleasi valori ca in model)."""
    return {"ag": spec.ag, "gamma_I": spec.gamma_I, "beta0": spec.beta0, "Tb": spec.Tb, "Tc": spec.Tc, "Td": spec.Td, "q": spec.q,
            "lambda_mfse": spec.lam, "ecc": spec.ecc, "basement": "nu", "tip_cladire": "rezidential_cadre"}


def default_path(spec: FrameSpec, out_dir: Path) -> Path:
    safe = re.sub(r"[^\w\-]+", "_", spec.name).strip("_") or "model"
    return out_dir / f"{safe}_{spec.stories}et_{spec.bays}x{spec.travei}.EDB"
