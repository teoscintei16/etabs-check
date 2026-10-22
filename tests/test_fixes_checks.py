import unittest

from tests.test_verifier_multitower import go
from tests.test_verifier_phase1 import df


class FixOfferTests(unittest.TestCase):
    def test_nodes_zero_vs_rounding_rows(self):
        j = df([dict(ObjType="Joint", ObjName="7", ObjLabel="7", Story="E1", GlobalX=0.00003, GlobalY=3.00004, GlobalZ=4.0),
                dict(ObjType="Joint", ObjName="8", ObjLabel="8", Story="E1", GlobalX=1.0, GlobalY=2.0, GlobalZ=4.0)])
        r = go({"Objects and Elements - Joints": j}, "r5_noduri")
        f = next(x for x in r["findings"] if x.get("fix"))
        rows = f["fix"]["args"]["rows"]
        self.assertEqual([(x["name"], x["axis"], x["value"]) for x in rows], [("7", "X", 0.0), ("7", "Y", 3.0)])
        self.assertEqual(rows[0]["current"], 0.00003)

    def test_mesh_findings_offer_standard(self):
        fl = df([dict(MeshOpt="General", Localized="No", MergeJoints="Yes", MaxMeshSize=1.0)])
        wl = df([dict(MaxMeshSize=0.5)])
        wa = df([dict(Story="E1", Label="W1", UniqueName="1", MeshOption="Auto Rectangular", Restraints="Yes"),
                 dict(Story="E1", Label="W2", UniqueName="2", MeshOption="Default", Restraints="No")])
        r = go({"Analysis Options - Automatic Mesh Settings for Floors": fl, "Analysis Options - Automatic Rectangular Mesh Options for Walls": wl,
                "Area Assignments - Wall Auto Mesh Options": wa}, "r5_mesh")
        scopes = [f["fix"]["args"]["scope"] for f in r["findings"] if f.get("fix")]
        self.assertEqual(scopes, ["floor_global", "wall_areas"])
        self.assertEqual(r["findings"][1]["count"], 2)

    def test_diaphragm_proposal_comes_from_same_story(self):
        asg = df([dict(UniqueName="1", Label="A", Story="E1", PropType="Slab", SectProp="S"),
                  dict(UniqueName="2", Label="B", Story="E1", PropType="Slab", SectProp="S"),
                  dict(UniqueName="3", Label="C", Story="E2", PropType="Slab", SectProp="S")])
        dsg = df([dict(UniqueName="1", Diaphragm="D1")])
        r = go({"Area Assignments - Section Properties": asg, "Area Assignments - Diaphragms": dsg,
                "Diaphragm Definitions": df([dict(Name="D1", Rigidity="Semi Rigid")])}, "r3_diafragme")
        f = next(x for x in r["findings"] if x["severity"] == "error")
        self.assertEqual(f["fix"]["args"]["assign"], [{"name": "2", "diaphragm": "D1"}])      # placa 3 (E2) nu are referinta
        self.assertIn("Pentru 1 nu există", f["message"])


if __name__ == "__main__":
    unittest.main()
