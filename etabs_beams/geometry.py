"""Geometrie comuna: capete de grinda care ating interiorul altei grinzi fara nod comun."""
from __future__ import annotations

import numpy as np

from .models import ModelData


def end_on_beam_hits(md: ModelData, names: list[str], dist_tol: float = 0.02, end_tol: float = 0.02,
                     targets: list[str] | None = None):
    """[(bara_care_se_termina, nod, bara_traversata)]: capete din `names` aflate in interiorul unei bare din `targets`
    (implicit tot `names`), la <= dist_tol de axa, fara nod comun."""
    ends = [md.frames[b] for b in names]
    beams = [md.frames[b] for b in (targets if targets is not None else names)]
    if not beams or not ends:
        return []
    A = np.array([f.start for f in beams])
    B = np.array([f.end for f in beams])
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    L = np.sqrt(L2)
    hits, seen = [], set()
    for f in ends:
        for p, xyz in ((f.p1, f.start), (f.p2, f.end)):
            if p in seen:
                continue
            seen.add(p)
            P = np.array(xyz)
            t = ((P - A) * AB).sum(1) / L2
            d = np.linalg.norm(P - (A + t[:, None] * AB), axis=1)
            for j in np.nonzero((d <= dist_tol) & (t * L > end_tol) & ((1 - t) * L > end_tol))[0]:
                g = beams[j]
                if p not in (g.p1, g.p2):
                    hits.append((f.name, p, g.name))
    # un nod poate fi capat pentru mai multe grinzi: raportam fiecare pereche (grinda, nod) o data
    return hits
