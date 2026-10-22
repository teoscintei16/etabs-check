# Plan — Verificator complet de model ETABS

Sursa regulilor: [Verificari si reguli ETABS Inainte de rulare.md](Verificari%20si%20reguli%20ETABS%20Inainte%20de%20rulare.md) (30 de reguli; ultimele 5 sunt pentru modele *multi-tower*).

## 1. Scop și delimitare

- **Acum:** doar verificatorul de model (nerulat + rulat). Aplicația **nu modifică modelul**; singurele efecte asupra ETABS sunt selecția obiectelor (la cerere) și schimbarea temporară a unităților (restaurate).
- **În fundal (cod păstrat, neexpus în GUI):** detecția grinzilor continue, extragerea eforturilor, centurile ca „obiect de extras”. Codul rămâne în `etabs_beams/` (`continuity.py`, `api.detect`, `cli detect`) și `gui/src/_later/`. Se reia după verificator.
- **Reutilizăm** din ce există: conectarea COM + firul dedicat, unitățile kN/m, selecția în ETABS, rezolvarea obiectelor în *etichetă + nume unic + etaj + secțiune*, geometria (capete pe grinzi/centuri/pereți, zone de perete), detecția centurilor.

## 2. Ce ne permite API-ul (concluzia analizei)

- ETABS 22 expune **931 de tabele** prin `DatabaseTables` (citire în bloc; ~2 s pentru zeci de mii de rânduri). Practic **fiecare regulă are o sursă de date în tabele**: materiale, modificatori, eliberări, restricții/arcuri, diafragme, etichete pier/spandrel, surse de masă, tipare de încărcare, cazuri, combinații, funcții de spectru, seism automat, moduri, mase pe etaj, CM/CR, reacțiuni, derive, rigiditate de etaj, mesaje de analiză, toleranța de unire (`Preferences - Tolerance`), setările mesh-ului, turnuri și baza seismică (`Tower and Base Story Definitions`).
- **Nu există** în API „Analyze > Check Model”, deci verificările de geometrie (puncte apropiate, suprapuneri) le implementăm noi.
- **Nu rulăm analize** din aplicație (regula 22 sugerează „rulare scurtă doar cu Dead”): ar schimba rezultatele din model. Pentru ea folosim rezultatele existente sau estimări din „Material List by Story”.
- Pentru **selecție în ETABS** avem `FrameObj/AreaObj/PointObj.SetSelected`. Obiectele fără geometrie (cazuri, combinații, materiale, secțiuni) nu se selectează: se afișează cu nume și rândul din tabel.

## 3. Arhitectura propusă

```
etabs_beams/
  checks/                  # câte un modul pe zonă; fiecare verificare = funcție pură pe un snapshot
    registry.py            # @check(id, reguli, zona, faza, nivel, tabele_necesare, parametri)
    z1_materiale.py ... z9_multitower.py
  snapshot.py              # TableStore: cere tabelele o dată, le ține ca DataFrame-uri; cache până la „Reîncarcă”
  roles.py                 # rolurile încărcărilor (G, SDL, Q, Zăpadă, Vânt, Ex, Ey, Temperatură…) + ghicire din tip/nume
  params.py                # praguri configurabile cu valori implicite (+ încărcare/salvare)
  waivers.py               # „justificat de utilizator” + notă, salvat lângă model (sidecar JSON)
  report.py                # JSON (apoi HTML/PDF)
  server.py                # API: /status, /run (zone/faze), /roles, /params, /waivers, /select
```

Principii:
1. **Verificare = funcție pură** `(snapshot, params, roluri) → [Constatare]` → testabilă fără ETABS (ca acum).
2. **Constatare** = cod, severitate (eroare / avertisment / info / OK / manual / neaplicabil / justificat), mesaj, regula din document (nr.), obiecte tipate (bară, perete, nod, pier, diafragmă, caz, combinație, material, secțiune, rând de tabel) + date numerice.
3. **Clase de automatizare**, afișate în GUI ca etichetă:
   - **A – complet automat** (nu depinde de intenția utilizatorului);
   - **B – automat cu parametri/roluri** (normativ, ag, Tc, ψ, tip clădire, praguri) pe care utilizatorul le confirmă o dată;
   - **C – semi-automat** (aplicația găsește *candidații*, utilizatorul confirmă sau justifică);
   - **D – vizual/manual** (listă de control cu casetă „verificat”, plus textul din document: ce, cum, semnale de alarmă).
