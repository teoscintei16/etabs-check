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
    Intoarce valorile vechi in aceeasi forma, pentru anulare."""
    if not changes:
        return {}
    version, fields, rows = read_table(sap, key)
    by_key = {(r[keyfield] if keyfield else None): r for r in rows}
    missing = [k for k in changes if k not in by_key]
    if missing:
        raise EtabsError(f"„{key}”: nu există rândurile {', '.join(map(str, missing[:5]))}.")
    inc = ([keyfield] if keyfield else []) + sorted({f for c in changes.values() for f in c})
    unknown = [f for f in inc if f not in fields]
    if unknown:
        raise EtabsError(f"„{key}”: câmpuri necunoscute {', '.join(unknown)}.")
    old, data = {}, []
    for k, c in changes.items():
        row = by_key[k]
        old[k] = {f: row[f] for f in c}
        data += [str(row[f]) if f == keyfield else str(c[f]) for f in inc]
    sap_t = sap.DatabaseTables
    r = sap_t.SetTableForEditingArray(key, version, inc, len(changes), data)
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
