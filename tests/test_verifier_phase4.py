import tempfile
import unittest
from pathlib import Path

import pandas as pd

from etabs_beams.checker import Extras
from etabs_beams.verifier import Sidecar, run
from tests.test_verifier_phase1 import Snap, df


class PostSnap(Snap):
    """Snapshot de test cu rezultate: tabele per cheie (selectia cazurilor e ignorata)."""

    def __init__(self, tables=None, model=None, analyzed=True, cases=None, combos=()):
        super().__init__(tables, model)
        self.analyzed = analyzed
        self.extras = Extras(analyzed=analyzed, case_status={c: 4 for c in (cases or [])}, combos=list(combos))

    def results_table(self, key, cases=(), combos=()):
        sel = self.tables.get((key, tuple(cases), tuple(combos)))
        return sel if sel is not None else self.table(key)


def go(tables, check_id, project=None, params=None, analyzed=True, cases=None, combos=()):
    store = Sidecar(str(Path(tempfile.mkdtemp()) / "m.EDB"))
    if project:
        store.set_project(project)
    if params:
        store.set_params(params)
    r = run(PostSnap(tables, None, analyzed, cases, combos), store, ids=[check_id])[0]
    assert r["error"] is None, r.get("trace")
    return r


def modal(sum_ux, sum_uy, rz_first=False):
    rows = [dict(Case="Modal", Mode=1, Period=1.0, UX=0.1, UY=0.4, RZ=0.6 if rz_first else 0.01, SumUX=0.1, SumUY=0.4),
            dict(Case="Modal", Mode=2, Period=0.9, UX=0.5, UY=0.1, RZ=0.01, SumUX=0.6, SumUY=0.5),
            dict(Case="Modal", Mode=3, Period=0.3, UX=0.2, UY=0.2, RZ=0.01, SumUX=sum_ux, SumUY=sum_uy)]
    return df(rows)