4. **Fază**: *Nerulat* (definiții) vs *Rulat* (rezultate). O regulă poate avea ambele componente (ex. 6, 20, 21, 22, 25).
5. **Rezultatele sunt cerute doar în tab-ul „Model rulat”**; dacă modelul nu e analizat, tab-ul arată starea și ce lipsește.
6. **Justificări** (waivers): „Acceptat, motiv…” per constatare; nu mai apare ca problemă la rulările următoare (cheie: verificare + obiect).

## 4. Structura GUI

Două **tab-uri mari**: **Model nerulat** | **Model rulat**. În fiecare, **un tab pentru fiecare zonă**, cu număr de probleme pe etichetă. Pe lângă ele, un panou „Setări” (roluri încărcări, parametri, centuri) și un tab „Rezumat” (tabloul de bord cu toate zonele).

| Tab zonă | Reguli (document) | Model nerulat | Model rulat |
|---|---|---|---|
| **1. Materiale, secțiuni, unități** | 1, 15 (modificatori), 19 | E, greutate, clase beton, J/I/A modificatori, unități | — |
| **2. Rezemare și fundații** | 2, (30) | restricții la bază, arcuri, ks, compresiune-only | presiuni sub radier, tasări; sensibilitate ks_min/med/max |
| **3. Planșee, diafragme, goluri** | 3, 16 | diafragme, tip shell/membrană, goluri > 1 m², sensul de descărcare | raportul deplasărilor între etaje (rigidă vs semi-rigidă) |
| **4. Elemente structurale** | 4, 11, 13, 14, 23, 25 | pier/spandrel, centuri, eliberări, offseturi, punct de inserție, axe locale, truss/tension-only | eforturi nerealiste în contravântuiri (M, T) |
| **5. Geometrie și mesh** | 5, 15 (Null) | noduri apropiate/duplicate, suprapuneri, mesh, aspect-ratio | mesaje „Check/warning” |
| **6. Încărcări și masă** | 6, 7, 17, 22, 24 | modele de încărcare, self-weight, mass source, presiuni, temperatură | mase pe etaj, reacțiuni vs estimare, „q topit” (kN/m²) |
| **7. Seism și combinații** | 8, 9, 12, 20, 29 | spectru, factori, excentricități, combinații, baza seismică | forță tăietoare statică vs dinamică |
| **8. Setări de analiză** | 10, 18, 21 | DOF, P-Delta, caz modal (Ritz/Eigen, nr. moduri), construcție etapizată | masă participantă ≥ 90 %, perioade, CM–CR |
| **9. Multi-tower** | 26, 27, 28, 29, 30 | separare, rosturi, continuitate, etichete pier pe turn | rigiditate pe etaj, comparații între turnuri |

## 5. Regulile, pe rând

Legendă: **N** nerulat, **R** rulat · **A/B/C/D** = clasa de automatizare.

