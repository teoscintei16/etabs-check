"""Constructor de modele de test (ModelData) pentru verificari fara ETABS."""
import math
import unittest

from etabs_beams.models import COLUMN, BEAM, Frame, ModelData, SectionInfo, Tolerances, WallInfo


class Builder:
    def __init__(self):
        self.md = ModelData()
        self.pts = {}
        self.n = 0
        self.md.sections["B30x60"] = SectionInfo("B30x60", "rect", 0.6, 0.3)
        self.md.sections["B30x40"] = SectionInfo("B30x40", "rect", 0.4, 0.3)
        self.md.sections["C40x60"] = SectionInfo("C40x60", "rect", 0.6, 0.4)   # T3=0.6, T2=0.4

    def pt(self, x, y, z=3.0):
        key = (x, y, z)
        return self.pts.setdefault(key, f"P{len(self.pts)+1}")

    def beam(self, a, b, sec="B30x60", story="S1", **kw):
        self.n += 1
        name = str(self.n)
        pa, pb = self.pt(*a), self.pt(*b)
        self.md.frames[name] = Frame(name, f"B{name}", story, sec, pa, pb, a, b, orientation=BEAM, **kw)
        self.md.beam_names.append(name)
        return name

    def column(self, x, y, sec="C40x60", angle=0.0):
        self.n += 1
        name = str(self.n)
        top, bot = self.pt(x, y, 3.0), self.pt(x, y, 0.0)
        self.md.frames[name] = Frame(name, f"C{name}", "S1", sec, bot, top, (x, y, 0.0), (x, y, 3.0),
                                     angle=angle, orientation=COLUMN)
        self.md.node_frames.setdefault(top, []).append(name)
        return name

    def wall(self, name, a, b, thickness=0.3, point_names=()):
        """Perete vertical de la a=(x,y,zmin) la b=(x,y,zmax)."""
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        pts = [(a[0], a[1], a[2]), (b[0], b[1], a[2]), (b[0], b[1], b[2]), (a[0], a[1], b[2])]
        self.md.walls[name] = WallInfo(name, thickness, d, pts, list(point_names), a[2], b[2])
        for p in point_names:
            self.md.node_areas.setdefault(p, []).append(name)

    def finish(self):
        for f in self.md.frames.values():
            if f.orientation == BEAM:
                for p in (f.p1, f.p2):
                    self.md.node_frames.setdefault(p, [])
        return self.md
