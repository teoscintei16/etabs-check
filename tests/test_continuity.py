import math
import unittest

from etabs_beams.continuity import build_chains
from etabs_beams.models import COLUMN, BEAM, Frame, ModelData, SectionInfo, Tolerances, WallInfo
from etabs_beams.selector import BeamSelector


class Builder:
    def __init__(self):
        self.md = ModelData()
        self.pts = {}
        self.n = 0
        self.md.sections["B30x60"] = SectionInfo("B30x60", "rect", 0.6, 0.3)
        self.md.sections["B30x40"] = SectionInfo("B30x40", "rect", 0.4, 0.3)
        self.md.sections["C40x60"] = SectionInfo("C40x60", "rect", 0.6, 0.4)   # T3=0.6, T2=0.4

    def pt(self, x, y, z=3.0):
        key = (x, y, z)
        return self.pts.setdefault(key, f"P{len(self.pts)+1}")

    def beam(self, a, b, sec="B30x60", story="S1", **kw):
        self.n += 1
        name = str(self.n)
        pa, pb = self.pt(*a), self.pt(*b)
        self.md.frames[name] = Frame(name, f"B{name}", story, sec, pa, pb, a, b, orientation=BEAM, **kw)
        self.md.beam_names.append(name)
        return name

    def column(self, x, y, sec="C40x60", angle=0.0):
        self.n += 1
        name = str(self.n)
        top, bot = self.pt(x, y, 3.0), self.pt(x, y, 0.0)
        self.md.frames[name] = Frame(name, f"C{name}", "S1", sec, bot, top, (x, y, 0.0), (x, y, 3.0),
                                     angle=angle, orientation=COLUMN)
        self.md.node_frames.setdefault(top, []).append(name)
        return name

    def wall(self, name, a, b, thickness=0.3, point_names=()):
        """Perete vertical de la a=(x,y,zmin) la b=(x,y,zmax)."""
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        pts = [(a[0], a[1], a[2]), (b[0], b[1], a[2]), (b[0], b[1], b[2]), (a[0], a[1], b[2])]
        self.md.walls[name] = WallInfo(name, thickness, d, pts, list(point_names), a[2], b[2])
        for p in point_names:
            self.md.node_areas.setdefault(p, []).append(name)

    def finish(self):
        for f in self.md.frames.values():
            if f.orientation == BEAM:
                for p in (f.p1, f.p2):
                    self.md.node_frames.setdefault(p, [])
        return self.md


