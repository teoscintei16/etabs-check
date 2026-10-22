"""Clasificare bare: grinda / stalp / altele."""
from __future__ import annotations

import fnmatch

from .models import BEAM, COLUMN, NULL, OTHER, ModelData, Tolerances, warn


def slope(frame) -> float:
    L = frame.length
    return abs(frame.end[2] - frame.start[2]) / L if L else 9.0


def is_beam(frame, tol: Tolerances) -> bool:
    """Grinda = orientare Beam, sau (fallback) Null/Other orizontala cu sectiune."""
    if frame.curved:
        return False
    if frame.orientation == BEAM:
        return slope(frame) <= 0.999          # exclude doar barele practic verticale
    if frame.orientation in (NULL, OTHER):
        return bool(frame.section) and slope(frame) <= tol.max_slope
    return False


def classify(model: ModelData, tol: Tolerances) -> list[str]:
    beams, belts, skipped_null = [], [], []
    pats = [p.lower() for p in tol.belt_sections]
    for f in model.frames.values():
        if is_beam(f, tol):
            if pats and any(fnmatch.fnmatchcase(f.section.lower(), p) for p in pats):
                belts.append(f.name)          # centura de perete (dummy): separata de grinzi
            else:
                beams.append(f.name)
        elif f.orientation in (NULL, OTHER) and not f.section:
            skipped_null.append(f.name)
        elif f.curved and f.orientation == BEAM:
            warn(model.warnings, "curved_beam", "Grinda curba ignorata", [("frame", f.name)])
    if skipped_null:
        warn(model.warnings, "null_frames_ignored",
             f"{len(skipped_null)} bare fara sectiune (Null) ignorate", skipped_null[:20])
    model.beam_names = beams
    model.belt_names = belts
    return beams
