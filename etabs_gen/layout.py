"""Citirea indicilor de grila din text („first,last”, „middle”, „all”, „none”, numere)."""
from __future__ import annotations

from .connect import GenError


def parse_indices(text: str, count: int, what: str, allow_none: bool = False) -> list[int]:
    """„first,last”, „middle”, „all” sau numere separate prin virgula, intre 0 si count-1. Intoarce indici unici, sortati."""
    out: set[int] = set()
    if allow_none and str(text).strip().lower() in ("", "none"):
        return []
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
