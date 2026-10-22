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
                self._s.setdefault("frames", []).append(f"O{self._s['n']}")
                return [f"O{self._s['n']}", 0]
            if name == "GetPoints":
                if self._p.startswith("AreaObj"):
                    return [4, tuple(f"{a[0]}{c}" for c in "abcd"), 0]
                return [f"P{a[0]}a", f"P{a[0]}b", 0]
            return 0
        return call


class FakeTables:
    """DatabaseTables fals: ApplyEditedTables inlocuieste tabelul intreg, ca in ETABS."""

    def __init__(self, frames_ref=lambda: []):
        self.frames_ref = frames_ref
        self.t = {
            "Analysis Options - Automatic Mesh Settings for Floors": (["MeshOpt", "Localized", "MergeJoints", "MaxMeshSize"],
                                                                      [dict(MeshOpt="General", Localized="No", MergeJoints="No", MaxMeshSize="1.25")]),
            "Analysis Options - Automatic Rectangular Mesh Options for Walls": (["MaxMeshSize"], [dict(MaxMeshSize="1.25")]),
            "Area Assignments - Floor Auto Mesh Options": (["UniqueName", "MeshOption", "Restraints"],
                                                           [dict(UniqueName="1", MeshOption="Default", Restraints="No")]),
            "Frame Assignments - End Length Offsets": (["UniqueName", "OffsetOpt", "OffsetI", "OffsetJ", "RigidFact", "SelfWtOpt"], []),
            "Frame Assignments - Insertion Point": (["UniqueName", "CardinalPt"], []),
            "Mass Source Definition": (["Name", "IsDefault", "IncLateral", "IncVertical", "LumpMass", "SourceSelf", "SourceAdded", "SourceLoads",
                                        "MoveMass", "LoadPattern", "Multiplier"], [dict(Name="MsSrc1", SourceLoads="No")]),
            "Functions - Response Spectrum - User Defined": (["Name", "Period", "Value", "DampRatio"], [dict(Name="UnifRS", Period="0", Value="1", DampRatio="0.05")]),
            "Load Pattern Definitions - Auto Seismic - User Coefficient": (["Name", "IsAuto", "XDir", "XDirPlusE", "XDirMinusE", "YDir", "YDirPlusE",
                                                                           "YDirMinusE", "EccRatio", "TopStory", "BotStory", "C", "K"], []),
        }
        self.pending = []
        self.modal = [dict(Mode=1, Period=0.9, UX=0.0, UY=0.7), dict(Mode=2, Period=0.5, UX=0.6, UY=0.0), dict(Mode=3, Period=0.4, UX=0.0, UY=0.01)]

    def seed_frames(self, names, key):
        """Dupa fiecare AddByCoord ETABS adauga cate o linie in tabelele pe bare (decalaje, punct de insertie), o singura data."""
        if self.t[key][1]:
            return
        if key == "Frame Assignments - End Length Offsets":
            self.t[key][1][:] = [dict(UniqueName=n, OffsetOpt="Auto", OffsetI="0.25", OffsetJ="0.25", RigidFact="0", SelfWtOpt="Auto") for n in names]
        else:
            self.t[key][1][:] = [dict(UniqueName=n, CardinalPt="10 (Centroid)") for n in names]

    def GetTableForEditingArray(self, key, g, v, f, n, d):
        if key in ("Frame Assignments - End Length Offsets", "Frame Assignments - Insertion Point"):
            self.seed_frames(self.frames_ref(), key)
        if key not in self.t:
            return [0, (), 0, (), 1]
        fields, rows = self.t[key]
        return [1, tuple(fields), len(rows), tuple(str(r.get(f, "")) for r in rows for f in fields), 0]

    def SetTableForEditingArray(self, key, v, fields, n, data):
        self.pending.append((key, list(fields), n, list(data)))
        return [v, 0]

    def ApplyEditedTables(self, log, a, b, c, d, e):
        for key, fields, n, data in self.pending:
            self.t[key] = (fields, [dict(zip(fields, data[i * len(fields):(i + 1) * len(fields)])) for i in range(n)])
        self.pending = []
        return [0, 0, 0, 0, "", 0]

    def GetTableForDisplayArray(self, key, g, grp, v, f, n, d):
        if key != "Modal Participating Mass Ratios":
            return [(), 0, (), 1]
        rows = self.modal
        fields = ("Mode", "Period", "UX", "UY")
        return [0, 0, fields, len(rows), tuple(str(r[f]) for r in rows for f in fields), 0]

    def CancelTableEditing(self):
        return 0


class FakeSap:
    def __init__(self, filename=""):
        self.s = {"calls": [], "n": 0}
        self.filename = filename
        for n in ("File", "PropMaterial", "PropFrame", "PropArea", "FrameObj", "AreaObj", "PointObj", "Diaphragm", "View", "RespCombo", "PierLabel", "SpandrelLabel", "Analyze"):
            setattr(self, n, Rec(self.s, n + "."))
        self.LoadPatterns = Rec(self.s, "LoadPatterns.")
        self.LoadCases = type("LC", (), {"ModalEigen": Rec(self.s, "ModalEigen."), "ResponseSpectrum": Rec(self.s, "RS.")})()
        self.Story = type("St", (), {"GetNameList": staticmethod(lambda: self.story_names()), "SetStories_2": staticmethod(self.set_stories)})()
        self.DatabaseTables = FakeTables(lambda: self.s.get("frames", []))

    def set_stories(self, base, n, names, heights, *rest):
        self.s["stories"] = (base, list(names), list(heights))
        return 0

    def story_names(self):
        if "stories" in self.s:
            names = tuple(reversed(self.s["stories"][1]))
            return [len(names), names, 0]
        return [3, ("Story3", "Story2", "Story1"), 0]

    def GetModelIsLocked(self):
        return "Analyze.RunAnalysis" in [n for n, _ in self.s["calls"]] and not self.s.get("unlocked")

    def SetModelIsLocked(self, v):
        self.s["unlocked"] = not v
        return 0

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
        spec.calibrate_static = False
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
