import tempfile
import unittest
from pathlib import Path

import pandas as pd

from etabs_beams.models import COLUMN, Frame, NULL
from etabs_beams.verifier import Sidecar, run
from tests.builders import Builder


class Snap:
    original_units = 6

    def __init__(self, tables=None, model=None):
        self.cache = {}
        self.tables = tables or {}
        self._model = model

    @property
    def model(self):
        return self._model

    def loaded_model(self):
        return self._model

    def table(self, key):
        return self.tables.get(key, pd.DataFrame())

    def legacy_issues(self):
        return {}


def go(snap, check_id):
    store = Sidecar(str(Path(tempfile.mkdtemp()) / "m.EDB"))
    r = run(snap, store, ids=[check_id])[0]
    assert r["error"] is None, r.get("trace")
    return r


def df(rows):
    return pd.DataFrame(rows)


class AnalysisTests(unittest.TestCase):
    def test_dof_and_diaphragms(self):
        t = {"Analysis Options - Active Degrees of Freedom": df([dict(UX="Yes", UY="Yes", UZ="Yes", RX="Yes", RY="Yes", RZ="No")])}
        r = go(Snap(t), "r21_dof_diafragme")
        self.assertEqual(r["status"], "error")
        self.assertIn("RZ", r["findings"][0]["message"])
        t["Analysis Options - Active Degrees of Freedom"] = df([dict(UX="Yes", UY="Yes", UZ="Yes", RX="Yes", RY="Yes", RZ="Yes")])
        self.assertEqual(go(Snap(t), "r21_dof_diafragme")["status"], "warning")        # fara diafragme
        t["Diaphragm Definitions"] = df([dict(Name="D1", Rigidity="Semi-Rigid")])
        t["Area Assignments - Diaphragms"] = df([dict(UniqueName="1", Diaphragm="D1")])
        self.assertEqual(go(Snap(t), "r21_dof_diafragme")["status"], "ok")

    def _modal(self, modes):
        return {"Load Case Definitions - Summary": df([dict(Name="Modal", Type="Modal - Eigen")]),
                "Modal Case Definitions - Eigen": df([dict(Name="Modal", MaxModes=modes, MassSource="MsSrc1")]),
                "Story Definitions": df([dict(Tower="T1", Story=f"E{i}") for i in range(14)])}

    def test_number_of_modes(self):
        self.assertEqual(go(Snap(self._modal(20)), "r10_moduri")["status"], "error")
        self.assertEqual(go(Snap(self._modal(42)), "r10_moduri")["status"], "ok")
        self.assertEqual(go(Snap({}), "r10_moduri")["status"], "error")                  # nu exista caz modal

    def test_ritz_start_vectors(self):
        bad = {"Modal Case Definitions - Ritz": df([dict(Name="R", LoadType="Acceleration", LoadName="UZ"),
                                                    dict(Name="R", LoadType="Load", LoadName="Dead")])}
        self.assertEqual(go(Snap(bad), "r10_ritz")["status"], "error")
        good = {"Modal Case Definitions - Ritz": df([dict(Name="R", LoadType="Acceleration", LoadName=a) for a in ("UX", "UY", "UZ")])}
        self.assertEqual(go(Snap(good), "r10_ritz")["status"], "ok")

    def test_ritz_accepts_etabs_accel_names(self):
        good = {"Modal Case Definitions - Ritz": df([dict(Name="R", LoadType="Accel", LoadName=f"Accel {a}") for a in ("UX", "UY", "UZ")])}
        self.assertEqual(go(Snap(good), "r10_ritz")["status"], "ok")
        bad = {"Modal Case Definitions - Ritz": df([dict(Name="R", LoadType="Accel", LoadName="Accel UZ")])}
        self.assertEqual(go(Snap(bad), "r10_ritz")["status"], "error")

    def test_ritz_continuation_rows_are_not_separate_cases(self):
        rows = [dict(Name="R", MassSource="Ms", MaxModes=12, LoadType="Accel", LoadName="Accel UX")]
        rows += [dict(Name="R", MassSource="", MaxModes=float("nan"), LoadType="Accel", LoadName=f"Accel {a}") for a in ("UY", "UZ")]
        snap = Snap({"Modal Case Definitions - Ritz": df(rows)})
        self.assertFalse(any("diferite" in f["message"] for f in go(snap, "r6_sursa_masa")["findings"]))
        self.assertEqual(go(snap, "r10_ritz")["status"], "ok")

    def test_pdelta(self):
        self.assertEqual(go(Snap({"P-Delta Option Definition": df([dict(AutoMethod="None")])}), "r10_pdelta")["status"], "warning")
        t = {"P-Delta Option Definition": df([dict(AutoMethod="None")]),
             "Load Case Definitions - Linear Static": df([dict(Name="Dead", StiffType="P-Delta")])}
        self.assertEqual(go(Snap(t), "r10_pdelta")["status"], "info")


