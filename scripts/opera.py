"""Construieste si verifica modelul „Opera” (podium + sali + coji sferice). Utilizare:  python scripts/opera.py [--analyze] [--no-calibrate] [--name opera]"""
import sys

from run_model import run

OPERA = dict(structure="opera", opera=True, stories=2, bays=12, travei=15, span_x=10.0, span_y=12.0, story_height=6.0, basement=1,
             basement_height=6.0, column_b=1.2, column_h=1.2, beam_b=0.6, beam_h=1.2, slab_t=0.25, concrete="C40/50", wall_t=0.5,
             basement_wall_t=0.6, mesh_max=2.0, modes_per_story=25, modal_type="ritz", diaphragm="rigid", dead_extra=3.0, live=5.0, soil_pressure=25.0)

if __name__ == "__main__":
    sys.exit(run(OPERA, "opera", __doc__))
