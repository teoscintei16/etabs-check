"""Structuri de date pure (fara dependenta de ETABS). Unitati: kN, m."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# eFrameDesignOrientation
COLUMN, BEAM, BRACE, NULL, OTHER = 1, 2, 3, 4, 5


@dataclass
class SectionInfo:
    name: str
    kind: str = "other"            # rect | circle | other
    depth: float | None = None     # T3 [m]
    width: float | None = None     # T2 [m]


@dataclass
class Frame:
    name: str                      # UniqueName (nume obiect ETABS)
    label: str
    story: str
    section: str
    p1: str                        # nume punct I
    p2: str                        # nume punct J
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    angle: float = 0.0             # unghi axe locale [deg]
    orientation: int = BEAM
    release_i: bool = False        # articulatie de moment la capatul I
    release_j: bool = False
    curved: bool = False
    cardinal: int = 8              # punct de insertie (8 = sus-centru)
    offsets: tuple = ()            # offseturi capete (1X,2X,1Y,2Y,1Z,2Z) [m]
    output_stations: tuple = ()    # (tip 1|2, max_seg_size, min_sections)

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)

    @property
    def direction(self) -> tuple[float, float, float]:
        L = self.length or 1.0
        return tuple((e - s) / L for s, e in zip(self.start, self.end))


@dataclass
class WallInfo:
    """Perete modelat cu shell vertical."""
    name: str
    thickness: float
    direction: tuple[float, float]  # directia orizontala a peretelui (unitar)
    points: list = field(default_factory=list)       # [(x, y, z)] varfurile poligonului
    point_names: list = field(default_factory=list)
    zmin: float = 0.0
    zmax: float = 0.0
    label: str = ""
    story: str = ""
    virtual: bool = False          # margine (sus/jos) a unui perete inclinat, reprezentata ca perete vertical subtire pentru logica grinda-pe-perete


@dataclass
class ModelData:
    frames: dict[str, Frame] = field(default_factory=dict)
    sections: dict[str, SectionInfo] = field(default_factory=dict)
    restrained: set[str] = field(default_factory=set)            # puncte cu reazem
    node_frames: dict[str, list[str]] = field(default_factory=dict)
    node_areas: dict[str, list[str]] = field(default_factory=dict)
    walls: dict[str, WallInfo] = field(default_factory=dict)     # doar arii de tip perete
    sloped_walls: dict[str, dict] = field(default_factory=dict)  # arii cu proprietate de perete dar neverticale (rampe): marginile reale de jos si de sus
    units: str = "kN_m"
    beam_names: list[str] = field(default_factory=list)          # rezultat clasificare
    belt_names: list[str] = field(default_factory=list)          # bare "centura" (dummy), separate de grinzi
    belt_segments: list = field(default_factory=list)            # [(start_xyz, end_xyz, [frame], id_centura)]
    warnings: list[dict] = field(default_factory=list)


@dataclass
class Tolerances:
    angle_deg: float = 10.0        # abatere max de la coliniaritate [deg]
    max_slope: float = 0.15        # |dz|/L peste care o bara nu mai e grinda (fallback geometric)
    belt_sections: list = field(default_factory=list)   # sabloane sectiuni "centura" (ex. "dummy*")
    # --- pereti ---
    wall_min_length: float = 0.80  # [m] perete in planul grinzii mai lung -> fara continuitate peste el
    wall_plane_tol: float = 0.10   # [m] abatere max a axei grinzii fata de planul peretelui
    wall_top_tol: float = 0.15     # [m] |cota varf perete - cota grinda|
    wall_gap_tol: float = 0.05     # [m] shell-uri/centuri alaturate care se unesc intr-un singur perete
    wall_length_tol: float = 0.05  # [m] toleranta la compararea lungimii (centura vs shell)
    wall_parallel_sin: float = 0.2 # |sin| max intre grinda si plan pentru a o considera in plan
    wall_member_frac: float = 0.5  # membru "pe perete" daca suprapunerea cu un perete lung >= acest procent
    eps: float = 1e-6


def warn(model_warnings: list[dict], code: str, message: str, objects=(), data: dict | None = None) -> None:
    """objects: [("frame", nume) | ("wall", nume)] - rezolvate la export (eticheta, etaj, sectiune)."""
    w = {"code": code, "message": message, "objects": [o if isinstance(o, tuple) else ("frame", o) for o in objects]}
    if data:
        w["data"] = data
    model_warnings.append(w)
