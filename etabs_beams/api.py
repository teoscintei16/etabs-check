"""Interfata publica a verificatorului pe linia de comanda: sectiunile barelor si verificarea modelului."""
from __future__ import annotations

import collections

from .connection import EtabsSession, ok
from .models import COLUMN, Tolerances
from .reader import read_model


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


def check_model(session: EtabsSession, tol: Tolerances | None = None):
    """Verifica daca modelul e curat si pregatit. Intoarce (ModelData, [Issue], Extras)."""
    from .checker import gather_extras, run_checks
    tol = tol or Tolerances()
    with session.units():
        md = read_model(session, tol)
    extras = gather_extras(session)
    return md, run_checks(md, tol, extras), extras
