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


class MastStoryTests(unittest.TestCase):
    def tables(self):
        masses = df([dict(Story="E2", UX=1000.0, UY=1000.0, UZ=0), dict(Story="E3", UX=900.0, UY=900.0, UZ=0),
                     dict(Story="M1", UX=20.0, UY=20.0, UZ=0), dict(Story="Base", UX=100.0, UY=100.0, UZ=0)])
        mat = df([dict(Story=s, ObjectType="All", Weight=1.0, FloorArea=1.0) for s in ("E2", "E3", "M1")])
        asg = df([dict(Story=s, Label=f"L{s}", UniqueName=str(i), SectProp="P", PropType="Slab") for i, s in enumerate(("E2", "E3"))])
        return {"Mass Summary by Story": masses, "Material List by Story": mat, "Area Assignments - Section Properties": asg}

    def test_frame_only_mast_stories_are_not_compared_for_mass_jumps(self):
        r = go(Snap(self.tables()), "r6_mase_etaj")
        msgs = " ".join(f["message"] for f in r["findings"])
        self.assertEqual([f for f in r["findings"] if f["severity"] != "info"], [])  # 900 -> 20 ar fi un salt de 98 %
        self.assertIn("M1", msgs)                                                   # dar nivelul e mentionat ca fiind catarg


if __name__ == "__main__":
    unittest.main()
