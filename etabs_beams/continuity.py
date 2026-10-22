"""Detectie grinzi continue, reazeme si deschideri. Logica pura (fara ETABS)."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from .geometry import end_on_beam_hits
from .models import COLUMN, Frame, ModelData, Tolerances, warn
from .walls import Zone, chain_zones, shell_intervals, walls_at_point


@dataclass
class ChainMember:
    frame: str
    section: str
    reversed: bool                 # True daca I->J e opus sensului lantului
    s0: float                      # abscisa la inceputul membrului [m]
    s1: float
    depth: float | None = None
    width: float | None = None


@dataclass
class Support:
    node: str
    station: float                 # abscisa pe lant [m]
    kind: str                      # column | wall | column+wall | restraint | beam | free | none
    offset_before: float = 0.0     # zona rigida (stalp / portiune peste perete) spre inceputul lantului [m]
    offset_after: float = 0.0      # ... spre sfarsitul lantului [m]
    elements: list[str] = field(default_factory=list)
    fixed_end: bool = False        # True: capat incastrat in perete (inclusiv perete cu centura/dummy)


@dataclass
class Span:
    index: int
    start_node: str
    end_node: str
    s0: float                      # abscise axa-la-axa
    s1: float
    length: float
    face_s0: float                 # abscise la fata reazemelor
    face_s1: float
    clear_length: float
    cantilever: bool
    members: list[str]
    sections: list[str]
    section_change: bool


@dataclass
class OnWall:
    """Portiune de grinda situata peste un perete lung (fara continuitate / fara deschidere)."""
    frames: list[str]
    sections: list[str]
    story: str
    length: float
    wall_length: float


@dataclass
class Chain:
    id: str
    kind: str                      # beam | belt
    story: str
    members: list[ChainMember]
    nodes: list[str]
    node_stations: list[float]
    supports: list[Support]
    spans: list[Span]
    warnings: list[str] = field(default_factory=list)
    wall_zones: list[dict] = field(default_factory=list)

    @property
    def length(self) -> float:
        return self.node_stations[-1]

    @property
    def continuity(self) -> str:
        return "single_span" if len(self.spans) == 1 else "continuous"


# ---------------------------------------------------------------- pereche in nod
def _away_dir(f: Frame, end: str):
    d = f.direction
    return d if end == "I" else tuple(-c for c in d)


def _pair_at_nodes(model: ModelData, beams: list[str], tol: Tolerances):
    incident: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for b in beams:
        f = model.frames[b]
        incident[f.p1].append((b, "I"))
        incident[f.p2].append((b, "J"))

    partner: dict[tuple[str, str], tuple[str, str]] = {}
    cos_lim = -math.cos(math.radians(tol.angle_deg))
    for node, items in incident.items():
        if len(items) < 2:
            continue
        cands = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (a, ea), (b, eb) = items[i], items[j]
                fa, fb = model.frames[a], model.frames[b]
                if (ea == "I" and fa.release_i) or (ea == "J" and fa.release_j):
                    continue
                if (eb == "I" and fb.release_i) or (eb == "J" and fb.release_j):
                    continue
                da, db = _away_dir(fa, ea), _away_dir(fb, eb)
                dot = sum(x * y for x, y in zip(da, db))
                if dot <= cos_lim:
                    cands.append((dot, items[i], items[j]))
        cands.sort(key=lambda c: c[0])
        used = set()
        for dot, x, y in cands:
            if x in used or y in used:
                continue
            partner[x] = y
            partner[y] = x
            used.update((x, y))
    return incident, partner


# ---------------------------------------------------------------- lanturi
def _build_member_chains(beams, partner):
    """Intoarce liste de (grinda, flip) ordonate; flip=True => parcurs J->I."""
    visited: set[str] = set()
    out, loops = [], []
    for b in beams:
        if b in visited:
            continue
        visited.add(b)
        seq = [(b, False)]
        closed = False
        cur, exit_end = b, "J"                    # inainte
        while True:
            p = partner.get((cur, exit_end))
            if p is None:
                break
            nb, entered = p
            if nb == b:
                closed = True
                break
            if nb in visited:
                break
            visited.add(nb)
            flip = entered == "J"
            seq.append((nb, flip))
            cur, exit_end = nb, ("I" if flip else "J")
        cur, entry_end = b, "I"                   # inapoi
        while not closed:
            p = partner.get((cur, entry_end))
            if p is None:
                break
            pb, pend = p                           # pb iese prin capatul pend
            if pb == b or pb in visited:
                break
            visited.add(pb)
            flip = pend == "I"
            seq.insert(0, (pb, flip))
            cur, entry_end = pb, ("J" if flip else "I")
        if closed:
            loops.append([m for m, _ in seq])
        out.append(seq)
    return out, loops


def _depth(model: ModelData, frame: Frame) -> float:
    sec = model.sections.get(frame.section)
    return (sec.depth or 0.0) if sec else 0.0


def column_half_extent(model: ModelData, f: Frame, d_xy, warnings) -> float:
    """Jumatate din dimensiunea stalpului paralela cu directia d_xy a grinzii."""
    sec = model.sections.get(f.section)
    if sec is None or sec.depth is None:
        warn(warnings, "column_section_unknown", "Dimensiunea stalpului nu a putut fi citita; offset 0", [("frame", f.name)])
        return 0.0
    if sec.kind == "circle":
        return sec.depth / 2
    a = math.radians(f.angle)
    u = (math.cos(a), math.sin(a))             # axa locala 2 (latime T2)
    v = (-math.sin(a), math.cos(a))            # axa locala 3 (adancime T3)
    du = abs(d_xy[0] * u[0] + d_xy[1] * u[1])
    dv = abs(d_xy[0] * v[0] + d_xy[1] * v[1])
    lim = []
    if du > 1e-9:
        lim.append((sec.width or 0.0) / 2 / du)
    if dv > 1e-9:
        lim.append(sec.depth / 2 / dv)
    return min(lim) if lim else 0.0


def _unit_xy(d):
    L = math.hypot(d[0], d[1])
    return (d[0] / L, d[1] / L) if L > 1e-12 else (1.0, 0.0)


def _end_xyz(f: Frame, end: str):
    return f.start if end == "I" else f.end


def _seq_ends(model, seq):
    """Coordonatele primului si ultimului nod ale unei secvente orientate."""
    (b0, r0), (b1, r1) = seq[0], seq[-1]
    f0, f1 = model.frames[b0], model.frames[b1]
    return (f0.end if r0 else f0.start), (f1.start if r1 else f1.end)


def _node_start(model, item):
    f = model.frames[item[0]]
    return f.p2 if item[1] else f.p1


def _node_end(model, item):
    f = model.frames[item[0]]
    return f.p1 if item[1] else f.p2


def _node_xyz(model, seq, i):
    """Coordonatele nodului i al unei secvente orientate (i = 0..n)."""
    if i == 0:
        return _seq_ends(model, seq)[0]
    b, rev = seq[i - 1]
    f = model.frames[b]
    return f.start if rev else f.end


def _belt_on_wall(model: ModelData, belt: str, tol: Tolerances) -> bool:
    cache = model.__dict__.setdefault("_belt_on_wall", {})
    if belt not in cache:
        f = model.frames[belt]
        L = f.length
        ov = 0.0
        for a, b in shell_intervals(model, f.start, f.end, tol):
            ov += max(0.0, min(b, L) - max(a, 0.0))
        cache[belt] = L > 0 and ov >= tol.wall_member_frac * L
    return cache[belt]


# ---------------------------------------------------------------- construire
def build_all(model: ModelData, tol: Tolerances | None = None):
    """Intoarce (lanturi_grinzi, lanturi_centuri, portiuni_pe_perete)."""
    tol = tol or Tolerances()
    belts, _ = _build(model, tol, model.belt_names, "belt", walls=False)
    model.belt_segments = []
    for c in belts:
        f0, f1 = model.frames[c.members[0].frame], model.frames[c.members[-1].frame]
        p0 = f0.end if c.members[0].reversed else f0.start
        p1 = f1.start if c.members[-1].reversed else f1.end
        model.belt_segments.append((p0, p1, [m.frame for m in c.members], c.id))
    beams, on_wall = _build(model, tol, model.beam_names, "beam", walls=True)
    return beams, belts, on_wall


def build_chains(model: ModelData, tol: Tolerances | None = None) -> list[Chain]:
    return build_all(model, tol)[0]


def _build(model, tol, names, kind, walls):
    incident, partner = _pair_at_nodes(model, names, tol)
    seqs, loops = _build_member_chains(names, partner)
    for lp in loops:
        warn(model.warnings, "closed_loop", "Grinda continua inchisa (bucla)", [("frame", x) for x in lp])

    tee: dict[str, list[str]] = defaultdict(list)       # nod -> grinzi traversate (capat pe interiorul lor)
    if kind == "beam":
        for _f, p, g in end_on_beam_hits(model, names):
            tee[p].append(g)

    belt_tee: dict[str, list[str]] = defaultdict(list)  # nod -> centuri pe al caror interior se termina o grinda
    if kind == "beam" and model.belt_names:
        for _f, p, g in end_on_beam_hits(model, names, targets=model.belt_names):
            belt_tee[p].append(g)

    chains: list[Chain] = []
    on_wall: list[OnWall] = []
    for seq in seqs:
        p_first, p_last = _seq_ends(model, seq)
        if (round(p_first[0], 3), round(p_first[1], 3)) > (round(p_last[0], 3), round(p_last[1], 3)):
            seq = [(b, not fl_) for b, fl_ in reversed(seq)]    # sens deterministic
        if walls:
            runs, removed = _split_on_wall(model, seq, tol)
            on_wall.extend(removed)
        else:
            runs = [(seq, frozenset())]
        for run, forced in runs:
            chains.append(_make_chain(model, run, incident, partner, tol, kind, walls, forced, tee, belt_tee))

    chains.sort(key=lambda c: (c.story, *_first_xyz(model, c)))
    for c in chains:        # id = numele unice ETABS ale barelor, in ordinea lantului (ex. "2080+2079+2078")
        c.id = "+".join(m.frame for m in c.members)
    return chains, on_wall


def _first_xyz(model, c: Chain):
    f = model.frames[c.members[0].frame]
    p = f.end if c.members[0].reversed else f.start
    return round(p[0], 3), round(p[1], 3), round(p[2], 3)


def _split_on_wall(model, seq, tol):
    """Rupe lantul in portiunile de grinda aflate peste pereti lungi (> wall_min_length).

    Intoarce ([(secventa, noduri_taiate)], [OnWall]); nodurile taiate devin reazem de tip perete."""
    p0, p1 = _seq_ends(model, seq)
    zones = chain_zones(model, p0, p1, tol, ref=[b for b, _ in seq])
    long = [z for z in zones if z.length > tol.wall_min_length + 1e-9]
    if not long:
        return [(seq, frozenset())], []
    s = 0.0
    flags = []
    for b, rev in seq:
        L = model.frames[b].length
        ov = sum(max(0.0, min(z.b, s + L) - max(z.a, s)) for z in long)
        frac = ov / L if L else 0.0
        zone_walls = sorted({w for z in long for w in z.walls})
        if 0.05 < frac < 0.95:
            warn(model.warnings, "wall_edge_mid_member",
                 f"Peretele se termina in interiorul grinzii {b} ({frac:.0%} peste perete): taiat la limita de element",
                 [("frame", b)] + [("wall", w) for w in zone_walls], {"overlap_fraction": round(frac, 3)})
        flags.append(frac >= tol.wall_member_frac)
        s += L

    runs, removed = [], []
    i, n = 0, len(seq)
    while i < n:
        j = i
        while j < n and flags[j] == flags[i]:
            j += 1
        part = seq[i:j]
        if flags[i]:
            fr = [model.frames[b] for b, _ in part]
            removed.append(OnWall([f.name for f in fr], sorted({f.section for f in fr}), fr[0].story,
                                  sum(f.length for f in fr), max(z.length for z in long)))
        else:
            forced = set()
            if i > 0:
                forced.add(_node_start(model, part[0]))
            if j < n:
                forced.add(_node_end(model, part[-1]))
            runs.append((part, frozenset(forced)))
        i = j
    return runs, removed


def _make_chain(model, seq, incident, partner, tol, kind="beam", walls=True, forced=frozenset(), tee=None, belt_tee=None) -> Chain:
    members, nodes, stations = [], [], [0.0]
    warns: list[str] = []
    s = 0.0
    dirs = []
    for b, rev in seq:
        f = model.frames[b]
        sec = model.sections.get(f.section)
        L = f.length
        members.append(ChainMember(b, f.section, rev, s, s + L,
                                   sec.depth if sec else None, sec.width if sec else None))
        if not nodes:
            nodes.append(f.p2 if rev else f.p1)
        nodes.append(f.p1 if rev else f.p2)
        s += L
        stations.append(s)
        d = f.direction
        dirs.append(tuple(-c for c in d) if rev else d)
    story = model.frames[seq[0][0]].story
    total = stations[-1]

    zones: list[Zone] = []
    if walls:
        p0, p1 = _seq_ends(model, seq)
        zones = chain_zones(model, p0, p1, tol, check=False)

    chain_beams = {b for b, _ in seq}
    belt_set = set(model.belt_names)
    supports: list[Support] = []
    last = len(nodes) - 1
    for i, node in enumerate(nodes):
        d_xy = _unit_xy(dirs[i] if i < len(dirs) else dirs[-1])
        sn = stations[i]
        kinds: list[str] = []
        ob = oa = 0.0
        elems: list[str] = []
        fixed = False

        cols = [fn for fn in model.node_frames.get(node, [])
                if fn in model.frames and model.frames[fn].orientation == COLUMN]
        if cols:
            kinds.append("column")
            for fn in cols:
                h = column_half_extent(model, model.frames[fn], d_xy, model.warnings)
                ob, oa = max(ob, h), max(oa, h)
            elems += cols
        if walls:
            wl = list(model.node_areas.get(node, []))
            wl += [w for w in walls_at_point(model, _node_xyz(model, seq, i), tol) if w not in wl]   # perete atins fara nod comun
            zone_hit = [z for z in zones if z.a - tol.wall_gap_tol <= sn <= z.b + tol.wall_gap_tol]
            belts_here = [fn for fn in list(model.node_frames.get(node, [])) + list((belt_tee or {}).get(node, []))
                          if fn in belt_set and _belt_on_wall(model, fn, tol)]
            if wl or node in forced or zone_hit or belts_here:
                kinds.append("wall")
                fixed = True            # capat incastrat in perete (si cand reazemul e o centura pe perete)
                elems += wl + belts_here
                for z in zone_hit:      # portiunea de grinda peste perete = zona rigida (offset)
                    ob = max(ob, max(0.0, sn - max(z.a, 0.0)))
                    oa = max(oa, max(0.0, min(z.b, total) - sn))
        if node in model.restrained:
            kinds.append("restraint")
        if kinds:
            supports.append(Support(node, sn, "+".join(kinds), ob, oa, elems, fixed))
            continue

        others = [(o, e) for o, e in incident.get(node, []) if o not in chain_beams]
        passing = [o for o, e in others if (o, e) in partner]
        passing += [g for g in (tee or {}).get(node, []) if g not in chain_beams and g not in passing]
        end_node = i in (0, last)
        if end_node and passing:
            supports.append(Support(node, sn, "beam", 0.0, 0.0, passing))
        elif end_node and others:
            supports.append(Support(node, sn, "beam", 0.0, 0.0, [o for o, _ in others]))
            warns.append(f"Capat sprijinit doar pe grinzi care se termina in nodul {node} (colt fara stalp)")
        elif passing:
            mine = max(_depth(model, model.frames[b]) for b in chain_beams
                       if node in (model.frames[b].p1, model.frames[b].p2))
            theirs = max(_depth(model, model.frames[o]) for o in passing)
            if mine < theirs - 1e-6:
                supports.append(Support(node, sn, "beam", 0.0, 0.0, passing))
            elif abs(mine - theirs) <= 1e-6:
                supports.append(Support(node, sn, "beam", 0.0, 0.0, passing))
                warns.append(f"Intersectie grinzi de aceeasi inaltime in nodul {node}: considerata reazem pentru ambele")
            else:
                supports.append(Support(node, sn, "none", 0.0, 0.0, passing))
        else:
            supports.append(Support(node, sn, "free" if end_node else "none"))

    chain = Chain("", kind, story, members, nodes, stations, supports, [], warns,
                  [{"a": z.a, "b": z.b, "length": z.length, "source": z.source,
                    "shell_length": z.shell_len, "belt_length": z.belt_len,
                    "walls": z.walls, "belt_frames": z.belt_frames} for z in zones])
    chain.spans = _make_spans(chain)
    return chain


def _make_spans(chain: Chain) -> list[Span]:
    sup = [s for s in chain.supports if s.kind not in ("none", "free")]
    total = chain.length
    spans: list[Span] = []

    def add(a, b, s0, s1, n0, n1, cant):
        fs0 = s0 + (a.offset_after if a else 0.0)
        fs1 = s1 - (b.offset_before if b else 0.0)
        mem = [m for m in chain.members if m.s1 > s0 + 1e-9 and m.s0 < s1 - 1e-9]
        secs: list[str] = []
        for m in mem:
            if m.section not in secs:
                secs.append(m.section)
        spans.append(Span(len(spans) + 1, n0, n1, s0, s1, s1 - s0, fs0, fs1, max(fs1 - fs0, 0.0), cant,
                          [m.frame for m in mem], secs, len(secs) > 1))

    if not sup:
        chain.warnings.append("Niciun reazem detectat pe grinda continua")
        add(None, None, 0.0, total, chain.nodes[0], chain.nodes[-1], False)
        return spans
    if sup[0].station > 1e-9:
        add(None, sup[0], 0.0, sup[0].station, chain.nodes[0], sup[0].node, True)
    for a, b in zip(sup, sup[1:]):
        add(a, b, a.station, b.station, a.node, b.node, False)
    if sup[-1].station < total - 1e-9:
        add(sup[-1], None, sup[-1].station, total, sup[-1].node, chain.nodes[-1], True)
    return spans
