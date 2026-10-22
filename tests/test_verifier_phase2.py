import tempfile
import unittest
from pathlib import Path

import pandas as pd

from etabs_beams.models import BRACE, Frame
from etabs_beams.verifier import Sidecar, run
from etabs_beams.verifier.checks.seismic import G, spectrum_shape
from tests.test_continuity import Builder
from tests.test_verifier_phase1 import Snap, df


def go(tables, check_id, project=None, params=None, model=None):
    store = Sidecar(str(Path(tempfile.mkdtemp()) / "m.EDB"))
    if project:
        store.set_project(project)
    if params:
        store.set_params(params)
    r = run(Snap(tables, model), store, ids=[check_id])[0]
    assert r["error"] is None, r.get("trace")
    return r


P = dict(ag=0.3, gamma_I=1.2, beta0=2.5, Tb=0.2, Tc=1.0, Td=3.0, q=4.6)


def spectrum_table(scale=1.0, q=4.6, floor=True):
    rows = []
    for T in (0, 0.2, 1.0, 1.7, 2.5, 3.0, 4.0):
        v = P["ag"] * G * P["gamma_I"] * max(spectrum_shape(T, P["beta0"], q, P["Tb"], P["Tc"], P["Td"]), 0.2 if floor else 0)
        rows.append(dict(Name="F1", Period=T, Value=v * scale, DampRatio=0.05))
    return df(rows)


def rs_cases(sf1=1.0, sf2=0.3, ecc=0.0, modal="CQC", dircomb="SRSS"):
    return df([dict(Name="specx", LoadName="U1", Function="F1", TransAccSF=sf1, ModalCombo=modal, DirCombo=dircomb, EccenRatio=ecc),
               dict(Name="specx", LoadName="U2", Function="F1", TransAccSF=sf2, ModalCombo="", DirCombo="", EccenRatio=float("nan"))])


class SpectrumTests(unittest.TestCase):
    def test_correct_spectrum_ok_and_missing_params_info(self):
        t = {"Functions - Response Spectrum - User Defined": spectrum_table(), "Load Case Definitions - Response Spectrum": rs_cases(),
             "Load Case Definitions - Summary": df([dict(Name="specx", Type="Response Spectrum")])}
        self.assertEqual(go(t, "r8_spectru")["status"], "info")                      # parametri nesetati
        self.assertEqual(go(t, "r8_spectru", P)["status"], "ok")

    def test_wrong_q_and_missing_g(self):
        t = {"Functions - Response Spectrum - User Defined": spectrum_table(q=3.0), "Load Case Definitions - Response Spectrum": rs_cases()}
        r = go(t, "r8_spectru", P)
        self.assertEqual(r["status"], "warning")
        t = {"Functions - Response Spectrum - User Defined": spectrum_table(scale=1 / G), "Load Case Definitions - Response Spectrum": rs_cases()}
        r = go(t, "r8_spectru", P)
        self.assertEqual(r["status"], "error")
        self.assertTrue(any("g (9.81)" in f["message"] for f in r["findings"]))

    def test_case_settings(self):
        t = {"Load Case Definitions - Response Spectrum": rs_cases(modal="SRSS", ecc=0.0, sf2=0.5)}
        r = go(t, "r8_caz_spectru")
        msgs = " ".join(f["message"] for f in r["findings"])
        self.assertIn("SRSS", msgs)
        self.assertIn("excentricitate", msgs)
        self.assertIn("0.50", msgs)


