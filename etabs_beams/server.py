"""Backend local pentru GUI: FastAPI peste modulul etabs_beams.

Toate apelurile ETABS (COM) ruleaza intr-un singur fir dedicat (COM cere acelasi apartament de fire)."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import comtypes
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import time
from datetime import datetime

from .analysis import analysis_state, run_analysis
from .api import check_model, list_sections
from .checker import report
from .connection import EtabsSession, EtabsError
from .models import Tolerances

_pool = ThreadPoolExecutor(max_workers=1, initializer=comtypes.CoInitialize)
_session: EtabsSession | None = None
# Starea analizei pornite de aplicatie: citita fara COM (analiza blocheaza firul COM cat dureaza)
_ANALYSIS: dict = {"state": "idle", "started": 0.0, "duration": None, "message": "", "by": ""}


def run(fn, *args, **kw):
    """Executa fn in firul COM dedicat."""
    return _pool.submit(fn, *args, **kw).result()


def _get_session() -> EtabsSession:
    """(in firul COM) atasare la ETABS; reatasare daca instanta s-a schimbat."""
    global _session
    if _session is not None:
        try:
            _session.model.GetModelFilename()
            return _session
        except Exception:
            _session = None
    try:
        _session = EtabsSession.attach()
    except EtabsError as e:
        raise HTTPException(503, str(e))
    return _session


class CheckRequest(BaseModel):
    belt_sections: list[str] = Field(default_factory=list)


class SelObject(BaseModel):
    type: str          # frame | wall
    name: str


class SelectRequest(BaseModel):
    objects: list[SelObject]
    clear: bool = True


app = FastAPI(title="ETABS Beams")


@app.get("/api/status")
def status():
    def _f():
        try:
            s = _get_session()
            return {"connected": True, "file": s.filename, "analyzed": s.analyzed}
        except HTTPException as e:
            return {"connected": False, "error": e.detail}
    return run(_f)


@app.get("/api/sections")
def sections():
    return run(lambda: [{"name": n, "count": c} for n, c in list_sections(_get_session())])


@app.post("/api/check")
def check(req: CheckRequest):
    def _f():
        s = _get_session()
        md, issues, extras = check_model(s, Tolerances(belt_sections=req.belt_sections))
        return report(md, issues, extras)
    return run(_f)


@app.post("/api/select")
def select(req: SelectRequest):
    """Selecteaza obiectele in ETABS (si reimprospateaza vederea)."""
    def _f():
        sap = _get_session().model
        if req.clear:
            sap.SelectObj.ClearSelection()
        done, failed = 0, []
        for o in req.objects:
            try:
                if o.type == "frame":
                    r = sap.FrameObj.SetSelected(o.name, True)
                elif o.type in ("wall", "area"):
                    r = sap.AreaObj.SetSelected(o.name, True)
                elif o.type == "joint":
                    r = sap.PointObj.SetSelected(o.name, True)
                else:
                    continue
                done += 1 if r == 0 else 0
                if r != 0:
                    failed.append(o.name)
            except Exception:
                failed.append(o.name)
        sap.View.RefreshView(0, False)
        return {"selected": done, "failed": failed}
    return run(_f)


# ------------------------------------------------------------------ verificator (nerulat / rulat)
from .verifier import Sidecar, Snapshot, catalog, run as run_verifier   # noqa: E402
from .verifier.history import compare as compare_runs, list_runs, record_run   # noqa: E402
from .verifier.report import build_html   # noqa: E402

_V: dict = {"snap": None, "key": None, "store": None, "store_file": None, "sections": None, "sections_file": None, "results": {}, "results_file": None}


def _store() -> Sidecar:
    s = _get_session()
    if _V["store"] is None or _V["store_file"] != s.filename:
        _V["store"], _V["store_file"] = Sidecar(s.filename), s.filename
    return _V["store"]


def _stories() -> list[str]:
    st = _snapshot().table("Story Definitions")
    return [str(x) for x in st["Story"]] if not st.empty else []


def _sections(s: EtabsSession, refresh: bool = False) -> list[dict]:
    """Sectiunile barelor (lent: ~2 s) - calculate o data per model."""
    if refresh or _V["sections"] is None or _V["sections_file"] != s.filename:
        _V["sections"] = [{"name": n, "count": c} for n, c in list_sections(s)]
        _V["sections_file"] = s.filename
    return _V["sections"]


def _snapshot(reload: bool = False) -> Snapshot:
    s = _get_session()
    belts = _store().belts
    key = (s.filename, s.analyzed, tuple(belts["sections"]) if belts.get("has") else ())
    if reload or _V["snap"] is None or _V["key"] != key:
        _V["snap"], _V["key"] = Snapshot(s, list(key[2])), key
    return _V["snap"]


class RunRequest(BaseModel):
    phase: str | None = None            # "pre" | "post"
    zones: list[str] | None = None
    ids: list[str] | None = None
    reload: bool = False


class SettingsRequest(BaseModel):
    belts: dict | None = None           # {"has": bool|None, "sections": [..]}
    params: dict | None = None          # {"<verificare>.<parametru>": valoare}
    project: dict | None = None         # parametrii proiectului: ag, q, ...


class WaiveRequest(BaseModel):
    keys: list[str]
    note: str = ""


class ManualRequest(BaseModel):
    id: str
    done: bool
    note: str = ""


@app.get("/api/v/catalog")
def v_catalog():
    return catalog()


@app.get("/api/v/state")
def v_state():
    def _f():
        s = _get_session()
        st = _store()
        return {"file": s.filename, "analyzed": s.analyzed, "sidecar": str(st.path),
                "belts": st.belts, "params": st.params, "manual": st.manual(), "project": st.project,
                "stories": _stories(),
                "waivers": len(st.data.get("waivers", [])),
                "sections": _sections(s)}
    return run(_f)


@app.post("/api/v/run")
def v_run(req: RunRequest):
    def _f():
        if req.phase == "post" and _store().project.get("auto_analiza") == "da":      # optiune: ruleaza singura analiza daca lipsesc rezultatele
            if analysis_state(_get_session(), _nonlinear())["needs_analysis"]:
                _do_analysis("auto")
        snap = _snapshot(req.reload)
        if req.reload:
            _sections(_get_session(), refresh=True)
        store = _store()
        results = run_verifier(snap, store, req.phase, req.zones, req.ids)
        if _V["results_file"] != snap.model_file:
            _V["results"], _V["results_file"] = {}, snap.model_file
        _V["results"].update({r["id"]: r for r in results})
        if req.phase and not req.zones and not req.ids:                 # rulare completa a unei faze -> istoric
            record_run(store, req.phase, results, snap.model_file, snap.analyzed)
        return {"file": snap.model_file, "analyzed": snap.analyzed, "results": results}
    return run(_f)


@app.get("/api/v/history")
def v_history():
    return run(lambda: list_runs(_store()))


@app.get("/api/v/compare")
def v_compare(a: str | None = None, b: str | None = None, phase: str | None = None):
    res = run(lambda: compare_runs(_store(), a, b, phase))
    if res is None:
        raise HTTPException(404, "Nu există rulări în istoric.")
    return res


@app.get("/api/v/report")
def v_report():
    """Raport HTML (romana) cu ultimele rezultate; se salveaza si o copie langa fisierul .EDB."""
    from datetime import datetime
    from fastapi.responses import Response

    def _f():
        s = _get_session()
        store = _store()
        if not _V["results"] or _V["results_file"] != s.filename:
            return None
        results = _V["results"]
        phases = {r["phase"] for r in results.values()}
        comp = compare_runs(store, phase="post" if phases == {"post"} else "pre")
        body = build_html(catalog=catalog(), results=results, model_file=s.filename, analyzed=s.analyzed,
                          project=store.project, belts=store.belts, params=store.params, manual=store.manual(),
                          waivers=store.data.get("waivers", []), comparison=comp, analysis_log=store.data.get("analysis_log"))
        saved = ""
        try:
            path = store.path.with_name(store.path.name.replace(".checks.json", ".raport.html"))
            path.write_text(body, encoding="utf-8")
            saved = str(path)
        except OSError:
            pass
        return body, saved

    out = run(_f)
    if out is None:
        raise HTTPException(409, "Nu există rezultate: rulează întâi verificările.")
    body, saved = out
    name = os.path.basename(_V["results_file"] or "model").rsplit(".", 1)[0]
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return Response(body, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="raport_{name}_{stamp}.html"', "X-Saved-To": saved.encode("ascii", "ignore").decode()})


def _nonlinear() -> bool:
    return _store().project.get("analiza_neliniara") == "da"


def _do_analysis(trigger: str) -> dict:
    """(in firul COM) Ruleaza analiza si inregistreaza rezultatul; invalideaza snapshot-ul."""
    s = _get_session()
    _ANALYSIS.update(state="running", started=time.time(), duration=None, by=trigger, message="Se rulează analiza în ETABS…")
    try:
        res = run_analysis(s, _nonlinear())
    except Exception as e:
        _ANALYSIS.update(state="error", duration=round(time.time() - _ANALYSIS["started"], 1), message=str(e))
        raise
    _ANALYSIS.update(state="done", duration=res["seconds"], message=f"Analiza s-a terminat în {res['seconds']:.0f} s.")
    _V["snap"], _V["key"] = None, None
    _V["results"] = {}
    store = _store()
    log = store.data.setdefault("analysis_log", [])
    log.append({"date": datetime.now().isoformat(timespec="seconds"), "by": trigger, "seconds": res["seconds"],
                "unfinished_after": res["unfinished_after"]})
    del log[:-20]
    store.save()
    return res


@app.get("/api/v/analyze/status")
def v_analyze_status():
    st = dict(_ANALYSIS)
    if st["state"] == "running":
        st["elapsed"] = round(time.time() - st["started"], 1)
    return st


@app.post("/api/v/analyze")
def v_analyze():
    """Porneste analiza in fundal (raspunde imediat); progresul se citeste din /api/v/analyze/status."""
    if _ANALYSIS["state"] == "running":
        raise HTTPException(409, "O analiză este deja în curs.")
    _ANALYSIS.update(state="running", started=time.time(), duration=None, by="manual", message="Se pornește analiza…")
    _pool.submit(_do_analysis, "manual")
    return {"started": True}


@app.get("/api/v/analyze/needed")
def v_analyze_needed():
    return run(lambda: analysis_state(_get_session(), _nonlinear()))


# ---------------------------------------------------------------- reparatii cu un click
class FixRequest(BaseModel):
    fix: str
    args: dict
    analyze: bool = False               # dupa aplicare, ruleaza analiza (fara cazurile neliniare, daca nu sunt cerute)


def _fix_def(fid: str):
    from .verifier.fixes import FIXES
    if fid not in FIXES:
        raise HTTPException(404, f"Reparație necunoscută: {fid}")
    return FIXES[fid]


@app.post("/api/v/fix/preview")
def v_fix_preview(req: FixRequest):
    fx = _fix_def(req.fix)
    return run(lambda: {"title": fx.title, **fx.preview(_get_session(), req.args)})


@app.post("/api/v/fix/apply")
def v_fix_apply(req: FixRequest):
    fx = _fix_def(req.fix)

    def _f():
        s = _get_session()
        changes = fx.preview(s, req.args)["changes"]
        undo = fx.apply(s, req.args)
        _V["snap"], _V["key"], _V["results"] = None, None, {}
        store = _store()
        log = store.data.setdefault("fix_log", [])
        entry = {"id": len(log) + 1, "date": datetime.now().isoformat(timespec="seconds"), "fix": req.fix, "title": fx.title,
                 "args": req.args, "changes": changes, "undo": undo, "undone": False}
        log.append(entry)
        del log[:-50]
        store.save()
        return entry
    entry = run(_f)
    if req.analyze and _ANALYSIS["state"] != "running":
        _ANALYSIS.update(state="running", started=time.time(), duration=None, by="fix", message="Se pornește analiza…")
        _pool.submit(_do_analysis, "fix")
    return {"id": entry["id"], "changes": entry["changes"], "analyzing": bool(req.analyze)}


@app.post("/api/v/fix/undo/{entry_id}")
def v_fix_undo(entry_id: int):
    def _f():
        store = _store()
        entry = next((e for e in store.data.get("fix_log", []) if e["id"] == entry_id), None)
        if entry is None or entry["undone"]:
            raise HTTPException(404, "Reparația nu există sau a fost deja anulată.")
        _fix_def(entry["fix"]).undo(_get_session(), entry["undo"])
        entry["undone"] = True
        _V["snap"], _V["key"], _V["results"] = None, None, {}
        store.save()
        return {"undone": entry_id}
    return run(_f)


@app.get("/api/v/fix/log")
def v_fix_log():
    return run(lambda: [{k: v for k, v in e.items() if k != "undo"} for e in _store().data.get("fix_log", [])])


@app.put("/api/v/settings")
def v_settings(req: SettingsRequest):
    def _f():
        st = _store()
        if req.belts is not None:
            st.set_belts(req.belts.get("has"), list(req.belts.get("sections", [])))
        if req.params:
            st.set_params(req.params)
        if req.project is not None:
            st.set_project(req.project)
        return {"belts": st.belts, "params": st.params, "project": st.project}
    return run(_f)


@app.post("/api/v/waive")
def v_waive(req: WaiveRequest):
    return run(lambda: (_store().waive(req.keys, req.note), {"ok": True})[1])


@app.post("/api/v/unwaive")
def v_unwaive(req: WaiveRequest):
    return run(lambda: (_store().unwaive(req.keys), {"ok": True})[1])


@app.post("/api/v/manual")
def v_manual(req: ManualRequest):
    return run(lambda: (_store().set_manual(req.id, req.done, req.note), {"ok": True})[1])


_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = os.path.join(_DIST, path)
        return FileResponse(f if path and os.path.isfile(f) else os.path.join(_DIST, "index.html"))


def serve(port: int = 8765):
    import uvicorn
    print(f"GUI: http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
