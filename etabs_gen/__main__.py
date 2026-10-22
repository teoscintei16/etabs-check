import argparse

from .server import serve

p = argparse.ArgumentParser(prog="etabs_gen", description="Generator de modele ETABS pentru testarea verificatorului")
p.add_argument("--port", type=int, default=8766)
serve(p.parse_args().port)
