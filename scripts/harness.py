"""Ajutoare comune pentru scripturile de testare incrucisata: creatorul de modele (8766) si verificatorul (8765), prin HTTP (fara dependente)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

CREATOR = "http://127.0.0.1:8766"
CHECK = "http://127.0.0.1:8765"


def call(base: str, path: str, body=None, timeout: int = 900, method: str | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except ValueError:
            pass
        raise RuntimeError(f"{path}: {e.code} {detail}") from e


def build(spec: dict) -> dict:
    """Creeaza modelul (instanta ETABS trebuie sa fie deschisa din creator)."""
    return call(CREATOR, "/api/build", {"spec": spec})


def run_check(phase: str, ids: list[str] | None = None) -> dict:
    """Ruleaza verificarile; intoarce {id_verificare: rezultat}."""
    body = {"phase": phase, "reload": True} if ids is None else {"ids": ids, "reload": True}
    return {r["id"]: r for r in call(CHECK, "/api/v/run", body)["results"]}


def analyze(timeout: int = 900) -> dict:
    """Porneste analiza (fara cazurile neliniare) si asteapta sa se termine."""
    call(CHECK, "/api/v/analyze", {})
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = call(CHECK, "/api/v/analyze/status")
        if s["state"] != "running":
            return s
        time.sleep(3)
    raise RuntimeError("analiza nu s-a terminat la timp")


def problems(results: dict, kinds=("error", "warning", "failed")) -> list[dict]:
    """Constatarile active (negajustificate) de gravitate data: [{check, severity, message, fix}]."""
    out = []
    for cid, r in results.items():
        if r["status"] == "failed":
            out.append({"check": cid, "severity": "failed", "message": r.get("error") or "", "fix": None})
        for f in r["findings"]:
            if f["severity"] in kinds and not f["waived"]:
                out.append({"check": cid, "severity": f["severity"], "message": f["message"], "fix": f.get("fix")})
    return out
