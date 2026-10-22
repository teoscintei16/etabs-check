"""Export JSON al grinzilor continue / centurilor (unitati kN, m)."""
from __future__ import annotations

import json
from dataclasses import asdict

from .api import BeamModel
from .refs import resolve

SCHEMA_VERSION = 3


def _resolve(bm: BeamModel, obj) -> dict:
    return resolve(bm.model, obj, bm.chains + bm.belts)


def _chain(c, labels):
    d = asdict(c)
    d["continuity"] = c.continuity
    d["length"] = c.length
    for m in d["members"]:
        m["label"] = labels.get(m["frame"], "")
    return d


def to_dict(bm: BeamModel, model_file: str = "", include=("beams",)) -> dict:
    labels = bm.labels
    out = {
        "schema_version": SCHEMA_VERSION,
        "units": {"length": "m", "force": "kN"},
        "model_file": model_file,
        "warnings": [{**w, "objects": [_resolve(bm, o) for o in w.get("objects", [])]}
                     for w in bm.model.warnings],
    }
    if "beams" in include:
        out["chains_total"] = len(bm.chains)
        out["chains_selected"] = len(bm.selected)
        out["chains"] = [_chain(c, labels) for c in bm.selected]
        out["on_wall"] = [asdict(o) for o in bm.on_wall]
    if "belts" in include:
        out["belts_total"] = len(bm.belts)
        out["belts_selected"] = len(bm.selected_belts)
        out["belts"] = [_chain(c, labels) for c in bm.selected_belts]
    return out


def write_json(bm: BeamModel, path: str, model_file: str = "", include=("beams",)) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(to_dict(bm, model_file, include), fh, ensure_ascii=False, indent=1)
