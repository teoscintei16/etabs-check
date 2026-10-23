"""Ruleaza doar anumite verificari pe modelul deschis. Utilizare:  python scripts/check_ids.py pre r8_spectru,r8_caz_spectru"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import harness as h  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    phase, ids = sys.argv[1], sys.argv[2].split(",")
    for k, v in h.run_check(phase, ids).items():
        print(k, v["status"])
        for f in v["findings"]:
            print("  ", f["severity"], f["message"][:240])
