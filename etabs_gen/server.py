"""Server local (FastAPI) pentru generatorul de modele ETABS: pagina simpla + endpoint-uri."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, fields
from pathlib import Path

import comtypes
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .connect import OUT_DIR, GenError, attach_if_safe, start_etabs
from .frames import CONCRETE, FrameSpec, build_frame_model, default_path

app = FastAPI(title="ETABS Model Generator")
STATIC = Path(__file__).parent / "static"
_pool = ThreadPoolExecutor(max_workers=1, initializer=comtypes.CoInitialize)   # COM ruleaza intr-un singur fir
_S: dict = {"obj": None, "models": []}


def run(fn, *a):
    try:
        return _pool.submit(fn, *a).result()
    except GenError as e:
        raise HTTPException(409, str(e)) from e


def _alive() -> bool:
    if _S["obj"] is None:
        return False
    try:
        _S["obj"].SapModel.GetPresentUnits()
        return True
    except Exception:
        _S["obj"] = None
        return False


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/defaults")
def defaults():
    return {"spec": asdict(FrameSpec()), "concrete": list(CONCRETE), "out_dir": str(OUT_DIR), "models": _S["models"]}


@app.get("/api/status")
def status():
    def _f():
        if not _alive():
            return {"open": False}
        sap = _S["obj"].SapModel
        return {"open": True, "file": sap.GetModelFilename() or "", "version": str(sap.GetVersion()[0])}
    return run(_f)


@app.post("/api/open")
def open_etabs():
    """Porneste o instanta ETABS noua (cea existenta, daca exista, ramane neatinsa)."""
    def _f():
        if _alive():
            return {"open": True, "already": True}
        t0 = time.time()
        _S["obj"] = attach_if_safe()
        if _S["obj"] is not None:
            return {"open": True, "already": True}
        _S["obj"] = start_etabs()
        return {"open": True, "already": False, "seconds": round(time.time() - t0, 1)}
    return run(_f)


class BuildRequest(BaseModel):
    spec: dict


@app.post("/api/build/frames")
def build_frames(req: BuildRequest):
    known = {f.name for f in fields(FrameSpec)}
    unknown = set(req.spec) - known
    if unknown:
        raise HTTPException(422, f"Câmpuri necunoscute: {', '.join(sorted(unknown))}")

    def _f():
        if not _alive():
            raise GenError("ETABS nu este pornit: apasă „Deschide ETABS”.")
        spec = FrameSpec(**req.spec)
        t0 = time.time()
        res = build_frame_model(_S["obj"].SapModel, spec, default_path(spec, OUT_DIR))
        res["seconds"] = round(time.time() - t0, 1)
        _S["models"].append({"file": res["file"], "objects": res["objects"], "name": spec.name})
        return res
    return run(_f)


@app.post("/api/close")
def close_etabs():
    def _f():
        if _alive():
            _S["obj"].ApplicationExit(False)
            _S["obj"] = None
        return {"open": False}
    return run(_f)


def serve(port: int = 8766) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
