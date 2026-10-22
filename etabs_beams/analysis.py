"""Rularea analizei din cod (optional): detectia lipsei rezultatelor si Analyze.RunAnalysis.

Cazurile neliniare (static neliniar / pushover, istorie in timp neliniara, dinamic neliniar) dureaza foarte mult:
implicit sunt excluse din rulare si din decizia „are nevoie de analiza”; se includ doar la cerere (`nonlinear=True`)."""
from __future__ import annotations

import time

from .connection import EtabsError, ok

NONLINEAR_TYPES = {2, 6, 8}          # eCaseType: NonlinearStatic, NonlinearHistory, NonlinearDynamic


def nonlinear_cases(sap) -> set[str]:
    """Numele cazurilor de incarcare neliniare (multime goala daca tipurile nu pot fi citite)."""
    lc = getattr(sap, "LoadCases", None)
    if lc is None:
        return set()
    out = set()
    try:
        for n in ok(sap.Analyze.GetCaseStatus())[1]:
            if ok(lc.GetTypeOAPI_1(n))[0] in NONLINEAR_TYPES:
                out.add(n)
    except Exception:
        return set()
    return out


def analysis_state(session, nonlinear: bool = False) -> dict:
    """Starea analizei: modelul e blocat (analizat)? Care cazuri marcate „Run” nu au rezultate?
    Cazurile neliniare nu conteaza decat daca `nonlinear` e True."""
    sap = session.model
    locked = bool(sap.GetModelIsLocked())
    st = ok(sap.Analyze.GetCaseStatus())
    flags = ok(sap.Analyze.GetRunCaseFlag())
    status = dict(zip(st[1], st[2]))
    flag = dict(zip(flags[1], flags[2]))
    skip = set() if nonlinear else nonlinear_cases(sap)
    unfinished = [n for n, f in flag.items() if f and status.get(n) != 4 and n not in skip]
    return {"analyzed": locked, "unfinished": unfinished, "needs_analysis": (not locked) or bool(unfinished),
            "cases": len(flag), "run_flagged": sum(1 for f in flag.values() if f), "skipped_nonlinear": sorted(skip & set(flag)),
            "file": session.filename}


def run_analysis(session, nonlinear: bool = False) -> dict:
    """Ruleaza analiza (cazurile marcate „Run” in model, fara cele neliniare daca `nonlinear` e False).
    Blocheaza pana la final. Modelul trebuie sa aiba cale de fisier. Marcajele „Run” ale cazurilor neliniare se
    dezactiveaza doar pe durata analizei si se refac la loc."""
    sap = session.model
    if not session.filename:
        raise EtabsError("Modelul nu are un fișier asociat: salvează-l o dată în ETABS înainte de analiză.")
    before = analysis_state(session, nonlinear)
    skipped = []
    if not nonlinear:
        flags = ok(sap.Analyze.GetRunCaseFlag())
        on = dict(zip(flags[1], flags[2]))
        skipped = [n for n in nonlinear_cases(sap) if on.get(n)]
    t0 = time.time()
    try:
        for n in skipped:
            ok(sap.Analyze.SetRunCaseFlag(n, False))
        code = sap.Analyze.RunAnalysis()
    finally:
        for n in skipped:
            sap.Analyze.SetRunCaseFlag(n, True)
    seconds = time.time() - t0
    if code != 0:
        raise EtabsError(f"Analiza a eșuat (cod {code}). Verifică mesajele de analiză din ETABS.")
    after = analysis_state(session, nonlinear)
    return {"seconds": round(seconds, 1), "cases_run": before["unfinished"] or before["cases"], "unfinished_after": after["unfinished"],
            "analyzed": after["analyzed"], "skipped_nonlinear": skipped}
