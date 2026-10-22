"""Rezolvarea obiectelor din avertismente/verificari in id-uri utile pentru ETABS."""
from __future__ import annotations

from .models import ModelData


def resolve(md: ModelData, obj, chains=()):
    """obj = (tip, nume) -> dict cu nume unic, eticheta, etaj, sectiune etc."""
    kind, name = obj
    if kind == "frame":
        f = md.frames.get(name)
        d = {"type": "frame", "name": name}
        if f:
            role = "belt" if name in md.belt_names else ("beam" if name in md.beam_names else "other")
            d.update(label=f.label, story=f.story, section=f.section, role=role)
        return d
    if kind == "wall":
        w = md.walls.get(name)
        d = {"type": "wall", "name": name}
        if w:
            d.update(label=w.label, story=w.story, thickness=w.thickness)
        return d
    return {"type": kind, "name": name}
