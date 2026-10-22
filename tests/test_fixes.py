import unittest

from etabs_beams.verifier.fixes import FIXES


class Eigen:
    def __init__(self):
        self.modes = {"Modal": [20, 1]}

    def GetNumberModes(self, n):
        return [*self.modes[n], 0]

    def SetNumberModes(self, n, mx, mn):
        self.modes[n] = [mx, mn]
        return 0


class Model:
    def __init__(self, locked):
        self.locked = locked
        self.LoadCases = type("LC", (), {"ModalEigen": Eigen()})()

    def GetModelIsLocked(self):
        return self.locked

    def SetModelIsLocked(self, v):
        self.locked = v
        return 0


class Session:
    def __init__(self, model):
        self.model = model


class ModalFixTests(unittest.TestCase):
    ARGS = {"cases": [{"name": "Modal", "max": 168}]}

    def test_preview_does_not_write(self):
        m = Model(True)
        p = FIXES["set_modal_modes"].preview(Session(m), self.ARGS)
        self.assertEqual((p["changes"][0]["before"], p["changes"][0]["after"], p["unlocks"]), (20, 168, True))
        self.assertTrue(m.locked)
        self.assertEqual(m.LoadCases.ModalEigen.modes["Modal"], [20, 1])

    def test_apply_unlocks_and_undo_restores(self):
        m = Model(True)
        fx, s = FIXES["set_modal_modes"], Session(m)
        undo = fx.apply(s, self.ARGS)
        self.assertFalse(m.locked)
        self.assertEqual(m.LoadCases.ModalEigen.modes["Modal"], [168, 1])
        fx.undo(s, undo)
        self.assertEqual(m.LoadCases.ModalEigen.modes["Modal"], [20, 1])

    def test_check_attaches_fix(self):
        from tests.test_verifier_phase1 import Snap, df
        from tests.test_verifier_multitower import go, story_defs
        t = {"Load Case Definitions - Summary": df([dict(Name="Modal", Type="Modal - Eigen")]),
             "Modal Case Definitions - Eigen": df([dict(Name="Modal", MaxModes=5)]), "Story Definitions": story_defs(("T1",), ("E3", "E2", "E1"))}
        r = go(t, "r10_moduri")
        self.assertEqual(r["findings"][0]["fix"]["args"], {"cases": [{"name": "Modal", "max": 9}]})


if __name__ == "__main__":
    unittest.main()
