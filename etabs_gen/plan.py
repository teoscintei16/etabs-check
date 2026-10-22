"""Planul constructiei (calcule pure, fara ETABS): niveluri (cu subsol), celule active pe etaj (forme neregulate), pereti, grinzi de cuplare.

Convenții: grila are `bays+1` linii pe X (indice ix) și `travei+1` linii pe Y (iy). O celula (i, j) e dreptunghiul dintre liniile
i..i+1 pe X si j..j+1 pe Y. Un perete paralel cu X pe linia j (indice iy) ocupa deschiderea i; unul paralel cu Y pe linia i ocupa
traveea j. Nivelurile sunt listate de jos in sus."""
from __future__ import annotations

from dataclasses import dataclass, field

from .connect import GenError
from .layout import parse_indices


@dataclass
class Story:
    name: str
    z_bot: float
    z_top: float
    basement: bool


def stories_of(spec) -> list[Story]:
    """Nivelurile de jos in sus. Fara subsol: Story1..StoryN (denumirile ETABS implicite); cu subsol: S<n>..S1 (S1 are cota superioara ±0.00),
    P (parter), E1, E2, …"""
    out: list[Story] = []
    nb, hb = spec.basement, spec.basement_height
    if nb:
        z = -nb * hb
        for k in range(nb, 0, -1):
            out.append(Story(f"S{k}", z, z + hb, True))
            z += hb
        names = ["P"] + [f"E{i}" for i in range(1, spec.stories)]
    else:
        z = 0.0
        names = [f"Story{i}" for i in range(1, spec.stories + 1)]
    for i, name in enumerate(names):
        h = spec.bottom if (i == 0 and not nb) else spec.story_height
        out.append(Story(name, z, z + h, False))
        z += h
    return out


def _cells_all(spec) -> set[tuple[int, int]]:
    return {(i, j) for i in range(spec.bays) for j in range(spec.travei)}


def active_cells(spec, above: int | None) -> set[tuple[int, int]]:
    """Celulele active la etajul `above` (1..stories, numarat de la parter); None = subsol (planul complet)."""
    cells = _cells_all(spec)
    if above is None or spec.shape == "rect":
        return cells
    if spec.shape == "L":
        return {(i, j) for i, j in cells if not (i >= spec.bays - spec.cut_bays and j >= spec.travei - spec.cut_travei)}
    if spec.shape == "setback":
        return cells if above <= spec.setback_story else {(i, j) for i, j in cells if i < spec.bays - spec.setback_bays}
    raise GenError(f"Formă necunoscută: {spec.shape}")


def parse_cells(text: str, spec) -> set[tuple[int, int]]:
    """„1,1;2,0” -> {(1, 1), (2, 0)} (goluri in plansee)."""
    out = set()
    for tok in (t.strip() for t in str(text).split(";") if t.strip()):
        try:
            i, j = (int(x) for x in tok.split(","))
        except ValueError as e:
            raise GenError(f"Gol în planșeu „{tok}”: folosește formatul i,j (ex. 1,1;2,0).") from e
        if not (0 <= i < spec.bays and 0 <= j < spec.travei):
            raise GenError(f"Gol în planșeu „{tok}”: celula nu există (i între 0 și {spec.bays - 1}, j între 0 și {spec.travei - 1}).")
        out.add((i, j))
    return out


def _edges(cells: set[tuple[int, int]]) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """(muchii pe X (iy, i), muchii pe Y (ix, j)) ale celulelor."""
    xe, ye = set(), set()
    for i, j in cells:
        xe |= {(j, i), (j + 1, i)}
        ye |= {(i, j), (i + 1, j)}
    return xe, ye


