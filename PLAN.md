# Plan — ETABS Beam Tool (detecție grinzi continue + extragere eforturi)

## 1. Obiectiv

Un modul/CLI care, conectat la un model ETABS deschis (sau la un fișier .edb):

1. **Detectează grinzile** din model și le grupează automat în **grinzi continue** (lanțuri de elemente coliniare peste reazeme).
2. **Extrage rapid eforturile** (M, V, N, T) pentru un set ales de cazuri/combinații, la stațiile de calcul.
3. Livrează totul într-un **format stabil (JSON / DataFrame)**, consumat de programul separat care calculează grinzile (armare / verificări).

Programul de calcul nu trebuie să știe nimic despre API-ul ETABS: primește doar „grinda continuă X, cu deschiderile, secțiunile și anvelopa/eforturile pe stații".

## 2. Ce s-a stabilit din analiza API-ului și a manualului

### Mediu
- ETABS 22 instalat (`C:\Program Files\Computers and Structures\ETABS 22\ETABSv1.dll`).
- Python 3.10 cu `comtypes`, `pandas`, `numpy`, `networkx`, `pywin32`. `pythonnet` și `dotnet` nu sunt instalate.
- Există deja un MCP `etabs` (read_model_geometry, read_frame_sections etc.), dar este orientat pe **modelare**. Pentru viteză și control, tool-ul nostru va avea propriul conector.

### Metode API relevante

