"""Amplasarea peretilor in grila (calcule pure): ce panouri de perete exista, ce stalpi/grinzi se omit unde sunt pereti, etichetele Pier."""
from __future__ import annotations

from .connect import GenError


def parse_indices(text: str, count: int, what: str) -> list[int]:
    """„first,last”, „middle”, „all” sau numere separate prin virgula, intre 0 si count-1. Intoarce indici unici, sortati."""
    out: set[int] = set()
    for tok in (t.strip().lower() for t in str(text).split(",") if t.strip()):
        if tok == "first":
            out.add(0)
        elif tok == "last":
            out.add(count - 1)
        elif tok == "middle":
            out.add((count - 1) // 2)
        elif tok == "all":
            out.update(range(count))
        else:
            try:
                i = int(tok)
            except ValueError as e:
                raise GenError(f"{what}: „{tok}” nu e un indice (folosește numere, first, last, middle, all).") from e
            if not 0 <= i < count:
                raise GenError(f"{what}: indicele {i} nu există (valori între 0 și {count - 1}).")
            out.add(i)
    if not out:
        raise GenError(f"{what}: nu ai ales nimic.")
    return sorted(out)


def _groups(bays: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for b in bays:
        if out and b == out[-1][-1] + 1:
            out[-1].append(b)
        else:
            out.append([b])
    return out


def wall_runs(spec) -> list[dict]:
    """[{"axis": "X"|"Y", "line": j, "bays": [i, ...], "pier": "PX1"}]: un perete = un sir de deschideri consecutive pe o linie de grila.
    Pe X, `line` e indicele liniei in directia Y (0..travei) si `bays` indicii deschiderilor (0..bays-1); pe Y invers."""
    runs: list[dict] = []
    for axis, lines_txt, bays_txt, n_lines, n_bays in (("X", spec.wall_lines_x, spec.wall_bays_x, spec.travei + 1, spec.bays),
                                                       ("Y", spec.wall_lines_y, spec.wall_bays_y, spec.bays + 1, spec.travei)):
        lines = parse_indices(lines_txt, n_lines, f"Pereți pe {axis}: linii")
        bays = parse_indices(bays_txt, n_bays, f"Pereți pe {axis}: deschideri")
        k = 0
        for line in lines:
            for g in _groups(bays):
                k += 1
                runs.append({"axis": axis, "line": line, "bays": g, "pier": f"P{axis}{k}"})
    return runs


def blocked(runs: list[dict]) -> tuple[set[tuple[int, int]], set[tuple[int, int]], set[tuple[int, int]]]:
    """(noduri (ix, iy) atinse de pereti, grinzi pe X (iy, bay) si grinzi pe Y (ix, bay) inlocuite de pereti)."""
    nodes: set[tuple[int, int]] = set()
    xb: set[tuple[int, int]] = set()
    yb: set[tuple[int, int]] = set()
    for r in runs:
        for b in r["bays"]:
            if r["axis"] == "X":
                nodes |= {(b, r["line"]), (b + 1, r["line"])}
                xb.add((r["line"], b))
            else:
                nodes |= {(r["line"], b), (r["line"], b + 1)}
                yb.add((r["line"], b))
    return nodes, xb, yb