class FrameTests(unittest.TestCase):
    def _beams(self):
        b = Builder()
        b.column(0, 0); b.column(10, 0); b.column(5, 6)
        main = b.beam((0, 0, 3), (10, 0, 3))
        sec = b.beam((5, 6, 3), (5, 0, 3), "B30x40")         # se termina pe interiorul grinzii principale
        return b.finish(), main, sec

    def test_releases_torsion_both_ends(self):
        rel = df([dict(UniqueName="7", PI="No", PJ="No", V2I="No", V2J="No", V3I="No", V3J="No", TI="Yes", TJ="Yes",
                       M2I="No", M2J="No", M3I="Yes", M3J="No")])
        self.assertEqual(go(Snap({"Frame Assignments - Releases and Partial Fixity": rel}), "r25_eliberari")["status"], "error")
        rel.loc[0, "TJ"] = "No"
        self.assertEqual(go(Snap({"Frame Assignments - Releases and Partial Fixity": rel}), "r25_eliberari")["status"], "ok")

    def test_secondary_beam_release(self):
        md, main, sec = self._beams()
        r = go(Snap({}, md), "r11_grinzi_secundare")
        self.assertEqual((r["status"], r["findings"][0]["objects"][0]["name"]), ("info", sec))
        end = "I" if md.frames[sec].p1 == md.frames[sec].p1 and md.frames[sec].start[1] == 0 else "J"
        # capatul care atinge grinda principala are y=0
        end = "I" if md.frames[sec].start[1] == 0 else "J"
        row = {k: "No" for k in ("PI", "PJ", "V2I", "V2J", "V3I", "V3J", "TI", "TJ", "M2I", "M2J", "M3I", "M3J")}
        row[f"M3{end}"] = "Yes"
        rel = df([dict(UniqueName=sec, **row)])
        r = go(Snap({"Frame Assignments - Releases and Partial Fixity": rel}, md), "r11_grinzi_secundare")
        self.assertEqual(r["status"], "ok")

    def test_rigid_zones(self):
        md, main, sec = self._beams()
        names = list(md.frames)
        off = df([dict(UniqueName=n, OffsetOpt="Auto", RigidFact=0.0) for n in names])
        r = go(Snap({"Frame Assignments - End Length Offsets": off}, md), "r13_zone_rigide")
        self.assertEqual(r["status"], "warning")
        off["RigidFact"] = 0.5
        self.assertEqual(go(Snap({"Frame Assignments - End Length Offsets": off}, md), "r13_zone_rigide")["status"], "ok")

    def test_column_axes_minority(self):
        b = Builder()
        c1, c2, c3 = b.column(0, 0, angle=0.0), b.column(5, 0, angle=0.0), b.column(10, 0, angle=90.0)
        md = b.finish()
        r = go(Snap({}, md), "r14_axe_locale_stalpi_arii")
        self.assertEqual(r["status"], "warning")
        self.assertEqual([o["name"] for o in r["findings"][0]["objects"]], [c3])

    def test_area_axes_mixed(self):
        b = Builder().finish() if False else Builder()
        md = b.finish()
        sp = df([dict(Story="S1", Label=f"F{i}", UniqueName=str(i), SectProp="PL15", PropType="Slab") for i in range(1, 5)])
        ax = df([dict(Story="S1", Label="F1", UniqueName="1", Angle=90)])
        r = go(Snap({"Area Assignments - Local Axes": ax, "Area Assignments - Section Properties": sp}, md), "r14_axe_locale_stalpi_arii")
        self.assertEqual(r["status"], "warning")
        self.assertEqual(r["findings"][0]["objects"][0]["type"], "area")

    def test_null_frames_with_mass(self):
        b = Builder()
        b.md.frames["99"] = Frame("99", "B99", "S1", "", "a", "b", (0, 0, 3), (5, 0, 3), orientation=NULL)
        md = b.finish()
        add = df([dict(UniqueName="99", Mass=10)])
        self.assertEqual(go(Snap({"Frame Assignments - Additional Mass": add}, md), "r15_null_masa")["status"], "warning")


