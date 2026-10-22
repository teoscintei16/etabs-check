"""Pornirea unei instante ETABS NOI (nu se atinge de instantele deschise de utilizator) si garda de siguranta."""
from __future__ import annotations

import os
from pathlib import Path

import comtypes.client

PROG_ID = "CSI.ETABS.API.ETABSObject"
KN_M_C = 6                                   # eUnits.kN_m_C
OUT_DIR = Path(__file__).resolve().parent.parent / "generated_models"


class GenError(RuntimeError):
    pass


def ok(res, what: str = ""):
    """Verifica codul de retur (ultimul element sau intregul rezultat)."""
    code = res[-1] if isinstance(res, (list, tuple)) else res
    if code != 0:
        raise GenError(f"{what or 'apel ETABS'} a eșuat (cod {code})")
    return list(res[:-1]) if isinstance(res, (list, tuple)) else []


ETABS_EXE = Path(os.environ.get("ETABS_EXE", r"C:\Program Files\Computers and Structures\ETABS 22\ETABS.exe"))


def attach_if_safe():
    """Se ataseaza la o instanta ETABS deja pornita DOAR daca nu are un model al utilizatorului (gol sau generat de aplicatie)."""
    try:
        obj = comtypes.client.GetActiveObject(PROG_ID)
        assert_safe_to_overwrite(obj.SapModel)
        return obj
    except (OSError, GenError):
        return None


def start_etabs():
    """Porneste o instanta ETABS noua (prin ETABSv1.Helper) si intoarce obiectul COM (ETABSObject).
    Instantele existente raman neatinse."""
    if not ETABS_EXE.exists():
        raise GenError(f"Nu găsesc ETABS.exe la {ETABS_EXE}. Setează variabila de mediu ETABS_EXE.")
    helper = comtypes.client.CreateObject("ETABSv1.Helper")
    try:
        obj = helper.CreateObject(str(ETABS_EXE))
    except OSError as e:
        raise GenError(f"ETABS nu a putut fi pornit ({e}).") from e
    if obj is None:
        raise GenError("ETABS nu a putut fi pornit (verifică licența).")
    ok(obj.ApplicationStart(), "ApplicationStart")
    return obj


def assert_safe_to_overwrite(sap, out_dir: Path = OUT_DIR) -> None:
    """InitializeNewModel inlocuieste modelul deschis: permis doar daca instanta e goala sau are un model generat de aplicatie."""
    name = sap.GetModelFilename() or ""
    if not name or name.strip("()").lower() == "untitled":
        return
    try:
        inside = Path(name).resolve().is_relative_to(out_dir.resolve())
    except (OSError, ValueError):
        inside = False
    if not inside:
        raise GenError(f"Instanța ETABS are deschis un model care nu a fost generat de aplicație ({os.path.basename(name)}); "
                       "nu îl înlocuiesc. Folosește „Deschide ETABS nou”.")
