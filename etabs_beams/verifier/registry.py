"""Registrul de verificari: fiecare verificare e o functie pura peste un Snapshot, legata de o regula din document."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

from ..refs import resolve
from .rules import RULE_META, load_rules
from .snapshot import Snapshot
from .store import Sidecar

ERROR, WARNING, INFO = "error", "warning", "info"
_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}


@dataclass
class Param:
    name: str
    default: float | str | bool | None
    label: str
    unit: str = ""
    kind: str = "number"          # number | choice | story
    options: list = field(default_factory=list)


@dataclass
class Finding:
    severity: str
    message: str
    objects: list = field(default_factory=list)      # [(tip, nume)] - frame | wall | material | loadpattern | ...
    data: dict = field(default_factory=dict)
    total: int = 0                                   # numarul real de obiecte (daca lista e trunchiata)


@dataclass
class CheckDef:
    id: str
    rule: int
    phase: str                  # "pre" | "post"
    title: str
    fn: Callable
    params: list[Param] = field(default_factory=list)

    @property
    def zone(self) -> str:
        return RULE_META[self.rule][0]


@dataclass
class Ctx:
    snap: Snapshot
    values: dict                # parametrii verificarii -> valori efective
    project: dict = field(default_factory=dict)     # parametrii proiectului (Setari): ag, q, ... (None = nesetat)

    def p(self, name: str):
        return self.values[name]

    def proj(self, name: str):
        return self.project.get(name)

    def missing(self, *names: str) -> list[str]:
        return [n for n in names if self.project.get(n) in (None, "", [])]

    # ---- infrastructura (subsoluri)
    def stories(self) -> list[str]:
        """Numele nivelurilor din model (unice), de sus in jos."""
        st = self.snap.table("Story Definitions")
        return list(dict.fromkeys(str(s) for s in st["Story"])) if not st.empty else []

    def towers(self) -> list[str]:
        st = self.snap.table("Story Definitions")
        return list(dict.fromkeys(str(t) for t in st["Tower"])) if not st.empty and "Tower" in st.columns else []

    def multi_tower(self) -> bool:
        return len(self.towers()) > 1

    def story_id(self, tower: str, story: str) -> str:
        """Identificatorul nivelului in tabelele de rezultate: „Tn-Nivel” la modele cu mai multe turnuri, altfel numele simplu."""
        return f"{tower}-{story}" if self.multi_tower() else story

    def story_ids(self, names) -> set[str]:
        """Toate formele sub care apar in tabele niveluri cu numele simple date (simplu si cu prefix de turn)."""
        out = set(names)
        for t in self.towers():
            out |= {f"{t}-{n}" for n in names}
        return out

    def plain_story(self, story_id: str) -> str:
        for t in self.towers():
            if story_id.startswith(f"{t}-"):
                return story_id[len(t) + 1:]
        return story_id

    def tower_of(self, story_id: str) -> str | None:
        for t in self.towers():
            if story_id.startswith(f"{t}-"):
                return t
        return self.towers()[0] if len(self.towers()) == 1 else None

    def basement_stories(self) -> list[str] | None:
        """Nivelurile de subsol: lista (posibil goala = fara subsol) sau None cand utilizatorul nu a precizat."""
        stories = self.stories()
        mode, sel, ground = self.project.get("basement"), self.project.get("basement_stories"), self.project.get("ground_story")
        if mode == "nu":
            return []
        if sel:
            return [s for s in stories if s in set(sel)]
        if ground in stories:
            return stories[stories.index(ground) + 1:]
        return None

    def ground_story(self) -> str | None:
        """Primul nivel peste ±0.00: indicat sau dedus din subsoluri; la model doar suprastructura = cel mai de jos nivel."""
        stories = self.stories()
        ground = self.project.get("ground_story")
        if ground in stories:
            return ground
        bs = self.basement_stories()
        if bs:
            top = min(stories.index(s) for s in bs)
            return stories[top - 1] if top > 0 else None
        if bs == [] and stories:
            return stories[-1]
        return None


CHECKS: dict[str, CheckDef] = {}


def check(id: str, rule: int, title: str, phase: str = "pre", params: list[Param] | None = None):
    """Decorator: inregistreaza o verificare. Functia primeste Ctx si intoarce o lista de Finding."""
    def deco(fn):
        CHECKS[id] = CheckDef(id, rule, phase, title, fn, params or [])
        return fn
    return deco


def param_key(check_id: str, name: str) -> str:
    return f"{check_id}.{name}"


def effective_params(cd: CheckDef, store: Sidecar) -> dict:
    return {p.name: store.params.get(param_key(cd.id, p.name), p.default) for p in cd.params}


def project_values(store: Sidecar) -> dict:
    from .params import PROJECT_PARAMS
    vals = {p.name: p.default for p in PROJECT_PARAMS}
    vals.update({k: v for k, v in store.data.get("project", {}).items() if v not in (None, "", [])})
    return vals


def finding_keys(check_id: str, f: Finding) -> list[str]:
    if f.objects:
        return [f"{check_id}|{o[0]}:{o[1]}" for o in f.objects]
    return [f"{check_id}|#{f.message}"]


def _object_dict(snap: Snapshot, o: tuple) -> dict:
    """(tip, nume[, extra]) -> dict cu nume unic, eticheta, etaj etc. Barele/peretii se rezolva din model."""
    kind, name = o[0], o[1]
    if len(o) > 2 and isinstance(o[2], dict):
        return {"type": kind, "name": name, **o[2]}
    model = getattr(snap, "loaded_model", lambda: None)()      # nu citim modelul doar pentru etichete
    if kind in ("frame", "wall") and model is not None:
        return resolve(model, (kind, name))
    return {"type": kind, "name": name}


def run(snap: Snapshot, store: Sidecar, phase: str | None = None, zones: list[str] | None = None,
        ids: list[str] | None = None) -> list[dict]:
    """Ruleaza verificarile selectate si intoarce rezultatele (JSON-serializabile)."""
    waived = store.waived_keys()
    out = []
    for cd in CHECKS.values():
        if (phase and cd.phase != phase) or (zones and cd.zone not in zones) or (ids and cd.id not in ids):
            continue
        t0 = time.time()
        res = {"id": cd.id, "rule": cd.rule, "phase": cd.phase, "zone": cd.zone, "title": cd.title,
               "findings": [], "error": None}
        if cd.phase == "post" and not getattr(snap, "analyzed", True):
            res.update(findings=[], status="skipped", seconds=0.0)
            out.append(res)
            continue
        try:
            findings = cd.fn(Ctx(snap, effective_params(cd, store), project_values(store))) or []
        except Exception as e:                       # o verificare defecta nu opreste restul
            findings, res["error"] = [], f"{type(e).__name__}: {e}"
            res["trace"] = traceback.format_exc(limit=3)
        for f in findings:
            keys = finding_keys(cd.id, f)
            is_waived = all(k in waived for k in keys)
            res["findings"].append({
                "severity": f.severity, "message": f.message, "count": f.total or len(f.objects), "data": f.data,
                "objects": [_object_dict(snap, o) for o in f.objects[:200]],
                "keys": keys, "waived": is_waived, "waiver_note": waived.get(keys[0], "") if is_waived else "",
            })
        res["seconds"] = round(time.time() - t0, 2)
        res["status"] = _status(res)
        out.append(res)
    return out


def _status(res: dict) -> str:
    if res["error"]:
        return "failed"
    active = [f for f in res["findings"] if not f["waived"]]
    if not active:
        return "waived" if res["findings"] else "ok"
    return min((f["severity"] for f in active), key=lambda s: _ORDER[s])


def catalog() -> dict:
    """Zone, reguli (cu textul din document), verificari implementate si parametrii lor."""
    from .manual import MANUAL_ITEMS
    from .rules import ZONES
    rules = load_rules()
    from .params import PROJECT_PARAMS
    return {
        "zones": [{"id": z, "title": t} for z, t in ZONES],
        "project_params": [vars(p) for p in PROJECT_PARAMS],
        "rules": [{
            "number": r.number, "title": r.title, "what": r.what, "how": r.how, "alarms": r.alarms,
            "notes": r.notes, "zone": r.zone, "phases": list(r.phases), "class": r.cls,
            "checks": [{"id": c.id, "phase": c.phase, "title": c.title,
                        "params": [vars(p) for p in c.params]} for c in CHECKS.values() if c.rule == r.number],
            "manual": [m for m in MANUAL_ITEMS if m["rule"] == r.number],
        } for r in rules.values()],
    }