class GeometryTests(unittest.TestCase):
    def _joints(self, coords):
        return df([dict(Story="S1", ElmName=str(i), ObjType="Joint", ObjLabel=f"J{i}", ObjName=str(i),
                        GlobalX=x, GlobalY=y, GlobalZ=z) for i, (x, y, z) in enumerate(coords, 1)])

    def test_close_nodes(self):
        j = self._joints([(0, 0, 0), (0.01, 0, 0), (5, 0, 0)])
        r = go(Snap({"Objects and Elements - Joints": j, "Preferences - Tolerance": df([dict(MergeTol=0.001)])}), "r5_noduri")
        self.assertEqual(r["status"], "error")
        self.assertEqual({o["name"] for o in r["findings"][0]["objects"]}, {"1", "2"})

    def test_parasitic_decimals(self):
        j = self._joints([(0.00000021, 0, 0), (5, 0, 0)])
        r = go(Snap({"Objects and Elements - Joints": j}), "r5_noduri")
        self.assertEqual(r["status"], "warning")
        self.assertEqual([o["name"] for o in r["findings"][0]["objects"]], ["1"])

    def test_clean_joints_ok(self):
        self.assertEqual(go(Snap({"Objects and Elements - Joints": self._joints([(0, 0, 0), (5, 0, 0), (5, 5, 3.2)])}), "r5_noduri")["status"], "ok")

    def test_mesh_size(self):
        t = {"Analysis Options - Automatic Mesh Settings for Floors": df([dict(MaxMeshSize=2.0)]),
             "Analysis Options - Automatic Rectangular Mesh Options for Walls": df([dict(MaxMeshSize=0.5)])}
        r = go(Snap(t), "r5_mesh")
        self.assertEqual((r["status"], len(r["findings"])), ("warning", 1))

    def test_overlapping_areas(self):
        rows = [dict(Story="S1", ElmName=f"{o}-1", ObjType="Floor", ObjLabel=f"F{o}", ObjName=str(o), ElmJt1="1", ElmJt2="2", ElmJt3="3", ElmJt4="4")
                for o in (10, 11)]
        rows.append(dict(Story="S1", ElmName="12-1", ObjType="Floor", ObjLabel="F12", ObjName="12", ElmJt1="5", ElmJt2="6", ElmJt3="7", ElmJt4="8"))
        r = go(Snap({"Objects and Elements - Areas": df(rows)}), "r5_arii_suprapuse")
        self.assertEqual(r["status"], "error")
        self.assertEqual({o["name"] for o in r["findings"][0]["objects"]}, {"10", "11"})


