import contextlib
import unittest

from etabs_beams.connection import EtabsError
from etabs_beams.verifier.fixes import FIXES


class Eigen:
    def __init__(self):
        self.modes = {"Modal": [20, 1]}

    def GetNumberModes(self, n):
        return [*self.modes[n], 0]

    def SetNumberModes(self, n, mx, mn):
        self.modes[n] = [mx, mn]
        return 0


class Ritz:
    def __init__(self):
        self.loads = {"Ritz": (["Accel"], ["UZ"], [0], [99.0])}

    def GetLoads(self, n):
        t, nm, c, g = self.loads[n]
        return [len(t), tuple(t), tuple(nm), tuple(c), tuple(g), 0]

    def SetLoads(self, n, k, t, nm, c, g):
        self.loads[n] = (list(t), list(nm), list(c), list(g))
        return 0


class Patterns:
    def __init__(self):
        self.mult = {"Dead": 0.0, "Perm": 1.0}
        self.type = {"Dead": 1, "utila": 1}

    def GetSelfWTMultiplier(self, n):
        return [self.mult[n], 0]

    def SetSelfWTMultiplier(self, n, v):
        self.mult[n] = v
        return 0

    def GetLoadType(self, n):
        return [self.type[n], 0]

    def SetLoadType(self, n, v):
        self.type[n] = v
        return 0


class Analyze:
    def __init__(self):
        self.dof = [True, True, False, True, True, False]

    def GetActiveDOF(self):
        return [tuple(self.dof), 0]

    def SetActiveDOF(self, d):
        self.dof = list(d)
        return 0


class Area:
    def __init__(self):
        self.dia, self.pier = {"A1": "None"}, {"A1": "P08", "A2": "P08"}

    def GetDiaphragm(self, n):
        return [self.dia[n], 0]

    def SetDiaphragm(self, n, d):
        self.dia[n] = d
        return 0

    def GetPier(self, n):
        return [self.pier[n], 0]

    def SetPier(self, n, p):
        self.pier[n] = p
        return 0


class Frame:
    def __init__(self):
        self.rel = {"B1": ([False] * 6, [False] * 6, [0.0] * 6, [0.0] * 6)}

    def GetReleases(self, n):
        a = self.rel[n]
        return [tuple(a[0]), tuple(a[1]), tuple(a[2]), tuple(a[3]), 0]

    def SetReleases(self, n, ii, jj, sv, ev):
        self.rel[n] = (list(ii), list(jj), list(sv), list(ev))
        return 0


class Tables:
    """DatabaseTables fals: tabele ca liste de dict; Set + Apply scriu randurile dupa cheie."""

    def __init__(self, tables):
        self.t, self.pending = tables, None

    def GetTableForEditingArray(self, key, group, v, f, n, d):
        rows = self.t[key]["rows"]
        fields = self.t[key]["fields"]
        return [1, tuple(fields), len(rows), tuple(str(r[f]) for r in rows for f in fields), 0]

    def SetTableForEditingArray(self, key, v, fields, n, data):
        self.pending = (key, list(fields), n, list(data))
        return [v, 0]

    def ApplyEditedTables(self, log, a, b, c, d, e):
        """Ca in ETABS: tabelul intreg se inlocuieste cu randurile trimise (cele netrimise se sterg)."""
        key, fields, n, data = self.pending
        self.t[key]["rows"][:] = [dict(zip(fields, data[i * len(fields):(i + 1) * len(fields)])) for i in range(n)]
        return [0, 0, 0, 0, "", 0]

    def CancelTableEditing(self):
        return 0


class Model:
    def __init__(self, locked, tables=None):
        self.locked = locked
        self.LoadCases = type("LC", (), {"ModalEigen": Eigen(), "ModalRitz": Ritz()})()
        self.LoadPatterns, self.Analyze, self.AreaObj, self.FrameObj = Patterns(), Analyze(), Area(), Frame()
        self.PierLabel = type("PL", (), {"SetPier": staticmethod(lambda n: 0)})()
        self.DatabaseTables = Tables(tables or {})

    def GetModelIsLocked(self):
        return self.locked

    def SetModelIsLocked(self, v):
        self.locked = v
        return 0


class Session:
    def __init__(self, model):
        self.model = model

    def units(self):
        return contextlib.nullcontext()


def roundtrip(fix_id, session, args):
    fx = FIXES[fix_id]
    fx.preview(session, args)
    undo = fx.apply(session, args)
    return fx, undo


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
        from tests.test_verifier_phase1 import df
        from tests.test_verifier_multitower import go, story_defs
        t = {"Load Case Definitions - Summary": df([dict(Name="Modal", Type="Modal - Eigen")]),
             "Modal Case Definitions - Eigen": df([dict(Name="Modal", MaxModes=5)]), "Story Definitions": story_defs(("T1",), ("E3", "E2", "E1"))}
        r = go(t, "r10_moduri")
        self.assertEqual(r["findings"][0]["fix"]["args"], {"cases": [{"name": "Modal", "max": 9}]})


