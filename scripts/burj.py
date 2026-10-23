"""Construieste si verifica turnul in Y inspirat de Burj Khalifa (165 de niveluri, 828 m). Utilizare:  python scripts/burj.py [--analyze] [--no-calibrate] [--name burj]"""
import sys

from run_model import run

BURJ = dict(structure="turn_inalt", tall=True, basement=2, basement_height=4.5, diaphragm="rigid", modal_type="ritz", modes_total=120, mesh_max=3.0,
            soil_pressure=25.0, basement_wall_t=0.8)

if __name__ == "__main__":
    sys.exit(run(BURJ, "burj", __doc__))
