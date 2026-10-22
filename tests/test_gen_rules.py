import unittest

from etabs_gen.connect import GenError
from etabs_gen.frames import FrameSpec, build_frame_model
from etabs_gen.seismic import SeismicParams, combos, seismic_coefficient, sd, spectrum_points
from tests.test_gen_frames import FakeSap


class SeismicMathTests(unittest.TestCase):
    P = SeismicParams(ag=0.2, gamma_I=1.0, beta0=2.5, Tb=0.07, Tc=0.7, Td=3.0, q=3.5)

    def test_spectrum_corners_and_floor(self):
        self.assertAlmostEqual(sd(0, self.P), 0.2 * 9.81, 6)                                  # Sd(0) = ag·g
        self.assertAlmostEqual(sd(0.4, self.P), 0.2 * 9.81 * 2.5 / 3.5, 6)                    # platou β0/q
        self.assertAlmostEqual(sd(6.0, self.P), 0.2 * 9.81 * 0.2, 6)                          # minim 0.2·ag·g
        pts = dict(spectrum_points(self.P))
        for t in (0.0, 0.07, 0.7, 3.0, 6.0):
            self.assertIn(t, pts)

    def test_coefficient_is_plateau_with_lambda(self):
        self.assertAlmostEqual(seismic_coefficient(self.P), 0.85 * 0.2 * 2.5 / 3.5, 5)

    def test_combo_counts_and_structure(self):
        cs = dict(combos(True, ["EXP", "EXN", "EYP", "EYN"], ["SPECX", "SPECY"], self.P))
        self.assertEqual(len(cs), 3 + 8 + 32 + 4)                                             # ULS/SLS + pure + ortogonale + spectru
        self.assertEqual(cs["ULS"], [("Dead", 1.35), ("Permanenta", 1.35), ("Live", 1.5)])
        self.assertEqual(cs["SLS_QP"][-1], ("Live", 0.3))
        orth = cs["S_+EXP_-0.3EYN"]
        self.assertEqual(orth[-2:], [("EXP", 1.0), ("EYN", -0.3)])
        self.assertTrue(all(c[:3] == [("Dead", 1.0), ("Permanenta", 1.0), ("Live", 0.3)] for n, c in cs.items() if n.startswith("S_")))