class SimpleFixTests(unittest.TestCase):
    def check_undo(self, fix_id, args, get):
        m = Model(True)
        s = Session(m)
        before = get(m)
        fx, undo = roundtrip(fix_id, s, args)
        self.assertNotEqual(get(m), before)
        self.assertFalse(m.locked)
        fx.undo(s, undo)
        self.assertEqual(get(m), before)

    def test_ritz_adds_missing_accelerations_and_undo(self):
        self.check_undo("ritz_add_accel", {"cases": [{"name": "Ritz", "missing": ["X", "Y"]}]},
                        lambda m: m.LoadCases.ModalRitz.loads["Ritz"])
        m = Model(False)
        roundtrip("ritz_add_accel", Session(m), {"cases": [{"name": "Ritz", "missing": ["X", "Y"]}]})
        self.assertEqual(m.LoadCases.ModalRitz.loads["Ritz"][1], ["UZ", "UX", "UY"])

    def test_selfweight(self):
        self.check_undo("set_selfwt", {"set": {"Dead": 1.0, "Perm": 0.0}}, lambda m: dict(m.LoadPatterns.mult))

    def test_dof(self):
        self.check_undo("set_dof_all", {}, lambda m: list(m.Analyze.dof))

    def test_load_types_reject_unknown(self):
        self.check_undo("set_load_types", {"rows": [{"name": "utila", "type": "Live"}]}, lambda m: dict(m.LoadPatterns.type))
        with self.assertRaises(EtabsError):
            FIXES["set_load_types"].apply(Session(Model(False)), {"rows": [{"name": "utila", "type": "Nimic"}]})
        p = FIXES["set_load_types"].preview(Session(Model(False)), {"rows": [{"name": "utila", "type": "Live"}]})
        self.assertEqual(p["rows"]["items"][0]["current"], "Dead")

    def test_diaphragm(self):
        self.check_undo("assign_diaphragm", {"assign": [{"name": "A1", "diaphragm": "D1"}]}, lambda m: dict(m.AreaObj.dia))

    def test_piers(self):
        self.check_undo("rename_piers", {"renames": [{"name": "A1", "pier": "T2_P08"}]}, lambda m: dict(m.AreaObj.pier))

    def test_release_secondary_sets_m3_at_chosen_end_only(self):
        args = {"ends": [{"name": "B1", "end": "J"}], "k": 0}
        self.check_undo("release_secondary", args, lambda m: m.FrameObj.rel["B1"])
        m = Model(False)
        roundtrip("release_secondary", Session(m), args)
        ii, jj, _sv, _ev = m.FrameObj.rel["B1"]
        self.assertEqual((ii[5], jj[5]), (False, True))
        with self.assertRaises(EtabsError):
            FIXES["release_secondary"].apply(Session(Model(False)), {"ends": [], "k": -1})