| # | Regula | Zona | Fază | Cl. | Surse (tabele / apeluri) | Ce verificăm concret |
|---|---|---|---|---|---|---|
| 1 | Materiale, secțiuni, modificatori | 1 | N | A/B | `Material Properties - Basic Mechanical`, `- Concrete Data`, `Frame/Shell Property Modifier Definitions`, `Frame/Area Assignments - …Modifiers` | E vs clasă beton (ex. C35/45 → Ecm), greutate ≠ 0, **J (torsiune) = 1** la grinzi în model fisurat, modificatori de rigiditate prezenți (cum se face fisurarea: modificatori sau E – întrebare la utilizator) |
| 2 | Rezemare și fundații | 2 | N+R | B/C | `Joint Assignments - Restraints/Springs`, `Area Assignments - Area Springs`, `Spring Property Definitions - Area Springs`, `Soil Pressures*` | baza articulată la cadre, noduri libere sub pereți, unități/ordin de mărime ks (kN/m³), ks_min/med/max (există 3 variante?), compression-only, rezemare pe Z obligatorie; (R) presiuni/tasări, sensibilitate |
| 3 | Planșee, diafragme, goluri | 3 | N+R | B/C/D | `Area Assignments - Diaphragms`, `Diaphragm Definitions` (Rigid/Semi), `Joint Assignments - Diaphragms`, `Slab Property Definitions`, `Area Section Property Definitions - Summary`, geometrie `Objects and Elements - Areas` | noduri la nivel fără diafragmă, planșee „Membrane” fără grinzi, diafragme rigide (recomandare semi-rigid), **goluri > 1 m²** găsite din geometrie; (R) `Diaphragm Max Over Avg Drifts`, `Story Max Over Avg Displacements` |
| 4 | Elemente verticale/grinzi, pier/spandrel, dummy | 4 | N | A/C | `Area/Frame Assignments - Pier Labels / Spandrel Labels`, `Pier Label Definitions`, `Spandrel Label Definitions`, geometrie | pereți fără etichetă pier, un perete pe mai multe felii cu etichete diferite, grinzi de cuplare fără spandrel, grinzi „sparte” în bucăți mici coliniare, **centurile (dummy)** lipsă la capete de pereți unde se descarcă grinzi, centuri fără perete dedesubt |
| 5 | Geometrie curată și mesh | 5 | N+R | A | `Objects and Elements - Joints/Frames/Areas`, `Preferences - Tolerance`, `Analysis Options - Automatic Mesh…`, `Area Assignments - Floor/Wall Auto Mesh Options`, `Analysis Messages` | noduri la distanță < toleranță, coordonate cu zecimale parazite (2·10⁻⁷), bare/arii suprapuse, bare ce trec pe lângă noduri, mărimea mesh-ului (0.5–1 m, radier ~1 m²), raportul de aspect/înclinarea elementelor shell; (R) avertismente din analiză |
| 6 | Sursă de masă | 6 | N+R | B | `Mass Source Definition`, `Load Pattern Definitions`; (R) `Mass Summary by Story/Diaphragm`, `Assembled Joint Masses`, `Modal Participating Mass Ratios` | masă proprie + modele cu multiplicatori ψ₂ (parametri), **dublarea greutății proprii**, masă lipsă la un nivel, salturi de masă între etaje (prag configurabil) |
| 7 | Încărcări gravitaționale / liniare | 6 | N | B/D | `Load Pattern Definitions`, `Area Load Assignments - Uniform / Uniform Load Sets / Non-uniform`, `Frame Loads Assignments - Distributed / Point`, `Joint Loads Assignments - Force` | tipare fără nicio încărcare asignată, tip greșit (zăpadă/trafic definite „Dead”), lipsa încărcărilor pe perimetru (fațade), presiuni pământ/apă la pereții subsolului; **tipurile cerute** în funcție de rolurile alese |
| 8 | Acțiunea seismică | 7 | N+R | B | `Functions - Response Spectrum - User Defined` (sau pe cod), `Load Case Definitions - Response Spectrum`, `Load Pattern Definitions - Auto Seismic…` | **spectru recalculat din parametri** (ag, TB, TC, TD, β₀, q — P100-1) și comparat punct cu punct, **g** în factorul de scară, spectru elastic vs de proiectare, excentricitate, combinare modală (CQC) și direcțională; (R) compararea supra- vs infrastructură = nivel C (necesită al doilea model) |
| 9 | Combinații | 7 | N | B | `Load Combination Definitions`, `Load Case Definitions - Summary` | ULS/SLS (caracteristică, frecventă, cvasipermanentă) și seismice, **ortogonale** (1.0·Ex ± 0.3·Ey, toate semnele), excentricitatea accidentală, „Add” vs „Envelope” |
| 10 | Setări de analiză | 8 | N+R | A/B | `Analysis Options - Active Degrees of Freedom`, `P-Delta Option Definition`, `Modal Case Definitions - Eigen/Ritz`, `Load Case Definitions - …` ; (R) `Modal Participating Mass Ratios`, `Modal Periods And Frequencies` | 3D complet, P-Delta bifat și pe combinația corectă, **număr de moduri ≥ 3 × nr. etaje**, Ritz cu accelerații UX/UY/UZ, (R) masă participantă ≥ 90 % pe X și Y |
| 11 | Eliberări (articulații) | 4 | N | A/C | `Frame Assignments - Releases and Partial Fixity`, `Frame Release Definitions` | grinzi secundare **fără** eliberare/partial fixity (candidați; deja știm din reguli că unele sunt intenționat rigide), contravântuiri cu moment, grinzi metalice pe stâlpi de beton |
| 12 | Baza seismică | 7 | N+R | B/C | `Tower and Base Story Definitions`, `Story Definitions` | baza = fundația la o clădire cu subsoluri rigide? Utilizatorul indică nivelul ±0.00 (parametru); (R) forța tăietoare de bază verosimilă |
| 13 | Zone rigide / puncte de inserție | 4 | N | A | `Frame Assignments - End Length Offsets`, `Frame Assignments - Insertion Point` | grinzi fără offseturi la capete (factor 0.5/1.0 – parametru), punct de inserție ≠ Top Center la grinzi, stâlpi la centroid |
| 14 | Axe locale | 4 | N | A/D | `Frame Assignments - Local Axes`, `Area Assignments - Local Axes` | stâlpi cu aceeași secțiune dar unghi diferit (0° și 90° amestecate), arii cu axe răsucite (normală pe sensuri diferite), pereți cu axa 3 inversată (+ vizual) |
| 15 | Elemente Null, modificatori de masă | 1, 5 | N | A/B | `Frame Assignments - Property Modifiers`, `Area Assignments - Stiffness Modifiers`, `Area Section Property Definitions - Summary`, `Null Line Object Connectivity` | elemente Null/ajutătoare cu masă/greutate ≠ 0, plăci subțiri „pentru vânt” cu masă |
| 16 | Direcții de descărcare | 3 | N | C/D | `Deck Property Definitions`, `Area Assignments - Local Axes`, `Floor Bays`, `Area Load Assignments - Uniform` | listăm planșeele *deck/ribbed/one-way* cu direcția lor; utilizatorul confirmă; semnalăm direcția către grinzi secundare |
| 17 | Temperatură/contracție | 6 | N | B | `Load Pattern Definitions` (Temperature), `Area/Frame/Joint Loads Assignments - Temperature` | lungimea clădirii > 40–50 m (parametru) fără caz de temperatură; aplicare uniformă ±ΔT |
| 18 | Construcție etapizată | 8 | N | B | `Load Case Definitions - Nonlinear Staged Construction`, `Load Case Definitions - Linear Static` | clădire înaltă (nr. etaje/înălțime – parametru) cu *Dead* liniar simplu |
| 19 | Unități | 1 | N | A | `SapModel.GetPresentUnits`, `Material Properties` | unități active; plauzibilitatea ordinelor de mărime (E, ks, γ) |
| 20 | Forțe statice echivalente | 7 | N+R | B | `Load Pattern Definitions - Auto Seismic - User Coefficient`; (R) `Base Reactions`, `Modal Periods` | tipare X și Y, excentricitate ±5 %; (R) Fb static vs Fb din calcul propriu (parametri) cu prag 20 % |
| 21 | Centre CM–CR | 8 | N+R | A | `Analysis Options - Active DOF`, (R) `Centers Of Mass And Rigidity` | (N) 3D + diafragme, (R) excentricitate CM–CR / dimensiunea în plan > 15–20 % |
| 22 | Greutate proprie | 6 | N+R | A | `Load Pattern Definitions` (multiplicator), `Material List by Story`; (R) `Base Reactions` | **multiplicator = 1 doar la un tipar Dead, 0 în rest**; (R) reacțiunea Fz din Dead vs estimare (volum beton × 25) și **„q topit”** în kN/m² după tipul clădirii |
| 23 | Truss / tension-only / cable | 4 | N | B | `Frame Assignments - Tension and Compression Limits`, `Frame Assignments - Releases…`, `Load Case Definitions - Nonlinear Static` | diagonale/tiranți cu limită de compresiune 0 în cazuri **neliniare**; contravântuiri cu M/T în rezultate |
| 24 | Împingeri pământ/apă | 6 | N | A/C | `Area Load Assignments - Non-uniform / Uniform`, `Area Assignments - Local Axes`, geometrie | **sensul presiunii** față de interiorul clădirii (produs scalar normală · direcția spre centroid), reacțiuni laterale anormale |
| 25 | Instabilități locale | 4, 5 | N+R | A | `Frame Assignments - Releases and Partial Fixity`; (R) `Analysis Messages` | torsiune eliberată la **ambele capete**, bare cu toate rotirile eliberate, mesaje „ill-conditioned”, „lost accuracy”, mecanisme |
| 26 | Separare pe turnuri / diafragme | 9 | N | B/C | `Tower and Base Story Definitions`, `Diaphragm Definitions`, `Area Assignments - Diaphragms`, `Group Definitions` | componente conexe (graf de elemente) pe etaj; aceeași diafragmă pe turnuri diferite; mai multe diafragme în același turn |
| 27 | Rosturi seismice | 9 | N | B | geometrie + conectivitate | noduri/arii comune între turnuri, distanța minimă între componente, elemente scurte care traversează rostul |
| 28 | Continuitate verticală | 9 | N+R | B | `Pier Label Definitions`, `Area Assignments - Pier Labels`; (R) `Story Stiffness` | etichete pier diferite între turnuri, pereți dispăruți la un etaj, (R) soft-story |
| 29 | Seism separat pe turnuri | 7, 9 | N+R | C | `Load Case Definitions - Response Spectrum`, `Load Pattern Definitions` | tipare/cazuri pe turn consecvente (mapare utilizator); (R) rezultate identice între turnuri = suspect |
| 30 | Podium comun | 9 | N+R | C/D | `Slab Property Definitions`, `Wall Property Definitions`, `Diaphragm Forces`, `Story Forces` | listă de control + procentul din forța laterală preluat de podium |

