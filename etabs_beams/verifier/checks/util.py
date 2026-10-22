"""Ajutoare comune pentru verificarile pe tabele."""
from __future__ import annotations

import pandas as pd


def yes(v) -> bool:
    """Valoare booleana dintr-o celula de tabel ('Yes', True, 1, 'True')."""
    if isinstance(v, (int, float)):
        return bool(v) and v == v
    return str(v).strip().lower() in ("yes", "true", "1", "y")


def sname(x) -> str:
    """Nume de obiect ca text: 1388.0 -> '1388' (coloanele numerice sunt convertite de pandas)."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x).strip()


def col(df: pd.DataFrame, *candidates: str) -> str | None:
    """Prima coloana al carei nume (fara majuscule/spatii) se potriveste cu un candidat."""
    norm = {c.lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    for cand in candidates:
        key = cand.lower().replace(" ", "").replace("_", "")
        if key in norm:
            return norm[key]
    for cand in candidates:
        key = cand.lower().replace(" ", "").replace("_", "")
        for k, c in norm.items():
            if k.startswith(key):
                return c
    return None


def frame_objects(names, kind: str = "frame") -> list[tuple]:
    return [(kind, sname(n)) for n in names]