def _nodes(cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    return {(i + a, j + b) for i, j in cells for a in (0, 1) for b in (0, 1)}


@dataclass
class Plan:
    spec: object
    stories: list[Story]
    cells: list[set[tuple[int, int]]]                       # celule active pe nivel
    voids: set[tuple[int, int]]
    runs: list[dict]                                        # pereti (sir de deschideri pe o linie), cu eticheta Pier
    coupling: set[tuple[str, int, int]] = field(default_factory=set)   # (axa, linie, deschidere) cu grinda de cuplare

    # ---- subsol
    def is_basement(self, idx: int) -> bool:
        return self.stories[idx].basement

    def _perimeter(self) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
        s = self.spec
        xe = {(j, i) for i in range(s.bays) for j in (0, s.travei)}
        ye = {(i, j) for j in range(s.travei) for i in (0, s.bays)}
        return xe, ye

    def basement_walls(self, idx: int) -> list[dict]:
        """Panourile peretilor perimetrali de infrastructura: [{"axis", "line", "bay", "side": "lo"|"hi"}] (side = partea pamantului)."""
        if not self.is_basement(idx):
            return []
        s = self.spec
        out = [{"axis": "X", "line": j, "bay": i, "side": "lo" if j == 0 else "hi"} for j in (0, s.travei) for i in range(s.bays)]
        out += [{"axis": "Y", "line": i, "bay": j, "side": "lo" if i == 0 else "hi"} for i in (0, s.bays) for j in range(s.travei)]
        return out

    # ---- pereti peste teren
    def wall_panels(self, idx: int) -> list[dict]:
        """Panourile de perete ale nivelului idx: [{"axis", "line", "bay", "pier"}], doar unde muchia e alipita de o celula activa."""
        if self.is_basement(idx):
            return []
        cells = self.cells[idx]
        out = []
        for r in self.runs:
            for b in r["bays"]:
                adj = ({(b, r["line"] - 1), (b, r["line"])} if r["axis"] == "X" else {(r["line"] - 1, b), (r["line"], b)})
                if adj & cells:
                    out.append({"axis": r["axis"], "line": r["line"], "bay": b, "pier": r["pier"]})
        return out

    def coupling_beams(self, idx: int) -> list[dict]:
        """Grinzile de cuplare ale nivelului: [{"axis", "line", "bay", "spandrel"}]."""
        if self.is_basement(idx):
            return []
        cells = self.cells[idx]
        out = []
        for axis, line, b in sorted(self.coupling):
            adj = ({(b, line - 1), (b, line)} if axis == "X" else {(line - 1, b), (line, b)})
            if adj & cells:
                out.append({"axis": axis, "line": line, "bay": b, "spandrel": f"SP{axis}{line}_{b}"})
        return out

    # ---- cadre
    def _replaced(self, idx: int) -> tuple[set, set]:
        """Muchiile de grinda inlocuite de pereti/grinzi de cuplare (pe X: (iy, i); pe Y: (ix, j))."""
        xs, ys = set(), set()
        for w in self.wall_panels(idx) + self.coupling_beams(idx):
            (xs if w["axis"] == "X" else ys).add((w["line"], w["bay"]))
        if self.is_basement(idx):
            px, py = self._perimeter()
            xs |= px
            ys |= py
        return xs, ys

    def beams(self, idx: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
        """(grinzi pe X (iy, i), grinzi pe Y (ix, j)) ale nivelului, fara cele inlocuite de pereti."""
        if not self.spec.gravity_frame and not self.is_basement(idx):
            return [], []
        xe, ye = _edges(self.cells[idx])
        rx, ry = self._replaced(idx)
        return sorted(xe - rx), sorted(ye - ry)

    def columns(self, idx: int) -> list[tuple[int, int]]:
        """Nodurile cu stalp pe nivelul idx: noduri folosite de celulele nivelului sau ale celor de deasupra, fara capetele de pereti
        (si fara nodurile de pe perimetrul subsolului, unde e peretele)."""
        if not self.spec.gravity_frame and not self.is_basement(idx):
            return []
        used: set[tuple[int, int]] = set()
        for c in self.cells[idx:]:
            used |= _nodes(c)
        skip: set[tuple[int, int]] = set()
        for w in self.wall_panels(idx) + self.coupling_beams(idx):
            b = w["bay"]
            skip |= {(b, w["line"]), (b + 1, w["line"])} if w["axis"] == "X" else {(w["line"], b), (w["line"], b + 1)}
        if self.is_basement(idx):
            s = self.spec
            skip |= {(i, j) for i in range(s.bays + 1) for j in range(s.travei + 1) if i in (0, s.bays) or j in (0, s.travei)}
        return sorted(used - skip)

    def slab_cells(self, idx: int) -> list[tuple[int, int]]:
        return sorted(self.cells[idx] - (set() if self.is_basement(idx) else self.voids))


def build_plan(spec) -> Plan:
    stories = stories_of(spec)
    cells, above = [], 0
    for st in stories:
        if st.basement:
            cells.append(active_cells(spec, None))
        else:
            above += 1
            cells.append(active_cells(spec, above))
    voids = parse_cells(spec.void_cells, spec) if spec.void_cells.strip() else set()
    runs: list[dict] = []
    if spec.walls:
        for axis, lines_txt, bays_txt, n_lines, n_bays in (("X", spec.wall_lines_x, spec.wall_bays_x, spec.travei + 1, spec.bays),
                                                           ("Y", spec.wall_lines_y, spec.wall_bays_y, spec.bays + 1, spec.travei)):
            lines = parse_indices(lines_txt, n_lines, f"Pereți pe {axis}: linii", allow_none=True)
            bays = parse_indices(bays_txt, n_bays, f"Pereți pe {axis}: deschideri", allow_none=True)
            k = 0
            for line in lines:
                for g in _groups(bays):
                    k += 1
                    runs.append({"axis": axis, "line": line, "bays": g, "pier": f"P{axis}{k}"})
    coupling: set[tuple[str, int, int]] = set()
    for axis, txt, n_bays in (("X", spec.coupling_bays_x, spec.bays), ("Y", spec.coupling_bays_y, spec.travei)):
        if not str(txt).strip():
            continue
        wall_lines = {r["line"] for r in runs if r["axis"] == axis}
        for b in parse_indices(txt, n_bays, f"Grinzi de cuplare pe {axis}: deschideri"):
            for line in wall_lines:
                if not any(r["axis"] == axis and r["line"] == line and b in r["bays"] for r in runs):
                    coupling.add((axis, line, b))
    return Plan(spec, stories, cells, voids, runs, coupling)


def _groups(bays: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for b in bays:
        if out and b == out[-1][-1] + 1:
            out[-1].append(b)
        else:
            out.append([b])
    return out
