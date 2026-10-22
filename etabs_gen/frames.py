"""Modele ETABS generate: cadre, pereti izolati/cuplati, structuri duale, subsol, forme neregulate (L, retrageri, goluri in plansee).

x etaje, y deschideri (directia X), z travei (directia Y); plansee, rezemare, diafragme, incarcari, apoi regulile (rules.py)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .connect import KN_M_C, GenError, assert_safe_to_overwrite, ok
from .plan import build_plan, parse_cells
from .rules import (apply_beam_insertion, apply_combinations, apply_cracking, apply_mass_source, apply_mesh, apply_modal, apply_rigid_zones,
                    apply_seismic, assert_finite, calibrate_static)

# clasa betonului -> (fck [kN/m2], Ecm [kN/m2]) conform EN 1992-1-1
CONCRETE = {"C20/25": (20e3, 30e6), "C25/30": (25e3, 31e6), "C30/37": (30e3, 33e6), "C35/45": (35e3, 34e6), "C40/50": (40e3, 35e6)}
BELT_H = 0.25                               # m, inaltimea centurii dummy
SLAB_DIR_GRAVITY = 10                       # directia de incarcare „Gravity” din API
LOCAL_3 = 3                                 # directia de incarcare „axa locala 3” (normala la perete)
STEEL, CONCRETE_TYPE, SLAB, SHELL_THIN, SUPER_DEAD, OTHER = 1, 2, 0, 1, 2, 8
SOIL_PATTERN = "Impingere_pamant"
STRUCTURES = ("cadre", "pereti_izolati", "pereti_cuplati", "dual", "neregulat")


@dataclass
class FrameSpec:
    name: str = "cadre"
    structure: str = "cadre"                # informativ: cadre | pereti_izolati | pereti_cuplati | dual | neregulat (presetarile sunt in formular)
    stories: int = 5                        # x: numar de etaje (deasupra terenului)
    bays: int = 3                           # y: deschideri (pe directia X)
    travei: int = 3                         # z: travei (pe directia Y)
    story_height: float = 3.0               # m
    bottom_height: float | None = None      # m (implicit = inaltimea etajului curent); fara subsol
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
    calibrate_static: bool = True           # dupa o analiza modala, C al fortelor statice se ia pentru T1 pe fiecare directie (cere ~20-60 s)
    # --- pereti structurali: panouri pe grila, un panou pe deschidere si pe etaj
    walls: bool = False
    wall_t: float = 0.25                    # m, grosimea peretilor
    wall_lines_x: str = "first,last"        # liniile de grila (pe Y) pe care sunt pereti paraleli cu X („none” = fara)
    wall_bays_x: str = "middle"             # deschiderile ocupate de acesti pereti
    wall_lines_y: str = "first,last"
    wall_bays_y: str = "middle"
    gravity_frame: bool = True              # stalpi si grinzi in afara peretilor
    belts: bool = True                      # centuri (grinzi „dummy”) deasupra peretilor, la fiecare etaj
    crack_wall_f: float = 0.5               # fisurare pereti: f11, f22, f12 (in plan)
    crack_wall_m: float = 0.25              # m11, m22, m12 (incovoiere din plan)
    # --- pereti cuplati: grinzi de cuplare (cu eticheta Spandrel) in deschiderile dintre doi pereti
    coupling_bays_x: str = ""               # deschideri pe X dintre doi pereti, pe liniile cu pereti („” = fara)
    coupling_bays_y: str = ""
    coupling_h: float = 0.90                # m, inaltimea grinzii de cuplare (latimea = grosimea peretelui)
    # --- subsol
    basement: int = 0                       # numar de niveluri de subsol (0 = fara)
    basement_height: float = 3.0
    basement_wall_t: float = 0.30
    soil_pressure: float = 25.0             # kN/m2, impingerea pamantului (uniforma, simplificata)
    # --- forme neregulate
    shape: str = "rect"                     # rect | L | setback
    cut_bays: int = 1                       # L: deschideri taiate din coltul (x, y) maxim
    cut_travei: int = 1
    setback_story: int = 3                  # setback: planul se reduce deasupra acestui etaj
    setback_bays: int = 1                   # deschideri eliminate pe latura x maxima
    void_cells: str = ""                    # goluri in plansee: celule „i,j;i,j” (ex. 1,1)

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
        if self.walls:
            if self.wall_t <= 0 or self.coupling_h <= 0:
                raise GenError("Grosimea peretelui și înălțimea grinzii de cuplare trebuie să fie pozitive.")
            for f in ("crack_wall_f", "crack_wall_m"):
                if not 0 < getattr(self, f) <= 1:
                    raise GenError(f"„{f}” trebuie să fie între 0 (exclusiv) și 1.")
        if self.coupling_bays_x.strip() or self.coupling_bays_y.strip():
            if not self.walls:
                raise GenError("Grinzile de cuplare cer pereți (bifează „Cu pereți”).")
        if not 0 <= self.basement <= 4:
            raise GenError("Numărul de niveluri de subsol trebuie să fie între 0 și 4.")
        if self.basement and (self.basement_height <= 0 or self.basement_wall_t <= 0 or self.soil_pressure < 0):
            raise GenError("Înălțimea subsolului și grosimea pereților de subsol trebuie să fie pozitive, iar presiunea pământului nenegativă.")
        if self.shape not in ("rect", "L", "setback"):
            raise GenError("Forma poate fi „rect”, „L” sau „setback”.")
        if self.shape == "L" and not (1 <= self.cut_bays < self.bays and 1 <= self.cut_travei < self.travei):
            raise GenError("Forma L cere 1 ≤ deschideri tăiate < deschideri și 1 ≤ travei tăiate < travei.")
        if self.shape == "setback" and not (1 <= self.setback_story < self.stories and 1 <= self.setback_bays < self.bays):
            raise GenError("Retragerea cere 1 ≤ etaj < etaje și 1 ≤ deschideri eliminate < deschideri.")
        if self.void_cells.strip():
            parse_cells(self.void_cells, self)
        if self.mesh_max <= 0 or self.modes_per_story < 1:
            raise GenError("Dimensiunea mesh-ului și numărul de moduri pe etaj trebuie să fie pozitive.")
        if self.seismic:
            assert_finite(self)
        build_plan(self)                     # valideaza si textele de amplasare ale peretilor / grinzilor de cuplare
        return self

    @property
    def bottom(self) -> float:
        return self.story_height if self.bottom_height is None else self.bottom_height


def _cm(v: float) -> str:
    return f"{v * 100:g}"


def section_names(spec: FrameSpec) -> dict[str, str]:
    n = {"column": f"C{_cm(spec.column_b)}x{_cm(spec.column_h)}", "beam": f"B{_cm(spec.beam_b)}x{_cm(spec.beam_h)}",
         "slab": f"P{_cm(spec.slab_t)}", "material": spec.concrete}
    if spec.belts and (spec.walls or spec.basement):
        n["belt"] = "CENTURA"
    if spec.walls:
        n["wall"] = f"W{_cm(spec.wall_t)}"
        if spec.coupling_bays_x.strip() or spec.coupling_bays_y.strip():
            n["cbeam"] = f"CB{_cm(spec.wall_t)}x{_cm(spec.coupling_h)}"
    if spec.basement:
        n["bwall"] = f"WB{_cm(spec.basement_wall_t)}"
    return n


def define_sections(sap, spec: FrameSpec) -> dict[str, str]:
    """Material beton + sectiuni de stalp, grinda, placa, perete, centura, grinda de cuplare, perete de subsol. Intoarce numele definite."""
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
    if "wall" in n:
        ok(sap.PropArea.SetWall(n["wall"], 0, SHELL_THIN, n["material"], spec.wall_t), "SetWall")
    if "belt" in n:                          # centura: grinda „dummy” cat grosimea peretelui, fara masa/greutate proprie (nu dubleaza peretele)
        ok(sap.PropFrame.SetRectangle(n["belt"], n["material"], BELT_H, spec.wall_t), "SetRectangle (centură)")
    if "cbeam" in n:
        ok(sap.PropFrame.SetRectangle(n["cbeam"], n["material"], spec.coupling_h, spec.wall_t), "SetRectangle (grindă de cuplare)")
    if "bwall" in n:
        ok(sap.PropArea.SetWall(n["bwall"], 0, SHELL_THIN, n["material"], spec.basement_wall_t), "SetWall (subsol)")
    return n


def _apply_stories(sap, plan) -> None:
    """Cu subsol: redenumeste nivelurile (S2, S1, P, E1…) si pune cota bazei; NewGridOnly lucreaza cu Story1.. de la cota 0."""
    names = [s.name for s in plan.stories]
    heights = [s.z_top - s.z_bot for s in plan.stories]
    n = len(names)
    ok(sap.Story.SetStories_2(plan.stories[0].z_bot, n, names, heights, [False] * n, [""] * n, [False] * n, [0.0] * n, [-1] * n), "Story.SetStories_2")


def build_frame_model(sap, spec: FrameSpec, out_path: str | Path | None = None) -> dict:
    """Creeaza modelul in `sap` (cSapModel) si il salveaza la `out_path`. Intoarce un sumar cu numarul de obiecte."""
    spec = spec.validate()
    assert_safe_to_overwrite(sap)
    plan = build_plan(spec)
    nb = spec.basement
    ok(sap.InitializeNewModel(KN_M_C), "InitializeNewModel")
    n_all = len(plan.stories)
    ok(sap.File.NewGridOnly(n_all, spec.story_height, spec.bottom if not nb else spec.story_height, spec.bays + 1, spec.travei + 1,
                            spec.span_x, spec.span_y), "NewGridOnly")
    ok(sap.SetPresentUnits(KN_M_C), "SetPresentUnits")
    if nb:
        _apply_stories(sap, plan)
    sec = define_sections(sap, spec)

    xs = [i * spec.span_x for i in range(spec.bays + 1)]
    ys = [j * spec.span_y for j in range(spec.travei + 1)]
    count = {"stalpi": 0, "grinzi": 0, "placi": 0}
    if spec.walls:
        count.update({"pereti": 0, "centuri": 0})
        if "cbeam" in sec:
            count["grinzi_cuplare"] = 0
    if nb:
        count["pereti_subsol"] = 0
    base_points: list[str] = []
    frames: list[str] = []                         # bare cu zone rigide (fara centuri)
    beams: list[str] = []                          # grinzi + centuri + grinzi de cuplare (insertie sus-centru)
    soil_areas: list[tuple[str, str, str]] = []    # (arie, axa, parte) pentru impingerea pamantului
    for pier in dict.fromkeys(r["pier"] for r in plan.runs):
        sap.PierLabel.SetPier(pier)                # eroare daca exista deja: se ignora
    spandrels: set[str] = set()

    def add_frame(a, b, prop, what):
        return ok(sap.FrameObj.AddByCoord(a[0], a[1], a[2], b[0], b[1], b[2], "", prop), f"AddByCoord ({what})")[0]

    for idx, st in enumerate(plan.stories):
        z0, z1 = st.z_bot, st.z_top
        first = idx == 0
        for ix, iy in plan.columns(idx):
            name = add_frame((xs[ix], ys[iy], z0), (xs[ix], ys[iy], z1), sec["column"], "stâlp")
            frames.append(name)
            count["stalpi"] += 1
            if first:
                base_points.append(ok(sap.FrameObj.GetPoints(name), "GetPoints")[0])
        bx, by = plan.beams(idx)
        for iy, i in bx:
            frames.append(add_frame((xs[i], ys[iy], z1), (xs[i + 1], ys[iy], z1), sec["beam"], "grindă X"))
            beams.append(frames[-1])
            count["grinzi"] += 1
        for ix, j in by:
            frames.append(add_frame((xs[ix], ys[j], z1), (xs[ix], ys[j + 1], z1), sec["beam"], "grindă Y"))
            beams.append(frames[-1])
            count["grinzi"] += 1
        for w in plan.wall_panels(idx):
            if w["axis"] == "X":
                y, i = ys[w["line"]], w["bay"]
                px, py = [xs[i], xs[i + 1], xs[i + 1], xs[i]], [y] * 4
            else:
                x, j = xs[w["line"]], w["bay"]
                px, py = [x] * 4, [ys[j], ys[j + 1], ys[j + 1], ys[j]]
            name = ok(sap.AreaObj.AddByCoord(4, px, py, [z0, z0, z1, z1], "", sec["wall"]), "AddByCoord (perete)")[-1]
            ok(sap.AreaObj.SetPier(name, w["pier"]), "AreaObj.SetPier")
            count["pereti"] += 1
            if first:
                base_points += list(ok(sap.AreaObj.GetPoints(name), "AreaObj.GetPoints")[1][:2])
            if "belt" in sec:
                beams.append(add_frame((px[0], py[0], z1), (px[1], py[1], z1), sec["belt"], "centură"))
                count["centuri"] += 1
        for c in plan.coupling_beams(idx):
            if c["axis"] == "X":
                a, b = (xs[c["bay"]], ys[c["line"]], z1), (xs[c["bay"] + 1], ys[c["line"]], z1)
            else:
                a, b = (xs[c["line"]], ys[c["bay"]], z1), (xs[c["line"]], ys[c["bay"] + 1], z1)
            name = add_frame(a, b, sec["cbeam"], "grindă de cuplare")
            beams.append(name)
            frames.append(name)
            if c["spandrel"] not in spandrels:
                sap.SpandrelLabel.SetSpandrel(c["spandrel"], True)
                spandrels.add(c["spandrel"])
            ok(sap.FrameObj.SetSpandrel(name, c["spandrel"]), "FrameObj.SetSpandrel")
            count["grinzi_cuplare"] += 1
        for w in plan.basement_walls(idx):
            if w["axis"] == "X":
                y, i = ys[w["line"]], w["bay"]
                px, py = [xs[i], xs[i + 1], xs[i + 1], xs[i]], [y] * 4
            else:
                x, j = xs[w["line"]], w["bay"]
                px, py = [x] * 4, [ys[j], ys[j + 1], ys[j + 1], ys[j]]
            name = ok(sap.AreaObj.AddByCoord(4, px, py, [z0, z0, z1, z1], "", sec["bwall"]), "AddByCoord (perete subsol)")[-1]
            count["pereti_subsol"] += 1
            soil_areas.append((name, w["axis"], w["side"]))
            if "belt" in sec:                      # centura dummy deasupra peretelui de subsol (grinzile care se descarca in nod)
                beams.append(add_frame((px[0], py[0], z1), (px[1], py[1], z1), sec["belt"], "centură subsol"))
                count["centuri"] = count.get("centuri", 0) + 1
            if first:
                base_points += list(ok(sap.AreaObj.GetPoints(name), "AreaObj.GetPoints")[1][:2])

    sap.Diaphragm.Delete("D1")                # NewGridOnly defineste deja o diafragma D1 (rigida): o redefinim cu tipul cerut
    ok(sap.Diaphragm.SetDiaphragm("D1", spec.diaphragm == "semirigid"), "SetDiaphragm")
    try:
        ok(sap.LoadPatterns.Add("Permanenta", SUPER_DEAD, 0, True), "LoadPatterns.Add")
    except GenError:
        pass                                  # exista deja
    for idx, st in enumerate(plan.stories):
        for i, j in plan.slab_cells(idx):
            name = ok(sap.AreaObj.AddByCoord(4, [xs[i], xs[i + 1], xs[i + 1], xs[i]], [ys[j], ys[j], ys[j + 1], ys[j + 1]], [st.z_top] * 4, "",
                                             sec["slab"]), "AddByCoord (placă)")[-1]   # COM intoarce si tablourile X, Y, Z
            ok(sap.AreaObj.SetDiaphragm(name, "D1"), "AreaObj.SetDiaphragm")
            if spec.dead_extra:
                ok(sap.AreaObj.SetLoadUniform(name, "Permanenta", spec.dead_extra, SLAB_DIR_GRAVITY), "SetLoadUniform (perm.)")
            if spec.live:
                ok(sap.AreaObj.SetLoadUniform(name, "Live", spec.live, SLAB_DIR_GRAVITY), "SetLoadUniform (utilă)")
            count["placi"] += 1

    extra_perm: list[str] = []
    if nb and spec.soil_pressure:
        ok(sap.LoadPatterns.Add(SOIL_PATTERN, OTHER, 0, True), "LoadPatterns.Add (pământ)")
        extra_perm.append(SOIL_PATTERN)
        for name, axis, side in soil_areas:
            # axa locala 3 a panoului (ordinea punctelor din AddByCoord): pe X -> -y, pe Y -> +x. Presiunea actioneaza spre interior.
            inward = {("X", "lo"): -1.0, ("X", "hi"): 1.0, ("Y", "lo"): 1.0, ("Y", "hi"): -1.0}[(axis, side)]
            ok(sap.AreaObj.SetLoadUniform(name, SOIL_PATTERN, inward * spec.soil_pressure, LOCAL_3, True, "Local"), "SetLoadUniform (pământ)")

    for p in dict.fromkeys(base_points):
        ok(sap.PointObj.SetRestraint(p, [True] * 6), "SetRestraint")

    notes = [apply_cracking(sap, spec, sec), apply_rigid_zones(sap, frames, spec.rigid_zone), apply_beam_insertion(sap, beams),
             apply_mesh(sap, spec.mesh_max), apply_mass_source(sap, spec, bool(spec.dead_extra)), apply_modal(sap, spec)]
    static, cases = [], []
    if spec.seismic:
        top = ok(sap.Story.GetNameList(), "Story.GetNameList")[1][0]            # primul = nivelul cel mai de sus
        base_story = "S1" if nb else "Base"                                       # cu subsol, fortele seismice incep de la S1 (±0.00)
        static, cases, extra = apply_seismic(sap, spec, top, base_story)
        notes += extra
    notes.append(f"{apply_combinations(sap, spec, bool(spec.dead_extra), static, cases, extra_perm)} combinații (ULS, SLS, seismice)")
    if nb and spec.soil_pressure:
        notes.append(f"subsol {nb} niveluri: pereți perimetrali {spec.basement_wall_t * 100:g} cm, împingerea pământului {spec.soil_pressure:g} kN/m² (uniformă)")
    if hasattr(sap, "View"):
        sap.View.RefreshView(0, False)

    path = None
    if out_path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ok(sap.File.Save(str(path)), "File.Save")
    if path and spec.seismic and spec.calibrate_static:
        notes.append(calibrate_static(sap, spec, str(path)))
        ok(sap.File.Save(str(path)), "File.Save (după calibrare)")
    return {"spec": asdict(spec), "sections": sec, "objects": count, "base_nodes": len(set(base_points)), "file": str(path) if path else None,
            "notes": notes, "project": project_params(spec) if spec.seismic else {},
            "belts": {"has": True, "sections": [sec["belt"]]} if "belt" in sec else None,
            "piers": sorted({r["pier"] for r in plan.runs}), "stories": [s.name for s in reversed(plan.stories)]}


def project_params(spec: FrameSpec) -> dict:
    """Parametrii proiectului pentru Setarile verificatorului (aceleasi valori ca in model)."""
    out = {"ag": spec.ag, "gamma_I": spec.gamma_I, "beta0": spec.beta0, "Tb": spec.Tb, "Tc": spec.Tc, "Td": spec.Td, "q": spec.q,
           "lambda_mfse": spec.lam, "ecc": spec.ecc, "basement": "nu", "tip_cladire": "rezidential_pereti" if spec.walls else "rezidential_cadre"}
    if spec.basement:
        out.update({"basement": "da", "basement_stories": [f"S{k}" for k in range(1, spec.basement + 1)], "ground_story": "P"})
    return out


def default_path(spec: FrameSpec, out_dir: Path) -> Path:
    safe = re.sub(r"[^\w\-]+", "_", spec.name).strip("_") or "model"
    return out_dir / f"{safe}_{spec.structure}_{spec.stories}et_{spec.bays}x{spec.travei}.EDB"
