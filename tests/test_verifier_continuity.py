import unittest

from etabs_beams.models import COLUMN, Frame, ModelData, WallInfo
from tests.test_verifier_phase1 import Snap, go


def column(md, name, x, y, z0, z1):
    md.frames[name] = Frame(name, f"C{name}", "S", "C50x50", f"a{name}", f"b{name}", (x, y, z0), (x, y, z1), orientation=COLUMN)


def wall(md, name, a, b, z0, z1):
    pts = [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)]
    md.walls[name] = WallInfo(name, 0.25, (1.0, 0.0), pts, [], z0, z1, f"W{name}", "S")


class ContinuityTests(unittest.TestCase):
    def check(self, md):
        return go(Snap({}, md), "r2_continuitate_verticala")

    def test_continuous_columns_and_walls_pass(self):
        md = ModelData()
        for k in range(3):
            column(md, f"c{k}", 0, 0, 3.0 * k, 3.0 * (k + 1))
            wall(md, f"w{k}", (5, 0), (10, 0), 3.0 * k, 3.0 * (k + 1))
        r = self.check(md)
        self.assertEqual(r["status"], "info")

    def test_wall_resting_on_a_slab_is_an_error(self):
        md = ModelData()
        wall(md, "base", (0, 0), (5, 0), 0.0, 3.0)                      # un perete jos, in alta parte
        wall(md, "up", (10, 0), (15, 0), 3.0, 6.0)                      # perete sus fara nimic dedesubt
        r = self.check(md)
        self.assertEqual(r["status"], "error")
        self.assertEqual([o["name"] for o in r["findings"][0]["objects"]], ["up"])

    def test_column_on_a_wall_is_supported_and_column_in_the_air_is_not(self):
        md = ModelData()
        wall(md, "w", (0, 0), (10, 0), 0.0, 3.0)
        column(md, "ok", 4.0, 0.0, 3.0, 6.0)                            # pe peretele de dedesubt
        column(md, "bad", 4.0, 5.0, 3.0, 6.0)                           # nimic dedesubt
        column(md, "foot", 4.0, 5.0, 0.0, 0.5)                          # stalp scund doar ca sa existe baza
        r = self.check(md)
        self.assertEqual([o["name"] for o in r["findings"][0]["objects"]], ["bad"])

    def test_partially_supported_wall_is_a_warning(self):
        md = ModelData()
        wall(md, "below", (0, 0), (5, 0), 0.0, 3.0)
        wall(md, "above", (0, 0), (10, 0), 3.0, 6.0)                    # jumatate pe perete, jumatate in gol
        r = self.check(md)
        self.assertEqual(r["status"], "warning")

    def test_model_without_vertical_elements_is_ignored(self):
        self.assertEqual(self.check(ModelData())["status"], "ok")


if __name__ == "__main__":
    unittest.main()
