"""Editarea tabelelor ETABS (DatabaseTables.*EditingArray): citire, modificare pe chei, aplicare, valori vechi pentru anulare."""
from __future__ import annotations

from ..connection import EtabsError


def read_table(sap, key: str):
    """(versiune, campuri, randuri ca dict) din tabelul editabil `key`."""
    r = sap.DatabaseTables.GetTableForEditingArray(key, "", 0, [], 0, [])
    if r[-1] != 0:
        raise EtabsError(f"Tabelul „{key}” nu poate fi editat (cod {r[-1]}).")
    version, fields, n, data = r[0], list(r[1]), int(r[2]), list(r[3])
    nf = len(fields)
    return version, fields, [dict(zip(fields, data[i * nf:(i + 1) * nf])) for i in range(n)]


def edit_table(sap, key: str, keyfield: str | None, changes: dict) -> dict:
    """Aplica `changes` {cheie_rand: {camp: valoare}} (cheie_rand=None si keyfield=None pentru tabele cu un singur rand).
    Intoarce valorile vechi in aceeasi forma, pentru anulare.

    IMPORTANT: ApplyEditedTables inlocuieste tabelul intreg (inregistrarile netrimise se STERG din model), deci se
    retrimit toate randurile si toate campurile editabile; doar valorile din `changes` difera."""
    if not changes:
        return {}
    version, fields, rows = read_table(sap, key)
    by_key = {(r[keyfield] if keyfield else None): r for r in rows}
    missing = [k for k in changes if k not in by_key]
    if missing:
        raise EtabsError(f"„{key}”: nu există rândurile {', '.join(map(str, missing[:5]))}.")
    unknown = sorted({f for c in changes.values() for f in c} - set(fields))
    if unknown:
        raise EtabsError(f"„{key}”: câmpuri necunoscute {', '.join(unknown)}.")
    old = {k: {f: by_key[k][f] for f in c} for k, c in changes.items()}
    data = []
    for r in rows:
        k = r[keyfield] if keyfield else None
        c = changes.get(k, {})
        data += [str(c.get(f, r[f])) for f in fields]
    sap_t = sap.DatabaseTables
    r = sap_t.SetTableForEditingArray(key, version, fields, len(rows), data)
    if r[-1] != 0:
        _cancel(sap_t)
        raise EtabsError(f"„{key}”: scrierea tabelului a eșuat (cod {r[-1]}).")
    a = sap_t.ApplyEditedTables(True, 0, 0, 0, 0, "")
    fatal, errors, log = a[0], a[1], a[4]
    if a[-1] != 0 or fatal or errors:
        raise EtabsError(f"„{key}”: aplicarea a eșuat ({fatal} erori fatale, {errors} erori). {str(log)[:400]}")
    return old


def _cancel(sap_t) -> None:
    try:
        sap_t.CancelTableEditing()
    except Exception:
        pass
