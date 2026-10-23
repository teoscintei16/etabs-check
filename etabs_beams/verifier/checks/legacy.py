"""Verificarile initiale (geometrie, centuri, grinzi), expuse in registrul nou, pe reguli."""
from __future__ import annotations

from ..registry import Finding, check
from .shells import without_ribs


def _convert(issue) -> Finding:
    data = dict(issue.data)
    return Finding(issue.severity, issue.message, list(issue.objects), data, total=issue.count)


def _legacy(check_id: str, rule: int, title: str, codes: list[str], phase: str = "pre", ribs: bool = False):
    """`ribs=True`: coastele cojilor (bare pe muchiile placilor inclinate) nu sunt grinzi de cadru si se scot din constatari."""
    @check(check_id, rule, title, phase)
    def fn(ctx):
        found = ctx.snap.legacy_issues()
        out = [_convert(found[c]) for c in codes if c in found]
        if ribs:
            out = [f for f in (without_ribs(ctx, f) for f in out) if f is not None]
        return out
    return fn


_legacy("r4_centuri", 4, "Centurile (dummy) sunt peste pereți",
        ["no_belt_frames", "belt_hint", "belt_without_wall", "belt_wall_above_only", "belt_partial_wall"])
_legacy("r4_conectivitate", 4, "Conectivitatea grinzilor la pereți/stâlpi/alte grinzi",
        ["beam_floating", "beam_on_wall", "no_walls"])
_legacy("r13_offset_insertie", 13, "Offseturi și punct de inserție la grinzi",
        ["beam_cardinal_point", "beam_joint_offsets"], ribs=True)
_legacy("r14_axe_locale", 14, "Axele locale ale grinzilor (unghi ≠ 0)", ["beam_local_axes_rotated"], ribs=True)
_legacy("r5_geometrie", 5, "Geometrie curată: bare suprapuse, noduri duplicate, cote, stații",
        ["zero_length_frame", "duplicate_frames", "duplicate_nodes", "beam_steep", "beam_sloped",
         "beam_off_story", "beam_few_output_stations"], ribs=True)
_legacy("r1_sectiuni_stalpi", 1, "Secțiunile stâlpilor (dimensiuni citibile)", ["column_section_unknown"])
_legacy("r15_null", 15, "Bare fără secțiune (Null)", ["null_section_frames"])
_legacy("r9_combinatii_existenta", 9, "Există combinații de încărcări", ["no_combinations"])
_legacy("r10_cazuri_rulate", 10, "Cazurile de încărcare au rezultate",
        ["model_not_analyzed", "cases_not_finished"], "post")
