import tempfile
import unittest
from pathlib import Path

from etabs_gen.connect import GenError
from etabs_gen.frames import FrameSpec, build_frame_model, section_names


class Rec:
    """Inregistreaza apelurile; AddByCoord intoarce nume incrementale."""

    def __init__(self, store, prefix=""):
        self._s, self._p = store, prefix

    def __getattr__(self, name):
        def call(*a):
            self._s["calls"].append((self._p + name, a))
            if name == "AddByCoord":
                self._s["n"] += 1
                if self._p.startswith("AreaObj"):
                    return [a[1], a[2], a[3], f"A{self._s['n']}", 0]        # ca in COM real: tablourile ref sunt returnate
                return [f"O{self._s['n']}", 0]
            if name == "GetPoints":
                return [f"P{a[0]}a", f"P{a[0]}b", 0]
            return 0
        return call


class FakeSap:
    def __init__(self, filename=""):
        self.s = {"calls": [], "n": 0}
        self.filename = filename
        for n in ("File", "PropMaterial", "PropFrame", "PropArea", "FrameObj", "AreaObj", "PointObj", "Diaphragm", "LoadPatterns", "View"):
            setattr(self, n, Rec(self.s, n + "."))

    def GetModelFilename(self):
        return self.filename

    def InitializeNewModel(self, u):
        return 0

    def SetPresentUnits(self, u):
        return 0

    def calls(self, name):
        return [a for n, a in self.s["calls"] if n == name]


class FrameModelTests(unittest.TestCase):
    def test_counts_and_geometry(self):
        sap = FakeSap()
        spec = FrameSpec(stories=2, bays=2, travei=3, story_height=3.0, span_x=5.0, span_y=4.0)
        with tempfile.TemporaryDirectory() as d:
            r = build_frame_model(sap, spec, Path(d) / "m.EDB")
        self.assertEqual(r["objects"], {"stalpi": 24, "grinzi": 34, "placi": 12})
        self.assertEqual(r["base_nodes"], 12)
        self.assertEqual(sap.calls("File.NewGridOnly")[0], (2, 3.0, 3.0, 3, 4, 5.0, 4.0))
        cols = [a for a in sap.calls("FrameObj.AddByCoord") if a[2] != a[5]]
        self.assertEqual(len(cols), 24)
        self.assertEqual(sorted({a[5] for a in cols}), [3.0, 6.0])                  # varfurile stalpilor la cotele etajelor
        slabs = sap.calls("AreaObj.AddByCoord")
        self.assertEqual(slabs[0][1:4], ([0.0, 5.0, 5.0, 0.0], [0.0, 0.0, 4.0, 4.0], [3.0] * 4))
        self.assertEqual(len(sap.calls("PointObj.SetRestraint")), 12)
        self.assertEqual(len(sap.calls("AreaObj.SetDiaphragm")), 12)
        self.assertTrue(all(isinstance(a[0], str) for a in sap.calls("AreaObj.SetDiaphragm")))
        self.assertEqual(len(sap.calls("AreaObj.SetLoadUniform")), 24)             # permanent + utila pe fiecare placa
        self.assertEqual(sap.calls("File.Save")[0][0], str(Path(d) / "m.EDB"))

    def test_sections_and_materials(self):
        sap = FakeSap()
        build_frame_model(sap, FrameSpec(stories=1, bays=1, travei=1, column_b=0.4, column_h=0.6, beam_b=0.25, beam_h=0.5, concrete="C30/37"))
        self.assertEqual(section_names(FrameSpec(column_b=0.4, column_h=0.6))["column"], "C40x60")
        self.assertEqual(sap.calls("PropFrame.SetRectangle")[0], ("C40x60", "C30/37", 0.6, 0.4))     # T3 = inaltime, T2 = latime
        self.assertEqual(sap.calls("PropMaterial.SetMPIsotropic")[0][1], 33e6)
        self.assertTrue(sap.calls("Diaphragm.SetDiaphragm")[0][1])                                    # semirigid implicit

    def test_validation(self):
        for bad in (dict(stories=0), dict(bays=0), dict(span_x=-1), dict(concrete="C99"), dict(diaphragm="x")):
            with self.assertRaises(GenError):
                build_frame_model(FakeSap(), FrameSpec(**bad))

    def test_never_replaces_a_users_model(self):
        with self.assertRaises(GenError):
            build_frame_model(FakeSap(r"C:\Users\x\Documents\modelul_meu.EDB"), FrameSpec(stories=1, bays=1, travei=1))


if __name__ == "__main__":
    unittest.main()
