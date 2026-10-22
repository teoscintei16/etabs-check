import unittest

from etabs_gen.connect import GenError
from etabs_gen.frames import FrameSpec, build_frame_model
from etabs_gen.layout import parse_indices
from etabs_gen.plan import build_plan
from tests.test_gen_frames import FakeSap


class LayoutTests(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(parse_indices("first,last", 4, "x"), [0, 3])
        self.assertEqual(parse_indices("middle", 3, "x"), [1])
        self.assertEqual(parse_indices("all", 3, "x"), [0, 1, 2])
        self.assertEqual(parse_indices("0, 2", 3, "x"), [0, 2])
        self.assertEqual(parse_indices("none", 3, "x", allow_none=True), [])
        for bad in ("5", "abc", "", "-1", "none"):
            with self.assertRaises(GenError):
                parse_indices(bad, 3, "x")

    def test_runs_group_consecutive_bays_into_one_pier(self):
        spec = FrameSpec(bays=4, travei=2, walls=True, wall_lines_x="0", wall_bays_x="0,1,3", wall_lines_y="first", wall_bays_y="middle")
        runs = build_plan(spec).runs
        self.assertEqual([(r["axis"], r["line"], r["bays"], r["pier"]) for r in runs],
                         [("X", 0, [0, 1], "PX1"), ("X", 0, [3], "PX2"), ("Y", 0, [0], "PY1")])

    def test_blocked_nodes_and_beams(self):
        plan = build_plan(FrameSpec(bays=3, travei=3, walls=True, wall_lines_x="0", wall_bays_x="1", wall_lines_y="0", wall_bays_y="1"))
        idx = len(plan.stories) - 1
        cols = set(plan.columns(idx))
        self.assertFalse(cols & {(1, 0), (2, 0), (0, 1), (0, 2)})                    # capetele peretilor n-au stalp
        bx, by = plan.beams(idx)
        self.assertNotIn((0, 1), bx)
        self.assertNotIn((0, 1), by)


class WallModelTests(unittest.TestCase):
    def build(self, **kw):
        sap = FakeSap()
        res = build_frame_model(sap, FrameSpec(stories=2, bays=3, travei=3, walls=True, **kw))
        return sap, res

    def test_counts_default_layout(self):
        sap, res = self.build()
        o = res["objects"]
        self.assertEqual(o["pereti"], 4 * 1 * 2)                        # 4 pereti (2 pe X, 2 pe Y) x 1 deschidere x 2 etaje
        self.assertEqual(o["centuri"], 8)
        self.assertEqual(o["stalpi"], (16 - 8) * 2)                     # nodurile de capat ale peretilor n-au stalp
        self.assertEqual(o["grinzi"], (24 - 4) * 2)                     # grinzile de sub pereti lipsesc
        self.assertEqual(res["piers"], ["PX1", "PX2", "PY1", "PY2"])
        self.assertEqual(res["belts"], {"has": True, "sections": ["CENTURA"]})
        self.assertEqual(res["project"]["tip_cladire"], "rezidential_pereti")

    def test_wall_geometry_and_piers(self):
        sap, _ = self.build()
        panels = sap.calls("AreaObj.AddByCoord")
        walls = [a for a in panels if a[5] == "W25"]
        self.assertEqual(len(walls), 8)
        x_wall = walls[0]                                                # primul: pe X, linia y=0, deschiderea 1, etajul 1
        self.assertEqual((x_wall[1], x_wall[2], x_wall[3]), ([5.0, 10.0, 10.0, 5.0], [0.0] * 4, [0.0, 0.0, 3.0, 3.0]))
        piers = [a[1] for a in sap.calls("AreaObj.SetPier")]
        self.assertEqual(piers, ["PX1", "PX2", "PY1", "PY2"] * 2)       # aceeasi eticheta la toate etajele
        self.assertEqual(len(sap.calls("PierLabel.SetPier")), 4)

    def test_base_restraints_include_wall_corners(self):
        sap, _ = self.build()
        restrained = {a[0] for a in sap.calls("PointObj.SetRestraint")}
        self.assertEqual(len(restrained), 8 + 4 * 2)                    # 8 stalpi + 4 pereti x 2 colturi (distincte in fake)

    def test_wall_and_belt_sections_and_modifiers(self):
        sap, _ = self.build(wall_t=0.3)
        self.assertEqual(sap.calls("PropArea.SetWall")[0], ("W30", 0, 1, "C25/30", 0.3))
        mods = {a[0]: a[1] for a in sap.calls("PropArea.SetModifiers")}
        self.assertEqual(mods["W30"], [0.5, 0.5, 0.5, 0.25, 0.25, 0.25, 1.0, 1.0, 1.0, 1.0])
        belt = {a[0]: a[1] for a in sap.calls("PropFrame.SetModifiers")}["CENTURA"]
        self.assertEqual(belt[-2:], [0.0, 0.0])                         # fara masa si greutate
        rigid = sap.DatabaseTables.t["Frame Assignments - End Length Offsets"][1]
        self.assertEqual(sum(1 for r in rigid if r["RigidFact"] == "0.75"), 8 * 2 + 20 * 2)    # centurile (8) nu primesc zone rigide
        self.assertEqual(sum(1 for r in rigid if r["RigidFact"] == "0"), 8)

    def test_beams_and_belts_top_center_columns_untouched(self):
        sap, res = self.build()
        ins = sap.DatabaseTables.t["Frame Assignments - Insertion Point"][1]
        top = [r for r in ins if r["CardinalPt"] == "8 (Top Center)"]
        self.assertEqual(len(top), res["objects"]["grinzi"] + res["objects"]["centuri"])
        self.assertEqual(sum(1 for r in ins if r["CardinalPt"] == "10 (Centroid)"), res["objects"]["stalpi"])

    def test_walls_without_frame_or_belts(self):
        sap, res = self.build(gravity_frame=False, belts=False)
        self.assertEqual((res["objects"]["stalpi"], res["objects"]["grinzi"], res["objects"]["centuri"]), (0, 0, 0))
        self.assertIsNone(res["belts"])
        self.assertEqual(sap.calls("PropFrame.SetModifiers")[0][0], "C50x50")   # sectiunile de cadre raman definite

    def test_invalid_layout(self):
        for bad in (dict(wall_bays_x="9"), dict(wall_lines_y="x"), dict(wall_t=0), dict(crack_wall_f=2)):
            with self.assertRaises(GenError):
                build_frame_model(FakeSap(), FrameSpec(walls=True, **bad))


if __name__ == "__main__":
    unittest.main()