| Scop | Metodă | Observații |
|---|---|---|
| Conectare | `cHelper.GetObject("CSI.ETABS.API.ETABSObject")` / `GetObjectProcess` / `CreateObjectProgID` | atașare la instanța deschisă sau pornire nouă |
| Unități | `SapModel.GetPresentUnits` / `SetPresentUnits` | forțăm și apoi restaurăm unitățile |
| **Toate barele într-un apel** | `FrameObj.GetAllFrames` | întoarce nume, secțiune, etaj, puncte I/J, coordonate I/J, unghi, offseturi, cardinal point. **Esențial pentru viteză** (evită N apeluri) |
| Tip bară | `FrameObj.GetDesignOrientation` | enum: Column=1, **Beam=2**, Brace=3, Null=4, Other=5. Este baza clasificării |
| Axe locale | `FrameObj.GetLocalAxes`, `GetTransformationMatrix` | pentru a lega M2/M3 de axa „puternică" și pentru orientarea grinzii |
| Releases | `FrameObj.GetReleases` | articulații la capete → afectează continuitatea (o articulație rupe lanțul de momente) |
| Offseturi capete | `GetEndLengthOffset`, `GetInsertionPoint_1` | lungimi libere, excentricități |
| Stații de ieșire | `FrameObj.GetOutputStations` | numărul de stații controlat de model (MaxSegSize / MinSections) |
| Conectivitate noduri | `PointObj.GetConnectivity`, `GetRestraint` | ce obiecte (stâlpi, pereți, grinzi) se leagă într-un nod și dacă are reazem |
| Etaje | `Story.GetStories` | grupare pe nivel, cote |
| **Eforturi** | `Results.FrameForce(Name, ItemTypeElm=ObjectElm, …)` | P, V2, V3, T, M2, M3 per stație (`ObjSta`) per caz/combinație (`LoadCase`, `StepType`, `StepNum`) |
| Selecție cazuri | `Results.Setup.DeselectAllCasesAndCombosForOutput`, `SetCaseSelectedForOutput`, `SetComboSelectedForOutput` | **obligatoriu** înainte de `FrameForce`, altfel nu întoarce nimic |
| Anvelope | `Results.Setup.SetOptionMultiValuedCombo` | controlează dacă combinațiile dau Max/Min (anvelopă) sau pas cu pas |
| Alternativă bulk | `DatabaseTables.GetTableForDisplayArray` / `…CSVFile` (tabelul „Element Forces - Beams") | o singură interogare pentru toate barele; de comparat ca viteză |
| Rulare analiză | `Analyze.GetCaseStatus`, `RunAnalysis`, `Model.GetModelIsLocked` | verificăm că rezultatele există |

### Convenții din manual (Output_Conventions / Frame_Element_Internal_Forces)
- M3 pozitiv = compresiune pe fața +2, tensiune pe fața −2. M2 pozitiv = compresiune pe fața +3.
- Pentru grinzi gravitaționale uzual: **M3 + V2** (axa locală 2 în plan vertical dacă unghiul local = 0).
- Trebuie normalizat semnul într-un convention unic al tool-ului (ex. M > 0 = întinde fibra inferioară) și documentat.

### Capcane identificate
- `GetDesignOrientation` poate fi `Null`/`Other` dacă utilizatorul nu a rulat designul. Avem nevoie de **fallback geometric** (bară orizontală, nu verticală, nu diagonală).
- `FrameForce` cere ca modelul să fie analizat, iar cazurile selectate explicit.
- Nodurile intermediare se pot crea prin meshing intern: în `FrameForce` folosim **`ObjectElm`** și `ObjSta` (stația pe obiect), nu pe element.
- Unitățile din API sunt cele „present units" — trebuie fixate explicit (ex. kN, m).
- `comtypes` și parametrii `ref` de tip array din API-ul .NET: **de validat într-un spike** (vezi riscuri).

## 3. Arhitectură propusă

```
etabs_beams/
  connection.py    # atașare/pornire ETABS, unități, context manager, verificări model
  model_reader.py  # GetAllFrames + puncte + secțiuni + etaje → structuri de date (bulk)
  classify.py      # grindă / stâlp / diagonală (orientation + fallback geometric)
  continuity.py    # graf noduri-grinzi → lanțuri continue
  results.py       # selecție cazuri, FrameForce bulk, normalizare semne/unități
  export.py        # JSON + DataFrame + CSV
  cache.py         # cache geometrie (hash model) și eforturi
  api.py           # interfața publică pentru programul de calcul
  cli.py           # linie de comandă
  tests/           # teste pe date sintetice (fără ETABS) + teste de integrare cu ETABS
```

Principiu: **separăm logica pură (clasificare, continuitate) de accesul ETABS**. Tot ce e în `classify`/`continuity` primește date simple (dataclass-uri) și poate fi testat fără ETABS.

### Modele de date (minim)
- `Beam`: `name`, `story`, `section`, `p1/p2` (nume + XYZ), `length`, `local_angle`, `releases`, `offsets`, `orientation`
- `Support`: `node`, `type` (`column` / `wall` / `beam` / `restraint` / `none`), `coords`
- `ContinuousBeam`: `id`, `story`, `members[]` ordonate, `supports[]`, `spans[]` (lungimi), `sections`, `total_length`, `warnings[]`
- `ForceRecord`: `beam_id`, `chain_id`, `station_chain` (abscisa pe grinda continuă), `station_member`, `case`, `step_type`, `P, V2, V3, T, M2, M3`

## 4. Algoritm detecție grinzi continue (partea critică)

1. **Filtrare**: păstrăm barele cu `Beam` (sau fallback: |Δz| / L < toleranță, ex. 2%) și `Straight`. Excludem stâlpi, diagonale și barele curbe (cu avertisment).
2. **Graf**: noduri = puncte ETABS, muchii = grinzi. Pentru fiecare nod: lista grinzilor incidente + obiecte conectate (stâlpi/pereți/reazem prin `PointObj.GetConnectivity`).
3. **Împerechere în nod** (la fiecare nod, pentru grinzile incidente):
   - calculăm unghiul dintre direcțiile a două grinzi (vectori pornind din nod);
   - două grinzi se leagă dacă sunt **coliniare** (unghi ≈ 180°, toleranță configurabilă, ex. 10°) și aceeași cotă (|Δz| ≤ tol);
   - dacă la un nod sunt mai mult de 2 grinzi (T / cruce), alegem perechea cu cea mai bună coliniaritate; **grinzile perpendiculare se opresc** în nod și tratează nodul ca reazem (grindă secundară pe grindă principală).
4. **Criterii care întrerup continuitatea**:
   - release de moment la capăt (articulație) pe unul dintre cele două capete din nod;
   - diferență mare de secțiune / înălțime (opțional, configurabil — în practică păstrăm continuitatea statică, dar semnalăm schimbarea);
   - grinzi pe etaje diferite sau cote diferite peste toleranță;
   - reguli utilizator (forțat „rupe aici" / „unește aici").
5. **Lanțuri**: componente conexe din muchiile de continuitate → fiecare lanț = `ContinuousBeam`. Ordonare de la un capăt la altul, calcul abscise cumulative (`station_chain`).
6. **Reazeme**: la fiecare nod al lanțului — stâlp sus/jos, perete, reazem punctual, sau grindă principală (reazem „elastic"). Capete libere → consolă. Notăm tipul de reazem, important pentru calculul ulterior.
7. **Controale de calitate** (emise ca `warnings`): grinzi neclasificate, lanțuri cu un singur element, goluri între grinzi (offseturi), grinzi suprapuse, schimbări mari de unghi, secțiuni diferite în același lanț.

## 5. Extragere rapidă a eforturilor

**Strategie în două variante, de măsurat în spike:**

- **A. `Results.FrameForce` în buclă pe bare** (ObjectElm). Simplu, dar N apeluri COM → poate fi lent pe modele mari.
- **B. `DatabaseTables.GetTableForDisplayArray`** pe tabelul de eforturi ale barelor, cu cazurile selectate o singură dată → un singur apel pentru tot modelul, filtrat apoi în pandas.

Optimizări (indiferent de variantă):
- se selectează **o singură dată** cazurile/combinațiile cerute (nu toate), cu `DeselectAll…` + `Set…SelectedForOutput`;
- se cer doar barele din lanțurile detectate (nu tot modelul);
- se folosesc anvelope Max/Min acolo unde se cer (combinații) pentru volum mic;
- cache pe (hash model, cazuri) — re-rularea cu aceleași cazuri nu mai interoghează ETABS;
- ieșirea e tabelară (numpy/pandas), fără obiecte per stație.

**Reconstrucția pe grinda continuă**: eforturile fiecărui element se mută pe abscisa lanțului (`station_chain = offset_membru + ObjSta`), se elimină stațiile duplicate din noduri (se păstrează ambele valori acolo unde există salt, ex. V) și se întorc ordonate. Se oferă și derivate utile programului de calcul: **valori pe față de reazem** (nu pe axa stâlpului), anvelopa M+ / M− per deschidere și V max per capăt de deschidere.

**Selecții de cazuri**: listă explicită de cazuri/combinații, sau filtre (prefix, tip: ULS/SLS/seism), plus „doar combinațiile de design" (`cCombo.GetNameList` + prefix/tip).

## 6. Interfața către programul de calcul

Două moduri, aceeași structură de date:

1. **Bibliotecă Python**:
   ```python
   with EtabsSession.attach() as s:
       beams = s.detect_continuous_beams(story=None, tolerances=...)
       forces = s.extract_forces(beams, cases=["ULS1", "ULS2"], units=("kN", "m"))
   ```
2. **CLI → JSON/CSV**, pentru ca programul de calcul să poată rula tool-ul ca proces separat:
   - `etabs-beams detect -o beams.json`
   - `etabs-beams forces --beams beams.json --cases ULS1,ULS2 -o forces.json`

Schema JSON versionată (`schema_version`), cu unități declarate explicit în fișier.

## 7. Etape de implementare

| Etapă | Conținut | Rezultat verificabil |
|---|---|---|
| **0. Spike** | Conectare din Python (`comtypes`) la ETABS 22; `GetAllFrames` și `FrameForce` pe un model mic; verificare marshalling pentru array-uri `ref`. Dacă `comtypes` nu merge: alternativă (script `.NET`/PowerShell sau `pythonnet`) | script care listează barele și eforturile unei grinzi |
| **1. Conector + model reader** | `connection.py`, `model_reader.py`, unități, verificări (model analizat/deblocat) | dump JSON al geometriei pentru un model real |
| **2. Clasificare + continuitate** | `classify.py`, `continuity.py` pe dataclass-uri, teste sintetice (grinzi în linie, T, cruce, console, grinzi decalate, articulații) | teste unitare verzi + raport vizual (listă lanțuri) pe un model real |
| **3. Eforturi** | `results.py` cu variantele A și B, benchmark, normalizare semne/unități, reconstrucție pe lanț | tabel eforturi + comparație cu ETABS (valori verificate manual pe 2–3 grinzi) |
| **4. Interfață și export** | `api.py`, `cli.py`, schema JSON, cache | integrare de probă cu programul de calcul |
| **5. Robustețe** | modele mari, avertismente, reguli utilizator (rupe/unește), logging | rulare pe modele reale fără intervenții |

## 8. Verificare

- **Teste fără ETABS**: geometrii sintetice pentru continuitate (în linie, T, cruce, console, ramură cu unghi, cote diferite, articulație).
- **Teste cu ETABS**: model de referință mic cu rezultate cunoscute (ex. grindă continuă pe 3 deschideri sub încărcare uniformă → comparat cu valorile teoretice M = qL²/10 etc.).
- **Validare încrucișată**: eforturile extrase vs. tabelul din ETABS (Display → Tables) pentru aceleași combinații.
- **Benchmark**: timp pe un model cu ≥ 1000 grinzi pentru variantele A și B.

## 9. Riscuri

| Risc | Mitigare |
|---|---|
| `comtypes` nu marshalează corect parametrii `ref` array ai API-ului ETABS | spike în etapa 0; alternative: `pythonnet` + `ETABSv1.dll`, sau mic utilitar C# |
| `FrameForce` lent pe modele mari | varianta B (DatabaseTables), filtrare doar pe lanțurile necesare, cache |
| Modele cu grinzi „neobișnuite" (în pantă, excentrice, cu offseturi) | toleranțe configurabile, avertismente, reguli manuale |
| Orientarea (Beam/Null) nesetată | fallback geometric |
| Semne/axe locale diferite între grinzi (rotiri 180°) | normalizare folosind matricea de transformare, nu doar numele axei |
| ETABS se poate bloca la apeluri pe modele neanalizate | verificări prealabile (`GetModelIsLocked`, `GetCaseStatus`) |

## 10. Decizii luate (confirmate de utilizator)

1. **Python** cât mai mult; JSON doar pentru exportul datelor.
2. **Eforturi**: M3, M2, V2, V3, N (P), T — toate. Plus **proprietățile deschiderii** (lungime, secțiune, reazeme etc.).
3. **Continuitate**: lanțul **nu** se întrerupe la schimbarea secțiunii (doar avertisment/informare).
4. **Grinzi perpendiculare**: intersecția este **reazem** pentru grinda care *se termină* în acel punct (capătul ei); grinda traversantă rămâne continuă.
5. **Reducere la fața stâlpului/elementului vertical**: calculată direct în program. La fiecare reazem se determină elementul vertical intersectat (stâlp/perete), se ia dimensiunea secțiunii **paralelă cu axa grinzii** și se aplică un offset de **jumătate din ea** de fiecare parte → eforturi la fața reazemului.
6. Există o instanță ETABS pornită și pregătită → se testează direct pe ea (etapa 0).

## 11. Rezultate spike (etapa 0) — făcut pe instanța ETABS reală

Model: 2154 bare, 14 etaje, 24 cazuri, 18 combinații, model analizat (`locked=True`). Scripturi: [etabs_beams/spike.py](etabs_beams/spike.py), [spike2.py](etabs_beams/spike2.py), [spike3.py](etabs_beams/spike3.py).

- **`comtypes` funcționează** (`GetActiveObject("CSI.ETABS.API.ETABSObject")`). Parametrii `ref` se întorcă ca listă/tuplu: `[valori..., cod_retur]` (codul de retur e ultimul). Rulat fără `-I` (are nevoie de site-packages ale utilizatorului).
- **Unități**: `GetPresentUnits = 9` → **N, mm** în modelul curent (coordonate în mm, forțe în N, momente în N·mm). Tool-ul trebuie să seteze/convertească explicit unitățile (ex. kN, m) și să le declare în export.
- **Clasificare**: `GetDesignOrientation` → 1585 Beam, 96 Column, **473 Null**. Cele 473 `Null` necesită clasificare geometrică de rezervă (decizie: se tratează ca grinzi dacă sunt orizontale; de verificat ce sunt).
  Apelul pe toate barele durează ~2,4 s.
- **`Results.FrameForce` (ObjectElm)**: primul apel ~1,1 s (inițializare), apoi **3–20 ms/apel**. Returnează stațiile pe elemente → **stații duplicate** la limitele elementelor (valori diferite la salturi de forță tăietoare) — trebuie tratate la reconstrucția pe lanț.
- **`DatabaseTables` – „Element Forces - Beams"**: **toate grinzile, o combinație, 45.643 rânduri în 1,84 s**. Câmpuri: Story, Beam (etichetă), UniqueName, OutputCase, CaseType, Station, P, V2, V3, T, M2, M3, Element, ElemStation. Se selectează combinațiile cu `SetLoadCombinationsSelectedForDisplay`.
  **Decizie provizorie**: tabelul pentru extragerea în masă (multe grinzi/combinații), `FrameForce` pentru interogări punctuale. De confirmat timpul pe toate cele 18 combinații.
- Numele de legătură: `UniqueName` din tabel = numele obiectului din `GetAllFrames`.
- Nu s-a modificat nimic în model (doar citire și selecția de ieșire a rezultatelor).

## 12. Stare implementare (etapele 1–2 realizate)

Cod în [etabs_beams/](etabs_beams/), teste în [tests/](tests/) (8 teste sintetice, trec; `python -m unittest discover -s tests -t .`).

| Modul | Rol |
|---|---|
| `connection.py` | atașare la ETABS pornit; `units()` setează temporar **kN, m** și restaurează unitățile modelului |
| `reader.py` | citire în bloc: bare, orientare, releases, secțiuni, conectivitate noduri, reazeme, pereți |
| `classify.py` | grindă = orientare Beam, sau Null/Other orizontală cu secțiune; `ignore_sections` (ex. `dummy*`) |
| `continuity.py` | împerechere coliniară în noduri, lanțuri, reazeme (stâlp/perete/reazem/grindă), **offset la fața elementului vertical**, deschideri |
| `selector.py` | `BeamSelector`: secțiuni (include/exclude, sabloane), etaje, nume/etichete, id lanț, lungime; `match="any"/"all"` |
| `api.py`, `export.py`, `cli.py` | `detect(session, tol, selector)`, export JSON, `python -m etabs_beams detect ...` |

**Reguli implementate (conform deciziilor):** schimbarea secțiunii nu rupe lanțul; grinda perpendiculară care se termină într-un nod are acolo reazem de tip `beam`, iar grinda traversantă rămâne continuă; releases de moment rup lanțul; offsetul = jumătate din dimensiunea stâlpului/peretelui pe direcția grinzii (dreptunghi rotit cu unghiul axelor locale, verificat cu `GetTransformationMatrix`).

**Pe modelul real** (2154 bare): 1585 `Beam` + 473 `Null` fără secțiune (ignorate). Cu `--ignore-sections "dummy*"`: 698 grinzi → 515 lanțuri, 625 deschideri. ~14 s pentru citire.

**De clarificat/ rafinat:**
- Secțiunile `dummy*` apar în lanțuri (ex. `dummy40`); sunt ignorate doar la cerere (`--ignore-sections`). Ce sunt în modelul vostru?
- Reazem „perete paralel cu grinda” (`wall_along`, grindă pe perete): se marchează, offset 0. Deschiderile pe astfel de grinzi pot să nu aibă sens static.
- Capete `free` (257) = console sau capete fără element vertical/grindă; de verificat vizual.
- Stâlpii se presupun centrați pe nod (insertion point / offseturi de capăt ignorate).

**Următor: etapa 3** — eforturi M3, M2, V2, V3, N, T (tabelul „Element Forces - Beams"), reconstrucție pe abscisa lanțului, valori la fața reazemului, selectarea combinațiilor.

## 13. Logica de pereți și centuri (hibrid) — implementat

- **Centuri (dummy)**: utilizatorul e întrebat (CLI) dacă există grinzi care simulează centurile și alege secțiunile (`--belt-section "dummy*"`, `--no-belts`). Barele cu acele secțiuni **ies din grinzi** și formează lanțuri separate `CT0001…` (dummy-urile coliniare cap la cap = o singură centură). Se pot extrage separat (`--only-belts`) sau împreună (`--with-belts`).
- **Pereți**: toate shell-urile verticale sunt citite (poligon + grosime). Pe axa fiecărui lanț se calculează **zone de perete**: shell-uri coplanare cu axa, cu vârful la cota grinzii (**doar pereți sub grindă**), unite când sunt lipite (toleranță `wall_gap_tol`). Se compară lungimea din shell-uri (L2) cu cea din centuri (L1), toleranță `wall_length_tol`; la diferență → avertisment `wall_length_mismatch`, se folosește L2 (L1 dacă nu există shell-uri).
- **Perete în planul grinzii mai lung de `wall_min_length` (0,80 m, configurabil)** → portiunea de grindă de deasupra iese din lanț (`on_wall`), lanțul se rupe, iar capetele rămase au reazem `wall` la capătul peretelui.
- **Perete perpendicular / la intersecție**: reazem `wall`, **fără offset**, `fixed_end=true`. Offset doar la stâlpi.
- **Nod aflat pe un perete scurt** (în plan, ≤ `wall_min_length`): porțiunea de grindă peste perete = offset, separat pe cele două părți (`offset_before` / `offset_after`).
- **Grindă sprijinită pe o centură aflată pe perete** → capăt încastrat în perete (`kind` conține `wall`, `fixed_end=true`).
- **Tip lanț**: `continuity` = `continuous` (≥2 deschideri) sau `single_span`; selectorul are `--continuity`.

Rezultate pe modelul real: 698 grinzi → 515 lanțuri (59 continue, 456 cu o deschidere), 625 centuri din 887 dummy-uri; **grinzile reale nu se suprapun cu pereți** (0 porțiuni pe perete), în schimb 874 din 887 dummy-uri sunt pe pereți. 787 reazeme de tip perete (încastrate). 13 teste trec.
Observație: lungimea din shell-uri e sistematic mai mare decât a centurii cu ~0,4 m (= grosimea peretelui) la ~42 pereți → de decis ce lungime e „adevărată” (vezi discuția).

## 14. Clarificări (L1 vs L2, perete în interiorul grinzii, stâlpi)

- **Centură vs shell**: dacă shell-ul depășește centura la un capăt cu ≈ jumătate din grosimea peretelui (a peretelui însuși sau a peretelui transversal din jonctiune; verificat geometric) → se folosește **lungimea centurii**. Orice altă diferență → avertisment `wall_length_mismatch` și se folosește shell-ul. Pe modelul real: 42 → **5** avertismente (4 dintre ele: centură de 20,1 m peste un perete de 1,8 m; 1: 4,95 vs 4,5 m).
- **Perete care se termină în interiorul unei grinzi** (grinda intră în perete): tăiat la limita de element (≥ 50% peste perete → membrul iese), cu avertisment `wall_edge_mid_member`.
- **Stâlpi**: centrați pe nod. Dimensiunea folosită = coarda dreptunghiului stâlpului pe direcția grinzii (funcționează pentru latura lungă pe direcția grinzii, pentru orice unghi al axelor locale și pentru grinzi oblice); testat unitar (unghi 0°/90°, grindă pe X/Y/diagonală).

## 15. Verificator de model (`python -m etabs_beams check`)

Interactiv: întreabă dacă există centuri și ce secțiuni (sau `--belt-section "dummy*"` / `--no-belts`), rulează verificările și tipărește pentru fiecare problemă **eticheta ETABS, numele unic, etajul și secțiunea** (lista completă în `-o raport.json`). Cod de ieșire 1 dacă sunt erori. Modul: [etabs_beams/checker.py](etabs_beams/checker.py).

| Verificare | Severitate |
|---|---|
| model neanalizat / cazuri fără rezultate / fără combinații | eroare (toate cazurile) / avertisment |
| centuri declarate dar inexistente | eroare |
| **centură care nu e peste niciun perete** (ar fi trebuit secțiune None) | eroare |
| centură cu perete doar deasupra / doar parțial dedesubt | avertisment |
| bare suprapuse, bare de lungime 0, **noduri duplicate** (grinzi neconectate) | eroare |
| grindă care se termină pe interiorul alteia fără nod comun (ETABS le leagă doar cu auto-mesh; tool-ul o consideră reazem) | avertisment |
| grinzi neconectate la nimic, cu axe locale rotite (M2/M3, V2/V3), cu offseturi de nod, cu prea puține stații de ieșire, cu pantă mare | avertisment |
| grinzi la cote între etaje, ușor înclinate, punct de inserție ne-implicit, bare fără secțiune, centuri nedeclarate (indiciu), grinzi pe pereți | info |
| secțiuni de stâlp cu dimensiune necitibilă | avertisment |

Efect secundar util: grinzile ce se termină pe interiorul altei grinzi fără nod comun sunt acum **reazem de tip grindă** și în detecția lanțurilor (capete `free`: 205 → 104).

## 16. GUI (React + TypeScript + Vite) — [gui/](gui/)

- **Backend** [etabs_beams/server.py](etabs_beams/server.py) (FastAPI): `/api/status`, `/api/sections`, `/api/check`, `/api/detect`, `/api/select`. Toate apelurile COM rulează într-un singur fir dedicat. `/api/select` golește selecția, selectează barele/pereții cerut(e) (`FrameObj.SetSelected`, `AreaObj.SetSelected`) și reîmprospătează vederea ETABS.
- **Frontend** [gui/src](gui/src): tab *Verificare model* (întrebarea despre centuri → alegerea secțiunilor → lista problemelor; **clic pe problemă = selecția obiectelor ei în ETABS**, clic pe rând = un singur obiect, cu etichetă / nume unic / etaj / secțiune) și tab *Grinzi continue* (filtre: secțiuni, etaje, tip, lungime, lungime perete; tabel lanțuri, clic = selectează barele lanțului; detalii deschideri și reazeme).
- **Rulare**: `python -m etabs_beams serve` → http://127.0.0.1:8765 (servește `gui/dist`). Dezvoltare: `cd gui && npm run dev` (proxy `/api` → 8765). Build: `npm run build`. Node.js LTS instalat cu winget (utilizator).
- Verificat pe ETABS real: clic pe „12 bare fără perete” a selectat exact cele 12 bare în ETABS.

### 16.1 Selecție multiplă în GUI
- Casetă pe fiecare **problemă**, **obiect** din listă și **lanț**; „Bifează toate / Debifează”; **Shift + clic** bifează un interval.
- Butonul „Selectează în ETABS (N … · M obiecte)” trimite uniunea fără dubluri într-o singură cerere.
- În bara de jos: „Adaugă la selecția din ETABS” (nu înlocuiește selecția curentă).
- Testat în browser cu backend simulat (ETABS oprit); selecția reală în ETABS a fost verificată la etapa anterioară.

## 17. Identificatori: doar nume unice ETABS
Id-urile proprii (`CB0001`, `CT0001`) au fost eliminate. **Id-ul unui lanț = numele unice ETABS ale barelor sale, în ordinea lanțului, unite cu `+`** (ex. `2080+2079+2078`; un lanț dintr-o singură bară are id-ul acelei bare). Etichetele ETABS rămân ca informație (`label` pe fiecare membru și pe obiectele din avertismente/verificări). Avertismentele listează direct barele/pereții implicați (nume unic + etichetă), fără obiecte „lanț”. Selectorul `chain_ids` folosește aceste id-uri; `frames` acceptă nume unic sau etichetă.

## 18. Corecții după verificarea utilizatorului
- **Grinzi secundare** (se termină pe interiorul altei grinzi, fără nod comun): sunt normale → verificarea `secondary_beams` este acum **info** (nu avertisment). Detecția le tratează ca reazem „grindă” pe grinda traversată (care rămâne continuă).
- **Grinzi „neconectate” care stau pe centuri pe pereți**: eroare a verificatorului. Acum se consideră conectat orice capăt care atinge: stâlp/centură/altă bară prin nod, **interiorul unei centuri sau grinzi fără nod comun**, **suprafața/muchia unui perete fără nod comun**, reazem punctual. Detecția: capătul unei grinzi pe interiorul unei centuri aflate pe perete, sau pe un perete → reazem `wall` cu `fixed_end` (capăt încastrat în perete).
- Pe modelul curent: 0 erori, 1 avertisment (cazurile „Push …” fără rezultate), 2 info; nicio grindă „neconectată”.

## 19. Temă GUI (paleta și fontul Claude)
Fundal crem `#faf9f5`, text `#141413`, accent terracotă `#c15f3c`, borduri `#e8e6dc`; semantice: albastru `#3f6f9f` (info), verde `#55693d` (ok), roșu/ambră atenuate. Temă întunecată automată (`prefers-color-scheme`): `#262624` / `#30302e`, accent `#d97757`. Fonturi: **Lora** (serif, titluri) și **Inter** (interfață), incluse local (`@fontsource-variable`), ca look-alike gratuit pentru fonturile proprietare Claude. Stil plat, simplu.

## 20. Reorientare: doar verificatorul de model (acum)
Detecția grinzilor continue și extragerea eforturilor trec **în fundal** (cod păstrat: `etabs_beams/continuity.py`, `api.detect`, `cli detect`, `gui/src/_later/`). Documentul de reguli este în [docs/](docs/Verificari%20si%20reguli%20ETABS%20Inainte%20de%20rulare.md), iar planul verificatorului complet (zone, model nerulat/rulat, faze) în [docs/PLAN_VERIFICATOR.md](docs/PLAN_VERIFICATOR.md).

## 21. Verificator — Faza 0 implementată
- **Backend** [etabs_beams/verifier/](etabs_beams/verifier/): `rules.py` (parsează cele 30 de reguli din `docs/`, cu zone/faze/clase), `snapshot.py` (tabele ETABS ca DataFrame, kN/m, cache), `registry.py` (`@check`, constatări, justificări, stare), `store.py` (sidecar `<model>.EDB.checks.json`: setări, centuri, justificări, liste de control), `manual.py` (clasa D), `checks/` (verificările vechi mutate pe reguli + `r1_materiale`, `r19_unitati`, `r22_greutate_proprie`).
- **API** `/api/v/*`: catalog, state, run (pe fază/zone/id), settings, waive/unwaive, manual.
- **GUI**: tab-uri mari *Model nerulat* / *Model rulat* / *Setări*; pe fiecare, tab pe zonă (9) cu numărul de probleme; carduri pe regulă (starea, clasa A–D, textul regulii, constatări cu selecție multiplă în ETABS, justificare, listă de control). Regulile neimplementate apar ca „neimplementat”.
- **Teste**: 39 (reguli parsate, verificări pe tabele sintetice, parametri din sidecar, justificări persistente, lista de control).

## 22. Verificator — Faza 1 implementată (model nerulat, clasa A)
Verificări noi (în `etabs_beams/verifier/checks/`): **10** (`r10_moduri` ≥ 3 moduri/etaj, `r10_ritz`, `r10_pdelta`), **21** (`r21_dof_diafragme`), **11** (`r11_grinzi_secundare` – info dacă lipsește eliberarea/partial fixity), **25** (`r25_eliberari` – torsiune eliberată la ambele capete), **13** (`r13_zone_rigide`), **14** (`r14_axe_locale_stalpi_arii`), **15** (`r15_null_masa`), **5** (`r5_noduri` – duplicate/apropiate + zecimale parazite, `r5_mesh`, `r5_arii_suprapuse`), **6** (`r6_sursa_masa`), **7** (`r7_tipare`), **1** (`r1_fisurare` – modificatori sau factor în materialul betonului, torsiune J).
Obiectele din constatări pot fi acum și arii (`area`) și noduri (`joint`), selectabile în ETABS. Teste: 62.

Constatări pe modelul curent: moduri insuficiente (20 față de 42 recomandate), fără zone rigide la capete (699 grinzi + 96 stâlpi, factor 0), 490 noduri cu zecimale parazite, 28 arii cu axe rotite față de restul, 399 grinzi secundare fără partial fixity (info). Fisurarea e prin factor în numele materialelor (0.2/0.5/0.6·C35/45); P-Delta prin rigiditate în cazuri.

## 23. Verificator — Faza 2 implementată (parametri de proiect + seism, combinații, rezemare)
- **Setări → Parametri proiect** (salvați lângă model): ag, γI, β0, TB, TC, TD, q, limita inferioară a spectrului (0.2), λ (0.85), excentricitatea accidentală (0.05), parterul (nivel peste ±0.00) și infrastructura rigidă (da/nu). Verificările care le cer afișează ce lipsește, nu ghicesc.
- **Verificări noi:** `r8_spectru` (spectrul P100-1 recalculat din parametri și comparat punct cu punct, cu limita inferioară; factorul de scară și **g**), `r8_caz_spectru` (CQC, combinare direcțională, 100%+30%, amortizare, excentricitate), `r20_forte_statice` (direcții X/Y, excentricități ±, coeficient față de platou), `r12_baza_seismica` (baza tiparelor seismice vs nivelul de sub parter), `r9_acoperire` (tipare neacoperite în ULS), `r9_seismice` (partea gravitațională vs masă, ortogonale, excentricitate), `r9_sls`, `r17_temperatura`, `r18_constructie_etapizata`, `r23_truss_tension`, `r24_presiuni`, `r2_rezemare` (noduri nerezemate la bază, bază articulată, arcuri/ks, unități), `r3_diafragme`.
- Teste: 78. Constatări reale pe modelul curent: baza tiparelor seismice la „Base” (nu „S1”), 3 tipare fără combinații ULS (pompieri, utila D, utila E), 4 din 32 combinații ortogonale, fără caz de temperatură la 76,6 m, fără tipar de presiune a pământului. Spectrul din model coincide cu P100-1 calculat (cu limita 0.2·ag și g inclus).

## 24. Verificator — Faza 3 implementată (geometrie și graf)
- **Elemente de mesh** (`checks/areas.py`): coordonatele elementelor de arie din tabele (joncțiune `ElmName` ↔ coordonate), cu `shapely` pentru goluri.
- **Verificări noi:** `r3_goluri` (goluri > 1 m² pe nivel, din uniunea plăcilor), `r4_pier_etichete` (pereți fără etichetă; felii coplanare cu etichete diferite), `r4_pier_continuitate` (etaje lipsă la o etichetă), `r4_grinzi_cuplare` (grinzi între doi pereți, fără spandrel), `r4_centuri_capete` (grinzi care se descarcă pe perete fără centură), `r5_calitate_mesh` (raport de aspect), `r14_normale_placi` (sensul plăcilor), `r16_directii_deck` (grupe de orientare Deck/Ribbed), `r26_corpuri` (componente conexe, turnuri definite, diafragme care leagă corpuri), `r27_rosturi` (distanța între corpuri), `r28_pier_pe_corpuri`.
- **Corecție:** `r3_diafragme` considera asignată orice placă din tabel; „None” înseamnă fără diafragmă (acum semnalat).
- **Bug reparat:** compararea ψ2 din combinații cu masa depindea de ordinea unui set (rezultat nedeterminist).
- Teste: 89.
- Constatări pe model: 535 pereți fără etichetă Pier (din 1223) și 446 felii cu etichete diferite/lipsă; etichete P08/P09/P13 cu etaje lipsă; 508 plăci fără diafragmă (504 × PL15, 4 × PL20; diafragma D4 e asignată doar celor 242 plăci PL20); 240 arii cu elemente de raport de aspect > 4; 30 de goluri > 1 m²; 154 grinzi între pereți fără spandrel (S1 definit, neasignat); un singur corp structural deasupra parterului.

## 25. Verificator — Faza 4 implementată (model rulat)
- **Infrastructură:** `Snapshot.results_table(cheie, cazuri, combinații)` selectează temporar cazurile/combinațiile cerute pentru tabelele de rezultate și **restaurează selecția de afișare din ETABS** (verificat). Verificările „rulat” sunt sărite (stare „fără rezultate”) dacă modelul nu e analizat.
- **Verificări (tab „Model rulat”):** `r10_masa_participanta` (≥ 90 % pe X/Y, moduri de torsiune la început), `r25_mesaje_analiza`, `r6_mase_etaj` (niveluri fără masă, salturi, masa totală vs greutate), `r21_cm_cr` (excentricitate față de latura clădirii, niveluri fără CM/CR), `r21_torsiune_etaj` (max/medie la cazurile seismice), `r22_reactiuni_dead` (reacțiunea din greutatea proprie vs „Material List by Story”), `r22_q_topit` (suprastructura, informativ implicit), `r2_reactiuni_intindere`, `r20_fb_static_dinamic` (Fb static vs calcul manual cu T1 și spectru, Fb dinamic/static), `r28_rigiditate_etaj` (etaje „moi”), `r3_diafragme_rigide_rezultate`.
- Parametru nou în Setări: tipul clădirii (pentru „q topit”). Teste: 100.
- Pe model: masă participantă 77,5 % (X) și 72,3 % (Y) după 20 moduri; CM/CR doar la 2 din 14 niveluri (diafragmă D4 doar la S1/S2); raport max/medie 2,03 la S1 (T1_XP); Dead = 300 099 kN vs 317 331 kN din liste (0,95, în regulă); Fb dinamic = 0,78 (X) / 0,72 (Y) din cel static; cu parametrii proiectului Fb static din model coincide cu calculul manual (−1 % la X, +11 % la Y).

## 26. Verificator — Faza 5 + hotărâri din clarificări
**Hotărâri aplicate:** parametrii proiectului îi introduce utilizatorul (nimic precompletat); în Setări: **Există subsol? (da/nu)** + **selecția nivelurilor de subsol** (parterul se deduce; „nu” = doar suprastructura, încastrată la bază → se sar verificările de subsol și se cere încastrare completă la bază); **ignorarea pereților de infra** la etichetele Pier (setare, activă dacă există subsol); **plăci fără diafragmă = eroare** (radierul de la nivelul de bază exceptat); **moduri insuficiente = eroare**; combinațiile ortogonale incomplete rămân informative (variantă simplificată asumată); **tipare absente din ULS**: eroare dacă au încărcări asignate (plăci prin seturi de încărcări uniforme / bare / noduri — cu numărul lor), info dacă nu au; **„q topit”** = încărcări aplicate (fără greutatea proprie) pe m² de planșeu al suprastructurii, comparat cu intervalele din document (avertisment în afara intervalului; pe model: 6,88 kN/m², în interval pentru pereți structurali rezidențial).
**Raport HTML** (în română): `GET /api/v/report` (buton „Exportă raport HTML”) — rezumat, parametri, comparație cu rularea anterioară, constatări pe zone/reguli cu obiecte (etichetă + nume unic + etaj + secțiune), **justificări cu motiv și dată**, liste de control, justificări acceptate; se salvează și o copie `<model>.EDB.raport.html`.
**Istoric** lângă .EDB (`history` în `<model>.EDB.checks.json`, ultimele 30 de rulări complete) + tab „Istoric” cu compararea față de rularea anterioară (rezolvate / noi / rămase pe verificare).
**Viteză:** citirea modelului din tabele (nu apeluri COM pe obiect): 18,4 s → 1,5 s, rezultate identice (lanțuri, reazeme); componente conexe vectorizate; snapshot păstrat între rulări. Rulare completă nerulat: ~90 s → **~34 s la prima rulare, ~9 s la a doua**; rulat: ~17 s. Restul timpului îl dau exporturile ETABS ale tabelelor mari de elemente (≈13 s). ETABS execută apelurile API pe un singur fir, deci procese paralele nu accelerează extragerea.
Teste: 105.

## 27. Analiză automată din aplicație + model multi-tower
**Rulare automată a analizei** (`etabs_beams/analysis.py`): `analysis_state` (model blocat? cazuri marcate „Run” fără rezultate, status 1–4) și `run_analysis` (`Analyze.RunAnalysis`, necesită fișier salvat). Endpoint-uri: `POST /api/v/analyze` (fir de fundal în firul COM, 409 dacă rulează deja), `GET /api/v/analyze/status`, `GET /api/v/analyze/needed`. Setare de proiect `auto_analiza` (da/nu, implicit **nu**): dacă „da”, rularea verificărilor din tabul „Model rulat” lansează întâi analiza când lipsesc rezultate. În GUI: banner + buton „Reîncarcă modelul și rulează” (cu confirmare, pentru că modifică modelul: salvează rezultatele) și polling la 2 s. Fiecare rulare se înregistrează în `analysis_log` lângă .EDB și apare în raport.
**Multi-tower:** id-uri de nivel „Tn-Etaj”; `Ctx` are `stories()` (unice), `towers()`, `story_id`, `plain_story`, `tower_of`, `story_ids`. Verificări adaptate: mase/etaj doar unde există elemente, torsiune și rigiditate doar pe turnul tiparului `Tn_…`, r18 pe turnul cel mai înalt, r12/r20 cu tipare „Auto Seismic – User Loads”, **regula 29** (seism pe fiecare turn; turnuri gemene cu forță tăietoare identică = info, copiere suspectă = avertisment).
**Testat pe instanța multi-tower** (4 turnuri × 14 niveluri): 8 cazuri cu status „nu a pornit” (specx, specy, Push …) → `needs_analysis`; analiza reală NU a fost rulată pe modelul utilizatorului fără acordul acestuia.
Teste: 121 (`tests/test_verifier_multitower.py`).

## 28. Reparații cu un click (infrastructură + număr de moduri)
`etabs_beams/verifier/fixes.py`: fiecare reparație are `preview` (fără scriere), `apply` (returnează datele de anulare) și `undo`. O verificare atașează reparația unei constatări prin `Finding.fix = {id, label, args}`. Endpoint-uri: `POST /api/v/fix/preview`, `POST /api/v/fix/apply` (opțional pornește analiza, fără cazurile neliniare), `POST /api/v/fix/undo/{id}`, `GET /api/v/fix/log`; jurnalul (`fix_log`) e salvat lângă .EDB. GUI: buton pe constatare → previzualizare cu valori înainte/după și avertismente → „Aplică în model” → „Anulează reparația”.
Prima reparație: `set_modal_modes` (r10_moduri, cazuri Eigen; Ritz nu). Aplicarea deblochează modelul (șterge rezultatele). Urmează P-Delta, greutate proprie, zone rigide, diafragme etc. Teste: 125.

## 29. Reparații cu un click — grupele 1 și 2
Implementate (`etabs_beams/verifier/fixes_more.py`, editare de tabele în `tableedit.py`): `ritz_add_accel` (r10_ritz), `set_selfwt` (r22_greutate_proprie), `set_dof_all` (r21_dof_diafragme), `set_load_types` (r7_tipare, tip nou editabil), `set_rigid_factor` (r13, factor editabil, implicit 0,75), `assign_diaphragm` (r3_diafragme, diafragma celor mai frecvente plăci de la același nivel), `move_nodes` (r5_noduri: valori aproape de 0 → 0 exact, restul rotunjite la 1 mm; fiecare valoare nouă e editabilă și se vede axa X/Y/Z), `apply_mesh_standard` (r5_mesh: plăci Rectangular + Localized + Merge Joints, 0,5 m; pereți 0,5 m; la nivel de arie „Default” + Add Restraints), `rename_piers` (r28: prefix turn/corp), `release_secondary` (r11: M3 eliberat la capătul grinzii, rigiditate partial fixity editabilă, 0 = articulație).
Excluse la cererea utilizatorului: r8_*, r14_*, r16, r4 (etichete, grinzi de cuplare), r25, r2, grupa 3 (doar semnalare) și grupa 4. Fără reparație, deoarece API-ul nu permite: P-Delta (`r10_pdelta`, opțiunea globală nu e în API/tabele).
GUI: previzualizarea acceptă intrări numerice și tabele de rânduri editabile cu bife; mesh-ul și coordonatele se scriu prin `DatabaseTables.SetTableForEditingArray` + `ApplyEditedTables` (testat live pe o valoare, apoi restaurată). Teste: 141.

## 30. Generator de modele ETABS (aplicație separată, `etabs_gen/`)
Scop: creează modele de test pentru verificator. Pornire: `python -m etabs_gen` (port 8766), pagină simplă cu formular. Pornește o instanță ETABS **nouă** prin `ETABSv1.Helper` (+ `ApplicationStart`), sau se atașează la una deja pornită doar dacă are modelul gol („(Untitled)”) sau generat de aplicație — modelul unui utilizator nu este înlocuit niciodată (`assert_safe_to_overwrite`).
Prima funcție: cadre (`etabs_gen/frames.py`, `FrameSpec`): x etaje, y deschideri (pe X), z travei (pe Y), secțiuni stâlp/grindă/placă, clasa betonului (C20/25…C40/50, EN 1992-1-1), permanent suplimentar și utilă pe plăci, diafragmă semirigidă/rigidă, rezemare încastrată la bază. Se salvează în `generated_models/` (ignorat de git). 5 etaje 3×3: 80 stâlpi, 120 grinzi, 45 plăci în ~4 s.
Descoperit prin testare cu verificatorul și reparat: sursa de masă fără coloanele LoadPattern/Multiplier făcea r6 să eșueze; secțiunile Membrane din șablon, neasignate, nu mai sunt semnalate; sidecar-ul modelelor salvate se pune lângă `.EDB` (nu lângă fișierul de lucru `.$et`).
Urmează: pereți izolați, pereți cuplați.

## 31. Generator — motor de creare conform regulilor
`etabs_gen/rules.py` + `seismic.py` + `tables.py` aplică după geometrie, în ordine: **fisurare** (modificatori pe secțiuni: stâlpi I×0,7 J×0,1, grinzi I×0,5 J×0,1, plăci m×0,5), **zone rigide** (×0,75 pe toate barele), **mesh** (plăci Rectangular + Localized + Merge Joints, 0,5 m; pereți 0,5 m; arii „Default” + Add Restraints), **sursa de masă** (elemente + Permanenta ×1 + Live ×ψ2, fără Dead, ca să nu se dubleze), **moduri** (3/etaj), **spectrul P100-1** (funcție user-defined în m/s², minim 0,2·ag·g), **SPECX/SPECY** (100 % + 30 %, CQC, SRSS, excentricitate 0,05), **4 tipare statice** EXP/EXN/EYP/EYN (User Coefficient, C = λ·γI·ag·β0/q, e = ±0,05) și **47 de combinații** (ULS, SLS caracteristică și cvasi-permanentă, seismice pure ± și cu componentă ortogonală 0,3). Parametrii seismici se completează în formular; se scriu și în setările verificatorului (`<model>.EDB.checks.json`).
**Descoperiri importante la testare:** (1) `ApplyEditedTables` **înlocuiește tabelul întreg** — înregistrările netrimise se șterg din model (am pierdut tiparele Dead/Live la un test cu un rând); `edit_table` din verificator și `tables.py` din generator retrimit acum tot tabelul. (2) `FrameObj.SetEndLengthOffset` ignoră factorul RZ la offset automat → se scrie tabelul „End Length Offsets”. (3) Tiparul seismic se creează întâi prin API (`LoadPatterns.Add`, tip Quake), apoi se completează tabelul „Auto Seismic - User Coefficient”; scrierea ambelor în același apply nu merge. (4) Verificatorul nu vedea modificatorii setați pe secțiuni (doar seturile de modificatori asignate) — corectat în `r1_fisurare`.
**Rezultat pe modelul generat (5 etaje, 3×3):** nerulat 42 ok / 9 info / 0 avertismente; rulat: Fb static = calcul manual (abatere 0 %), Fb dinamic 0,99·Fb static, masă participantă 90 % la modul 5/4. Avertismente rămase, legitime: mod de torsiune printre primele 3 și CR necalculat la diafragmă semirigidă (ETABS calculează CR doar la diafragme rigide). Teste: 157.

## 32. Generator — pereți izolați
`etabs_gen/layout.py` (amplasare pure: `first/last/middle/all` sau indici, grupare în pereți = șiruri de deschideri consecutive) + extensia `FrameSpec(walls=True, ...)`. Un panou de perete (secțiune Wall, ShellThin) per deschidere și per etaj, **aceeași etichetă Pier la toate etajele și panourile aceluiași perete** (PX1, PX2, PY1, PY2 la configurația implicită: câte doi pereți pe X și pe Y, pe liniile extreme, în deschiderea din mijloc). Stâlpii și grinzile se omit unde sunt pereți (opțional, `gravity_frame`); centuri dummy `CENTURA` deasupra pereților (`belts`; fără masă și greutate, ca să nu dubleze peretele) declarate automat în setările verificatorului; reazeme la colțurile bazei peretelui; fisurare pereți f×0,5 / m×0,25; grinzile și centurile au punct de inserție sus-centru (tabelul „Frame Assignments - Insertion Point”).
Descoperire importantă în verificator: tabelele „Objects and Elements - …” există doar când modelul de analiză e creat, deci un model **nerulat** părea gol verificărilor de geometrie, pereți și noduri. `Snapshot` apelează acum `Analyze.CreateAnalysisModel()` (nu rulează analiza și nu blochează modelul).
Rezultat pe modele generate (5 etaje, 3×3): pereți — nerulat 42 ok / 9 info, rulat Fb static = manual, q topit 5,0 kN/m² în interval; cadre — 41 ok / 10 info. Teste: 167.
Urmează: pereți cuplați (grinzi de cuplare + Spandrel), subsol.

## 33. Generator — pereți cuplați, subsol, structuri duale, forme neregulate
`etabs_gen/plan.py` (planul construcției, calcule pure): niveluri cu subsol (S<n>…S1 cu cota ±0.00 la partea de sus a lui S1, P, E1…), celule active pe etaj (forma `L`, `setback`), goluri în planșee (`void_cells`), pereți (șiruri de deschideri consecutive = un perete = o etichetă Pier), grinzi de cuplare în deschiderile dintre picioarele pereților (`coupling_bays_*`, cu etichetă Spandrel multi-etaj), pereți perimetrali de subsol (fără stâlpi pe perimetru, centuri dummy deasupra). `FrameSpec.structure` + presetări în formular: cadre / pereți izolați / pereți cuplați / dual (pereți pe X, cadre pe Y) / neregulat.
**Subsol:** `Story.SetStories_2` redenumește nivelurile și pune cota bazei; împingerea pământului = tipar `Impingere_pamant` (uniform, spre interior pe toate laturile) în combinațiile ULS/SLS (nu în cele seismice); forțele statice încep de la S1; parametri de proiect `basement=da`, `basement_stories=[S1…]`, `ground_story=P`. Numărul de moduri se calculează cu și subsolul.
**Calibrarea forțelor statice:** după o analiză modală, `C = λ·Sd(T1)/g` cu T1 al modului dominant pe fiecare direcție (ca în verificator); se deblochează modelul înainte de scriere (ETABS ignoră în tăcere editarea tabelelor pe model blocat) și se confirmă prin citire.
**Corectură în verificator și generator:** pereții se meshează „Auto Rectangular” (cu „Default” rămâneau un singur element pe panou, iar placa meshată la 0,5 m nu se lega de perete); standardul verificatorului pentru pereți e acum „Auto Rectangular” (așa e și în modelul utilizatorului).
Verificate pe modele generate (nerulat / rulat): cuplați 42 ok 9 info / Fb static = manual pe ambele direcții; subsol 42 ok / Fb = manual; dual și L/golf: curat nerulat; retragere cu etaj moale: avertismente reale (torsiune 1,53, etaj moale 0,66). Teste: 183.

## 34. Creatorul de modele — repo separat
Generatorul a fost mutat într-un proiect propriu, `etabs-creator/` (repo: github.com/teoscintei16/etabs-creator), cu codul spart în fișiere mici pe subiect (`spec/`, `plan/`, `seismic/`, `build/`, `rules/`, `server/`). Folderul rămâne lângă acest proiect, dar e ignorat de git aici. Dependența dinspre verificator spre creator nu mai există; creatorul scrie direct `<model>.EDB.checks.json`.
Modificări în verificator, descoperite cu modelele generate: **numărul de moduri se calculează doar cu etajele de peste teren** (subsolul rigid nu vibrează) când subsolul e declarat; **torsiunea nu se evaluează la nivelurile de subsol** (raport max/medie la deplasări aproape nule); punctele create automat de ETABS (`IsAuto`) nu mai sunt tratate ca erori de desen la `r5_noduri`. Teste: 149.

## 35. Continuitatea verticală (regula 2)
Verificare nouă `r2_continuitate_verticala` (`checks/continuity.py`): fiecare stâlp și perete care nu e la baza modelului trebuie să aibă dedesubt un stâlp sau un perete (nu o placă sau o grindă). Stâlpii se verifică în punctul de jos, pereții pe 5 eșantioane de-a lungul marginii de jos: nimic sprijinit = eroare, sprijin parțial = avertisment. Găsită la modelele cu subsol mai mare decât turnul, unde peretele turnului stătea pe placa subsolului; creatorul are acum `walls_through_basement` (implicit da; debifat reproduce defectul pentru test: verificatorul dă avertisment la cei 2 pereți parțial sprijiniți).

## 36. Separarea în trei proiecte
Extragerea grinzilor (detecție lanțuri/centuri, selector, export JSON, CLI `detect`, pagina proprie) a trecut în `etabs-beam-extract` (github.com/teoscintei16/etabs-beam-extract): citire rapidă din tabele, 31 de teste, pornire cu `python -m etabs_beam_extract serve`. Din verificator au ieșit `selector.py`, `export.py`, `continuity.py`, endpoint-ul `/api/detect`, comanda `detect` și tabul vechi de grinzi din GUI. Cele trei proiecte (verificator, creator, extractor) au repo, teste și pornire proprii; codul de bază comun (modele de date, citirea tabelelor) e copiat în fiecare. Teste verificator: 137.

## 37. Planuri libere în creator; pereți înclinați în verificator
`etabs-creator` generează acum planuri libere (cerc, elipsă, semicerc, poligon, trapez, lobi, spline), piramide (netede sau în trepte), răsucire, înclinare, atriu, pereți trapezoidali și subsol sub ele. Au ieșit la iveală, și s-au corectat în verificator:
- **Pereți înclinați:** o arie cu proprietate Wall care nu e verticală e o „rampă” pentru ETABS (nu primește etichetă Pier). `build_walls` o păstrează în `ModelData.sloped_walls` (marginile reale de jos și de sus) și o reprezintă în logica grindă-pe-perete prin două benzi verticale subțiri (`WallInfo.virtual`) pe margini; `r4_pier_etichete` o ignoră; `r2_continuitate_verticala` folosește marginile reale (reazemul se caută pe marginea de sus a peretelui de dedesubt).
- **`r14_normale_placi`:** sensul plăcii se ia din aria orientată (formula lui Gauss), nu din colțul 1: la patrulatere concave dădea fals „placă inversată”.
Teste: 141.

## 38. Creatorul respectă regulile verificatorului; reparațiile sunt verificate de la cap la cap
Instrumente de test între proiecte în `scripts/` (doar bibliotecă standard, cer ETABS deschis din creator + serverele pornite): `matrix.py` (17 structuri generate → verificator „pre”/„post”, raport în `scripts/out/matrix.json`) și `fix_roundtrip.py` (12 defecte intenționate create de creator cu `defects=<nume>` → reparația cu un click aplicată ca din GUI → defectul trebuie să dispară, să nu apară probleme noi, iar anularea să-l readucă).
**Creator:** mesh de plăci „General” la planuri libere (`mesh_floor=auto`; Rectangular lăsa elemente-ciobuc cu raport de aspect mare), registru de defecte (`defects/`), repornirea preventivă a ETABS la fiecare 8 modele și reîncercare la „Invalid pointer” (`server/recovery.py`).
**Verificator:** `r5_mesh` așteaptă „General” când există planșee neortogonale; Centrul de Rigiditate necalculat de ETABS e INFO; avertismentul de torsiune doar pentru primele 2 moduri; cazurile Ritz cu mai mulți vectori de pornire (rânduri de continuare, nume „Accel UX”) erau citite greșit de `r10_ritz`, `r10_moduri`, `r6_sursa_masa` — reparația `ritz_add_accel` nu făcea nimic și apoi dădea regresii. Rezultat: 12/12 reparații funcționează. Teste: 145.

## 39. Opera: structură cu coji sferice (creator) și coji în verificator
`etabs-creator`: `structure=opera` — podium ortogonal (motorul existent) + 2 săli cu pereți de cutie + 14 coji = petice ale aceleiași sfere (R = 75,2 m, soluția lui Utzon) cu coaste, grindă de picior, grindă frontală și legături de coamă; niveluri suplimentare T1…T4 pentru forțe seismice; vânt (presiune proiectată) și temperatură; caz modal Ritz (`modal_type=ritz`). Concept scris înainte de desen: `etabs-creator/docs/OPERA_CONCEPT.md`. Rulare: `scripts/opera.py`.
`etabs-check`: plăcile Slab înclinate > 15° sunt coji (nu cer diafragmă; INFO), coastele lor sunt excluse din r13/r23/r5_geometrie/r13_offset/r14_axe, nodurile de reazem ale cojilor din r4_centuri_capete, nivelurile doar-coji din r6_mase_etaj; r10_ritz cere Z doar cu masă verticală; r10_moduri/r6_sursa_masa citesc corect cazurile Ritz cu mai mulți vectori (rânduri de continuare; nume „Accel UX”) — acea eroare făcea ca reparația `ritz_add_accel` să nu repare nimic. 12/12 reparații verificate de la cap la cap. Teste: 151 verificator, 134 creator.

## 40. Turn foarte înalt (Burj Khalifa) și funcțiile noi ale motorului
`etabs-creator`: `structure=turn_inalt` — plan în Y (miez hexagonal + 3 aripi, retrageri în spirală), 156 niveluri de beton + 7 de spire de oțel, 2 niveluri de subsol, zone de secțiuni pe înălțime, niveluri tehnice cu centuri adânci, seturi de încărcări pe ocupare, vânt pe înălțime, temperatură, construcție etapizată, Ritz cu număr total de vectori. Concept: `etabs-creator/docs/BURJ_CONCEPT.md`; rulare: `scripts/burj.py`.
Funcții generale adăugate motorului: `build/loadsets.py` (Shell Uniform Load Sets), `build/staged.py` (grupuri + caz etapizat), `spec.modes_total`, amplificarea dinamică în `rules/calibrate.py`, `Ctx.sec_all` (fisurare pe mai multe secțiuni), `Ctx.waivers` și `params` către setările verificatorului.
Verificator: `r6_mase_etaj` fără nivelurile de catarg, `r21_torsiune_etaj` doar în direcția forței, cazuri neliniare ne-rulate ignorate la „cazuri neterminate”, secțiuni țeavă, `r8_spectru` acceptă amplificarea voită. Teste: 154 verificator, 154 creator.
