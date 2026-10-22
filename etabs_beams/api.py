"""Interfata publica: detectie grinzi continue / centuri (+ selector) si export."""
from __future__ import annotations

import collections
import fnmatch
from dataclasses import dataclass, field

from .connection import EtabsSession, ok
from .continuity import Chain, OnWall, build_all
from .models import COLUMN, ModelData, Tolerances
from .reader import read_model
from .selector import BeamSelector


@dataclass
class BeamModel:
    model: ModelData
    chains: list[Chain]                       # grinzi
    belts: list[Chain]                        # centuri de perete (dummy), separate
    on_wall: list[OnWall]
    selected: list[Chain] = field(default_factory=list)
    selected_belts: list[Chain] = field(default_factory=list)

    @property
    def labels(self) -> dict[str, str]:
        return {n: f.label for n, f in self.model.frames.items()}

    def select(self, selector: BeamSelector | None, belt_selector: BeamSelector | None = None):
        self.selected = selector.apply(self.chains, self.labels) if selector else list(self.chains)
        bs = belt_selector or selector
        self.selected_belts = bs.apply(self.belts, self.labels) if bs else list(self.belts)
        return self.selected


def list_sections(session: EtabsSession) -> list[tuple[str, int]]:
    """Sectiunile barelor care nu sunt stalpi, cu numarul de bare (pentru intrebarea despre centuri)."""
    sap = session.model
    r = ok(sap.FrameObj.GetAllFrames())
    names, props = r[1], r[2]
    cnt: collections.Counter = collections.Counter()
    for nm, pr in zip(names, props):
        if pr and sap.FrameObj.GetDesignOrientation(nm)[0] != COLUMN:
            cnt[pr] += 1
    return sorted(cnt.items(), key=lambda kv: kv[0].lower())


def detect(session: EtabsSession, tol: Tolerances | None = None,
           selector: BeamSelector | None = None, belt_selector: BeamSelector | None = None) -> BeamModel:
    """Citeste modelul (kN, m), detecteaza lanturile pe TOATE grinzile/centurile, apoi aplica selectorul.

    tol.belt_sections: sabloane de sectiuni care simuleaza centurile peretilor (ex. ["dummy*"]);
    acele bare sunt excluse din grinzi si tratate separat in `belts`."""
    tol = tol or Tolerances()
    with session.units():
        md = read_model(session, tol)
    beams, belts, on_wall = build_all(md, tol)
    bm = BeamModel(md, beams, belts, on_wall)
    bm.select(selector, belt_selector)
    return bm


def check_model(session: EtabsSession, tol: Tolerances | None = None):
    """Verifica daca modelul e curat si pregatit. Intoarce (ModelData, [Issue], Extras)."""
    from .checker import gather_extras, run_checks
    tol = tol or Tolerances()
    with session.units():
        md = read_model(session, tol)
    extras = gather_extras(session)
    return md, run_checks(md, tol, extras), extras
