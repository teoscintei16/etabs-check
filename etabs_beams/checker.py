"""Verificator de model: este modelul ETABS curat si pregatit pentru extragere?

Verificarile sunt functii pure peste ModelData (+ Extras citite din ETABS), deci testabile fara ETABS."""
from __future__ import annotations

import collections
import fnmatch
import math
from dataclasses import dataclass, field

from .models import BEAM, COLUMN, ModelData, Tolerances
from .geometry import end_on_beam_hits
from .refs import resolve
from .walls import shell_intervals, walls_at_point

ERROR, WARNING, INFO = "error", "warning", "info"
_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}
MAX_LISTED = 200            # obiecte listate pe verificare in raport (restul doar numarate)


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    objects: list = field(default_factory=list)       # [("frame"|"wall", nume)]
    data: dict = field(default_factory=dict)
    count: int = 0

    def __post_init__(self):
        self.count = self.count or len(self.objects)


@dataclass
class Extras:
    """Date din ETABS care nu sunt in ModelData."""
    model_file: str = ""
    analyzed: bool | None = None
    case_status: dict = field(default_factory=dict)       # nume caz -> cod (4 = terminat)
    combos: list = field(default_factory=list)
    stories: dict = field(default_factory=dict)           # nume etaj -> cota [m]


def gather_extras(session) -> Extras:
    """Citeste din ETABS fisierul, starea analizei, cazurile, combinatiile si etajele (kN, m)."""
    from .connection import ok
    sap = session.model
    ex = Extras(model_file=session.filename, analyzed=session.analyzed)
    with session.units():
        st = ok(sap.Story.GetStories_2())
        ex.stories = dict(zip(st[2], st[3]))
        cs = ok(sap.Analyze.GetCaseStatus())
        ex.case_status = dict(zip(cs[1], cs[2]))
        from .analysis import nonlinear_cases
        skipped = nonlinear_cases(sap)                    # cazurile neliniare (ex. etapizat) nu se ruleaza implicit: lipsa rezultatelor lor nu e o problema
        ex.case_status = {n: s for n, s in ex.case_status.items() if s == 4 or n not in skipped}
        ex.combos = list(ok(sap.RespCombo.GetNameList())[1])
    return ex


# ---------------------------------------------------------------- verificari
def run_checks(md: ModelData, tol: Tolerances, extras: Extras | None = None) -> list[Issue]:
    issues: list[Issue] = []
    ex = extras or Extras()
    _check_analysis(issues, ex)
    _check_belts(issues, md, tol)
    _check_frames(issues, md, tol)
    _check_connectivity(issues, md, tol)
    _check_beams(issues, md, tol, ex)
    _check_columns(issues, md)
    _check_walls(issues, md, tol)
    issues.sort(key=lambda i: _ORDER[i.severity])
    return issues


def _add(issues, code, sev, msg, objs=(), data=None):
    objs = list(objs)
    issues.append(Issue(code, sev, msg, objs[:MAX_LISTED], data or {}, count=len(objs)))


def _check_analysis(issues, ex: Extras):
    if ex.analyzed is False:
        _add(issues, "model_not_analyzed", ERROR, "Modelul nu este analizat (rezultate lipsa). Rulati analiza.")
    bad = [n for n, s in ex.case_status.items() if s != 4]
    if bad:
        _add(issues, "cases_not_finished", ERROR if len(bad) == len(ex.case_status) else WARNING,
             f"{len(bad)} cazuri de incarcare nu au rezultate (neterminate/nerulate), nu pot fi alese: {', '.join(bad[:8])}"
             f"{'...' if len(bad) > 8 else ''}", data={"cases": bad})
    if ex.case_status and not ex.combos:
        _add(issues, "no_combinations", WARNING, "Modelul nu are combinatii de incarcari definite.")


def _check_belts(issues, md: ModelData, tol: Tolerances):
    """Centurile (dummy) trebuie sa fie peste pereti; cele fara perete ar fi trebuit sa aiba sectiune None."""
    if not tol.belt_sections:
        cand = sorted({f.section for f in md.frames.values()
                       if f.section and any(k in f.section.lower() for k in ("dummy", "centur", "belt"))})
        if cand:
            _add(issues, "belt_hint", INFO,
                 "Nu ati declarat centuri, dar exista sectiuni care par de centura: " + ", ".join(cand) +
                 ". Daca sunt centuri, declarati-le (--belt-section).")
        return
    if not md.belt_names:
        _add(issues, "no_belt_frames", ERROR,
             "Ati declarat sectiuni de centura (" + ", ".join(tol.belt_sections) + "), dar nu exista bare cu ele.")
        return
    none, partial, above = [], [], []
    for b in md.belt_names:
        f = md.frames[b]
        L = f.length
        if L < 1e-6:
            continue
        cover = sum(max(0.0, min(y, L) - max(x, 0.0)) for x, y in shell_intervals(md, f.start, f.end, tol)) / L
        if cover >= 0.9:
            continue
        if cover > 0.05:
            partial.append((b, cover))
            continue
        up = sum(max(0.0, min(y, L) - max(x, 0.0)) for x, y in shell_intervals(md, f.start, f.end, tol, True)) / L
        (above if up > 0.05 else none).append((b, cover))
    if none:
        _add(issues, "belt_without_wall", ERROR,
             f"{len(none)} bare cu sectiune de centura NU sunt peste niciun perete (nici sub, nici deasupra). "
             "Probabil trebuiau sa aiba sectiunea None sau sa fie sterse.",
             [("frame", b) for b, _ in none])
    if above:
        _add(issues, "belt_wall_above_only", WARNING,
             f"{len(above)} centuri au perete doar deasupra, nu dedesubt (conteaza doar peretii de sub grinda).",
             [("frame", b) for b, _ in above])
    if partial:
        _add(issues, "belt_partial_wall", WARNING,
             f"{len(partial)} centuri sunt doar partial peste perete (sub 90%): centura depaseste peretele sau are goluri.",
             [("frame", b) for b, _ in partial],
             {"overlap": {b: round(c, 3) for b, c in partial[:MAX_LISTED]}})


