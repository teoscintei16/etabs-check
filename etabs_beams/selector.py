"""Selectie de grinzi (la nivel de lant) dupa sectiune, etaj, nume, lungime."""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from .continuity import Chain


def _match(value: str, patterns: list[str]) -> bool:
    v = value.lower()
    return any(fnmatch.fnmatchcase(v, p.lower()) for p in patterns)


@dataclass
class BeamSelector:
    """Toate campurile goale = fara restrictie.

    sections / exclude_sections : sabloane (*, ?) pe numele sectiunii.
    stories / exclude_stories   : nume etaj (exact sau sablon).
    frames                      : nume ETABS sau etichete de grinzi (un lant e ales daca contine una).
    chain_ids                   : id-ul lantului = nume unice ETABS unite cu "+", ex. ["2080+2079+2078"].
    min_length / max_length     : lungimea totala a lantului [m].
    match                       : "any" - lantul e ales daca ORICE membru satisface regulile de sectiune;
                                  "all" - doar daca TOTI membrii o satisfac.
    continuity                  : "any" | "continuous" | "single_span".
    """
    sections: list[str] = field(default_factory=list)
    exclude_sections: list[str] = field(default_factory=list)
    stories: list[str] = field(default_factory=list)
    exclude_stories: list[str] = field(default_factory=list)
    frames: list[str] = field(default_factory=list)
    chain_ids: list[str] = field(default_factory=list)
    min_length: float | None = None
    max_length: float | None = None
    match: str = "any"
    continuity: str = "any"        # any | continuous (>=2 deschideri) | single_span (o singura deschidere)

    def _section_ok(self, name: str) -> bool:
        if self.sections and not _match(name, self.sections):
            return False
        if self.exclude_sections and _match(name, self.exclude_sections):
            return False
        return True

    def accepts(self, chain: Chain, labels: dict[str, str] | None = None) -> bool:
        if self.chain_ids and chain.id not in self.chain_ids:
            return False
        if self.stories and not _match(chain.story, self.stories):
            return False
        if self.exclude_stories and _match(chain.story, self.exclude_stories):
            return False
        if self.continuity != "any" and chain.continuity != self.continuity:
            return False
        if self.min_length is not None and chain.length < self.min_length:
            return False
        if self.max_length is not None and chain.length > self.max_length:
            return False
        if self.frames:
            wanted = {f.lower() for f in self.frames}
            names = {m.frame.lower() for m in chain.members}
            if labels:
                names |= {labels.get(m.frame, "").lower() for m in chain.members}
            if not (wanted & names):
                return False
        if self.sections or self.exclude_sections:
            oks = [self._section_ok(m.section) for m in chain.members]
            if not (all(oks) if self.match == "all" else any(oks)):
                return False
        return True

    def apply(self, chains: list[Chain], labels: dict[str, str] | None = None) -> list[Chain]:
        return [c for c in chains if self.accepts(c, labels)]
