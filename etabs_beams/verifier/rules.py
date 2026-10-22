"""Regulile din documentul de verificari (parsate din docs/*.md) + harta pe zone/faze/clase."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "Verificari si reguli ETABS Inainte de rulare.md"

# (id, titlu) - ordinea = ordinea tab-urilor in GUI
ZONES = [
    ("z1", "Materiale, secțiuni, unități"),
    ("z2", "Rezemare și fundații"),
    ("z3", "Planșee, diafragme, goluri"),
    ("z4", "Elemente structurale"),
    ("z5", "Geometrie și mesh"),
    ("z6", "Încărcări și masă"),
    ("z7", "Seism și combinații"),
    ("z8", "Setări de analiză"),
    ("z9", "Multi-tower"),
]

# regula -> (zona, faze, clasa de automatizare)   faze: "pre" = nerulat, "post" = rulat
RULE_META: dict[int, tuple[str, tuple[str, ...], str]] = {
    1: ("z1", ("pre",), "A"),
    2: ("z2", ("pre", "post"), "C"),
    3: ("z3", ("pre", "post"), "C"),
    4: ("z4", ("pre",), "C"),
    5: ("z5", ("pre", "post"), "A"),
    6: ("z6", ("pre", "post"), "B"),
    7: ("z6", ("pre",), "B"),
    8: ("z7", ("pre", "post"), "B"),
    9: ("z7", ("pre",), "B"),
    10: ("z8", ("pre", "post"), "A"),
    11: ("z4", ("pre",), "C"),
    12: ("z7", ("pre", "post"), "C"),
    13: ("z4", ("pre",), "A"),
    14: ("z4", ("pre",), "A"),
    15: ("z1", ("pre",), "A"),
    16: ("z3", ("pre",), "C"),
    17: ("z6", ("pre",), "B"),
    18: ("z8", ("pre",), "B"),
    19: ("z1", ("pre",), "A"),
    20: ("z7", ("pre", "post"), "B"),
    21: ("z8", ("pre", "post"), "A"),
    22: ("z6", ("pre", "post"), "A"),
    23: ("z4", ("pre",), "B"),
    24: ("z6", ("pre",), "C"),
    25: ("z4", ("pre", "post"), "A"),
    26: ("z9", ("pre",), "B"),
    27: ("z9", ("pre",), "B"),
    28: ("z9", ("pre", "post"), "B"),
    29: ("z7", ("pre", "post"), "C"),
    30: ("z9", ("pre", "post"), "C"),
}


@dataclass
class Rule:
    number: int
    title: str
    what: str = ""
    how: str = ""
    alarms: str = ""
    notes: str = ""
    zone: str = ""
    phases: tuple[str, ...] = ()
    cls: str = "A"
    extra: dict = field(default_factory=dict)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


_LABELS = {
    "ce se verifica": "what",
    "cum se verifica": "how",
    "semnale de alarma": "alarms",
    "observatie": "notes",
}


@lru_cache(maxsize=1)
def load_rules() -> dict[int, Rule]:
    """Parseaza documentul de reguli. Daca fisierul lipseste, intoarce regulile fara text."""
    rules: dict[int, Rule] = {}
    text = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    chunks = re.split(r"^###\s+(\d+)\.\s*(.+)$", text, flags=re.M)
    parsed = {}
    for i in range(1, len(chunks), 3):
        num, title, body = int(chunks[i]), chunks[i + 1].strip(), chunks[i + 2]
        r = Rule(num, title)
        for m in re.finditer(r"^\s*\*\s*\*\*(.+?):\*\*\s*(.*)$", body, flags=re.M):
            key = _LABELS.get(_norm(m.group(1)))
            if key:
                setattr(r, key, (getattr(r, key) + " " + m.group(2).strip()).strip())
        parsed[num] = r
    for num, (zone, phases, cls) in RULE_META.items():
        r = parsed.get(num) or Rule(num, f"Regula {num}")
        r.zone, r.phases, r.cls = zone, phases, cls
        rules[num] = r
    return rules