class EngineTests(unittest.TestCase):
    def build(self, **kw):
        sap = FakeSap()
        res = build_frame_model(sap, FrameSpec(stories=3, bays=2, travei=2, **kw))
        return sap, res

    def test_cracking_modifiers_reduce_I_and_J(self):
        sap, _ = self.build()
        mods = {a[0]: a[1] for a in sap.calls("PropFrame.SetModifiers")}
        self.assertEqual(mods["C50x50"], [1.0, 1.0, 1.0, 0.1, 0.7, 0.7, 1.0, 1.0])
        self.assertEqual(mods["B30x60"], [1.0, 1.0, 1.0, 0.1, 0.5, 0.5, 1.0, 1.0])
        self.assertEqual(sap.calls("PropArea.SetModifiers")[0][1][3:6], [0.5, 0.5, 0.5])

    def test_rigid_zones_on_every_frame_via_table(self):
        sap, res = self.build(rigid_zone=0.6)
        rows = sap.DatabaseTables.t["Frame Assignments - End Length Offsets"][1]
        self.assertEqual(len(rows), res["objects"]["stalpi"] + res["objects"]["grinzi"])
        self.assertTrue(all(r["RigidFact"] == "0.6" and r["OffsetOpt"] == "Auto" for r in rows))
        self.assertEqual(sap.calls("FrameObj.SetEndLengthOffset"), [])                       # API-ul ignora RZ la offset automat

    def test_mesh_and_mass_source_tables(self):
        sap, _ = self.build()
        t = sap.DatabaseTables.t
        fl = t["Analysis Options - Automatic Mesh Settings for Floors"][1][0]
        self.assertEqual((fl["MeshOpt"], fl["Localized"], fl["MergeJoints"], fl["MaxMeshSize"]), ("Rectangular", "Yes", "Yes", "0.5"))
        self.assertEqual(t["Analysis Options - Automatic Rectangular Mesh Options for Walls"][1][0]["MaxMeshSize"], "0.5")
        area = t["Area Assignments - Floor Auto Mesh Options"][1][0]
        self.assertEqual((area["MeshOption"], area["Restraints"]), ("Default", "Yes"))
        ms = t["Mass Source Definition"][1]
        self.assertEqual([(r["LoadPattern"], r["Multiplier"]) for r in ms], [("Permanenta", "1"), ("Live", "0.3")])
        self.assertEqual((ms[0]["SourceSelf"], ms[0]["SourceLoads"]), ("Yes", "Yes"))

    def test_modes_spectrum_cases_patterns_and_combos(self):
        sap, res = self.build()
        self.assertEqual(sap.calls("ModalEigen.SetNumberModes")[0], ("Modal", 9, 1))
        fn = [r for r in sap.DatabaseTables.t["Functions - Response Spectrum - User Defined"][1] if r["Name"] == "SPECTRU_P100"]
        self.assertEqual(float(fn[0]["Value"]), round(0.2 * 9.81, 5))
        self.assertEqual(fn[0]["DampRatio"], "0.05")
        loads = sap.calls("RS.SetLoads")
        self.assertEqual([(a[0], a[2], a[4]) for a in loads], [("SPECX", ["U1", "U2"], [1.0, 0.3]), ("SPECY", ["U2", "U1"], [1.0, 0.3])])
        self.assertEqual([a[1] for a in sap.calls("RS.SetEccentricity")], [0.05, 0.05])
        uc = sap.DatabaseTables.t["Load Pattern Definitions - Auto Seismic - User Coefficient"][1]
        self.assertEqual([r["Name"] for r in uc], ["EXP", "EXN", "EYP", "EYN"])
        self.assertEqual((uc[1]["XDirMinusE"], uc[1]["XDirPlusE"], uc[3]["YDirMinusE"]), ("Yes", "No", "Yes"))
        self.assertEqual((uc[0]["TopStory"], uc[0]["BotStory"], uc[0]["EccRatio"]), ("Story3", "Base", "0.05"))
        self.assertEqual(len(sap.calls("RespCombo.Add")), 47)
        self.assertEqual(res["project"]["ag"], 0.2)
        self.assertEqual(res["project"]["lambda_mfse"], 0.85)

    def test_static_coefficient_is_calibrated_to_each_directions_t1(self):
        import tempfile
        from pathlib import Path
        sap = FakeSap()
        spec = FrameSpec(stories=3, bays=2, travei=2)
        with tempfile.TemporaryDirectory() as d:
            res = build_frame_model(sap, spec, Path(d) / "m.EDB")
        uc = {r["Name"]: float(r["C"]) for r in sap.DatabaseTables.t["Load Pattern Definitions - Auto Seismic - User Coefficient"][1]}
        p = SeismicParams()
        self.assertEqual(sap.calls("Analyze.RunAnalysis"), [()])
        self.assertAlmostEqual(uc["EXP"], round(0.85 * sd(0.5, p) / 9.81, 5), 5)          # X: modul dominant 0.5 s (platou)
        self.assertAlmostEqual(uc["EYN"], round(0.85 * sd(0.9, p) / 9.81, 5), 5)          # Y: modul dominant 0.9 s (> TC): C mai mic
        self.assertLess(uc["EYN"], uc["EXP"])
        self.assertTrue(any("forțe statice calibrate" in n for n in res["notes"]))
        self.assertEqual(len(sap.calls("File.Save")), 2)                                     # salvat inainte si dupa calibrare

    def test_calibration_can_be_disabled(self):
        import tempfile
        from pathlib import Path
        sap = FakeSap()
        with tempfile.TemporaryDirectory() as d:
            build_frame_model(sap, FrameSpec(stories=3, bays=2, travei=2, calibrate_static=False), Path(d) / "m.EDB")
        self.assertEqual(sap.calls("Analyze.RunAnalysis"), [])

    def test_gravity_only_model(self):
        sap, res = self.build(seismic=False)
        self.assertEqual(len(sap.calls("RespCombo.Add")), 3)
        self.assertEqual(res["project"], {})
        self.assertEqual(sap.calls("RS.SetCase"), [])

    def test_validation_of_new_fields(self):
        for bad in (dict(crack_beam_I=0), dict(crack_slab=1.5), dict(mesh_max=0), dict(modes_per_story=0), dict(Tb=1.0, Tc=0.7), dict(q=-1)):
            with self.assertRaises(GenError):
                build_frame_model(FakeSap(), FrameSpec(stories=1, bays=1, travei=1, **bad))


if __name__ == "__main__":
    unittest.main()


class VerifierSectionCrackingTests(unittest.TestCase):
    """Modificatorii setati direct pe sectiuni (cum ii scrie generatorul) trebuie recunoscuti de verificator."""

    def test_section_level_modifiers_detected(self):
        from tests.test_verifier_multitower import go
        from tests.test_verifier_phase1 import df
        beams = df([dict(Name="B30x60", AMod=1, A2Mod=1, A3Mod=1, JMod=0.1, I2Mod=0.5, I3Mod=0.5, MMod=1, WMod=1),
                    dict(Name="ConcBm", AMod=1, A2Mod=1, A3Mod=1, JMod=1, I2Mod=1, I3Mod=1, MMod=1, WMod=1)])
        r = go({"Frame Section Property Definitions - Concrete Rectangular": beams}, "r1_fisurare")
        self.assertEqual([f["severity"] for f in r["findings"]], ["info"])
        self.assertIn("modificatori de secțiune", r["findings"][0]["message"])

    def test_inertia_reduced_but_torsion_not(self):
        from tests.test_verifier_multitower import go
        from tests.test_verifier_phase1 import df
        beams = df([dict(Name="B30x60", AMod=1, A2Mod=1, A3Mod=1, JMod=1, I2Mod=0.5, I3Mod=0.5, MMod=1, WMod=1)])
        r = go({"Frame Section Property Definitions - Concrete Rectangular": beams}, "r1_fisurare")
        self.assertTrue(any("torsiune J = 1" in f["message"] for f in r["findings"]))

    def test_shell_modifiers_count(self):
        from tests.test_verifier_multitower import go
        from tests.test_verifier_phase1 import df
        slab = df([dict(Name="P15", f11Mod=1, f22Mod=1, f12Mod=1, m11Mod=0.5, m22Mod=0.5, m12Mod=0.5, v13Mod=1, v23Mod=1)])
        r = go({"Slab Property Definitions": slab}, "r1_fisurare")
        self.assertEqual(r["findings"][0]["severity"], "info")
