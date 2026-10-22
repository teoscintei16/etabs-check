"""Salvare persistenta langa fisierul .EDB: justificari, liste de control, setari, centuri."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

VERSION = 1
FALLBACK_DIR = Path(__file__).resolve().parents[2] / "data"


def sidecar_path(model_file: str) -> Path:
    """<model>.EDB.checks.json langa model; daca modelul nu are cale sau folderul nu e scriptibil -> data/."""
    if model_file:
        p = Path(model_file + ".checks.json")
        if os.access(p.parent, os.W_OK):
            return p
        name = Path(model_file).name
    else:
        name = "model_nesalvat.EDB"
    FALLBACK_DIR.mkdir(exist_ok=True)
    return FALLBACK_DIR / (name + ".checks.json")


def _empty() -> dict:
    return {"version": VERSION, "belts": {"has": None, "sections": []}, "params": {}, "waivers": [], "manual": {}}


class Sidecar:
    def __init__(self, model_file: str):
        self.path = sidecar_path(model_file)
        self.data = _empty()
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass                      # fisier corupt: pornim curat (nu il suprascriem pana la prima salvare)

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- setari
    @property
    def belts(self) -> dict:
        return self.data.setdefault("belts", {"has": None, "sections": []})

    def set_belts(self, has: bool | None, sections: list[str]) -> None:
        self.data["belts"] = {"has": has, "sections": sections}
        self.save()

    @property
    def project(self) -> dict:
        return self.data.setdefault("project", {})

    def set_project(self, values: dict) -> None:
        for k, v in values.items():
            if v in (None, "", []):
                self.project.pop(k, None)
            else:
                self.project[k] = v
        self.save()

    @property
    def params(self) -> dict:
        return self.data.setdefault("params", {})

    def set_params(self, values: dict) -> None:
        self.params.update(values)
        self.save()

    # ---- justificari
    def waived_keys(self) -> dict[str, str]:
        return {w["key"]: w.get("note", "") for w in self.data.get("waivers", [])}

    def waive(self, keys: list[str], note: str) -> None:
        cur = {w["key"]: w for w in self.data.setdefault("waivers", [])}
        for k in keys:
            cur[k] = {"key": k, "note": note, "date": datetime.now().isoformat(timespec="seconds")}
        self.data["waivers"] = list(cur.values())
        self.save()

    def unwaive(self, keys: list[str]) -> None:
        drop = set(keys)
        self.data["waivers"] = [w for w in self.data.get("waivers", []) if w["key"] not in drop]
        self.save()

    # ---- liste de control (clasa D)
    def manual(self) -> dict:
        return self.data.setdefault("manual", {})

    def set_manual(self, item_id: str, done: bool, note: str = "") -> None:
        if done:
            self.manual()[item_id] = {"done": True, "note": note, "date": datetime.now().isoformat(timespec="seconds")}
        else:
            self.manual().pop(item_id, None)
        self.save()
