"""Rularea analizei din cod (optional): detectia lipsei rezultatelor si Analyze.RunAnalysis."""
from __future__ import annotations

import time

from .connection import EtabsError, ok


def analysis_state(session) -> dict:
    """Starea analizei: modelul e blocat (analizat)? Care cazuri marcate „Run” nu au rezultate?"""
    sap = session.model
    locked = bool(sap.GetModelIsLocked())
    st = ok(sap.Analyze.GetCaseStatus())
    flags = ok(sap.Analyze.GetRunCaseFlag())
    status = dict(zip(st[1], st[2]))
    flag = dict(zip(flags[1], flags[2]))
    unfinished = [n for n, f in flag.items() if f and status.get(n) != 4]
    return {"analyzed": locked, "unfinished": unfinished, "needs_analysis": (not locked) or bool(unfinished),
            "cases": len(flag), "run_flagged": sum(1 for f in flag.values() if f), "file": session.filename}


def run_analysis(session) -> dict:
    """Ruleaza analiza (cazurile marcate „Run” in model). Blocheaza pana la final. Modelul trebuie sa aiba cale de fisier."""
    sap = session.model
    if not session.filename:
        raise EtabsError("Modelul nu are un fișier asociat: salvează-l o dată în ETABS înainte de analiză.")
    before = analysis_state(session)
    t0 = time.time()
    code = sap.Analyze.RunAnalysis()
    seconds = time.time() - t0
    if code != 0:
        raise EtabsError(f"Analiza a eșuat (cod {code}). Verifică mesajele de analiză din ETABS.")
    after = analysis_state(session)
    return {"seconds": round(seconds, 1), "cases_run": before["unfinished"] or before["cases"], "unfinished_after": after["unfinished"],
            "analyzed": after["analyzed"]}
