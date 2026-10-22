import unittest

from tests.test_verifier_multitower import go, story_defs
from tests.test_verifier_phase1 import df
from tests.test_verifier_phase4 import PostSnap


def modal(n_modes, towers=("T1",), stories=("E3", "E2", "E1", "P", "S2", "S1")):
    return {"Load Case Definitions - Summary": df([dict(Name="Modal", Type="Modal - Eigen")]),
            "Modal Case Definitions - Eigen": df([dict(Name="Modal", MaxModes=n_modes)]), "Story Definitions": story_defs(towers, stories)}


class ModesAboveGroundTests(unittest.TestCase):
    PROJECT = {"basement": "da", "basement_stories": ["S1", "S2"]}

    def test_basement_stories_do_not_count(self):
        self.assertEqual(go(modal(12), "r10_moduri", self.PROJECT)["status"], "ok")                 # 4 etaje peste teren x 3
        r = go(modal(9), "r10_moduri", self.PROJECT)
        self.assertEqual(r["status"], "error")
        self.assertIn("pentru 4 etaje", r["findings"][0]["message"])

    def test_without_declared_basement_all_stories_count(self):
        self.assertEqual(go(modal(12), "r10_moduri")["status"], "error")                            # 6 etaje x 3 = 18
        self.assertEqual(go(modal(18), "r10_moduri")["status"], "ok")

    def test_multi_tower_uses_the_tallest_tower(self):
        t = modal(15, towers=("T1", "T2"))
        self.assertEqual(go(t, "r10_moduri", self.PROJECT)["status"], "ok")                         # 4 etaje pe turn (nu 8 randuri)


class TorsionIgnoresBasementTests(unittest.TestCase):
    def _tables(self):
        lp = df([dict(Name="EXP", Type="Seismic", SelfWtMult=0, IsAuto="Yes", AutoLoad="User Coefficient")])
        auto = df([dict(Name="EXP", IsAuto="No", XDir="No", XDirPlusE="Yes", XDirMinusE="No", YDir="No", YDirPlusE="No", YDirMinusE="No", EccRatio=0.05)])
        drifts = df([dict(Story="S1", OutputCase="EXP", Direction="X", Ratio=2.5), dict(Story="E1", OutputCase="EXP", Direction="X", Ratio=1.1)])
        return {"Load Pattern Definitions": lp, "Load Pattern Definitions - Auto Seismic - User Coefficient": auto,
                "Story Max Over Avg Drifts": drifts, "Story Definitions": story_defs(("T1",), ("E1", "P", "S1"))}

    def test_rigid_box_ratio_is_ignored_when_basement_is_declared(self):
        t = self._tables()
        self.assertEqual(go(t, "r21_torsiune_etaj", {"basement": "da", "basement_stories": ["S1"]}, snap_cls=PostSnap, cases=["EXP"])["status"], "info")
        self.assertEqual(go(t, "r21_torsiune_etaj", snap_cls=PostSnap, cases=["EXP"])["status"], "error")                # fara subsol declarat se vede 2.5


if __name__ == "__main__":
    unittest.main()
