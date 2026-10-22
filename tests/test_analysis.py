import unittest

from etabs_beams.analysis import analysis_state, run_analysis
from etabs_beams.connection import EtabsError


class FakeAnalyze:
    def __init__(self, status, flags, run_code=0, locks_after=True):
        self.status, self.flags, self.run_code, self.locks_after = status, flags, run_code, locks_after
        self.ran = 0
        self.flag_log = []
        self.owner = None

    def GetCaseStatus(self):
        return [len(self.status), tuple(self.status), tuple(self.status.values()), 0]

    def GetRunCaseFlag(self):
        return [len(self.flags), tuple(self.flags), tuple(self.flags.values()), 0]

    def SetRunCaseFlag(self, name, flag):
        self.flags[name] = flag
        self.flag_log.append((name, flag))
        return 0

    def RunAnalysis(self):
        self.ran += 1
        self.during = dict(self.flags)
        if self.run_code == 0:
            self.status = {k: 4 for k in self.status}
            self.owner.locked = self.locks_after
        return self.run_code


class FakeLoadCases:
    def __init__(self, nl):
        self.nl = nl

    def GetTypeOAPI_1(self, name):
        return [2 if name == "Push" else 1, 1, 0, 0, 0, 0]


class FakeModel:
    def __init__(self, analyze, locked, nl=False):
        self.Analyze, self.locked = analyze, locked
        analyze.owner = self
        if nl:
            self.LoadCases = FakeLoadCases(True)

    def GetModelIsLocked(self):
        return self.locked


class FakeSession:
    def __init__(self, model, filename="C:/m/model.EDB"):
        self.model, self.filename = model, filename


class AnalysisTests(unittest.TestCase):
    def test_state_not_needed_when_locked_and_all_finished(self):
        a = FakeAnalyze({"Dead": 4, "Modal": 4}, {"Dead": True, "Modal": True})
        st = analysis_state(FakeSession(FakeModel(a, True)))
        self.assertEqual((st["analyzed"], st["needs_analysis"], st["unfinished"]), (True, False, []))

    def test_state_needed_when_unlocked_or_case_missing(self):
        a = FakeAnalyze({"Dead": 4, "Push": 1}, {"Dead": True, "Push": True})
        st = analysis_state(FakeSession(FakeModel(a, True)))
        self.assertTrue(st["needs_analysis"])
        self.assertEqual(st["unfinished"], ["Push"])
        a2 = FakeAnalyze({"Dead": 1}, {"Dead": True})
        self.assertTrue(analysis_state(FakeSession(FakeModel(a2, False)))["needs_analysis"])

    def test_cases_not_flagged_do_not_count(self):
        a = FakeAnalyze({"Dead": 4, "Push": 1}, {"Dead": True, "Push": False})
        self.assertFalse(analysis_state(FakeSession(FakeModel(a, True)))["needs_analysis"])

    def test_nonlinear_cases_ignored_and_not_run_by_default(self):
        a = FakeAnalyze({"Dead": 4, "Push": 2}, {"Dead": True, "Push": True})
        m = FakeModel(a, True, nl=True)
        st = analysis_state(FakeSession(m))
        self.assertFalse(st["needs_analysis"])
        self.assertEqual(st["skipped_nonlinear"], ["Push"])
        self.assertTrue(analysis_state(FakeSession(m), nonlinear=True)["needs_analysis"])
        a2 = FakeAnalyze({"Dead": 1, "Push": 1}, {"Dead": True, "Push": True})
        r = run_analysis(FakeSession(FakeModel(a2, False, nl=True)))
        self.assertEqual(a2.during, {"Dead": True, "Push": False})        # pushover dezactivat pe durata analizei
        self.assertEqual(a2.flags, {"Dead": True, "Push": True})           # si refacut dupa
        self.assertEqual(r["skipped_nonlinear"], ["Push"])
        a3 = FakeAnalyze({"Dead": 1, "Push": 1}, {"Dead": True, "Push": True})
        run_analysis(FakeSession(FakeModel(a3, False, nl=True)), nonlinear=True)
        self.assertEqual(a3.flag_log, [])

    def test_run_success(self):
        a = FakeAnalyze({"Dead": 1}, {"Dead": True})
        r = run_analysis(FakeSession(FakeModel(a, False)))
        self.assertEqual((a.ran, r["analyzed"], r["unfinished_after"]), (1, True, []))

    def test_run_requires_saved_file(self):
        a = FakeAnalyze({"Dead": 1}, {"Dead": True})
        with self.assertRaises(EtabsError):
            run_analysis(FakeSession(FakeModel(a, False), filename=""))
        self.assertEqual(a.ran, 0)

    def test_run_failure_raises(self):
        a = FakeAnalyze({"Dead": 1}, {"Dead": True}, run_code=1)
        with self.assertRaises(EtabsError):
            run_analysis(FakeSession(FakeModel(a, False)))


if __name__ == "__main__":
    unittest.main()
