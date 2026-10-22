import tempfile
import unittest
from pathlib import Path

from etabs_beams.verifier import Sidecar, run
from etabs_beams.verifier.registry import Ctx
from tests.test_verifier_phase1 import Snap, df
from tests.test_verifier_phase4 import PostSnap


def story_defs(towers=("T1", "T2"), stories=("E2", "E1", "P", "S1")):
    return df([dict(Tower=t, Story=s, Height=3.0) for t in towers for s in stories])


def user_loads(rows):
    """rows: (nume, ecc, story, fx, fy)."""
    out, last = [], None
    for name, ecc, story, fx, fy in rows:
        out.append(dict(Name=name if name != last else "", EccRatio=ecc if name != last else float("nan"), Story=story, Diaphragm="D1", Fx=fx, Fy=fy, Mz=0))
        last = name
    return df(out)


def go(tables, check_id, project=None, snap_cls=Snap, **kw):
    store = Sidecar(str(Path(tempfile.mkdtemp()) / "m.EDB"))
    if project:
        store.set_project(project)
    r = run(snap_cls(tables, **kw), store, ids=[check_id])[0]
    assert r["error"] is None, r.get("trace")
    return r


class CtxTests(unittest.TestCase):
    def test_story_helpers(self):
        c = Ctx(Snap({"Story Definitions": story_defs()}), {}, {"basement": "da", "basement_stories": ["S1"]})
        self.assertEqual(c.stories(), ["E2", "E1", "P", "S1"])                      # unice, nu 8 randuri
        self.assertEqual(c.towers(), ["T1", "T2"])
        self.assertEqual(c.story_id("T2", "P"), "T2-P")
        self.assertEqual(c.plain_story("T2-E1"), "E1")
        self.assertEqual(c.tower_of("T2-E1"), "T2")
        self.assertEqual(c.story_ids(["S1"]), {"S1", "T1-S1", "T2-S1"})
        self.assertEqual(c.ground_story(), "P")
        single = Ctx(Snap({"Story Definitions": story_defs(("T1",))}), {}, {})
        self.assertEqual(single.story_id("T1", "P"), "P")                           # un singur turn: nume simplu

    def test_ground_variants(self):
        sd = {"Story Definitions": story_defs(("T1",))}
        self.assertIsNone(Ctx(Snap(sd), {}, {}).ground_story())
        self.assertEqual(Ctx(Snap(sd), {}, {"basement": "nu"}).ground_story(), "S1")      # doar suprastructura: cel mai de jos nivel
        self.assertEqual(Ctx(Snap(sd), {}, {"ground_story": "E1"}).basement_stories(), ["P", "S1"])


class SeismicUserLoadsTests(unittest.TestCase):
    ROWS = [("T1_XP", 0.05, "T1-E2", 100.0, 0.0), ("T1_XP", 0.05, "T1-E1", 200.0, 0.0), ("T1_XN", -0.05, "T1-E2", 100.0, 0.0),
            ("T1_XN", -0.05, "T1-E1", 200.0, 0.0), ("T1_YP", 0.05, "T1-E2", 0.0, 100.0), ("T1_YN", -0.05, "T1-E2", 0.0, 100.0)]

    def _tables(self, rows):
        return {"Load Pattern Definitions - Auto Seismic - User Loads": user_loads(rows), "Story Definitions": story_defs(("T1", "T2")),
                "Load Pattern Definitions": df([dict(Name=n, Type="Seismic", SelfWtMult=0, IsAuto="No", AutoLoad="User Loads") for n in dict.fromkeys(r[0] for r in rows)])}

    def test_complete_set_is_info(self):
        r = go(self._tables(self.ROWS), "r20_forte_statice")
        self.assertEqual(r["status"], "info")
        self.assertIn("300 kN", r["findings"][-1]["message"])                       # T1_XP: 100 + 200

    def test_missing_pattern_and_wrong_eccentricity(self):
        r = go(self._tables([x for x in self.ROWS if x[0] != "T1_YN"]), "r20_forte_statice", {"ecc": 0.1})
        msgs = " ".join(f["message"] for f in r["findings"])
        self.assertIn("lipsesc", msgs)
        self.assertIn("Y-", msgs)
        self.assertIn("diferă de 0.1", msgs)
        self.assertEqual(r["status"], "warning")

    def test_towers_without_patterns_and_unassigned(self):
        t = self._tables(self.ROWS)
        r = go(t, "r29_seism_pe_turnuri")
        self.assertEqual(r["status"], "warning")
        self.assertIn("T2", r["findings"][0]["message"])                            # T2 nu are tipare seismice
        t["Load Pattern Definitions"] = df([dict(Name="T1_XP", Type="Seismic", SelfWtMult=0, IsAuto="No", AutoLoad="User Loads"),
                                            dict(Name="T2_XP", Type="Seismic", SelfWtMult=0, IsAuto="No", AutoLoad="User Loads")])
        r = go(t, "r29_seism_pe_turnuri")
        self.assertTrue(any("nu au nicio încărcare" in f["message"] for f in r["findings"]))         # T2_XP fara forte
        self.assertEqual(go({"Story Definitions": story_defs(("T1",))}, "r29_seism_pe_turnuri")["status"], "ok")   # un turn: nu se aplica

    def test_basement_forces(self):
        tw = df([dict(Tower="T1", BSName="T1-Base", BSElev=0.0)])
        t = dict(self._tables(self.ROWS + [("T1_XP", 0.05, "T1-S1", 50.0, 0.0)]), **{"Tower and Base Story Definitions": tw})
        proj = {"basement": "da", "basement_stories": ["S1"]}
        r = go(t, "r12_baza_seismica", proj)
        self.assertEqual(r["status"], "error")
        self.assertIn("T1_XP", r["findings"][0]["message"])
        ok_t = dict(self._tables(self.ROWS), **{"Tower and Base Story Definitions": tw})
        self.assertEqual(go(ok_t, "r12_baza_seismica", proj)["status"], "info")

    def test_staged_uses_tallest_tower_not_row_count(self):
        sd = story_defs(("T1", "T2", "T3", "T4"), tuple(f"E{i}" for i in range(10)))          # 40 randuri, dar 10 etaje pe turn
        self.assertEqual(go({"Story Definitions": sd}, "r18_constructie_etapizata")["status"], "ok")


