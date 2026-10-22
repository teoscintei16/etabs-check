import tempfile
import unittest
from pathlib import Path

from etabs_beams.verifier import Sidecar, catalog, run
from etabs_beams.verifier.history import compare, list_runs, record_run
from etabs_beams.verifier.report import build_html
from tests.test_verifier_phase1 import Snap, df


def _store():
    return Sidecar(str(Path(tempfile.mkdtemp()) / "m.EDB"))


def _patterns(*rows):
    return Snap({"Load Pattern Definitions": df([dict(Name=n, Type="Dead", SelfWtMult=m) for n, m in rows])})


class HistoryTests(unittest.TestCase):
    def _run(self, store, rows):
        res = run(_patterns(*rows), store, ids=["r22_greutate_proprie"])
        record_run(store, "pre", res, "m.EDB", False)
        return res

    def test_history_and_compare(self):
        store = _store()
        self._run(store, [("Dead", 1), ("SDL", 1)])          # dublare: 2 obiecte in constatare
        self._run(store, [("Dead", 1), ("SDL", 0)])          # rezolvat
        runs = list_runs(store)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["counts"]["error"], 1)
        self.assertEqual(runs[1]["counts"]["error"], 0)
        c = compare(store)
        self.assertEqual((c["totals"]["rezolvate"], c["totals"]["noi"]), (2, 0))
        self.assertEqual(c["checks"][0]["check"], "r22_greutate_proprie")
        # persistenta pe disc
        again = Sidecar(str(store.path)[: -len(".checks.json")])
        self.assertEqual(len(again.data["history"]), 2)

    def test_new_findings_and_first_run(self):
        store = _store()
        self._run(store, [("Dead", 1)])
        self.assertEqual(compare(store)["a"], None)              # nu exista rulare anterioara
        self._run(store, [("Dead", 1), ("SDL", 1)])
        self.assertEqual(compare(store)["totals"]["noi"], 2)

    def test_waived_findings_are_not_in_history(self):
        store = _store()
        snap = _patterns(("Dead", 1), ("SDL", 1))
        keys = run(snap, store, ids=["r22_greutate_proprie"])[0]["findings"][0]["keys"]
        store.waive(keys, "ok")
        res = run(snap, store, ids=["r22_greutate_proprie"])
        e = record_run(store, "pre", res, "m.EDB", False)
        self.assertEqual((e["counts"]["error"], e["waived"]), (0, 1))


class ReportTests(unittest.TestCase):
    def test_html_report_romanian_with_justification(self):
        store = _store()
        snap = _patterns(("Dead", 1), ("SDL <b>", 1))
        res = run(snap, store, ids=["r22_greutate_proprie"])
        store.waive(res[0]["findings"][0]["keys"], "intenționat, verificat de <proiectant>")
        res = run(snap, store, ids=["r22_greutate_proprie"])
        html = build_html(catalog=catalog(), results={r["id"]: r for r in res}, model_file="C:/m/model.EDB", analyzed=False,
                          project={"ag": 0.3}, belts={"has": False, "sections": []}, params={}, manual={}, waivers=store.data["waivers"], comparison=None)
        self.assertIn("<html lang='ro'>", html)
        self.assertIn("Raport de verificare a modelului ETABS", html)
        self.assertIn("Justificare:", html)
        self.assertIn("intenționat, verificat de &lt;proiectant&gt;", html)      # textul justificarii, cu escape
        self.assertNotIn("<proiectant>", html)
        self.assertNotIn("SDL <b>", html)                                           # numele din date e escapat
        self.assertIn("Model nerulat", html)
        self.assertIn("Reguli fără verificare automată", html)

    def test_report_lists_manual_checklist_and_comparison(self):
        store = _store()
        res = run(_patterns(("Dead", 1)), store, ids=["r22_greutate_proprie"])
        store.set_manual("m3_diaphragm_extent", True)
        # r22 nu are listă de control; includem una prin regula 3 cu un rezultat fals
        fake = {"id": "x", "rule": 3, "phase": "pre", "zone": "z3", "title": "Verificare", "findings": [], "error": None, "seconds": 0, "status": "ok"}
        comp = {"a": "2026-01-01T10:00:00", "b": "2026-01-02T10:00:00", "phase": "pre", "totals": {"rezolvate": 3, "noi": 1, "ramase": 5},
                "checks": [{"check": "r22", "rezolvate": 3, "noi": 1, "ramase": 5}]}
        html = build_html(catalog=catalog(), results={r["id"]: r for r in res + [fake]}, model_file="m.EDB", analyzed=True, project={},
                          belts={}, params={}, manual=store.manual(), waivers=[], comparison=comp)
        self.assertIn("☑", html)
        self.assertIn("3</b> rezolvate", html)
        self.assertIn("Comparație cu rularea anterioară", html)


if __name__ == "__main__":
    unittest.main()
