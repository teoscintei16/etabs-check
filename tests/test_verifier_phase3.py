import tempfile
import unittest
from pathlib import Path

import pandas as pd

from etabs_beams.verifier import Sidecar, run
from tests.test_continuity import Builder
from tests.test_verifier_phase1 import Snap, df


class Mesh:
    """Construieste tabelele 'Objects and Elements' pentru cateva arii dreptunghiulare (un element per arie)."""

    def __init__(self):
        self.joints, self.areas, self._j = [], [], {}

    def jt(self, x, y, z, story):
        k = (round(x, 4), round(y, 4), round(z, 4))
        if k not in self._j:
            self._j[k] = f"~{len(self._j) + 1}"
            self.joints.append(dict(Story=story, ElmName=self._j[k], ObjType="Shell", ObjLabel="", ObjName="x", GlobalX=x, GlobalY=y, GlobalZ=z))
        return self._j[k]

    def rect(self, name, kind, story, x0, y0, w, h, z=3.0, ccw=True, vertical_x=None):
        if vertical_x is None:
            pts = [(x0, y0, z), (x0 + w, y0, z), (x0 + w, y0 + h, z), (x0, y0 + h, z)]
            if not ccw:
                pts = pts[::-1]
        else:                                   # perete in planul XZ: x0..x0+w, z intre y0..y0+h
            pts = [(x0, vertical_x, y0), (x0 + w, vertical_x, y0), (x0 + w, vertical_x, y0 + h), (x0, vertical_x, y0 + h)]
        js = [self.jt(*p, story) for p in pts]
        self.areas.append(dict(Story=story, ElmName=f"{name}-1", ObjType=kind, ObjLabel=f"L{name}", ObjName=name,
                               ElmJt1=js[0], ElmJt2=js[1], ElmJt3=js[2], ElmJt4=js[3]))

    def tables(self):
        return {"Objects and Elements - Joints": df(self.joints), "Objects and Elements - Areas": df(self.areas)}


def go(tables, check_id, project=None, params=None, model=None):
    store = Sidecar(str(Path(tempfile.mkdtemp()) / "m.EDB"))
    if project:
        store.set_project(project)
    if params:
        store.set_params(params)
    r = run(Snap(tables, model), store, ids=[check_id])[0]
    assert r["error"] is None, r.get("trace")
    return r


class AreaGeometryTests(unittest.TestCase):
    def test_aspect_ratio(self):
        m = Mesh()
        m.rect("1", "Floor", "S1", 0, 0, 1, 1)
        m.rect("2", "Floor", "S1", 5, 0, 10, 1)
        r = go(m.tables(), "r5_calitate_mesh")
        self.assertEqual(r["status"], "warning")
        self.assertEqual([o["name"] for o in r["findings"][0]["objects"]], ["2"])

    def test_slab_orientation(self):
        m = Mesh()
        for i in range(3):
            m.rect(str(i), "Floor", "S1", i * 2, 0, 1, 1)
        m.rect("9", "Floor", "S1", 20, 0, 1, 1, ccw=False)
        r = go(m.tables(), "r14_normale_placi")
        self.assertEqual((r["status"], r["findings"][0]["objects"][0]["name"]), ("warning", "9"))

    def test_holes(self):
        m = Mesh()
        m.rect("a", "Floor", "S1", 0, 0, 10, 4)           # banda de jos
        m.rect("b", "Floor", "S1", 0, 6, 10, 4)           # banda de sus
        m.rect("c", "Floor", "S1", 0, 4, 4, 2)            # stanga
        m.rect("d", "Floor", "S1", 6, 4, 4, 2)            # dreapta  -> gol 2 x 2 = 4 m2 la mijloc
        r = go(m.tables(), "r3_goluri")
        self.assertEqual(r["status"], "info")
        self.assertAlmostEqual(r["findings"][0]["data"]["goluri"][0]["suprafata_m2"], 4.0)
        r = go(m.tables(), "r3_goluri", params={"r3_goluri.gol_min": 5.0})
        self.assertEqual(r["status"], "ok")


