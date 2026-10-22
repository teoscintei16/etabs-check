"""Parametrii proiectului (Setari): valorile pe care utilizatorul le confirma o data pe model."""
from .registry import Param

PROJECT_PARAMS = [
    Param("ag", None, "Accelerația de proiectare ag", "g", "number"),
    Param("gamma_I", None, "Factor de importanță-expunere γI (inclus în spectru)", "", "number"),
    Param("beta0", None, "β0 – amplificarea dinamică maximă", "", "number"),
    Param("Tb", None, "Perioada TB", "s", "number"),
    Param("Tc", None, "Perioada TC", "s", "number"),
    Param("Td", None, "Perioada TD", "s", "number"),
    Param("q", None, "Factor de comportare q", "", "number"),
    Param("beta_lim", 0.2, "Limita inferioară a spectrului (fracțiune din ag)", "", "number"),
    Param("lambda_mfse", 0.85, "λ – factor de corecție pentru metoda forțelor statice echivalente", "", "number"),
    Param("ecc", 0.05, "Excentricitate accidentală (fracțiune din latura clădirii)", "", "number"),
    Param("tip_cladire", None, "Tip de clădire (pentru „q topit”)", "", "choice",
          ["rezidential_cadre", "rezidential_pereti", "birouri_cadre", "birouri_pereti", "incarcari_grele"]),
    Param("auto_analiza", "nu", "Rulează automat analiza din aplicație când modelul nu are rezultate (modifică modelul: salvează rezultatele)", "", "choice", ["da", "nu"]),
    Param("basement", None, "Există subsol (infrastructură rigidă tip cutie)? „nu” = doar suprastructura, încastrată la bază", "", "choice", ["da", "nu"]),
    Param("basement_stories", None, "Nivelurile de subsol", "", "stories"),
    Param("ground_story", None, "Primul nivel peste ±0.00 (opțional: se deduce din subsoluri)", "", "story"),
    Param("pier_ignora_infra", "da", "Ignoră pereții de la subsol la verificarea etichetelor Pier (dacă există subsol)", "", "choice", ["da", "nu"]),
]
