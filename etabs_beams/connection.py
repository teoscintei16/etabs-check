"""Conectare la o instanta ETABS pornita (COM, via comtypes)."""
from __future__ import annotations

from contextlib import contextmanager

import comtypes.client

KN_M_C = 6   # eUnits.kN_m_C
PROG_ID = "CSI.ETABS.API.ETABSObject"


class EtabsError(RuntimeError):
    pass


def ok(res, what=""):
    """Verifica codul de retur (ultimul element) si intoarce valorile fara el."""
    if isinstance(res, (list, tuple)):
        if res[-1] != 0:
            raise EtabsError(f"{what or 'apel ETABS'} a esuat (cod {res[-1]})")
        return list(res[:-1])
    if res != 0:
        raise EtabsError(f"{what or 'apel ETABS'} a esuat (cod {res})")
    return []


class EtabsSession:
    def __init__(self, etabs_object):
        self.obj = etabs_object
        self.model = etabs_object.SapModel

    @classmethod
    def attach(cls) -> "EtabsSession":
        try:
            return cls(comtypes.client.GetActiveObject(PROG_ID))
        except OSError as e:
            raise EtabsError("Nu am gasit o instanta ETABS pornita") from e

    @property
    def filename(self) -> str:
        return self.model.GetModelFilename()

    @property
    def analyzed(self) -> bool:
        return bool(self.model.GetModelIsLocked())

    @contextmanager
    def units(self, code: int = KN_M_C):
        """Seteaza temporar unitatile (implicit kN, m) si le restaureaza la iesire."""
        prev = self.model.GetPresentUnits()
        ok(self.model.SetPresentUnits(code), "SetPresentUnits")
        try:
            yield
        finally:
            self.model.SetPresentUnits(prev)