class MassLoadTests(unittest.TestCase):
    PATTERNS = [dict(Name="Dead", Type="Dead", IsAuto="No", SelfWtMult=1, AutoLoad=""),
                dict(Name="Perm", Type="Dead", IsAuto="No", SelfWtMult=0, AutoLoad=""),
                dict(Name="Util", Type="Live", IsAuto="No", SelfWtMult=0, AutoLoad=""),
                dict(Name="Snow", Type="Live", IsAuto="No", SelfWtMult=0, AutoLoad="")]

    def _ms(self, lateral="Yes", self_mass="Yes", pats=(("Perm", 1.0), ("Util", 0.3))):
        rows = [dict(Name="MsSrc1", IncLateral=lateral, SourceSelf=self_mass, SourceLoads="Yes", LoadPattern=pats[0][0], Multiplier=pats[0][1])]
        rows += [dict(Name="MsSrc1", IncLateral="", SourceSelf="", SourceLoads="", LoadPattern=p, Multiplier=m) for p, m in pats[1:]]
        return df(rows)

    def test_mass_source_ok_and_doubling(self):
        t = {"Mass Source Definition": self._ms(), "Load Pattern Definitions": df(self.PATTERNS)}
        self.assertEqual(go(Snap(t), "r6_sursa_masa")["status"], "ok")
        t["Mass Source Definition"] = self._ms(pats=(("Dead", 1.0), ("Util", 0.3)))           # Dead are greutate proprie
        r = go(Snap(t), "r6_sursa_masa")
        self.assertEqual(r["status"], "error")
        self.assertIn("dublează", r["findings"][0]["message"])

    def test_mass_source_no_lateral_and_big_multiplier(self):
        t = {"Mass Source Definition": self._ms(lateral="No", pats=(("Perm", 1.0), ("Util", 1.5))), "Load Pattern Definitions": df(self.PATTERNS)}
        r = go(Snap(t), "r6_sursa_masa")
        self.assertEqual(r["status"], "error")
        self.assertEqual(len(r["findings"]), 2)

    def test_patterns_unused_and_type(self):
        t = {"Load Pattern Definitions": df(self.PATTERNS),
             "Frame Loads Assignments - Distributed": df([dict(LoadPattern="Perm")])}
        r = go(Snap(t), "r7_tipare")
        msgs = " ".join(f["message"] for f in r["findings"])
        self.assertIn("Util", msgs)                                # fara incarcari asignate
        self.assertIn("Snow", msgs)                                # zapada definita ca Live
        self.assertEqual(r["status"], "warning")

    def test_patterns_via_load_sets(self):
        t = {"Load Pattern Definitions": df(self.PATTERNS[:3]),
             "Area Load Assignments - Uniform Load Sets": df([dict(UniqueName="1", LoadSet="S")]),
             "Shell Uniform Load Sets": df([dict(Name="S", LoadPattern="Perm", LoadValue=3), dict(Name="S", LoadPattern="Util", LoadValue=2)])}
        self.assertEqual(go(Snap(t), "r7_tipare")["status"], "ok")


class CrackingTests(unittest.TestCase):
    def test_no_reduction_warns(self):
        mats = {"Material Properties - General": df([dict(Material="C35/45", Type="Concrete", Grade="C35/45")])}
        self.assertEqual(go(Snap(mats), "r1_fisurare")["status"], "warning")

    def test_factor_in_material_info(self):
        mats = {"Material Properties - General": df([dict(Material="0.5*C35/45", Type="Concrete", Grade="C35/45")])}
        self.assertEqual(go(Snap(mats), "r1_fisurare")["status"], "info")

    def test_both_methods_warn(self):
        t = {"Material Properties - General": df([dict(Material="0.5*C35/45", Type="Concrete", Grade="C35/45")]),
             "Frame Property Modifier Definitions": df([{"Name": "M1", "Area Modifier": 1, "J Modifier": 1, "I33 Modifier": 0.5, "I22 Modifier": 0.5}])}
        r = go(Snap(t), "r1_fisurare")
        self.assertEqual(r["status"], "warning")

    def test_torsion_not_reduced(self):
        t = {"Frame Property Modifier Definitions": df([{"Name": "M1", "Area Modifier": 1, "J Modifier": 1, "I33 Modifier": 0.5, "I22 Modifier": 0.5}])}
        r = go(Snap(t), "r1_fisurare")
        self.assertTrue(any("torsiune" in f["message"] for f in r["findings"]))


if __name__ == "__main__":
    unittest.main()
