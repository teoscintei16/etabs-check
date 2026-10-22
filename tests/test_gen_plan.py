import unittest

from etabs_gen.connect import GenError
from etabs_gen.frames import SOIL_PATTERN, FrameSpec, build_frame_model
from etabs_gen.plan import active_cells, build_plan, stories_of
from tests.test_gen_frames import FakeSap


class StoriesTests(unittest.TestCase):
    def test_without_basement_default_names(self):
        st = stories_of(FrameSpec(stories=3, bottom_height=4.0))
        self.assertEqual([(s.name, s.z_bot, s.z_top) for s in st], [("Story1", 0.0, 4.0), ("Story2", 4.0, 7.0), ("Story3", 7.0, 10.0)])

    def test_basement_names_and_levels(self):
        st = stories_of(FrameSpec(stories=3, basement=2, basement_height=3.2))
        self.assertEqual([s.name for s in st], ["S2", "S1", "P", "E1", "E2"])
        self.assertEqual([(s.z_bot, s.z_top) for s in st][:3], [(-6.4, -3.2), (-3.2, 0.0), (0.0, 3.0)])   # S1 are cota superioara ±0.00
        self.assertEqual([s.basement for s in st], [True, True, False, False, False])


class ShapeTests(unittest.TestCase):
    def test_L_and_setback(self):
        s = FrameSpec(bays=4, travei=3, stories=4, shape="L", cut_bays=2, cut_travei=1)
        c = active_cells(s, 1)
        self.assertEqual(len(c), 12 - 2)
        self.assertNotIn((3, 2), c)
        self.assertEqual(len(active_cells(s, None)), 12)                                    # subsolul e planul complet
        s = FrameSpec(bays=4, travei=3, stories=4, shape="setback", setback_story=2, setback_bays=1)
        self.assertEqual((len(active_cells(s, 2)), len(active_cells(s, 3))), (12, 9))

    def test_columns_follow_upper_floors_and_beams_follow_cells(self):
        spec = FrameSpec(bays=3, travei=2, stories=3, shape="setback", setback_story=1, setback_bays=1)
        plan = build_plan(spec)
        low, top = plan.columns(0), plan.columns(2)
        self.assertEqual(len(low), 4 * 3)
        self.assertEqual(len(top), 3 * 3)                                                     # fara linia x=3
        self.assertTrue(all(ix < 3 for ix, _ in top))
        bx, by = plan.beams(2)
        self.assertTrue(all(i < 2 for _, i in bx))
        self.assertEqual(len(by), 3 * 2)

    def test_voids_remove_slabs_not_beams(self):
        plan = build_plan(FrameSpec(bays=3, travei=3, stories=2, void_cells="1,1"))
        self.assertEqual(len(plan.slab_cells(0)), 8)
        self.assertEqual(len(plan.beams(0)[0]), 4 * 3)
        for bad in ("9,9", "x", "1"):
            with self.assertRaises(GenError):
                FrameSpec(void_cells=bad).validate()


class CoupledTests(unittest.TestCase):
    SPEC = dict(walls=True, bays=3, travei=3, stories=2, wall_lines_x="first,last", wall_bays_x="0,2", wall_lines_y="none", coupling_bays_x="middle")

    def test_plan(self):
        plan = build_plan(FrameSpec(**self.SPEC))
        self.assertEqual(plan.coupling, {("X", 0, 1), ("X", 3, 1)})
        cb = plan.coupling_beams(0)
        self.assertEqual([c["spandrel"] for c in cb], ["SPX0_1", "SPX3_1"])
        self.assertNotIn((0, 1), plan.beams(0)[0])                                            # grinda normala din golul peretilor lipseste

    def test_model(self):
        sap = FakeSap()
        res = build_frame_model(sap, FrameSpec(**self.SPEC))
        self.assertEqual(res["objects"]["grinzi_cuplare"], 2 * 2)
        self.assertEqual(res["objects"]["pereti"], 4 * 2)                                     # 2 linii x 2 picioare x 2 etaje
        self.assertEqual(len(sap.calls("FrameObj.SetSpandrel")), 4)
        self.assertEqual(len(sap.calls("SpandrelLabel.SetSpandrel")), 2)                      # eticheta multi-etaj, definita o singura data
        self.assertEqual(sap.calls("PropFrame.SetRectangle")[-1][0], "CB25x90")
        mods = {a[0]: a[1] for a in sap.calls("PropFrame.SetModifiers")}
        self.assertEqual(mods["CB25x90"][4], 0.5)

    def test_coupling_needs_walls(self):
        with self.assertRaises(GenError):
            FrameSpec(coupling_bays_x="middle").validate()


class BasementTests(unittest.TestCase):
    def build(self, **kw):
        sap = FakeSap()
        res = build_frame_model(sap, FrameSpec(stories=2, bays=2, travei=2, basement=2, **kw))
        return sap, res

    def test_stories_and_base_story(self):
        sap, res = self.build()
        base, names, heights = sap.s["stories"]
        self.assertEqual((base, names), (-6.0, ["S2", "S1", "P", "E1"]))
        self.assertEqual(res["stories"], ["E1", "P", "S1", "S2"])
        uc = sap.DatabaseTables.t["Load Pattern Definitions - Auto Seismic - User Coefficient"][1]
        self.assertEqual({r["BotStory"] for r in uc}, {"S1"})                                  # fortele seismice incep deasupra ±0.00
        self.assertEqual(uc[0]["TopStory"], "E1")

    def test_perimeter_walls_and_interior_columns(self):
        sap, res = self.build()
        o = res["objects"]
        self.assertEqual(o["pereti_subsol"], 8 * 2)                                           # perimetru: 2 deschideri x 4 laturi, 2 niveluri
        self.assertEqual(o["stalpi"], 1 * 2 + 9 * 2)                                          # subsol: doar nodul interior; deasupra: toate 9 noduri
        self.assertEqual(len(sap.calls("PropArea.SetWall")), 1)
        self.assertEqual(sap.calls("PropArea.SetWall")[0][0], "WB30")

    def test_soil_pressure_is_inward_on_every_side(self):
        sap, _ = self.build(soil_pressure=20.0)
        loads = [a for a in sap.calls("AreaObj.SetLoadUniform") if a[1] == SOIL_PATTERN]
        self.assertEqual(len(loads), 16)
        self.assertEqual({a[2] for a in loads}, {-20.0, 20.0})
        self.assertTrue(all(a[3] == 3 and a[5] == "Local" for a in loads))
        pairs = {(a[2] > 0) for a in loads}
        self.assertEqual(pairs, {True, False})

    def test_combinations_include_pressure_only_in_uls_and_sls(self):
        sap, _ = self.build()
        combos = {a[0] for a in sap.calls("RespCombo.SetCaseList") if a[2] == SOIL_PATTERN}
        self.assertEqual(combos, {"ULS", "SLS_CAR", "SLS_QP"})

    def test_project_params_declare_basement(self):
        _, res = self.build()
        p = res["project"]
        self.assertEqual((p["basement"], p["basement_stories"], p["ground_story"]), ("da", ["S1", "S2"], "P"))

    def test_invalid(self):
        for bad in (dict(basement=5), dict(basement=1, basement_height=0), dict(shape="L", cut_bays=9), dict(shape="x")):
            with self.assertRaises(GenError):
                FrameSpec(stories=3, bays=3, travei=3, **bad).validate()


if __name__ == "__main__":
    unittest.main()