def _check_frames(issues, md: ModelData, tol: Tolerances):
    zero = [f.name for f in md.frames.values() if f.section and f.length < 1e-3]
    if zero:
        _add(issues, "zero_length_frame", ERROR, f"{len(zero)} bare cu lungime ~0.", [("frame", n) for n in zero])
    seen: dict = {}
    dup = []
    for f in md.frames.values():
        if not f.section:
            continue
        k = frozenset((f.p1, f.p2))
        if k in seen:
            dup += [seen[k], f.name]
        seen[k] = f.name
    if dup:
        _add(issues, "duplicate_frames", ERROR,
             f"{len(set(dup))} bare suprapuse (aceleasi noduri la capete); eforturile s-ar dubla/imparti.",
             [("frame", n) for n in dict.fromkeys(dup)])
    null = [f.name for f in md.frames.values() if not f.section]
    if null:
        _add(issues, "null_section_frames", INFO,
             f"{len(null)} bare fara sectiune (None/Null) - ignorate de tool.", [("frame", n) for n in null])


def _check_connectivity(issues, md: ModelData, tol: Tolerances):
    # noduri duplicate: acelasi loc, nume diferite -> grinzile nu sunt conectate
    by_xyz: dict = collections.defaultdict(set)
    pts: dict = {}
    for f in md.frames.values():
        if not f.section:
            continue
        for p, xyz in ((f.p1, f.start), (f.p2, f.end)):
            by_xyz[tuple(round(c, 3) for c in xyz)].add(p)
            pts[p] = xyz
    dup_nodes = [v for v in by_xyz.values() if len(v) > 1]
    if dup_nodes:
        frames = [f.name for f in md.frames.values() if f.section and ({f.p1, f.p2} & set().union(*dup_nodes))]
        _add(issues, "duplicate_nodes", ERROR,
             f"{len(dup_nodes)} locuri cu noduri duplicate (acelasi punct, noduri diferite): barele de acolo nu sunt "
             "conectate, deci continuitatea nu poate fi detectata corect.",
             [("frame", n) for n in frames], {"nodes": [sorted(v) for v in dup_nodes[:50]]})

    # capete de grinda care ating interiorul altei grinzi / al unei centuri, fara nod comun
    beams = [md.frames[b] for b in md.beam_names]
    if beams:
        on_beams = end_on_beam_hits(md, md.beam_names)
        on_belts = end_on_beam_hits(md, md.beam_names, targets=md.belt_names) if md.belt_names else []
        if on_beams:
            hit = [n for f_, _p, g_ in on_beams for n in (f_, g_)]
            _add(issues, "secondary_beams", INFO,
                 f"{len(on_beams)} grinzi secundare se termina pe interiorul altei grinzi (fara nod comun): "
                 "considerate sprijinite pe grinda traversata, care ramane continua.",
                 [("frame", n) for n in dict.fromkeys(hit)])
        tee_nodes = {p for _f, p, _g in on_beams + on_belts}
        floating = []
        for f in beams:
            def attached(p, xyz):
                return (bool(set(md.node_frames.get(p, [])) - {f.name}) or bool(md.node_areas.get(p))
                        or p in md.restrained or p in tee_nodes or bool(walls_at_point(md, xyz, tol)))
            if not attached(f.p1, f.start) and not attached(f.p2, f.end):
                floating.append(f.name)
        if floating:
            _add(issues, "beam_floating", WARNING,
                 f"{len(floating)} grinzi nu ating nimic la niciun capat (nici stalp/perete/centura/alta grinda).",
                 [("frame", n) for n in floating])