## 6. Plan de atac pe faze

**Faza 0 — Fundație (prima)**
- Documentul în `docs/` (făcut), grinzile scoase din GUI (făcut), actualizarea planului.
- `snapshot.py` (TableStore + cache), `checks/registry.py`, modelul „Constatare”, migrarea verificărilor existente (centuri fără perete, bare suprapuse, noduri duplicate, capete neconectate, unități) în registru.
- API: `/run?zona=&faza=`, stările modelului (nerulat/rulat) și acces la tabele.
- GUI: scheletul — două tab-uri mari, tab pe zonă, card de verificare cu text *ce / cum / alarme* din document, selecție multiplă (deja existentă), „justificat”.

**Faza 1 — Nerulat, clasa A (fără parametri)**: 1, 19, 22 (multiplicator), 10 (DOF, Ritz, P-Delta bifat), 11/25 (eliberări), 13, 14, 15, 5 (geometrie/mesh), 6 (self-mass dublat), 7 (tipare goale/tip greșit).

**Faza 2 — Parametri și roluri**: ecranul „Setări” (normativ P100-1, ag, TB, TC, TD, q, ψ, tip clădire, praguri) și **rolurile încărcărilor**; apoi 8, 9, 12, 17, 18, 20 (pre), 23, 24, 3 (diafragme/goluri), 2 (rezemare).

