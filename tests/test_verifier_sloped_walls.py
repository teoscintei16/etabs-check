import unittest

from etabs_beams.models import ModelData
from etabs_beams.verifier.elements import build_walls
from tests.test_verifier_phase1 import Snap, df, go
from tests.test_verifier_phase3 import Mesh


def wall_tables(m: Mesh, names):
    sp = df([dict(Story="S1", Label=f"W{n}", UniqueName=n, SectProp="PE25", PropType="Wall") for n in names])
    sec = df([dict(Name="PE25", Type="Wall", AnalType="Shell-Thin", Material="C25/30", TotalThick=0.25)])
    return {**m.tables(), "Area Assignments - Section Properties": sp, "Area Section Property Definitions - Summary": sec}


def sloped_quad(m: Mesh, name, bottom, top, story="S1"):
    """Panou inclinat: marginea de jos (a, b, z) si cea de sus (a, b, z), fiecare cu puncte (x, y)."""
    pts = [(*bottom[0], bottom[2]), (*bottom[1], bottom[2]), (*top[1], top[2]), (*top[0], top[2])]
    js = [m.jt(*p, story) for p in pts]
    m.areas.append(dict(Story=story, ElmName=f"{name}-1", ObjType="Wall", ObjLabel=f"L{name}", ObjName=name,
                        ElmJt1=js[0], ElmJt2=js[1], ElmJt3=js[2], ElmJt4=js[3]))


class SlopedWallTests(unittest.TestCase):
    def build(self):
        m = Mesh()
        m.rect("1", "Wall", "S1", 0, 0, 5, 3, vertical_x=0.0)                                   # perete vertical
        sloped_quad(m, "2", ((0.0, 10.0), (6.0, 10.0), 0.0), ((1.0, 10.5), (5.0, 10.5), 3.0))   # trapez inclinat (pe fata laterala)
        cache: dict = {}
        walls = build_walls(df_tables(wall_tables(m, ["1", "2"])), cache)
        return walls, cache

    def test_vertical_wall_stays_a_wall_and_sloped_becomes_edges(self):
        walls, cache = self.build()
        self.assertIn("1", walls)
        self.assertNotIn("2", walls)
        self.assertEqual(set(cache["sloped_walls"]), {"2"})
        self.assertEqual(sorted(k for k in walls if k.startswith("2#")), ["2#B", "2#T"])
        self.assertTrue(all(walls[k].virtual for k in ("2#B", "2#T")))
        e = cache["sloped_walls"]["2"]
        self.assertEqual((e["bottom"][2], e["top"][2]), (0.0, 3.0))
        self.assertAlmostEqual(abs(e["bottom"][0][0] - e["bottom"][1][0]), 6.0)                  # margine de jos = latura lunga
        self.assertAlmostEqual(abs(e["top"][0][0] - e["top"][1][0]), 4.0)                        # margine de sus = latura scurta

    def test_virtual_edge_bands_sit_on_the_real_edges(self):
        walls, _ = self.build()
        top, bottom = walls["2#T"], walls["2#B"]
        self.assertEqual((top.zmax, round(top.zmin, 3)), (3.0, 2.8))                             # banda de 0.2 m sub marginea de sus
        self.assertEqual((bottom.zmin, round(bottom.zmax, 3)), (0.0, 0.2))
        self.assertTrue(all(abs(p[1] - 10.5) < 1e-9 for p in top.points))                       # in planul marginii de sus, nu in planul mediu


def df_tables(tables):
    return lambda key: tables.get(key, df([]))


class ContinuityWithSlopesTests(unittest.TestCase):
    def check(self, md):
        return go(Snap({}, md), "r2_continuitate_verticala")

    def test_tapered_stack_is_continuous_and_a_floating_one_is_not(self):
        md = ModelData()
        md.sloped_walls = {
            "a": dict(label="Wa", story="S1", bottom=((0.0, 0.0), (10.0, 0.0), 0.0), top=((1.0, 0.5), (9.0, 0.5), 3.0)),
            "b": dict(label="Wb", story="S2", bottom=((1.0, 0.5), (9.0, 0.5), 3.0), top=((2.0, 1.0), (8.0, 1.0), 6.0)),          # sprijinit pe a
            "c": dict(label="Wc", story="S2", bottom=((20.0, 0.0), (30.0, 0.0), 3.0), top=((21.0, 0.5), (29.0, 0.5), 6.0))}      # in aer
        r = self.check(md)
        self.assertEqual(r["status"], "error")
        self.assertEqual([o["name"] for o in r["findings"][0]["objects"]], ["c"])


if __name__ == "__main__":
    unittest.main()