class MultiTowerResultsTests(unittest.TestCase):
    def test_zero_mass_only_where_elements_exist(self):
        ms = df([dict(Story="T1-E1", UX=100.0), dict(Story="T1-Base", UX=900.0), dict(Story="T2-E1", UX=0.0), dict(Story="T2-E2", UX=0.0)])
        wt = df([dict(Story="T1-E1", ObjectType="Floor", Weight=10.0, FloorArea=5.0), dict(Story="T2-E1", ObjectType="Floor", Weight=10.0, FloorArea=5.0)])
        r = go({"Mass Summary by Story": ms, "Material List by Story": wt, "Story Definitions": story_defs(("T1", "T2"), ("E2", "E1"))},
               "r6_mase_etaj", snap_cls=PostSnap)
        msg = r["findings"][0]["message"]
        self.assertEqual(r["findings"][0]["severity"], "error")
        self.assertIn("T2-E1", msg)
        self.assertNotIn("T2-E2", msg)                                              # T2-E2 nu are elemente: turn mai scund

    def test_identical_shear_twins_vs_copied(self):
        auto = df([])
        lp = df([dict(Name=n, Type="Seismic", SelfWtMult=0, IsAuto="No", AutoLoad="User Loads") for n in ("T1_XP", "T3_XP")])
        ul = user_loads([("T1_XP", 0.05, "T1-E1", 10.0, 0.0), ("T3_XP", 0.05, "T3-E1", 10.0, 0.0)])
        br = df([dict(OutputCase="T1_XP", FX=500.0, FY=0.0), dict(OutputCase="T3_XP", FX=500.0, FY=0.0)])
        base = {"Load Pattern Definitions": lp, "Load Pattern Definitions - Auto Seismic - User Loads": ul, "Base Reactions": br,
                "Story Definitions": story_defs(("T1", "T3"), ("E1",))}
        twins = go(dict(base, **{"Mass Summary by Story": df([dict(Story="T1-E1", UX=100.0), dict(Story="T3-E1", UX=100.5)])}),
                   "r29_rezultate_turnuri", snap_cls=PostSnap, cases=["T1_XP", "T3_XP"])
        self.assertEqual(twins["status"], "info")
        copied = go(dict(base, **{"Mass Summary by Story": df([dict(Story="T1-E1", UX=100.0), dict(Story="T3-E1", UX=300.0)])}),
                    "r29_rezultate_turnuri", snap_cls=PostSnap, cases=["T1_XP", "T3_XP"])
        self.assertEqual(copied["status"], "warning")

    def test_torsion_only_on_the_cases_tower(self):
        lp = df([dict(Name="T1_XP", Type="Seismic", SelfWtMult=0, IsAuto="No", AutoLoad="User Loads")])
        ul = user_loads([("T1_XP", 0.05, "T1-E1", 10.0, 0.0)])
        drifts = df([dict(Story="T1-E1", OutputCase="T1_XP", Direction="X", Ratio=1.1),
                     dict(Story="T2-E1", OutputCase="T1_XP", Direction="X", Ratio=20.0)])       # alt turn: neincarcat, raport fara sens
        r = go({"Load Pattern Definitions": lp, "Load Pattern Definitions - Auto Seismic - User Loads": ul, "Story Max Over Avg Drifts": drifts,
                "Story Definitions": story_defs(("T1", "T2"), ("E1",))}, "r21_torsiune_etaj", snap_cls=PostSnap, cases=["T1_XP"])
        self.assertEqual(r["status"], "info")


if __name__ == "__main__":
    unittest.main()