class StaticTests(unittest.TestCase):
    def _auto(self, c=0.166, y_minus=True):
        rows = [dict(Name="XP", XDir="No", XDirPlusE="Yes", XDirMinusE="No", YDir="No", YDirPlusE="No", YDirMinusE="No", EccRatio=0.05, BotStory="Base", C=c),
                dict(Name="XN", XDir="No", XDirPlusE="No", XDirMinusE="Yes", YDir="No", YDirPlusE="No", YDirMinusE="No", EccRatio=0.05, BotStory="Base", C=c),
                dict(Name="YP", XDir="No", XDirPlusE="No", XDirMinusE="No", YDir="No", YDirPlusE="Yes", YDirMinusE="No", EccRatio=0.05, BotStory="Base", C=c)]
        if y_minus:
            rows.append(dict(Name="YN", XDir="No", XDirPlusE="No", XDirMinusE="No", YDir="No", YDirPlusE="No", YDirMinusE="Yes", EccRatio=0.05, BotStory="Base", C=c))
        return {"Load Pattern Definitions - Auto Seismic - User Coefficient": df(rows)}

    def test_missing_eccentricity_pattern(self):
        r = go(self._auto(y_minus=False), "r20_forte_statice")
        self.assertEqual(r["status"], "warning")
        self.assertIn("Y", r["findings"][0]["message"])

    def test_coefficient_above_plateau(self):
        proj = dict(P, lambda_mfse=0.85)
        self.assertEqual(go(self._auto(c=0.166), "r20_forte_statice", proj)["status"], "info")
        self.assertEqual(go(self._auto(c=0.25), "r20_forte_statice", proj)["status"], "error")

    def test_seismic_base(self):
        t = dict(self._auto(), **{"Tower and Base Story Definitions": df([dict(Tower="T1", BSName="Base", BSElev=0)]),
                                  "Story Definitions": df([dict(Story=s) for s in ("E1", "P", "S1", "S2")])})
        proj = {"ground_story": "P", "basement": "da"}
        self.assertEqual(go(t, "r12_baza_seismica", proj)["status"], "error")             # trebuie S1, e Base
        t["Load Pattern Definitions - Auto Seismic - User Coefficient"]["BotStory"] = "S1"
        self.assertEqual(go(t, "r12_baza_seismica", proj)["status"], "info")
        self.assertEqual(go(t, "r12_baza_seismica")["status"], "info")                    # fara parametri


def combos(rows):
    out, n = [], None
    for name, typ, load, sf in rows:
        out.append(dict(Name=name if name != n else "", Type=typ if name != n else "", LoadName=load, SF=sf))
        n = name
    return df(out)


class ComboTests(unittest.TestCase):
    LP = df([dict(Name="Dead", Type="Dead", SelfWtMult=1), dict(Name="Perm", Type="Dead", SelfWtMult=0), dict(Name="Util", Type="Live", SelfWtMult=0),
             dict(Name="Util2", Type="Live", SelfWtMult=0), dict(Name="XP", Type="Seismic", SelfWtMult=0), dict(Name="XN", Type="Seismic", SelfWtMult=0)])

    def test_uls_coverage(self):
        lc = combos([("U1", "Linear Add", "Dead", 1.35), ("U1", "", "Perm", 1.35), ("U1", "", "Util", 1.5)])
        t = {"Load Combination Definitions": lc, "Load Pattern Definitions": self.LP}
        r = go(t, "r9_acoperire")                                       # Util2 lipseste din ULS dar nu are incarcari
        self.assertEqual((r["status"], r["findings"][0]["severity"]), ("info", "info"))
        t["Shell Uniform Load Sets"] = df([dict(Name="S", LoadPattern="Util2", LoadValue=2)])
        t["Area Load Assignments - Uniform Load Sets"] = df([dict(UniqueName="1", LoadSet="S"), dict(UniqueName="2", LoadSet="S")])
        r = go(t, "r9_acoperire")                                       # acum Util2 e asignat la 2 placi prin set
        self.assertEqual(r["status"], "error")
        self.assertIn("2 plăci", r["findings"][0]["message"])
        self.assertEqual([o["name"] for o in r["findings"][0]["objects"]], ["Util2"])

    def test_uls_missing_entirely(self):
        lc = combos([("C", "Linear Add", "Dead", 1.0), ("C", "", "Util", 1.0)])
        self.assertEqual(go({"Load Combination Definitions": lc, "Load Pattern Definitions": self.LP}, "r9_acoperire")["status"], "error")

    def test_seismic_combos_psi_and_orthogonal(self):
        auto = df([dict(Name="XP", XDir="No", XDirPlusE="Yes", XDirMinusE="No", YDir="No", YDirPlusE="No", YDirMinusE="No"),
                   dict(Name="XN", XDir="No", XDirPlusE="No", XDirMinusE="Yes", YDir="No", YDirPlusE="No", YDirMinusE="No")])
        lc = combos([("S1", "Linear Add", "Dead", 1), ("S1", "", "Perm", 1), ("S1", "", "Util", 0.3), ("S1", "", "XP", 1),
                     ("S2", "Linear Add", "Dead", 1), ("S2", "", "Perm", 1), ("S2", "", "Util", 0.6), ("S2", "", "XN", -1)])
        ms = df([dict(LoadPattern="Perm", Multiplier=1.0), dict(LoadPattern="Util", Multiplier=0.3)])
        r = go({"Load Combination Definitions": lc, "Load Pattern Definitions": self.LP, "Mass Source Definition": ms,
                "Load Pattern Definitions - Auto Seismic - User Coefficient": auto}, "r9_seismice")
        msgs = " ".join(f["message"] for f in r["findings"])
        self.assertIn("diferă între combinațiile seismice", msgs)                       # psi2 0.3 vs 0.6
        self.assertIn("diferă de multiplicatorii", msgs)                                # 0.6 vs masa 0.3

    def test_sls(self):
        lc = combos([("C", "Linear Add", "Dead", 1.0), ("C", "", "Util", 1.0), ("Q", "Linear Add", "Dead", 1.0), ("Q", "", "Util", 0.3)])
        r = go({"Load Combination Definitions": lc, "Load Pattern Definitions": self.LP}, "r9_sls")
        self.assertEqual(r["status"], "info")
        lc = combos([("U", "Linear Add", "Dead", 1.35), ("U", "", "Util", 1.5)])
        self.assertEqual(go({"Load Combination Definitions": lc, "Load Pattern Definitions": self.LP}, "r9_sls")["status"], "warning")