class PierTests(unittest.TestCase):
    def _walls(self):
        m = Mesh()
        m.rect("1", "Wall", "S1", 0, 0, 3, 3, vertical_x=0.0)
        m.rect("2", "Wall", "S1", 3, 0, 3, 3, vertical_x=0.0)           # coplanara cu 1, lipita
        m.rect("3", "Wall", "S1", 0, 0, 3, 3, vertical_x=10.0)          # alt perete
        sp = df([dict(Story="S1", Label=f"W{i}", UniqueName=i, SectProp="PE40", PropType="Wall") for i in ("1", "2", "3")])
        return m, sp

    def test_missing_and_split_labels(self):
        m, sp = self._walls()
        pl = df([dict(Story="S1", Label="W1", UniqueName="1", PierName="P1"), dict(Story="S1", Label="W2", UniqueName="2", PierName="P2")])
        t = dict(m.tables(), **{"Area Assignments - Section Properties": sp, "Area Assignments - Pier Labels": pl})
        r = go(t, "r4_pier_etichete")
        msgs = " ".join(f["message"] for f in r["findings"])
        self.assertIn("nu au etichetă", msgs)                                   # peretele 3
        self.assertIn("felii", msgs)                                            # 1 si 2: aceeasi felie, etichete diferite
        pl = df([dict(Story="S1", Label=f"W{i}", UniqueName=i, PierName=p) for i, p in (("1", "P1"), ("2", "P1"), ("3", "P2"))])
        t["Area Assignments - Pier Labels"] = pl
        self.assertEqual(go(t, "r4_pier_etichete")["status"], "ok")

    def test_label_continuity(self):
        stories = df([dict(Story=s, Tower="T1") for s in ("E3", "E2", "E1")])
        sp = df([dict(Story=s, Label="W", UniqueName=str(i), SectProp="PE40", PropType="Wall") for i, s in enumerate(("E3", "E2", "E1"))])
        pl = df([dict(Story=s, Label="W", UniqueName=str(i), PierName="P1") for i, s in ((0, "E3"), (2, "E1"))])
        r = go({"Story Definitions": stories, "Area Assignments - Section Properties": sp, "Area Assignments - Pier Labels": pl}, "r4_pier_continuitate")
        self.assertEqual(r["status"], "warning")
        self.assertIn("E2", str(r["findings"][0]["data"]))

    def test_coupling_beams_and_belt_ends(self):
        b = Builder()
        b.column(0, 0)
        n = b.beam((0, 0, 3), (4, 0, 3))
        md = b.finish()
        f = md.frames[n]
        md.node_areas[f.p1], md.node_areas[f.p2] = ["W1"], ["W2"]
        r = go({}, "r4_grinzi_cuplare", model=md)
        self.assertEqual((r["status"], r["findings"][0]["objects"][0]["name"]), ("info", n))
        md.node_areas[f.p2] = ["W1"]                                           # acelasi perete: grinda pe perete
        self.assertEqual(go({}, "r4_grinzi_cuplare", model=md)["status"], "ok")
        md.belt_names = ["999"]                                                 # exista centuri, dar niciuna la capatul grinzii
        md.frames["999"] = type(f)("999", "B999", "S1", "dummy", "z1", "z2", (50, 0, 3), (54, 0, 3))
        self.assertEqual(go({}, "r4_centuri_capete", model=md)["status"], "warning")

    def test_deck_groups(self):
        t = {"Area Section Property Definitions - Summary": df([dict(Name="Deck1", Type="Deck", AnalType="Membrane")]),
             "Area Assignments - Section Properties": df([dict(Story="S1", Label="F1", UniqueName="1", SectProp="Deck1", PropType="Slab"),
                                                           dict(Story="S1", Label="F2", UniqueName="2", SectProp="Deck1", PropType="Slab")]),
             "Area Assignments - Local Axes": df([dict(UniqueName="2", Angle=90)])}
        r = go(t, "r16_directii_deck")
        self.assertEqual(r["status"], "info")
        self.assertIn("2 grupe", r["findings"][0]["message"])


class BodyTests(unittest.TestCase):
    def _bodies(self, gap):
        m = Mesh()
        m.rect("1", "Floor", "E1", 0, 0, 10, 10)
        m.rect("2", "Floor", "E1", 10 + gap, 0, 10, 10)
        f = df([dict(Story="E1", ElmName="1-1", ObjType="Frame", ObjLabel="B1", ObjName="1", ElmJtI="~1", ElmJtJ="~2")])
        t = dict(m.tables(), **{"Story Definitions": df([dict(Story="E1", Tower="T1"), dict(Story="P", Tower="T1")]),
                                "Objects and Elements - Frames": f})
        return t

    def test_two_bodies_and_shared_diaphragm(self):
        t = self._bodies(5.0)
        t["Area Assignments - Diaphragms"] = df([dict(Story="E1", Label="L1", UniqueName="1", Diaphragm="D1"),
                                                 dict(Story="E1", Label="L2", UniqueName="2", Diaphragm="D1")])
        r = go(t, "r26_corpuri", params={"r26_corpuri.corp_min_elem": 4})
        self.assertEqual(r["status"], "error")
        msgs = " ".join(f["message"] for f in r["findings"])
        self.assertIn("2 corpuri independente", msgs)
        self.assertIn("diafragme", msgs)
        t["Area Assignments - Diaphragms"] = df([dict(Story="E1", Label="L1", UniqueName="1", Diaphragm="D1"),
                                                 dict(Story="E1", Label="L2", UniqueName="2", Diaphragm="D2")])
        self.assertNotEqual(go(t, "r26_corpuri", params={"r26_corpuri.corp_min_elem": 4})["status"], "error")

    def test_narrow_joint_between_bodies(self):
        r = go(self._bodies(0.05), "r27_rosturi", params={"r27_rosturi.corp_min_nod": 4})
        self.assertEqual(r["status"], "warning")
        self.assertEqual(go(self._bodies(0.5), "r27_rosturi", params={"r27_rosturi.corp_min_nod": 4})["status"], "ok")

    def test_pier_labels_shared_between_bodies(self):
        t = self._bodies(5.0)
        t["Area Assignments - Pier Labels"] = df([dict(Story="E1", Label="L1", UniqueName="1", PierName="P1"),
                                                  dict(Story="E1", Label="L2", UniqueName="2", PierName="P1")])
        # praguri mici pentru exemplul minuscul
        import etabs_beams.verifier.checks.areas as areas
        src = areas._components
        r = go(t, "r28_pier_pe_corpuri")
        self.assertEqual(r["status"], "ok")         # corpurile au 8 noduri (< 200): ignorate implicit, ca elementele izolate
        self.assertTrue(callable(src))

    def test_diaphragm_none_is_unassigned(self):
        t = {"Area Assignments - Section Properties": df([dict(Story="S", Label="F1", UniqueName="1", SectProp="PL15", PropType="Slab")]),
             "Area Assignments - Diaphragms": df([dict(Story="S", Label="F1", UniqueName="1", Diaphragm="None")])}
        self.assertEqual(go(t, "r3_diafragme")["status"], "error")


if __name__ == "__main__":
    unittest.main()
