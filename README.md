# ETABS Check

Verificatorul complet de model ETABS (v22): ~65 de verificări pe 9 zone, pentru modelul **nerulat** și **rulat**, cu reparații cu un click, istoric,
raport HTML în română și GUI (React + FastAPI) în care un clic pe o problemă selectează obiectele în ETABS.

```
pip install -r requirements.txt        # comtypes, fastapi, uvicorn, pandas, numpy, scipy, shapely, networkx
cd gui && npm install && npm run build && cd ..
python -m etabs_beams serve            # http://127.0.0.1:8765
python -m unittest discover -s tests -t .
```

Documentația de proiectare: `PLAN.md` și `docs/`.

## Trei proiecte independente

| Proiect | Rol |
|---|---|
| **etabs-check** (acesta) | verifică modelul ETABS înainte și după analiză |
| [etabs-creator](https://github.com/teoscintei16/etabs-creator) | generează modele de test (cadre, pereți, nuclee, subsol, turnuri) pe care se încearcă verificatorul |
| [etabs-beam-extract](https://github.com/teoscintei16/etabs-beam-extract) | detectează grinzile continue și centurile de perete și exportă JSON |

Fiecare are repo, teste și pornire proprii; codul comun de bază (modele de date, citirea tabelelor) este copiat în fiecare, ca să funcționeze separat.