class StructureTests(unittest.TestCase):
    def _joints(self, n=3, story="Base"):
        return df([dict(Story=story, ElmName=str(i), ObjType="Joint", ObjLabel=f"J{i}", ObjName=str(i), GlobalX=i * 5.0, GlobalY=0.0, GlobalZ=0.0)
                   for i in range(1, n + 1)])

    def test_unsupported_base_joints(self):
        t = {"Objects and Elements - Joints": self._joints(), "Tower and Base Story Definitions": df([dict(Tower="T1", BSName="Base", BSElev=0)]),
             "Joint Assignments - Restraints": df([dict(Story="Base", Label="J1", UniqueName="1", UX="Yes", UY="Yes", UZ="Yes", RX="Yes", RY="Yes", RZ="Yes")])}
        r = go(t, "r2_rezemare")
        self.assertEqual(r["status"], "error")
        self.assertEqual({o["name"] for o in r["findings"][0]["objects"]}, {"2", "3"})
        # nodurile unei placi (radier) sunt rezemate prin placa
        els = df([dict(ObjType="Floor", ObjName="9", ElmJt1="2", ElmJt2="3", ElmJt3="~5", ElmJt4="~6")])
        t["Objects and Elements - Areas"] = els
        self.assertEqual(go(t, "r2_rezemare")["status"], "info")

    def test_pinned_base_and_ks(self):
        t = {"Joint Assignments - Restraints": df([dict(Story="Base", Label="J1", UniqueName="1", UX="Yes", UY="Yes", UZ="Yes", RX="No", RY="No", RZ="No")]),
             "Spring Property Definitions - Area Springs": df([dict(Name="k", StiffU1=0, StiffU2=0, StiffU3=80.0, NonlinOpt3="Compression Only")])}
        msgs = " ".join(f["message"] for f in go(t, "r2_rezemare")["findings"])
        self.assertIn("articulate", msgs)
        self.assertIn("kN/m³", msgs)                                                    # ks = 80 (kN/m in loc de kN/m3)

    def test_diaphragms(self):
        t = {"Diaphragm Definitions": df([dict(Name="D1", Rigidity="Rigid")]),
             "Area Section Property Definitions - Summary": df([dict(Name="PL15", Type="Slab", AnalType="Membrane"), dict(Name="Deck1", Type="Deck", AnalType="Membrane")]),
             "Area Assignments - Section Properties": df([dict(Story="S", Label="F1", UniqueName="1", SectProp="PL15", PropType="Slab"),
                                                           dict(Story="S", Label="F2", UniqueName="2", SectProp="Radier 1m", PropType="Slab")]),
             "Area Assignments - Diaphragms": df([dict(UniqueName="9", Diaphragm="D1")])}
        r = go(t, "r3_diafragme")
        self.assertEqual(r["status"], "error")                                           # placa fara diafragma = eroare
        self.assertEqual(len(r["findings"]), 3)
        mem = [f for f in r["findings"] if "Membrane" in f["message"]][0]
        self.assertEqual([o["name"] for o in mem["objects"]], ["PL15"])                 # Deck1 din sablon nu e asignat: nu conteaza
        miss = [f for f in r["findings"] if f["objects"] and f["objects"][0]["type"] == "area"][0]
        self.assertEqual([o["name"] for o in miss["objects"]], ["1"])                    # radierul e exceptat

    def test_temperature_and_staged(self):
        j = df([dict(Story="E", ObjType="Joint", ObjLabel="a", ObjName="1", GlobalX=0, GlobalY=0, GlobalZ=0),
                dict(Story="E", ObjType="Joint", ObjLabel="b", ObjName="2", GlobalX=60, GlobalY=10, GlobalZ=0)])
        self.assertEqual(go({"Objects and Elements - Joints": j}, "r17_temperatura")["status"], "warning")
        lp = df([dict(Name="T", Type="Temperature")])
        self.assertEqual(go({"Objects and Elements - Joints": j, "Load Pattern Definitions": lp}, "r17_temperatura")["status"], "warning")  # fara incarcari
        st = df([dict(Story=f"E{i}") for i in range(16)])
        self.assertEqual(go({"Story Definitions": st}, "r18_constructie_etapizata")["status"], "warning")
        self.assertEqual(go({"Story Definitions": st[:5]}, "r18_constructie_etapizata")["status"], "ok")

    def test_braces_and_tension_only(self):
        b = Builder()
        b.md.frames["9"] = Frame("9", "BR1", "S1", "L100", "a", "b", (0, 0, 0), (4, 0, 3), orientation=BRACE)
        md = b.finish()
        self.assertEqual(go({}, "r23_truss_tension", model=md)["status"], "warning")
        rel = df([dict(UniqueName="9", PI="No", PJ="No", V2I="No", V2J="No", V3I="No", V3J="No", TI="No", TJ="No", M2I="Yes", M2J="Yes", M3I="Yes", M3J="Yes")])
        self.assertEqual(go({"Frame Assignments - Releases and Partial Fixity": rel}, "r23_truss_tension", model=md)["status"], "ok")
        tl = df([dict(UniqueName="9", Compression=0)])
        r = go({"Frame Assignments - Releases and Partial Fixity": rel, "Frame Assignments - Tension and Compression Limits": tl}, "r23_truss_tension", model=md)
        self.assertEqual(r["status"], "warning")                                          # nu exista cazuri neliniare

    def test_soil_pressure(self):
        st = df([dict(Story=s) for s in ("E1", "P", "S1")])
        proj = {"ground_story": "P", "basement": "da"}
        lp = df([dict(Name="Dead", Type="Dead")])
        self.assertEqual(go({"Story Definitions": st, "Load Pattern Definitions": lp}, "r24_presiuni", proj)["status"], "warning")
        lp = df([dict(Name="Dead", Type="Dead"), dict(Name="Impingere pamant", Type="Other")])
        self.assertEqual(go({"Story Definitions": st, "Load Pattern Definitions": lp}, "r24_presiuni", proj)["status"], "warning")   # fara incarcari
        t = {"Story Definitions": st, "Load Pattern Definitions": lp, "Area Load Assignments - Non-uniform": df([dict(LoadPattern="Impingere pamant")])}
        self.assertEqual(go(t, "r24_presiuni", proj)["status"], "info")


if __name__ == "__main__":
    unittest.main()