class PostTests(unittest.TestCase):
    def test_not_analyzed_is_skipped(self):
        self.assertEqual(go({}, "r10_masa_participanta", analyzed=False)["status"], "skipped")

    def test_participating_mass(self):
        self.assertEqual(go({"Modal Participating Mass Ratios": modal(0.95, 0.93)}, "r10_masa_participanta")["status"], "info")
        r = go({"Modal Participating Mass Ratios": modal(0.80, 0.93)}, "r10_masa_participanta")
        self.assertEqual(r["status"], "error")
        self.assertIn("X", r["findings"][0]["message"])
        r = go({"Modal Participating Mass Ratios": modal(0.95, 0.93, rz_first=True)}, "r10_masa_participanta")
        self.assertEqual(r["status"], "warning")                                    # primul mod = torsiune
        third = modal(0.95, 0.93)
        third.loc[third["Mode"] == 3, "RZ"] = 0.7                                   # torsiune la modul 3: situatia normala, fara avertisment
        self.assertEqual(go({"Modal Participating Mass Ratios": third}, "r10_masa_participanta")["status"], "info")

    def test_analysis_messages(self):
        m = df([dict(Type="Information", Message="TOTAL TIME"), dict(Type="Warning", Message="Ill-conditioned matrix at joint 5")])
        r = go({"Analysis Messages": m}, "r25_mesaje_analiza")
        self.assertEqual(r["status"], "error")
        m = df([dict(Type="Warning", Message="Some warning")])
        self.assertEqual(go({"Analysis Messages": m}, "r25_mesaje_analiza")["status"], "warning")

    def test_story_masses(self):
        ms = df([dict(Story="E2", UX=100.0), dict(Story="E1", UX=105.0), dict(Story="S1", UX=400.0), dict(Story="Base", UX=900.0)])
        r = go({"Mass Summary by Story": ms}, "r6_mase_etaj")
        self.assertEqual(r["status"], "warning")
        self.assertIn("E1→S1", r["findings"][0]["message"])
        ms = df([dict(Story="E2", UX=100.0), dict(Story="E1", UX=0.0)])
        self.assertEqual(go({"Mass Summary by Story": ms}, "r6_mase_etaj")["status"], "error")

    def test_cm_cr(self):
        st = df([dict(Story=s, Tower="T1") for s in ("E2", "E1")])
        joints = df([dict(Story="E1", ObjType="Joint", GlobalX=x, GlobalY=0.0, GlobalZ=0.0) for x in (0, 20)])
        ok = df([dict(Story="E1", Diaphragm="D1", XCM=10.0, YCM=0.0, XCR=11.0, YCR=0.0)])
        t = {"Centers Of Mass And Rigidity": ok, "Story Definitions": st, "Objects and Elements - Joints": joints}
        r = go(t, "r21_cm_cr")
        self.assertEqual(r["status"], "warning")                                    # lipseste E2
        t["Story Definitions"] = st[1:]
        self.assertEqual(go(t, "r21_cm_cr")["status"], "info")
        t["Centers Of Mass And Rigidity"] = df([dict(Story="E1", Diaphragm="D1", XCM=10.0, YCM=0.0, XCR=16.0, YCR=0.0)])    # e = 6/20 = 30 %
        self.assertEqual(go(t, "r21_cm_cr")["status"], "warning")
        self.assertEqual(go({}, "r21_cm_cr")["status"], "error")

    def test_missing_cr_is_information_with_any_diaphragm_type(self):
        st = df([dict(Story=s, Tower="T1") for s in ("E2", "E1")])
        cm = df([dict(Story="E1", Diaphragm="D1", XCM=10.0, YCM=0.0, XCR=float("nan"), YCR=float("nan"))])
        t = {"Centers Of Mass And Rigidity": cm, "Story Definitions": st, "Diaphragm Definitions": df([dict(Name="D1", Rigidity="Semi Rigid")])}
        r = go(t, "r21_cm_cr")
        self.assertEqual(r["status"], "info")
        self.assertIn("Semi Rigid", r["findings"][0]["message"])
        t["Diaphragm Definitions"] = df([dict(Name="D1", Rigidity="Rigid")])
        self.assertEqual(go(t, "r21_cm_cr")["status"], "info")                         # nici cu diafragma rigida ETABS nu da mereu CR

    def test_torsion(self):
        auto = df([dict(Name="XP", XDir="No", XDirPlusE="Yes", XDirMinusE="No", YDir="No", YDirPlusE="No", YDirMinusE="No")])
        t = {"Load Pattern Definitions - Auto Seismic - User Coefficient": auto, "Load Pattern Definitions": df([dict(Name="XP", Type="Seismic")]),
             "Story Max Over Avg Drifts": df([dict(Story="E1", OutputCase="XP", Direction="X", Ratio=1.1),
                                              dict(Story="E2", OutputCase="XP", Direction="X", Ratio=1.7)])}
        r = go(t, "r21_torsiune_etaj", cases=["XP"])
        self.assertEqual(r["status"], "error")
        t["Story Max Over Avg Drifts"] = df([dict(Story="E1", OutputCase="XP", Direction="X", Ratio=1.1)])
        self.assertEqual(go(t, "r21_torsiune_etaj", cases=["XP"])["status"], "info")

    def test_dead_reaction_vs_weight(self):
        lp = df([dict(Name="Dead", Type="Dead", SelfWtMult=1)])
        wt = df([dict(Story="E1", ObjectType="Wall", Weight=600.0, FloorArea=100.0), dict(Story="E1", ObjectType="Floor", Weight=400.0, FloorArea=100.0),
                 dict(Story="E1", ObjectType="All", Weight=1000.0, FloorArea=100.0), dict(Story="Total", ObjectType="All", Weight=1000.0, FloorArea=100.0)])
        t = {"Load Pattern Definitions": lp, "Material List by Story": wt}
        ok = go(dict(t, **{"Base Reactions": df([dict(OutputCase="Dead", FZ=980.0)])}), "r22_reactiuni_dead", cases=["Dead"])
        self.assertEqual(ok["status"], "info")                                       # randurile All/Total nu se dubleaza
        dbl = go(dict(t, **{"Base Reactions": df([dict(OutputCase="Dead", FZ=2000.0)])}), "r22_reactiuni_dead", cases=["Dead"])
        self.assertEqual(dbl["status"], "error")
        self.assertIn("dublă", dbl["findings"][0]["message"])

    def test_q_topit_info_and_warning(self):
        lp = df([dict(Name="Dead", Type="Dead", SelfWtMult=1), dict(Name="Util", Type="Live", SelfWtMult=0)])
        lc = df([dict(Name="GC", Type="Linear Add", LoadName="Dead", SF=1.0), dict(Name="GC", Type="", LoadName="Util", SF=1.0)])
        wt = df([dict(Story=s, ObjectType="Floor", Weight=1.0, FloorArea=100.0) for s in ("E2", "E1", "P", "Base")])
        st = df([dict(Story=s, Tower="T1") for s in ("E2", "E1", "P", "S1")])

        def tables(combo_p):
            return {"Load Pattern Definitions": lp, "Load Combination Definitions": lc, "Material List by Story": wt, "Story Definitions": st,
                    ("Story Forces", ("Dead",), ("GC",)): df([dict(Story="P", OutputCase="GC", Location="Bottom", P=combo_p),
                                                              dict(Story="P", OutputCase="Dead", Location="Bottom", P=1800.0)])}   # greutatea proprie = 1800 kN
        proj = {"ground_story": "P", "tip_cladire": "rezidential_cadre"}
        # (3000 - 1800) / 300 m2 = 4 kN/m2  -> sub intervalul 5.0-6.5
        r = go(tables(3000.0), "r22_q_topit", proj, combos=["GC"], cases=["Dead"])
        self.assertEqual(r["status"], "warning")
        self.assertIn("q = 4.00 kN/m²", r["findings"][0]["message"])
        # (3600 - 1800) / 300 = 6 kN/m2 -> in interval
        r = go(tables(3600.0), "r22_q_topit", proj, combos=["GC"], cases=["Dead"])
        self.assertEqual(r["status"], "info")
        self.assertIn("În intervalul tipic", r["findings"][0]["message"])
        # fara avertisment daca parametrul e 0
        r = go(tables(3000.0), "r22_q_topit", proj, params={"r22_q_topit.q_avertisment": 0}, combos=["GC"], cases=["Dead"])
        self.assertEqual(r["status"], "info")

    def test_tension_reactions(self):
        lp = df([dict(Name="Dead", Type="Dead", SelfWtMult=1)])
        lc = df([dict(Name="GC", Type="Linear Add", LoadName="Dead", SF=1.0)])
        jr = df([dict(Story="Base", Label="J1", UniqueName="1", FZ=500.0), dict(Story="Base", Label="J2", UniqueName="2", FZ=-80.0)])
        r = go({"Load Pattern Definitions": lp, "Load Combination Definitions": lc, "Joint Reactions": jr}, "r2_reactiuni_intindere", combos=["GC"])
        self.assertEqual((r["status"], r["findings"][0]["objects"][0]["name"]), ("warning", "2"))

    def test_base_shear_static_dynamic(self):
        auto = df([dict(Name="XP", XDir="No", XDirPlusE="Yes", XDirMinusE="No", YDir="No", YDirPlusE="No", YDirMinusE="No", C=0.166, WeightUsed=1000.0)])
        lp = df([dict(Name="XP", Type="Seismic")])
        cs = df([dict(Name="specx", Type="Response Spectrum")])
        rs = df([dict(Name="specx", LoadName="U1", Function="F", TransAccSF=1.0, ModalCombo="CQC", DirCombo="SRSS", EccenRatio=0.0)])
        br = df([dict(OutputCase="XP", FX=170.0, FY=0.0), dict(OutputCase="specx", FX=120.0, FY=10.0)])
        t = {"Load Pattern Definitions - Auto Seismic - User Coefficient": auto, "Load Pattern Definitions": lp, "Load Case Definitions - Summary": cs,
             "Load Case Definitions - Response Spectrum": rs, "Base Reactions": br}
        r = go(t, "r20_fb_static_dinamic", cases=["XP", "specx"])
        msgs = " ".join(f["message"] for f in r["findings"])
        self.assertIn("0.71", msgs)                                                  # 120 / 170
        self.assertEqual(r["status"], "warning")
        self.assertNotIn("pe Y", msgs)                                               # cazul specx e pe X: nu se compara cu Y

    def test_soft_story(self):
        auto = df([dict(Name="XP", XDir="No", XDirPlusE="Yes", XDirMinusE="No", YDir="No", YDirPlusE="No", YDirMinusE="No")])
        st = df([dict(Story=s, Tower="T1", Height=3.0) for s in ("E3", "E2", "E1")])
        drifts = df([dict(Story="E3", OutputCase="XP", Direction="X", Drift=0.001), dict(Story="E2", OutputCase="XP", Direction="X", Drift=0.001),
                     dict(Story="E1", OutputCase="XP", Direction="X", Drift=0.003)])
        forces = df([dict(Story=s, OutputCase="XP", Location="Bottom", VX=v, VY=0.0) for s, v in (("E3", 100.0), ("E2", 200.0), ("E1", 300.0))])
        t = {"Load Pattern Definitions - Auto Seismic - User Coefficient": auto, "Load Pattern Definitions": df([dict(Name="XP", Type="Seismic")]),
             "Story Definitions": st, "Story Drifts": drifts, "Story Forces": forces}
        r = go(t, "r28_rigiditate_etaj", cases=["XP"])
        self.assertEqual(r["status"], "warning")
        self.assertEqual(r["findings"][0]["data"]["etaje"][0]["etaj"], "E1")


if __name__ == "__main__":
    unittest.main()
