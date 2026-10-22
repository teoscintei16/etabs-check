"""Scrierea tabelelor ETABS (DatabaseTables) pentru lucrurile care nu au functii in API: functii spectrale, sursa de masa,
optiuni de mesh, tipare seismice automate.

IMPORTANT: ApplyEditedTables inlocuieste tabelul intreg (inregistrarile netrimise se sterg din model). De aceea fiecare
scriere citeste tabelul complet, modifica doar ce trebuie si retrimite toate randurile."""
from __future__ import annotations

from .connect import GenError


def read_table(sap, key: str):
    """(versiune, campuri, randuri ca dict) din tabelul editabil `key`."""
    r = sap.DatabaseTables.GetTableForEditingArray(key, "", 0, [], 0, [])
    if r[-1] != 0:
        raise GenError(f"Tabelul „{key}” nu poate fi citit pentru editare (cod {r[-1]}).")
    version, fields, n, data = r[0], list(r[1]), int(r[2]), list(r[3])
    nf = len(fields)
    return version, fields, [dict(zip(fields, data[i * nf:(i + 1) * nf])) for i in range(n)]


def write_table(sap, key: str, version, fields: list[str], rows: list[dict]) -> str:
    """Scrie tabelul intreg si il aplica; intoarce jurnalul de import. Ridica GenError la erori."""
    t = sap.DatabaseTables
    data = [str(r.get(f, "")) for r in rows for f in fields]
    r = t.SetTableForEditingArray(key, version, fields, len(rows), data)
    if r[-1] != 0:
        _cancel(t)
        raise GenError(f"„{key}”: scrierea tabelului a eșuat (cod {r[-1]}).")
    a = t.ApplyEditedTables(True, 0, 0, 0, 0, "")
    fatal, errors, log = a[0], a[1], str(a[4])
    if a[-1] != 0 or fatal or errors:
        raise GenError(f"„{key}”: aplicarea a eșuat ({fatal} erori fatale, {errors} erori). {log[-500:]}")
    return log


def _cancel(t) -> None:
    try:
        t.CancelTableEditing()
    except Exception:
        pass


def upsert_entities(sap, key: str, name_field: str, new_rows: list[dict], extra_fields: list[str] | None = None) -> None:
    """Adauga entitati (grupuri de randuri cu acelasi nume) la tabel; cele cu nume existent sunt inlocuite integral.
    `extra_fields` = campuri de trimis in plus fata de cele deja prezente (daca tabelul nu le contine inca)."""
    version, fields, rows = read_table(sap, key)
    names = {r[name_field] for r in new_rows}
    missing = [f for f in {f for r in new_rows for f in r} if f not in fields]
    if missing:
        raise GenError(f"„{key}”: câmpuri necunoscute {', '.join(sorted(missing))} (disponibile: {', '.join(fields)}).")
    keep = [r for r in rows if r.get(name_field) not in names]
    write_table(sap, key, version, fields, keep + [{f: r.get(f, "") for f in fields} for r in new_rows])


def update_rows(sap, key: str, changes: dict[str | None, dict], key_field: str | None) -> int:
    """Modifica campuri in randurile identificate prin `key_field` (None = tabel cu un singur rand). Intoarce nr. de randuri modificate."""
    version, fields, rows = read_table(sap, key)
    unknown = sorted({f for c in changes.values() for f in c} - set(fields))
    if unknown:
        raise GenError(f"„{key}”: câmpuri necunoscute {', '.join(unknown)}.")
    n = 0
    for r in rows:
        c = changes.get(r[key_field] if key_field else None)
        if c:
            diff = {f: v for f, v in c.items() if str(r[f]) != str(v)}
            r.update(diff)
            n += bool(diff)
    if n:
        write_table(sap, key, version, fields, rows)
    return n


def read_display(sap, key: str) -> list[dict]:
    """Tabela de afisare (rezultate etc.) ca lista de dict; goala daca nu exista."""
    r = sap.DatabaseTables.GetTableForDisplayArray(key, [""], "All", 0, [], 0, [])
    if r[-1] != 0 or not r[3]:
        return []
    fields, n, data = list(r[2]), int(r[3]), list(r[4])
    return [dict(zip(fields, data[i * len(fields):(i + 1) * len(fields)])) for i in range(n)]
