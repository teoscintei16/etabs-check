"""Reparatii cu un click: fiecare modifica modelul ETABS deschis, dupa previzualizare si confirmare, si se poate anula.

O reparatie are `preview` (ce se schimba, fara sa scrie nimic), `apply` (scrie si intoarce datele pentru anulare)
si `undo`. Verificarile ataseaza reparatia unei constatari prin `Finding.fix = {"id", "args", "label"}`."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..connection import EtabsError, ok


@dataclass
class Fix:
    id: str
    title: str
    preview: Callable        # (session, args) -> {"changes": [{"what","before","after"}], "warnings": [str], "unlocks": bool}
    apply: Callable          # (session, args) -> undo (dict serializabil)
    undo: Callable           # (session, undo) -> None


FIXES: dict[str, Fix] = {}


def _in_units(fn):
    """Ruleaza functia cu unitatile kN, m (si le restaureaza), ca tabelele si valorile numerice sa fie in unitatile asteptate."""
    def wrapped(session, arg):
        with session.units():
            return fn(session, arg)
    return wrapped


def fix(id: str, title: str):
    def deco(cls):
        FIXES[id] = Fix(id, title, _in_units(cls.preview), _in_units(cls.apply), _in_units(cls.undo))
        return cls
    return deco


def _unlock(sap) -> bool:
    """Deblocheaza modelul (sterge rezultatele) daca e blocat; intoarce True daca a fost blocat."""
    if sap.GetModelIsLocked():
        ok(sap.SetModelIsLocked(False))
        return True
    return False


_LOCK_WARNING = "Modelul este analizat: modificarea îl deblochează și șterge rezultatele; trebuie reanalizat."


# ---------------------------------------------------------------- numar de moduri (caz modal Eigen)
@fix("set_modal_modes", "Setează numărul de moduri al cazului modal")
class SetModalModes:
    """args: {"cases": [{"name": "Modal", "max": 168}]} (maximul de moduri; minimul se ridica daca depaseste maximul)."""

    @staticmethod
    def _get(sap, name):
        r = ok(sap.LoadCases.ModalEigen.GetNumberModes(name))
        return int(r[0]), int(r[1])

    @staticmethod
    def preview(session, args):
        sap = session.model
        changes, warnings = [], []
        for c in args["cases"]:
            mx, mn = SetModalModes._get(sap, c["name"])
            if c["max"] < 1:
                raise EtabsError("Numărul de moduri trebuie să fie pozitiv.")
            changes.append({"what": f"Caz modal „{c['name']}”: număr maxim de moduri", "before": mx, "after": int(c["max"])})
        locked = bool(sap.GetModelIsLocked())
        if locked:
            warnings.append(_LOCK_WARNING)
        warnings.append("Un număr mare de moduri mărește timpul analizei; nu garantează singur masa participantă ≥ 90 %.")
        return {"changes": changes, "warnings": warnings, "unlocks": locked}

    @staticmethod
    def apply(session, args):
        sap = session.model
        undo = {"cases": [], "was_locked": _unlock(sap)}
        for c in args["cases"]:
            mx, mn = SetModalModes._get(sap, c["name"])
            ok(sap.LoadCases.ModalEigen.SetNumberModes(c["name"], int(c["max"]), min(mn, int(c["max"]))))
            undo["cases"].append({"name": c["name"], "max": mx, "min": mn})
        return undo

    @staticmethod
    def undo(session, undo):
        sap = session.model
        _unlock(sap)
        for c in undo["cases"]:
            ok(sap.LoadCases.ModalEigen.SetNumberModes(c["name"], c["max"], c["min"]))


from . import fixes_more  # noqa: E402,F401  (inregistreaza reparatiile grupelor 1 si 2)
