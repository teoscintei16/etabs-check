import unittest

from etabs_beams.verifier.checks.shells import inclined_slabs, shell_ribs, shell_stories
from tests.builders import Builder
from tests.test_verifier_phase1 import Snap, df, go
from tests.test_verifier_phase3 import Mesh


def tilted_quad(m: Mesh, name, story, x0, y0, w, h, rise):
    """Placa inclinata: marginea de jos la z = 3, cea de sus la z = 3 + rise."""
    pts = [(x0, y0, 3.0), (x0 + w, y0, 3.0), (x0 + w, y0 + h, 3.0 + rise), (x0, y0 + h, 3.0 + rise)]
    js = [m.jt(*p, story) for p in pts]
    m.areas.append(dict(Story=story, ElmName=f"{name}-1", ObjType="Ramp", ObjLabel=f"L{name}", ObjName=name,
                        ElmJt1=js[0], ElmJt2=js[1], ElmJt3=js[2], ElmJt4=js[3]))


def tables(m: Mesh, names_stories, diaphragms=()):
    asg = df([dict(Story=s, Label=f"L{n}", UniqueName=n, SectProp="P15", PropType="Slab") for n, s in names_stories])
    dsg = df([dict(Story=dict(names_stories)[n], Label=f"L{n}", UniqueName=n, Diaphragm="D1") for n in diaphragms] or [dict(Story="", Label="", UniqueName="", Diaphragm="None")])
    return {**m.tables(), "Area Assignments - Section Properties": asg, "Area Assignments - Diaphragms": dsg,
            "Area Section Property Definitions - Summary": df([dict(Name="P15", Type="Slab", AnalType="Shell-Thin", Material="C25/30", TotalThick=0.15)])}


class ShellSurfaceTests(unittest.TestCase):
    def setUp(self):
        m = Mesh()
        m.rect("1", "Floor", "E1", 0, 0, 5, 5)                                       # placa orizontala, fara diafragma
        tilted_quad(m, "2", "T1", 10, 0, 5, 5, 4.0)                                  # coaja: ~39° fata de orizontala
        tilted_quad(m, "3", "T1", 20, 0, 5, 5, 0.4)                                  # panta mica (4.6°): ramane planseu
        self.snap = Snap(tables(m, [("1", "E1"), ("2", "T1"), ("3", "T1")]))

    def test_only_steeply_inclined_slabs_are_shells(self):
        class Ctx:
            snap = self.snap
        self.assertEqual(inclined_slabs(Ctx), {"2"})

    def test_missing_diaphragm_is_an_error_for_floors_but_info_for_shells(self):
        r = go(self.snap, "r3_diafragme")
        sev = {f["severity"]: f for f in r["findings"]}
        self.assertEqual({o["name"] for o in sev["error"]["objects"]}, {"1", "3"})
        self.assertEqual({o["name"] for o in sev["info"]["objects"]}, {"2"})
        self.assertIn("coji", sev["info"]["message"])

    def test_stories_with_only_shells_are_detected(self):
        class Ctx:
            snap = self.snap
        m = Mesh()
        m.rect("1", "Floor", "E1", 0, 0, 5, 5)
        tilted_quad(m, "2", "T1", 10, 0, 5, 5, 4.0)
        self.assertEqual(shell_stories(type("C", (), {"snap": Snap(tables(m, [("1", "E1"), ("2", "T1")]))})), {"T1"})


class RibTests(unittest.TestCase):
    def build(self):
        m = Mesh()
        tilted_quad(m, "2", "T1", 10, 0, 5, 5, 4.0)
        b = Builder()
        rib = b.beam((10, 0, 3.0), (15, 0, 3.0))                                     # pe muchia de jos a cojii: coasta
        free = b.beam((30, 0, 3.0), (35, 0, 3.0))                                    # grinda obisnuita, departe de coaja
        b.finish()
        offsets = df([dict(UniqueName=n, OffsetOpt="Auto", RigidFact=0.0) for n in (rib, free)])
        t = {**tables(m, [("2", "T1")]), "Frame Assignments - End Length Offsets": offsets}
        return Snap(t, b.md), rib, free

    def test_frames_on_shell_nodes_are_ribs(self):
        snap, rib, free = self.build()
        self.assertEqual(shell_ribs(type("C", (), {"snap": snap})), {rib})

    def test_ribs_do_not_need_rigid_zones_but_ordinary_beams_do(self):
        snap, rib, free = self.build()
        f = go(snap, "r13_zone_rigide")["findings"][0]
        self.assertEqual([o["name"] for o in f["objects"]], [free])


if __name__ == "__main__":
    unittest.main()
