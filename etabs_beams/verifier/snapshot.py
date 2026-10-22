"""Instantaneu al modelului: tabele ETABS citite o singura data (kN, m) + geometria/clasificarea din reader."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..connection import EtabsSession
from ..models import ModelData, Tolerances


class Snapshot:
    def __init__(self, session: EtabsSession, belt_sections: list[str] | None = None):
        self.session = session
        self.tol = Tolerances(belt_sections=list(belt_sections or []))
        self.model_file = session.filename
        self.analyzed = session.analyzed
        self.original_units = session.model.GetPresentUnits()     # unitatile modelului (le restauram dupa citire)
        self.analysis_model_created = self._ensure_analysis_model()
        self._tables: dict[str, pd.DataFrame] = {}
        self.unavailable: set[str] = set()
        self._model: ModelData | None = None
        self._extras = None
        self._legacy: dict | None = None
        self.cache: dict = {}

    def _ensure_analysis_model(self) -> bool:
        """Tabelele „Objects and Elements - ...” exista doar daca modelul de analiza e creat (nu cere rularea analizei si nu blocheaza modelul).
        Fara el, un model nerulat ar arata gol verificarilor de geometrie/pereti/noduri."""
        try:
            return self.session.model.Analyze.CreateAnalysisModel() == 0
        except Exception:
            return False

    # ---- tabele
    def table(self, key: str) -> pd.DataFrame:
        """Tabela ETABS ca DataFrame (coloane numerice convertite). Gol daca tabela nu exista/nu are date."""
        if key in self._tables:
            return self._tables[key]
        self._tables[key] = self._fetch(key)
        return self._tables[key]

    def results_table(self, key: str, cases=(), combos=()) -> pd.DataFrame:
        """Tabela de rezultate pentru cazurile/combinatiile cerute. Selectia de afisare din ETABS se salveaza si se restaureaza."""
        ck = (key, tuple(cases), tuple(combos))
        if ck in self._tables:
            return self._tables[ck]
        db = self.session.model.DatabaseTables

        def chosen(r):
            return [str(x) for x in r[1] if x]

        with self.session.units():
            prev_cases, prev_combos = chosen(db.GetLoadCasesSelectedForDisplay()), chosen(db.GetLoadCombinationsSelectedForDisplay())
            db.SetLoadCasesSelectedForDisplay(list(cases))
            db.SetLoadCombinationsSelectedForDisplay(list(combos))
            try:
                df = self._fetch(key)
            finally:
                db.SetLoadCasesSelectedForDisplay(prev_cases)
                db.SetLoadCombinationsSelectedForDisplay(prev_combos)
        self._tables[ck] = df
        return df

    def _fetch(self, key: str) -> pd.DataFrame:
        sap = self.session.model
        with self.session.units():
            r = sap.DatabaseTables.GetTableForDisplayArray(key, [""], "All", 0, [], 0, [])
        df = pd.DataFrame()
        if r[-1] == 0 and r[3]:
            fields, n, data = list(r[2]), r[3], r[4]
            df = pd.DataFrame(np.array(data, dtype=object).reshape(n, len(fields)), columns=fields)
            for c in df.columns:
                s = df[c].replace("", np.nan)
                conv = pd.to_numeric(s, errors="coerce")
                if conv.notna().sum() == s.notna().sum():
                    df[c] = conv
                else:
                    df[c] = df[c].where(df[c].notna(), "")
        else:
            self.unavailable.add(key)
        return df

    # ---- geometrie / clasificare (reader existent)
    def loaded_model(self) -> ModelData | None:
        """Modelul doar daca a fost deja citit (fara a declansa citirea)."""
        return self._model

    @property
    def model(self) -> ModelData:
        if self._model is None:
            from ..reader_fast import read_model_fast
            with self.session.units():
                self._model = read_model_fast(self.session, self.table, self.cache, self.tol)
        return self._model

    @property
    def extras(self):
        if self._extras is None:
            from ..checker import gather_extras
            self._extras = gather_extras(self.session)
        return self._extras

    def legacy_issues(self) -> dict:
        """Rezultatele verificatorului initial (geometrie, centuri, grinzi), grupate pe cod."""
        if self._legacy is None:
            from ..checker import run_checks
            self._legacy = {i.code: i for i in run_checks(self.model, self.tol, self.extras)}
        return self._legacy