class ContinuityTests(unittest.TestCase):
    def test_three_spans_with_face_offsets(self):
        b = Builder()
        for x in (0, 5, 11, 15):
            b.column(x, 0)
        n1 = b.beam((0, 0, 3), (5, 0, 3)); n2 = b.beam((5, 0, 3), (11, 0, 3)); n3 = b.beam((11, 0, 3), (15, 0, 3))
        chains = build_chains(b.finish())
        self.assertEqual(len(chains), 1)
        c = chains[0]
        self.assertEqual(c.id, f"{n1}+{n2}+{n3}")            # id = nume unice ETABS, in ordinea lantului
        self.assertEqual([round(s.length, 3) for s in c.spans], [5, 6, 4])
        # grinda pe X, stalp angle=0: latime T2=0.4 pe X -> offset 0.2
        self.assertAlmostEqual(c.supports[1].offset_before, 0.2)
        self.assertAlmostEqual(c.spans[1].clear_length, 6 - 0.4)

    def test_column_rotated_uses_depth(self):
        b = Builder()
        b.column(0, 0, angle=90.0); b.column(5, 0, angle=90.0)
        b.beam((0, 0, 3), (5, 0, 3))
        c = build_chains(b.finish())[0]
        self.assertAlmostEqual(c.supports[0].offset_after, 0.3)   # T3/2 pe X

    def test_section_change_does_not_break_chain(self):
        b = Builder()
        for x in (0, 4, 8):
            b.column(x, 0)
        b.beam((0, 0, 3), (4, 0, 3), "B30x60"); b.beam((4, 0, 3), (8, 0, 3), "B30x40")
        chains = build_chains(b.finish())
        self.assertEqual(len(chains), 1)
        self.assertEqual(len(chains[0].members), 2)

    def test_release_breaks_chain(self):
        b = Builder()
        for x in (0, 4, 8):
            b.column(x, 0)
        b.beam((0, 0, 3), (4, 0, 3), release_j=True); b.beam((4, 0, 3), (8, 0, 3))
        self.assertEqual(len(build_chains(b.finish())), 2)

    def test_perpendicular_beam_ends_on_through_beam(self):
        b = Builder()
        b.column(0, 0); b.column(10, 0); b.column(5, 6)
        a1 = b.beam((0, 0, 3), (5, 0, 3)); a2 = b.beam((5, 0, 3), (10, 0, 3))
        s = b.beam((5, 6, 3), (5, 0, 3), "B30x40")
        chains = build_chains(b.finish())
        self.assertEqual(len(chains), 2)
        main = next(c for c in chains if len(c.members) == 2)
        sec = next(c for c in chains if len(c.members) == 1)
        # grinda principala: nodul de mijloc nu e reazem (nu are stalp, secundara se termina in ea)
        self.assertEqual(main.supports[1].kind, "none")
        self.assertEqual(len(main.spans), 1)
        # secundara: capatul pe grinda principala = reazem de tip grinda
        kinds = sorted(x.kind for x in sec.supports)
        self.assertEqual(kinds, ["beam", "column"])

    def test_wall_perpendicular_no_offset_fixed_end(self):
        b = Builder()
        b.column(0, 0)
        b.beam((0, 0, 3), (6, 0, 3))
        md = b.finish()
        end = md.frames["2"].p2
        b.wall("W1", (6, -2, 0), (6, 2, 3), thickness=0.3, point_names=[end])
        c = build_chains(md)[0]
        self.assertEqual(c.supports[1].kind, "wall")
        self.assertTrue(c.supports[1].fixed_end)
        self.assertEqual(c.supports[1].offset_before, 0.0)       # fara offset la perete

    def test_cantilever_and_free_end(self):
        b = Builder()
        b.column(0, 0); b.column(5, 0)
        b.beam((0, 0, 3), (5, 0, 3)); b.beam((5, 0, 3), (7, 0, 3))
        c = build_chains(b.finish())[0]
        self.assertEqual([s.cantilever for s in c.spans], [False, True])
        self.assertEqual(c.supports[-1].kind, "free")

    def test_selector(self):
        b = Builder()
        for x in (0, 4, 8):
            b.column(x, 0); b.column(x, 6)
        b.beam((0, 0, 3), (4, 0, 3), "B30x60"); b.beam((4, 0, 3), (8, 0, 3), "B30x40")
        b.beam((0, 6, 3), (8, 6, 3), "B30x40")
        chains = build_chains(b.finish())
        self.assertEqual(len(chains), 2)
        self.assertEqual(len(BeamSelector(sections=["B30x60"]).apply(chains)), 1)           # any
        self.assertEqual(len(BeamSelector(sections=["B30x40"], match="all").apply(chains)), 1)
        self.assertEqual(len(BeamSelector(exclude_sections=["B30x60"]).apply(chains)), 2)   # any membru ok
        self.assertEqual(len(BeamSelector(exclude_sections=["B30x60"], match="all").apply(chains)), 1)

    def test_long_wall_under_beam_breaks_continuity(self):
        b = Builder()
        for x in (0, 4, 8, 12, 16):
            b.column(x, 0)
        n1 = b.beam((0, 0, 3), (4, 0, 3)); n2 = b.beam((4, 0, 3), (8, 0, 3))      # n2 peste perete lung
        n3 = b.beam((8, 0, 3), (12, 0, 3)); b.beam((12, 0, 3), (16, 0, 3))
        b.wall("W", (4, 0, 0), (8, 0, 3))                               # perete 4 m sub grinda 2
        tol = Tolerances(wall_min_length=0.8)
        md = b.finish()
        from etabs_beams.continuity import build_all
        beams, belts, on_wall = build_all(md, tol)
        self.assertEqual(len(on_wall), 1)
        self.assertEqual(on_wall[0].frames, [n2])
        self.assertEqual(len(beams), 2)
        self.assertTrue(all(s.fixed_end for c in beams for s in c.supports if s.node in (
            md.frames[n1].p2, md.frames[n3].p1)))

    def test_short_wall_in_plane_gives_asymmetric_offsets(self):
        b = Builder()
        b.beam((0, 0, 3), (4, 0, 3)); b.beam((4, 0, 3), (8, 0, 3)); b.column(0, 0); b.column(8, 0)
        b.wall("W", (3.8, 0, 0), (4.5, 0, 3))      # 0.7 m < 0.8, nodul 4 e pe perete, nu la capat
        c = build_chains(b.finish())[0]
        self.assertEqual(len(c.members), 2)
        mid = c.supports[1]
        self.assertTrue(mid.kind.startswith("wall"))
        self.assertAlmostEqual(mid.offset_before, 0.2)
        self.assertAlmostEqual(mid.offset_after, 0.5)

    def test_beam_on_belt_over_wall_is_fixed(self):
        b = Builder()
        b.md.sections["dummy"] = SectionInfo("dummy", "rect", 0.4, 0.2)
        b.column(0, 0)
        nb = b.beam((0, 0, 3), (5, 0, 3))
        nt = b.beam((5, -3, 3), (5, 3, 3), "dummy")                      # centura peste perete
        b.wall("W", (5, -3, 0), (5, 3, 3), point_names=[])
        md = b.finish()
        from etabs_beams.continuity import build_all
        md.beam_names, md.belt_names = [nb], [nt]
        node = md.frames[nb].p2
        md.node_frames[node] = [nb, nt]
        beams, belts, _ = build_all(md, Tolerances())
        self.assertEqual(len(belts), 1)
        self.assertEqual(beams[0].supports[-1].kind, "wall")
        self.assertTrue(beams[0].supports[-1].fixed_end)

    def test_belts_two_collinear_pieces_merge_into_one(self):
        b = Builder()
        b.md.sections["dummy"] = SectionInfo("dummy", "rect", 0.4, 0.2)
        b.beam((0, 0, 3), (3, 0, 3), "dummy"); b.beam((3, 0, 3), (6, 0, 3), "dummy")
        md = b.finish()
        md.beam_names, md.belt_names = [], list(md.frames)
        from etabs_beams.continuity import build_all
        _, belts, _ = build_all(md, Tolerances())
        self.assertEqual(len(belts), 1)
        self.assertAlmostEqual(belts[0].length, 6.0)

    def test_continuity_types(self):
        b = Builder()
        for x in (0, 4, 8):
            b.column(x, 0); b.column(x, 6)
        b.beam((0, 0, 3), (4, 0, 3)); b.beam((4, 0, 3), (8, 0, 3))
        b.beam((0, 6, 3), (4, 6, 3))
        chains = build_chains(b.finish())
        self.assertEqual(sorted(c.continuity for c in chains), ["continuous", "single_span"])
        self.assertEqual(len(BeamSelector(continuity="single_span").apply(chains)), 1)

    def test_rectangular_column_long_side_along_beam(self):
        b = Builder()
        # C40x60: T2 (latime)=0.4 pe axa locala 2, T3 (adancime)=0.6 pe axa locala 3
        for ang, expected in ((0.0, 0.2), (90.0, 0.3)):                 # grinda pe X
            bb = Builder()
            bb.column(0, 0, angle=ang); bb.column(5, 0, angle=ang)
            bb.beam((0, 0, 3), (5, 0, 3))
            c = build_chains(bb.finish())[0]
            self.assertAlmostEqual(c.supports[0].offset_after, expected)
        # grinda pe Y: dimensiunile se inverseaza
        bb = Builder()
        bb.column(0, 0, angle=0.0); bb.column(0, 5, angle=0.0)
        bb.beam((0, 0, 3), (0, 5, 3))
        self.assertAlmostEqual(build_chains(bb.finish())[0].supports[0].offset_after, 0.3)

    def test_diagonal_beam_column_chord(self):
        bb = Builder()
        bb.column(0, 0); bb.column(4, 4)
        bb.beam((0, 0, 3), (4, 4, 3))
        c = build_chains(bb.finish())[0]
        self.assertAlmostEqual(c.supports[0].offset_after, 0.4 / 2 / math.cos(math.radians(45)))

    def _belt_zone_model(self, belt_x0, belt_x1):
        from etabs_beams.walls import chain_zones
        b = Builder()
        b.md.sections["dummy"] = SectionInfo("dummy", "rect", 0.4, 0.2)
        b.beam((0, 0, 3), (4, 0, 3))
        b.beam((belt_x0, 0, 3), (belt_x1, 0, 3), "dummy")
        b.wall("W", (0, 0, 0), (4, 0, 3), thickness=0.4)                # shell 0..4
        md = b.finish()
        md.belt_names = ["1"]
        md.beam_names = []
        md.belt_segments = [((belt_x0, 0, 3), (belt_x1, 0, 3), ["1"], "1")]
        return md, chain_zones(md, (0, 0, 3), (4, 0, 3), Tolerances())

    def test_belt_shorter_by_half_thickness_uses_belt_length(self):
        md, zones = self._belt_zone_model(0.2, 3.8)                      # centura retrasa cu t/2 la capete
        self.assertEqual(zones[0].source, "belt")
        self.assertAlmostEqual(zones[0].length, 3.6)
        self.assertFalse([w for w in md.warnings if w["code"] == "wall_length_mismatch"])

    def test_unexplained_difference_warns_and_uses_shell(self):
        md, zones = self._belt_zone_model(0.0, 3.4)                      # 0.6 m mai scurta: nu e t/2
        self.assertEqual(zones[0].source, "shell")
        self.assertAlmostEqual(zones[0].length, 4.0)
        w = [w for w in md.warnings if w["code"] == "wall_length_mismatch"]
        self.assertTrue(w)
        objs = set(w[0]["objects"])
        self.assertIn(("wall", "W"), objs)          # id-ul peretelui
        self.assertIn(("frame", "1"), objs)         # bara de centura
        self.assertAlmostEqual(w[0]["data"]["shell_length"], 4.0)


if __name__ == "__main__":
    unittest.main()
