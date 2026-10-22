"""Istoricul rularilor (salvat langa .EDB) si compararea a doua rulari."""
from __future__ import annotations

from datetime import datetime

from .store import Sidecar

MAX_RUNS = 30
MAX_KEYS = 400


def _active(results: list[dict]):
    for r in results:
        for f in r["findings"]:
            if not f["waived"]:
                yield r, f


def record_run(store: Sidecar, phase: str, results: list[dict], model_file: str, analyzed: bool) -> dict:
    """Adauga in istoric o rulare completa a unei faze (constatarile active, fara cele justificate)."""
    counts = {"error": 0, "warning": 0, "info": 0}
    findings = []
    for r, f in _active(results):
        counts[f["severity"]] += 1
        findings.append({"check": r["id"], "severity": f["severity"], "message": f["message"][:300], "keys": f["keys"][:MAX_KEYS]})
    hist = store.data.setdefault("history", [])
    stamp = datetime.now().isoformat(timespec="seconds")
    same = sum(1 for e in hist if e["id"] == stamp or e["id"].startswith(stamp + "#"))
    entry = {
        "id": stamp if not same else f"{stamp}#{same + 1}",
        "phase": phase, "file": model_file, "analyzed": analyzed,
        "counts": counts,
        "waived": sum(1 for r in results for f in r["findings"] if f["waived"]),
        "checks": {r["id"]: r["status"] for r in results},
        "findings": findings,
    }
    hist.append(entry)
    del hist[:-MAX_RUNS]
    store.save()
    return entry


def list_runs(store: Sidecar) -> list[dict]:
    return [{k: e[k] for k in ("id", "phase", "analyzed", "counts", "waived")} for e in store.data.get("history", [])]


def _keys(entry: dict) -> dict[str, tuple[str, str]]:
    """{cheie_obiect: (verificare, mesaj)} pentru constatarile active ale unei rulari."""
    out = {}
    for f in entry["findings"]:
        for k in f["keys"]:
            out[k] = (f["check"], f["message"])
    return out


def compare(store: Sidecar, a_id: str | None = None, b_id: str | None = None, phase: str | None = None) -> dict | None:
    """Compara doua rulari (implicit ultimele doua ale aceleiasi faze). Intoarce rezolvate / noi / ramase pe verificare."""
    hist = store.data.get("history", [])
    if b_id:
        b = next((e for e in hist if e["id"] == b_id), None)
    else:
        runs = [e for e in hist if not phase or e["phase"] == phase]
        b = runs[-1] if runs else None
    if b is None:
        return None
    if a_id:
        a = next((e for e in hist if e["id"] == a_id), None)
    else:
        before = hist[: hist.index(b)]
        prev = [e for e in before if e["phase"] == b["phase"]]
        a = prev[-1] if prev else None
    if a is None:
        return {"a": None, "b": b["id"], "phase": b["phase"], "checks": [], "totals": {"rezolvate": 0, "noi": 0, "ramase": len(_keys(b))}}
    ka, kb = _keys(a), _keys(b)
    per: dict[str, dict] = {}

    def slot(check):
        return per.setdefault(check, {"check": check, "rezolvate": [], "noi": [], "ramase": 0})

    for k, (chk, msg) in ka.items():
        if k not in kb:
            slot(chk)["rezolvate"].append(k)
    for k, (chk, msg) in kb.items():
        if k in ka:
            slot(chk)["ramase"] += 1
        else:
            slot(chk)["noi"].append(k)
    # statusuri schimbate
    changed = [{"check": c, "inainte": a["checks"].get(c), "acum": s} for c, s in b["checks"].items() if a["checks"].get(c) not in (None, s)]
    rows = [{"check": v["check"], "rezolvate": len(v["rezolvate"]), "noi": len(v["noi"]), "ramase": v["ramase"],
             "exemple_rezolvate": v["rezolvate"][:5], "exemple_noi": v["noi"][:5]} for v in per.values() if v["rezolvate"] or v["noi"]]
    return {"a": a["id"], "b": b["id"], "phase": b["phase"], "checks": rows, "status_schimbat": changed,
            "totals": {"rezolvate": sum(r["rezolvate"] for r in rows), "noi": sum(r["noi"] for r in rows),
                       "ramase": sum(v["ramase"] for v in per.values())}}