def _check_beams(issues, md: ModelData, tol: Tolerances, ex: Extras):
    beams = [md.frames[b] for b in md.beam_names]
    steep = [f.name for f in beams if f.length and abs(f.end[2] - f.start[2]) / f.length > tol.max_slope]
    if steep:
        _add(issues, "beam_steep", WARNING, f"{len(steep)} grinzi cu panta mare (> {tol.max_slope:.0%}).",
             [("frame", n) for n in steep])
    sloped = [f.name for f in beams if f.length and 0.002 < abs(f.end[2] - f.start[2]) / f.length <= tol.max_slope]
    if sloped:
        _add(issues, "beam_sloped", INFO, f"{len(sloped)} grinzi usor inclinate (rampe sau erori de cota).",
             [("frame", n) for n in sloped])
    rot = [f.name for f in beams if abs(math.remainder(f.angle, 360.0)) > 1e-6]
    if rot:
        _add(issues, "beam_local_axes_rotated", WARNING,
             f"{len(rot)} grinzi au axele locale rotite (unghi != 0): M2/M3 si V2/V3 pot fi inversate sau cu semn schimbat.",
             [("frame", n) for n in rot])
    card = [f.name for f in beams if f.cardinal != 8]
    if card:
        _add(issues, "beam_cardinal_point", INFO, f"{len(card)} grinzi au alt punct de insertie decat sus-centru (8).",
             [("frame", n) for n in card])
    off = [f.name for f in beams if any(abs(o) > 1e-4 for o in f.offsets)]
    if off:
        _add(issues, "beam_joint_offsets", WARNING,
             f"{len(off)} grinzi au offseturi de nod: axa reala difera de linia dintre noduri.",
             [("frame", n) for n in off])
    few = [f.name for f in beams if f.output_stations and (
        (f.output_stations[0] == 1 and f.output_stations[1] > 1.0) or
        (f.output_stations[0] == 2 and f.output_stations[2] < 3))]
    if few:
        _add(issues, "beam_few_output_stations", WARNING,
             f"{len(few)} grinzi au prea putine statii de iesire (pas > 1 m sau < 3 statii): eforturile vor fi rare.",
             [("frame", n) for n in few])
    if ex.stories:
        lv = list(ex.stories.values())
        off_story = [f.name for f in beams if min(abs(f.start[2] - z) for z in lv) > 0.05
                     or min(abs(f.end[2] - z) for z in lv) > 0.05]
        if off_story:
            _add(issues, "beam_off_story", INFO, f"{len(off_story)} grinzi nu sunt la cota unui etaj.",
                 [("frame", n) for n in off_story])


def _check_columns(issues, md: ModelData):
    cols = [f for f in md.frames.values() if f.orientation == COLUMN]
    unk = [f.name for f in cols if (md.sections.get(f.section) is None or md.sections[f.section].depth is None)]
    if unk:
        _add(issues, "column_section_unknown", WARNING,
             f"{len(unk)} stalpi au sectiune a carei dimensiune nu a putut fi citita (alta decat dreptunghi/cerc): offset 0.",
             [("frame", n) for n in unk])


def _check_walls(issues, md: ModelData, tol: Tolerances):
    if not md.walls:
        _add(issues, "no_walls", INFO, "Nu exista pereti (shell vertical) in model.")
    # grinzi (nu centuri) aflate peste pereti
    onwall = []
    for b in md.beam_names:
        f = md.frames[b]
        L = f.length
        if L > 1e-6 and sum(max(0.0, min(y, L) - max(x, 0.0))
                            for x, y in shell_intervals(md, f.start, f.end, tol)) >= 0.5 * L:
            onwall.append(b)
    if onwall:
        _add(issues, "beam_on_wall", INFO,
             f"{len(onwall)} grinzi (nu centuri) sunt peste pereti; vor fi tratate ca grinda pe perete, fara deschidere.",
             [("frame", b) for b in onwall])


# ---------------------------------------------------------------- raport
def report(md: ModelData, issues: list[Issue], extras: Extras | None = None) -> dict:
    counts = collections.Counter(i.severity for i in issues)
    return {
        "model_file": (extras.model_file if extras else ""),
        "ready": counts[ERROR] == 0,
        "counts": {"errors": counts[ERROR], "warnings": counts[WARNING], "info": counts[INFO]},
        "issues": [{"code": i.code, "severity": i.severity, "message": i.message, "count": i.count,
                    "listed": len(i.objects), "data": i.data,
                    "objects": [resolve(md, o) for o in i.objects]} for i in issues],
    }


def format_report(rep: dict, max_objects: int = 12) -> str:
    tag = {ERROR: "EROARE", WARNING: "AVERT.", INFO: "INFO"}
    lines = [f"Model: {rep['model_file']}",
             f"Rezultat: {'PREGATIT' if rep['ready'] else 'NEPREGATIT'} - "
             f"{rep['counts']['errors']} erori, {rep['counts']['warnings']} avertismente, {rep['counts']['info']} info", ""]
    for i in rep["issues"]:
        lines.append(f"[{tag[i['severity']]}] {i['message']}")
        for o in i["objects"][:max_objects]:
            if o["type"] == "frame":
                lines.append(f"    - bara  eticheta {o.get('label', '?'):<8} nume unic {o['name']:<6} "
                             f"etaj {o.get('story', '?'):<5} sectiune {o.get('section', '?')}")
            elif o["type"] == "wall":
                lines.append(f"    - perete eticheta {o.get('label', '?'):<8} nume unic {o['name']:<6} "
                             f"etaj {o.get('story', '?')}")
        if i["count"] > max_objects:
            lines.append(f"    ... (+{i['count'] - max_objects}; lista completa in JSON)")
    return "\n".join(lines)