class TableFixTests(unittest.TestCase):
    def tables(self):
        return {"Frame Assignments - End Length Offsets": {"key": "UniqueName", "fields": ["UniqueName", "OffsetOpt", "RigidFact"],
                                                           "rows": [{"UniqueName": "1", "OffsetOpt": "Auto", "RigidFact": "0"},
                                                                    {"UniqueName": "2", "OffsetOpt": "Auto", "RigidFact": "0"}]},
                "Point Object Connectivity": {"key": "UniqueName", "fields": ["UniqueName", "X", "Y", "Z"],
                                              "rows": [{"UniqueName": "7", "X": "0.00003", "Y": "3.00004", "Z": "4"}]},
                "Analysis Options - Automatic Mesh Settings for Floors": {"key": None, "fields": ["MeshOpt", "Localized", "MergeJoints", "MaxMeshSize"],
                                                                         "rows": [{"MeshOpt": "General", "Localized": "No", "MergeJoints": "Yes", "MaxMeshSize": "1"}]},
                "Area Assignments - Wall Auto Mesh Options": {"key": "UniqueName", "fields": ["UniqueName", "MeshOption", "Restraints"],
                                                              "rows": [{"UniqueName": "W1", "MeshOption": "Auto Rectangular", "Restraints": "Yes"},
                                                                       {"UniqueName": "W2", "MeshOption": "Default", "Restraints": "Yes"}]}}

    def test_rigid_factor_only_listed_rows_and_undo(self):
        m = Model(True, self.tables())
        fx, undo = roundtrip("set_rigid_factor", Session(m), {"frames": ["1"], "factor": 0.75})
        rows = m.DatabaseTables.t["Frame Assignments - End Length Offsets"]["rows"]
        self.assertEqual([r["RigidFact"] for r in rows], ["0.75", "0"])
        self.assertEqual(len(rows), 2)                                               # nicio inregistrare stearsa
        fx.undo(Session(m), undo)
        rows = m.DatabaseTables.t["Frame Assignments - End Length Offsets"]["rows"]
        self.assertEqual([r["RigidFact"] for r in rows], ["0", "0"])
        with self.assertRaises(EtabsError):
            FIXES["set_rigid_factor"].apply(Session(m), {"frames": ["1"], "factor": 2})

    def test_nodes_zero_and_rounding_with_manual_value(self):
        m = Model(False, self.tables())
        rows = [{"name": "7", "axis": "X", "current": 0.00003, "value": 0.0}, {"name": "7", "axis": "Y", "current": 3.00004, "value": 3.0005}]
        p = FIXES["move_nodes"].preview(Session(m), {"rows": rows})
        self.assertEqual([i["kind"] for i in p["rows"]["items"]], ["→ 0 exact", "rotunjit la 1 mm"])
        fx, undo = roundtrip("move_nodes", Session(m), {"rows": rows})
        pt = m.DatabaseTables.t["Point Object Connectivity"]["rows"][0]
        self.assertEqual((pt["X"], pt["Y"], pt["Z"]), ("0", "3.0005", "4"))
        fx.undo(Session(m), undo)
        pt = m.DatabaseTables.t["Point Object Connectivity"]["rows"][0]
        self.assertEqual((pt["X"], pt["Y"]), ("0.00003", "3.00004"))

    def test_mesh_standard_changes_only_differences(self):
        m = Model(False, self.tables())
        fx, undo = roundtrip("apply_mesh_standard", Session(m), {"scope": "floor_global", "mesh_max": 0.5})
        row = m.DatabaseTables.t["Analysis Options - Automatic Mesh Settings for Floors"]["rows"][0]
        self.assertEqual((row["MeshOpt"], row["Localized"], row["MergeJoints"], row["MaxMeshSize"]), ("Rectangular", "Yes", "Yes", "0.5"))
        fx.undo(Session(m), undo)
        row = m.DatabaseTables.t["Analysis Options - Automatic Mesh Settings for Floors"]["rows"][0]
        self.assertEqual((row["MeshOpt"], row["Localized"], row["MaxMeshSize"]), ("General", "No", "1"))
        fx, undo = roundtrip("apply_mesh_standard", Session(m), {"scope": "wall_areas"})
        walls = m.DatabaseTables.t["Area Assignments - Wall Auto Mesh Options"]["rows"]
        self.assertEqual([w["MeshOption"] for w in walls], ["Default", "Default"])
        self.assertEqual(list(undo["old"]), ["W1"])


class CheckOffersTests(unittest.TestCase):
    def test_selfweight_and_load_type_findings_carry_fixes(self):
        from tests.test_verifier_phase1 import df
        from tests.test_verifier_multitower import go
        lp = df([dict(Name="Dead", Type="Dead", SelfWtMult=0.0, IsAuto="No", AutoLoad="None"),
                 dict(Name="utila A", Type="Dead", SelfWtMult=0.0, IsAuto="No", AutoLoad="None")])
        r = go({"Load Pattern Definitions": lp}, "r22_greutate_proprie")
        self.assertEqual(r["findings"][0]["fix"]["args"], {"set": {"Dead": 1.0}})
        r = go({"Load Pattern Definitions": lp}, "r7_tipare")
        fixes = [f["fix"] for f in r["findings"] if f.get("fix")]
        self.assertEqual(fixes[0]["args"]["rows"], [{"name": "utila A", "type": "Live"}])

    def test_multiple_selfweight_keeps_primary(self):
        from tests.test_verifier_phase1 import df
        from tests.test_verifier_multitower import go
        lp = df([dict(Name="Dead", Type="Dead", SelfWtMult=1.0, IsAuto="No", AutoLoad="None"),
                 dict(Name="Perm", Type="Dead", SelfWtMult=1.0, IsAuto="No", AutoLoad="None")])
        r = go({"Load Pattern Definitions": lp}, "r22_greutate_proprie")
        self.assertEqual(r["findings"][0]["fix"]["args"], {"set": {"Perm": 0.0, "Dead": 1.0}})

    def test_dof_finding_carries_fix(self):
        from tests.test_verifier_phase1 import df
        from tests.test_verifier_multitower import go
        t = {"Analysis Options - Active Degrees of Freedom": df([dict(UX="Yes", UY="Yes", UZ="No", RX="Yes", RY="Yes", RZ="Yes")])}
        self.assertEqual(go(t, "r21_dof_diafragme")["findings"][0]["fix"]["id"], "set_dof_all")


if __name__ == "__main__":
    unittest.main()
