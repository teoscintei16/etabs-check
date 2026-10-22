import unittest

from etabs_beams.checker import ERROR, Extras, report, run_checks
from etabs_beams.models import BEAM, Frame, SectionInfo, Tolerances
from tests.builders import Builder


def codes(issues):
    return {i.code: i for i in issues}


class CheckerTests(unittest.TestCase):
    def _belt_model(self, with_wall):
        b = Builder()
        b.md.sections["dummy"] = SectionInfo("dummy", "rect", 0.4, 0.2)
        nb = b.beam((0, 0, 3), (4, 0, 3), "dummy")
        if with_wall:
            b.wall("W", (0, 0, 0), (4, 0, 3))
        md = b.finish()
        md.beam_names, md.belt_names = [], [nb]
        return md, nb

    def test_belt_over_wall_ok(self):
        md, _ = self._belt_model(True)
        c = codes(run_checks(md, Tolerances(belt_sections=["dummy"])))
        self.assertNotIn("belt_without_wall", c)

    def test_belt_without_wall_is_error_with_ids(self):
        md, nb = self._belt_model(False)
        iss = run_checks(md, Tolerances(belt_sections=["dummy"]))
        c = codes(iss)
        self.assertEqual(c["belt_without_wall"].severity, ERROR)
        self.assertIn(("frame", nb), c["belt_without_wall"].objects)
        rep = report(md, iss)
        self.assertFalse(rep["ready"])
        obj = [i for i in rep["issues"] if i["code"] == "belt_without_wall"][0]["objects"][0]
        self.assertEqual(obj["label"], "B" + nb)            # eticheta ETABS
        self.assertEqual(obj["name"], nb)                    # nume unic
        self.assertEqual(obj["story"], "S1")

    def test_belt_hint_when_not_declared(self):
        md, _ = self._belt_model(False)
        self.assertIn("belt_hint", codes(run_checks(md, Tolerances())))

    def test_declared_belts_but_none_found(self):
        b = Builder()
        b.beam((0, 0, 3), (4, 0, 3))
        self.assertEqual(codes(run_checks(b.finish(), Tolerances(belt_sections=["dummy*"])))["no_belt_frames"].severity, ERROR)

    def test_duplicates_and_rotation(self):
        b = Builder()
        b.beam((0, 0, 3), (4, 0, 3)); b.beam((0, 0, 3), (4, 0, 3))
        b.beam((0, 5, 3), (4, 5, 3), angle=90.0)
        c = codes(run_checks(b.finish(), Tolerances()))
        self.assertIn("duplicate_frames", c)
        self.assertEqual(len(c["beam_local_axes_rotated"].objects), 1)

    def test_duplicate_nodes(self):
        b = Builder()
        n1 = b.beam((0, 0, 3), (4, 0, 3)); n2 = b.beam((4, 0, 3), (8, 0, 3))
        md = b.finish()
        md.frames[n2].p1 = "OTHER"                           # acelasi loc, alt nod
        self.assertIn("duplicate_nodes", codes(run_checks(md, Tolerances())))

    def test_beam_end_on_beam_without_node_is_support(self):
        b = Builder()
        b.column(0, 0); b.column(8, 0); b.column(4, 6)
        b.beam((0, 0, 3), (8, 0, 3))                          # grinda principala, fara nod la x=4
        sec = b.beam((4, 6, 3), (4, 0, 3), "B30x40")         # se termina pe interiorul ei
        md = b.finish()
        c = codes(run_checks(md, Tolerances()))
        self.assertEqual(c["secondary_beams"].severity, "info")      # grinda secundara: normal, nu avertisment

    def _beam_ending_on_belt(self):
        b = Builder()
        b.md.sections["dummy"] = SectionInfo("dummy", "rect", 0.4, 0.2)
        b.column(0, 0)
        nb = b.beam((0, 0, 3), (5, 0, 3))                        # se termina pe interiorul centurii, fara nod comun
        nt = b.beam((5, -3, 3), (5, 3, 3), "dummy")              # centura (peste perete)
        b.wall("W", (5, -3, 0), (5, 3, 3))
        md = b.finish()
        md.beam_names, md.belt_names = [nb], [nt]
        return md, nb

    def test_beam_ending_on_belt_over_wall_is_fixed_and_not_floating(self):
        md, nb = self._beam_ending_on_belt()
        self.assertNotIn("beam_floating", codes(run_checks(md, Tolerances(belt_sections=["dummy"]))))

    def test_beam_end_on_wall_face_without_node_is_wall_support(self):
        b = Builder()
        nb = b.beam((0, 0, 3), (5, 0, 3))
        b.wall("W", (5, -3, 0), (5, 3, 3), thickness=0.3)         # nicio legatura de nod cu grinda
        md = b.finish()
        self.assertNotIn("beam_floating", codes(run_checks(md, Tolerances())))

    def test_truly_floating_beam_is_flagged(self):
        b = Builder()
        b.beam((0, 0, 3), (5, 0, 3))
        self.assertIn("beam_floating", codes(run_checks(b.finish(), Tolerances())))


if __name__ == "__main__":
    unittest.main()
