import tempfile
import unittest
from pathlib import Path

import pandas as pd

from etabs_beams.verifier import CHECKS, Sidecar, catalog, run
from etabs_beams.verifier.rules import RULE_META, load_rules


class FakeSnap:
    """Snapshot fara ETABS: tabele date direct."""
    model = None
    original_units = 6

    def __init__(self, tables):
        self.tables = tables

    def table(self, key):
        return self.tables.get(key, pd.DataFrame())

    def legacy_issues(self):
        return {}


def _mats(rows):
    gen = pd.DataFrame([{"Material": n, "Type": t, "Grade": g} for n, t, g, *_ in rows])
    mech = pd.DataFrame([{"Material": n, "UnitWeight": w, "E1": e} for n, _t, _g, w, e in rows])
    return {"Material Properties - General": gen, "Material Properties - Basic Mechanical Properties": mech}


def _store():
    return Sidecar(str(Path(tempfile.mkdtemp()) / "m.EDB"))


def _res(snap, check_id, store=None):
    return next(r for r in run(snap, store or _store(), ids=[check_id]))


class RulesTests(unittest.TestCase):
    def test_all_30_rules_parsed_with_text(self):
        rules = load_rules()
        self.assertEqual(sorted(rules), list(range(1, 31)))
        for r in rules.values():
            self.assertTrue(r.title and r.what and r.how, f"regula {r.number} fara text")
            self.assertEqual((r.zone, r.phases, r.cls), RULE_META[r.number])

    def test_catalog_lists_checks_per_rule(self):
        cat = catalog()
        self.assertEqual(len(cat["zones"]), 9)
        by = {r["number"]: r for r in cat["rules"]}
        self.assertTrue(by[22]["checks"])
        self.assertTrue(by[3]["manual"])           # lista de control pentru regula 3


class CheckTests(unittest.TestCase):
    def test_self_weight_ok_single_dead(self):
        lp = pd.DataFrame([{"Name": "Dead", "Type": "Dead", "SelfWtMult": 1}, {"Name": "Q", "Type": "Live", "SelfWtMult": 0}])
        self.assertEqual(_res(FakeSnap({"Load Pattern Definitions": lp}), "r22_greutate_proprie")["status"], "ok")

    def test_self_weight_doubled_is_error(self):
        lp = pd.DataFrame([{"Name": "Dead", "Type": "Dead", "SelfWtMult": 1}, {"Name": "SDL", "Type": "Dead", "SelfWtMult": 1}])
        r = _res(FakeSnap({"Load Pattern Definitions": lp}), "r22_greutate_proprie")
        self.assertEqual(r["status"], "error")
        self.assertEqual({o["name"] for o in r["findings"][0]["objects"]}, {"Dead", "SDL"})

    def test_self_weight_missing_is_error(self):
        lp = pd.DataFrame([{"Name": "Dead", "Type": "Dead", "SelfWtMult": 0}])
        self.assertEqual(_res(FakeSnap({"Load Pattern Definitions": lp}), "r22_greutate_proprie")["status"], "error")

    def test_materials_class_and_factor(self):
        ok = _mats([("0.5*C35/45", "Concrete", "C35/45", 25.0, 17.0e6), ("S355", "Steel", "S355", 77.0, 2.1e8)])
        self.assertEqual(_res(FakeSnap(ok), "r1_materiale")["status"], "ok")
        bad = _mats([("C35/45", "Concrete", "C35/45", 25.0, 2.0e7)])               # E prea mic fata de clasa
        r = _res(FakeSnap(bad), "r1_materiale")
        self.assertEqual(r["status"], "warning")
        self.assertEqual(r["findings"][0]["objects"][0]["name"], "C35/45")

    def test_materials_zero_weight_and_units(self):
        r = _res(FakeSnap(_mats([("B", "Concrete", "C30/37", 0.0, 3.3e7)])), "r1_materiale")
        self.assertEqual(r["status"], "error")
        r = _res(FakeSnap(_mats([("B", "Concrete", "C30/37", 25.0, 33000.0)])), "r19_unitati")   # MPa in loc de kN/m2
        self.assertEqual(r["status"], "error")

    def test_param_override_from_sidecar(self):
        store = _store()
        snap = FakeSnap(_mats([("C35/45", "Concrete", "C35/45", 25.0, 3.2e7)]))   # ~ -6%
        self.assertEqual(_res(snap, "r1_materiale", store)["status"], "warning")
        store.set_params({"r1_materiale.ecm_tolerance_pct": 10.0})
        self.assertEqual(_res(snap, "r1_materiale", store)["status"], "ok")

    def test_waiver_and_persistence(self):
        store = _store()
        lp = pd.DataFrame([{"Name": "Dead", "Type": "Dead", "SelfWtMult": 1}, {"Name": "SDL", "Type": "Dead", "SelfWtMult": 1}])
        snap = FakeSnap({"Load Pattern Definitions": lp})
        keys = _res(snap, "r22_greutate_proprie", store)["findings"][0]["keys"]
        store.waive(keys, "intentionat")
        r = _res(snap, "r22_greutate_proprie", store)
        self.assertEqual((r["status"], r["findings"][0]["waived"], r["findings"][0]["waiver_note"]), ("waived", True, "intentionat"))
        again = Sidecar(store.path.with_suffix("").as_posix()[: -len(".checks")])          # reincarcare de pe disc
        self.assertEqual(again.waived_keys().get(keys[0]), "intentionat")
        store.unwaive(keys)
        self.assertEqual(_res(snap, "r22_greutate_proprie", store)["status"], "error")

    def test_manual_checklist_persists(self):
        store = _store()
        store.set_manual("m3_diaphragm_extent", True, "ok vizual")
        self.assertTrue(Sidecar(str(store.path)[: -len(".checks.json")]).manual()["m3_diaphragm_extent"]["done"])

    def test_broken_check_does_not_stop_others(self):
        r = run(FakeSnap({}), _store(), ids=["r22_greutate_proprie", "r1_materiale"])
        self.assertEqual(len(r), 2)                      # fara tabele: "info", nu exceptie
        self.assertTrue(all(x["error"] is None for x in r))

    def test_every_check_is_bound_to_known_rule(self):
        for cd in CHECKS.values():
            self.assertIn(cd.rule, RULE_META)


if __name__ == "__main__":
    unittest.main()
