import unittest

from tests.test_verifier_multitower import go
from tests.test_verifier_phase1 import df


class VerifierSectionCrackingTests(unittest.TestCase):
    """Modificatorii setati direct pe sectiuni (cum ii scrie generatorul) trebuie recunoscuti de verificator."""

    def test_section_level_modifiers_detected(self):
        beams = df([dict(Name="B30x60", AMod=1, A2Mod=1, A3Mod=1, JMod=0.1, I2Mod=0.5, I3Mod=0.5, MMod=1, WMod=1),
                    dict(Name="ConcBm", AMod=1, A2Mod=1, A3Mod=1, JMod=1, I2Mod=1, I3Mod=1, MMod=1, WMod=1)])
        r = go({"Frame Section Property Definitions - Concrete Rectangular": beams}, "r1_fisurare")
        self.assertEqual([f["severity"] for f in r["findings"]], ["info"])
        self.assertIn("modificatori de secțiune", r["findings"][0]["message"])

    def test_inertia_reduced_but_torsion_not(self):
        beams = df([dict(Name="B30x60", AMod=1, A2Mod=1, A3Mod=1, JMod=1, I2Mod=0.5, I3Mod=0.5, MMod=1, WMod=1)])
        r = go({"Frame Section Property Definitions - Concrete Rectangular": beams}, "r1_fisurare")
        self.assertTrue(any("torsiune J = 1" in f["message"] for f in r["findings"]))

    def test_shell_modifiers_count(self):
        slab = df([dict(Name="P15", f11Mod=1, f22Mod=1, f12Mod=1, m11Mod=0.5, m22Mod=0.5, m12Mod=0.5, v13Mod=1, v23Mod=1)])
        r = go({"Slab Property Definitions": slab}, "r1_fisurare")
        self.assertEqual(r["findings"][0]["severity"], "info")


if __name__ == "__main__":
    unittest.main()