**Faza 3 — Geometrie și graf**: componente conexe (turnuri), rosturi, continuitate verticală (26–28), pier/spandrel (4), goluri din geometrie, calitatea mesh-ului, direcții de descărcare (16).

**Faza 4 — Model rulat**: masă participantă și perioade (10), mase pe etaj și CM–CR (6, 21), reacțiuni vs estimare și „q topit” (22), forța tăietoare statică vs dinamică (8, 20), derive/rigiditate pe etaj (28), mesaje de analiză (25), diafragmă rigidă vs semi-rigidă (3), comparații între turnuri (29, 30).

**Faza 5 — Raport și finisaj**: export JSON/HTML/PDF cu constatări, justificări și parametri; comparare între două rulări ale verificatorului (ce s-a rezolvat); salvarea setărilor lângă model.

Fiecare fază se închide cu: teste unitare pe date sintetice + rulare pe modelul real + capturi din GUI.

## 7. Decizii luate

1. **Parametri** (normativ, ag, TB, TC, TD, q, ψ, tip clădire, praguri): se **introduc în „Setări”**; verificatorul îi compară cu ce e în model. Normativ implicit P100-1/2013 + EN 1990/1992.
2. **Model rulat**: pornim de la pragurile din cele 30 de reguli (CM–CR 15–20 %, masă participantă 90 %, „q topit” pe tip de clădire, Fb static vs manual 20 %).
3. **Grinzi secundare fără partial fixity / eliberare** (regula 11): doar **info**.
4. **Justificări, liste de control, setări**: salvate **lângă fișierul .EDB** (`<model>.EDB.checks.json`).
5. **Dependență nouă**: `shapely` (goluri, suprapuneri de arii) — acceptat; se instalează când ajungem la faza 3.
6. **Compararea a două modele** (supra vs infra): mai târziu.
7. **Verificările vizuale (clasa D)**: listă de control cu casetă „verificat”, persistată per model.

## 8. Stare implementare
- Faza 0 (fundație): în lucru — vezi secțiunea 9 din [PLAN.md](../PLAN.md).
