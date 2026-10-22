# VERIFICARI INAINTE DE RULARE

### 1. Materiale, Sectiuni si Factori de Rigiditate (Modifiers sau Beton)
*   **Ce se verifica:** Clasele de beton, corectitudinea sectiunilor si aplicarea factorilor de rigiditate fisurata pentru seism sau pentru tipul de calcul prin modifiers la sectiune sau prin modifcarea modulului de elasticitate al materialului.
*   **Cum se verifica:** Din meniul `Define > Materials` si `Section Properties`. Se verifica modulul de elasticitate ($E$), greutatea specifica si tabelul de sectiuni.
*   **Semnale de alarma:** Modul de elasticitate incorect, greutati specifice zero.
*	**Observatie:** Intr-un model care are per grinzi rigiditatea la torsiune cu valoarea 1, acestea ar putea atrage incorect un efort foarte mare de torsiune. In special in stadiul fisurat aceasta rigiditate scade foarte mult, iar torsiunea de compatibilitate (cea care permite rotiri/deformatii) se duce la sistem.

### 2. Conditii de Rezemare si Fundatii
*   **Ce se verifica:** Modul în care cladirea transmite eforturile la teren. Sunt noduri încastrate perfect (pentru modele supra-structura) sau s-au folosit spring-uri de suprafata (coeficient de pat Winkler) pentru radier? Coeficientul de pat ks: valori/units corecte, diferentiere pe GF vs GS (unde e justificat) si incertitudinea terenului. Gradele de libertate ale resorturilor: Z obligatoriu; X/Y si rotatii folosite doar daca sunt justificate (altfel pot introduce artefacte). 
*   **Cum se verifica:** Selectezi planul de la baza (`Base`), afisezi restictiile (Joint Restraints) sau asignarile de tip Area Spring. Valori/units corecte, diferentiere pe GF vs GS (unde e justificat) si incertitudinea terenului. Pentru radier: verifici ks si unitatile (kN/m³ pentru Winkler pe suprafata). Setezi 3 variante de teren: ks_min / ks_med / ks_max (ex. ±30–50% sau conform geotehnic) pentru envelope la rezultate pentru o analiza corecta, dar "overkill". Compression-only daca se foloseste radier cu coeficient de pat. Se verifica suplimentar si forma deformata in situatia impingerii laterale la seism, iar o vedere laterala ar putea arata artefacte de miscare la planseele de infra/radier.
*   **Semnale de alarma:** Baza articulata (Pinned) la structuri în cadre (cladirea va fi instabila), noduri libere la baza peretilor, rigiditate la spring-uri calculata în unitati gresite (ex: introdus $kN/m$ în loc de $kN/m^3$). Rezultatele (presiuni/tasari/eforturi) se schimba masiv între ks_min si ks_max → sistem sensibil, trebuie rigidizat radierul sau recalibrat ipoteza de teren.

### 3. Modelarea Placilor, Diafragmelor si Golurilor
*   **Ce se verifica:** Comportamentul corect al planseelor. Daca placa are "Rigid Diaphragm" (sau Semi-Rigid), daca tipul de element (Membrane vs Shell) e ales corect, si daca golurile de peste 1m² (casa scarii, lift, ghene) sunt decupate fizic din placa. Diafragmele se considera rigide doar sub niste criterii foarte bine stabilitate, cel mai usor fiind analiza deformatiilor si compararea (deformatii in placile de supra vs deformatii in placile de infra). In general se recomanda folosirea diafragmelor semi-rigide.
*   **Cum se verifica:** `Display > Diaphragm Extent`. Verificare vizuala în plan pentru împartirea placilor la intersectia cu grinzile (forme cât mai rectangulare/simple). La `Define > Diaphragm` se analizeaza tipul de rigiditate.
*   **Semnale de alarma:** Noduri esentiale neconectate la diafragma (ramân pe loc la cutremur), elemente de tip *Membrane* folosite la placi tip dala fara grinzi (Membrane nu preia încovoiere!), lipsa golurrilor care artificial rigidizeaza structura.

### 4. Modelarea Elementelor Verticale si a Grinzilor
*   **Ce se verifica:** Continuitatea fizica a elementelor si etichetarea lor corecta pentru a putea extrage eforturi (Piers/Spandrel daca e cazul). Prezenta grinzilor dummy pentru citirea eforturilor in centurile peretilor.
*   **Cum se verifica:** Se afiseaza `Pier Labels` pentru pereti / stâlpi si `Spandrel Labels` pentru grinzile de cuplare sau deasupra golurilor de usi. Grinzile se vizualizeaza extrudate pentru usurinta.
*   **Semnale de alarma:** Perete din 3 bucati care nu are acelasi "Pier Label" (programul va da eforturi pe fiecare feliuta, nu per ansamblu), grinzi "sparte" artificial în bucatele mici în loc sa fie continue si intersectate prin automesh, grinzi *dummy* (fara greutate/rigiditate) omise la capetele peretilor unde se descarca grinzi reale (pentru transferul corect al momentelor).

### 5. Curatenia Geometrica si Mesh-ul de Calcul
*   **Ce se verifica:** Precizia modelarii. Fara noduri zburatoare, fara linii suprapuse de 2 ori, fara puncte cu coordonate infime din cauza desenului din AutoCAD (ex: coordonata X = 0.00000021 în loc de 0.0). Dimensiunea optima a mesh-ului la placi si pereti (de obicei 0.5m - 1.0m, 1.0m la radier).
*   **Cum se verifica:** Rularea optiunii `Analyze > Check Model` bifând toleranta dorita (ex: 1 mm). Exportarea modelului ca fisier `$et` (text) si verificarea rapida a blocului de *Joint Coordinates*. Verificarea optiunilor de *Automesh*. Mesh dedicat pentru radier: discretizare cât mai “patrata”, orientativ cu aria elementului de ordinul ~1 m² (unde permite geometria), pentru stabilitate si presiuni/tasari coerente.
*   **Semnale de alarma:** `Check Model` raporteaza mesaje de tipul *"Area overlaps Area"*, *"Points are too close"*. Noduri de grinda care trec la 1 cm pe lânga nodul stâlpului de care trebuiau sa se lege.

### 6. Surse de Masa si Greutatea Seismica (Mass Source)
*   **Ce se verifica:** Ce intra în masa pentru generarea fortelor seismice ($G + \psi_2 \cdot Q$, finisaje, compartimentari, fatade, echipamente), distributia pe nivel, excentricitati inerente.
*   **Cum se verifica:** Se verifica setarea `Define > Mass Source`. Dupa o analiza prealabila (sau tabelar), vizualizezi „Mass summary by Story” si „Center of Mass vs Center of Rigidity”. O idee puna ar fi si verificarea % de masa ce reuseste sa fie preluat in analizeze gravitationale si dinamice.
*   **Semnale de alarma:** Masa lipsa la un nivel, salturi masive de greutate între nivele curente fara o justificare arhitecturala (ex: s-a pus o încarcare în kg în loc de kN), greutatea proprie a elementelor (Self-Weight) introdusa de doua ori (o data automat, o data ca încarcare aplicata manual).

### 7. Incarcari Gravitationale si Liniar-Distribuite
*   **Ce se verifica:** Daca pachetele de încarcari pe placi (Uniform Load Sets) sunt corect definite (spatii publice, balcoane, birouri, acoperis tehnic) si daca încarcarile din peretii de închidere (fatade) sau de compartimentare grea sunt puse ca forte liniare pe grinzi/placi. Se verifica si cazurile de incarcari exceptionale (ex. pompieri sau utilaje). Se verifica prezenta incarcarilor din presiunea pamantului sau presiunea hidrostatica la peretii din infrastructura. Se verifica prezenta incarcarilor din camerele cu apa (presiunea apei pe pereti/placa).
*   **Cum se verifica:** `Display > Load Assigns` pentru fiecare caz static (Dead, Superimposed Dead, Live, Snow, Wind). `Display > Frame Load Assigns`.
*   **Semnale de alarma:** Incarcari din trafic auto/Zapada definite eronat în Load Pattern sub tipul "Dead", fatade grele omise pe grinzile perimetrale (afecteaza centrul de masa si rasturnarea). Incarcari speciale omise.

### 8. Definirea Actiunii Seismice
*   **Ce se verifica:** Functia de spectru ($T_b, T_c, T_d, a_g$) definita conform P100-1 si factorul de scara din cazul de analiza (Load Case). Daca se folosec fortele static echivalente, se verifica coeficientul introdus sau inarcarile laterale introduse.
*   **Cum se verifica:** `Define > Functions > Response Spectrum`. Pentru verificare pura a fisierului, se poate citi în exportul `$et` daca functia si-a luat correct perechile de Puncte (Perioada, Acceleratie). La load patterns se verifica fiecare din metoda fortelor static echivalente. Atentie sa se faca o analiza de suprastructura (incastrare la baza) astfel incat sa se faca corecturi ulterioare astfel incat sa existe aceleasi eforturi pe elemente si aceleasi forte taietoare.
*   **Semnale de alarma:** Lipsa acceleratiei gravitationale ($9.81 m/s^2$) în factorul de scara (`Scale Factor`) daca spectrul a fost definit normalizat (adimensional). Folosirea spectrului elastic (neasumat factorul de comportare $q$). Coeficient gresit pentru MFSE sau excentricitati gresite. Incarcari laterale introduse gresit. Eforturi diferite in elemente la compararea modelelor suprastructura vs infrastructura.

### 9. Combinatii de Incarcari si Setup pentru Rezultate
*   **Ce se verifica:** Existenta si corectitudinea combinatiilor de ULS (Stare Limita Ultima), SLS (Stare Limita de Serviciu: Caracteristica, Frecventa, Cvasi-permanenta) si Seismice. Setarea grupelor pentru extractia usoara a tabelelor.
*   **Cum se verifica:** `Define > Load Combinations`. Crearea de `Table Name Sets` (pentru a printa instant Drift-uri, Baze Reactions, Modal Periods fara a cauta prin sute de tabele).
*   **Semnale de alarma:** Lipsa combinatiilor seismice ortogonale (ex: $1.0 E_x \pm 0.3 E_y$), excentricitatea accidentala omisa din combinatii (daca nu e definita în Load Case), combinatii create ca "Add" (adunare simpla) în loc de "Envelope" (Infasuratoare) pentru verificarea eforturilor maxime.

### 10. Setari Globale de Analiza si Rulare
*   **Ce se verifica:** Tipul de analiza selectat, numarul de moduri de vibratie cerute, includerea efectelor de ordinul II (P-Delta).
*   **Cum se verifica:** `Analyze > Set Load Cases to Run`. Meniul de `P-Delta Options` (de regula se seteaza Iterativ pe baza combinatiei $1.0 G + 0.3 Q$). Meniul Modal Case: se cere analiza `Ritz` (preferabila pentru seism) sau `Eigen`, si un numar minim de moduri (ex: 3 moduri / planseu - cate unul pentru x,y,rotatie).
*   **Semnale de alarma:** Analiza P-Delta nebifata, moduri de vibratie cerute insuficient (ex: lasat *default* 12 moduri la o cladire P+15E, ceea ce nu va atinge 90% masa antrenata (important), analiza Ritz setata fara a include acceleratiile pe X, Y si Z ca *Starting Load Vectors*.

### 11. Eliberari de Eforturi si Articulatii (End Releases)
*   **Ce se verifica:** Daca elementele care în realitate nu pot prelua momente încovoietoare (grinzi secundare articulate pe grinzi principale, contravântuiri metalice, tiranti, elemente de sarpanta) sunt modelate ca atare. Se recomanda la cazurile cu beton armat sa se foloseasca "partial fixity", conexiunea nu este intr-adevar perfect incastrata ,dar nici perfect articulata.
*   **Cum se verifica:** Afisarea în 3D a eliberarilor (`Display > Assigns > Frame > Releases`). Vor aparea niste "buline" verzi/albastre la capetele elementelor.
*   **Semnale de alarma:** Grinzi secundare de beton care intra rigid în mijlocul altor grinzi (vor genera torsiune masiva si nerealista în grinda principala, in mare torsiune de compatibilitate); contravântuiri în X care preiau moment încovoietor (ele trebuie sa lucreze doar axial - *Truss/Pinned*); noduri de grinda metalica pe stâlp de beton lasate încastrate fara detaliu de rigidizare.

### 12. Setarea Nivelului de Baza pentru Seism (Seismic Base)
*   **Ce se verifica:** Locul de unde programul considera ca începe excitatia seismica. Daca ai subsoluri rigide (infrastructura cutie cu pereti perimetrali), forta taietoare de baza se calculeaza de la cota $\pm 0.00$ în sus, nu de la radier.
*   **Cum se verifica:** (In ETABS) Click dreapta pe ecran `Add/Modify Grids > Modify Story Data`. Se cauta coloana sau setarea generala de *Seismic Base* sau *Bottom Story* sau din load patterns la fiecare caz seismic pentru MFSE.
*   **Semnale de alarma:** Nivelul seismic lasat la fundatie (ex: -9.00m) la o cladire cu 3 subsoluri rigide încastrate în teren. Asta va atrage o masa uriasa în calculul taietoarei de baza, va strica forma modurilor de vibratie si va supradimensiona absurd suprastructura.

### 13. Zone Rigide si Puncte de Insertie (Important la cadre)
*   **Ce se verifica:** Daca intersectiile stâlp-grinda sunt considerate zone rigide (în realitate, grinda nu se deformeaza *în interiorul* stâlpului) si daca grinzile sunt aliniate corect la fata superioara a placii (T-beam effect).
*   **Cum se verifica:** Selectare grinzi/stâlpi > `Assign > Frame > End Length Offsets` (se pune factor de rigiditate 0.5 pentru modelare uzuala, 1.0 pentru rigiditate completa). Pentru aliniere: `Assign > Frame > Insertion Point` (setat pe *Top Center* în loc de *Centroid*).
*   **Semnale de alarma:** Model cu elemente de tip linie (axe centroidale) unde stâlpii de 100x100 cm se intersecteaza cu grinzi de 30x60 cm. Daca nu pui *End Length Offsets*, programul calculeaza deschiderea grinzii din axul stâlpului, facând structura mult prea flexibila (drift-uri false). Placi care "taie" vizual grinzile pe la jumatate.

### 14. Orientarea Axelor Locale (Local Axes 1, 2, 3)
*   **Ce se verifica:** Directia în care sunt orientate elementele. Eforturile ($M_2, M_3, V_2, V_3$ la cadru; $M_{11}, M_{22}$ la placi) depind 100% de axele locale.
*   **Cum se verifica:** Se bifeaza `Local Axes` din setarile de afisare pentru *Frames* si *Areas*. Sagetile (rosu=1, verde=2, albastru=3) trebuie sa fie orientate logic (ex: la placi, axa rosie paralela cu global X, verde paralela cu global Y).
*   **Semnale de alarma:** Stâlpi rotiti la 90 de grade (axa 2 locala este pe Y la unii si pe X la altii), ceea ce face imposibila extragerea tabelara a efortului $M_3$ pentru toti stâlpii simultan. Placi cu axe locale rotite haotic (unele desenate de la stânga la dreapta, altele de la dreapta la stânga).

### 15. Elemente "Null" si Managementul Greutatii (Modifiers)
*   **Ce se verifica:** Daca ai folosit elemente ajutatoare (grinzi "None" / "Null", placi cu greutate zero folosite doar pentru a distribui vântul sau o încarcare de zona), acestea NU trebuie sa adauge masa sau rigiditate structurii.
*   **Cum se verifica:** Selectezi elementele *Null* > `Assign > Property Modifiers`. Te asiguri ca *Mass = 0* si *Weight = 0*.
*   **Semnale de alarma:** Folosirea unei placi subtiri de beton doar pentru a prelua presiunea vântului pe fatada, dar careia ai uitat sa-i anulezi masa. Structura va fi "îmbracata" gresit în tone de beton perimetral, modificând centrul de masa si generând torsiune.

### 16. Verificarea directiilor de descarcare la placi (One-Way vs Two-Way)
*   **Ce se verifica:** Daca planseele prefabricate, fasiile cu goluri, tabla cutata (decking) sau placile monolite extrem de lungi descarca încarcarile pe directia corecta (pe grinzile/peretii de reazem).
*   **Cum se verifica:** `Display > Load Assigns` sau vizualizarea axelor locale. In ETABS, o placa de tip *Deck* sau *Ribbed* are o sageata mare pe ea care indica directia de descarcare (Span Direction).
*   **Semnale de alarma:** Tabla cutata orientata gresit care descarca gravitational pe grinzile secundare (care nu duc nicaieri) sau pe fatada, lasand grinzile principale neîncarcate. 

### 17. Efecte de Temperatura si Contractie (Daca e cazul)
*   **Ce se verifica:** Pentru cladiri lungi (fara rosturi de dilatare pe o lungime > 40-50m), normativul cere considerarea variatiilor de temperatura ($\Delta T$).
*   **Cum se verifica:** Verifici în *Load Patterns* daca exista un caz de tip *Temperature*. Apoi verifici daca este aplicat uniform pe elemente (ex: $+20^\circ C$ / $-20^\circ C$).
*   **Semnale de alarma:** Structura de 80m lungime monolita fara variatie de temperatura aplicata. In realitate, placile vor "trage" de stalpii marginali la contractie, generand eforturi taietoare masive si fisuri pe care modelul lipsit de $\Delta T$ nu le va prevedea.

### 18. Verificarea Stadiilor de Constructie (Staged Construction / Auto-Sequential - Daca e cazul)
*   **Ce se verifica:** Daca ai o cladire foarte inalta, stalpii si peretii se vor scurta elastic pe masura ce se construieste.
*   **Cum se verifica:** In setarile cazului *Dead Load*, te asiguri ca ai selectat analiza `Nonlinear Staged Construction` sau `Auto-Sequential Construction`. 
*   **Semnale de alarma:** Grinzi de la etajele superioare care prezinta eforturi taietoare si momente gravitationale uriase la nodurile cu stalpii (din cauza scurtarii axiale cumulate a stalpilor, programul considera ca grinda se deformeaza ca sa compenseze, desi în realitate ea a fost turnata "la orizontala" DUPA ce scurtarea etajelor inferioare a avut loc).

### 19. Verificarea Unitatilor de Masura Curente
*   **Ce se verifica:** Unitatile de masura folosite.
*   **Cum se verifica:** Se verifica mereu în coltul ecranului pentru a vedea unitatile active curente (ex: $kN, m, ^\circ C$) înainte de a introduce sau edita o valoare.
*   **Semnale de alarma:** Introducerea unui modul de elasticitate ($E$) în $N/mm^2$ (MPa) – de exemplu 30.000 – cand unitatile active sunt setate pe $kN/m^2$. Rezultatul va fi un material de 1.000 de ori mai slab, rezultand o cladire de 1.000 de ori prea flexibila (vei avea drift-uri de zeci de metri la seism).

### 20. Definirea corecta a Fortelor Echivalente Statice
*   **Ce se verifica:** Desi pentru dimensionare folosesti de obicei spectrul de raspuns (metoda dinamica), este vital sa ai definit si un caz de încarcare statica echivalenta (User Coefficient sau conform codului selectat) pentru a verifica forta taietoare de baza ($F_b$) si pentru a asigura scalarea corecta a rezultatelor dinamice.
*   **Cum se verifica:** `Define > Load Patterns`. Adauga cazuri de tip *Seismic* pe directiile X si Y, aplicand coeficientul seismic de baza ($c = S_d(T) \cdot \lambda \cdot m / q$) calculat manual sau generat de program. Verifica excentricitatea accidentala (de obicei $\pm 5\%$ din lungimea laturii cladirii perpendiculare pe directia cutremurului) bifata în aceste cazuri.
*   **Semnale de alarma:** Forta taietoare de baza obtinuta din cazul static echivalent difera masiv (ex. cu peste 20%) de calculul manual. Aceasta indica o problema majora în definirea sursei de masa (*Mass Source*) sau a coeficientului seismic (ex. perioada fundamentala calculata eronat de program vs. cea estimata empiric).

### 21. Corelarea Centrelor de Rigiditate (CR) si Masa (CM) la nivelul etajelor
*   **Ce se verifica:** Daca programul calculeaza corect pozitia centrului de rigiditate pentru fiecare etaj. CR este indicatorul vital pentru a întelege torsiunea inerenta a cladirii înainte de a trece la armare.
*   **Cum se verifica:** Se asigura ca în meniul `Analyze > Set Active Degrees of Freedom` e setata analiza tridimensionala completa (Full 3D). `Calculate Diaphragm Centers of Rigidity` în setarile de analiza.
*   **Semnale de alarma:** Lipsa tabelului *"Centers of Mass and Rigidity"* dupa o rulare test. Daca distanta (excentricitatea inerenta) dintre CM si CR extrasa din tabel este foarte mare (ex. $> 15-20\%$ din dimensiunea laturii cladirii pe acea directie), structura va fi extrem de sensibila la torsiune si s-ar putea sa necesite reconfigurarea masiva a peretilor structurali (echilibrarea lor pe contur) înainte de a continua cu analiza detaliata.

### 22. Self-Weight Multiplier si dublari
*   **Ce se verifica:** Daca programul îsi calculeaza automat greutatea proprie a elementelor modelate (beton, otel) corect si daca nu cumva ai dublat aceasta greutate aplicand-o ulterior si manual pe placi sau grinzi.
*   **Cum se verifica:** Mergi la `Define > Load Patterns`. Asigura-te ferm ca `Self Weight Multiplier` este setat la **1** EXCLUSIV pentru cazul de încarcare permanenta principala (de obicei numit *Dead*). Pentru toate celelalte cazuri (Superimposed Dead / Finisaje, Live / Utile, Wind, Snow etc.), multiplicatorul trebuie sa fie obligatoriu **0**. Apoi, fa o rulare scurta doar pentru cazul *Dead* pentru a verifica reactiunile.
*   **Semnale de alarma:** Reactiunile verticale ($F_z$) la baza structurii din cazul *Dead* sunt duble fata de o estimare bruta manuala (volum de beton $\times 25 kN/m^3$). Asta înseamna ca ai aplicat o încarcare de suprafata "din greutate proprie" pe placi, desi programul o calcula deja. Alternativ, reactiuni extrem de mici sugereaza ca multiplicatorul a ramas setat pe 0 peste tot, iar cladirea "pluteste" fara greutatea elementelor structurale.
* 	**Observatie:** Se poate folosi o verificare cu un q topit. Rezidential cadre: 5.0-6.5 kN/m2. Rezidential pereti structurali: 5.5-7.5 kN/m2. Birouri cadre: 6.0-8.0 kN/m2. Birouri pereti structurali: 6.5-9.0 kN/m2. Cazuri cu incarcari grele in cladire: 8.5-10.5 kN/m2.

### 23. Elemente cu comportare speciala: "Truss", "Tension-only", "Compression-only", "Cable"
*   **Ce se verifica:** Daca elementele care în realitate au un rol strict axial (contravantuiri metalice, elemente de sarpanta zvelte, tiranti, cabluri) sunt instruite matematic sa lucreze doar asa cum trebuie. De exemplu, un tirant preia doar întindere (la compresiune flambeaza instantaneu), iar o diagonala articulata nu preia încovoiere.
*   **Cum se verifica:** Selecteaza elementele respective si verifica din `Define / Assign > Frame Type` sau din eliberari (`Releases`) ca ele sa fie tip "Truss" (Axial-only). Pentru tiranti, se intra în `Assign > Frame > Tension/Compression Limits` si se seteaza limita de compresiune la 0. **Atentie:** Comportamentul de tip "Tension-only" devine activ doar daca Load Case-ul este setat pe analiza neliniara (*Nonlinear*)!
*   **Semnale de alarma:** Contravantuiri metalice care în rezultate prezinta momente încovoietoare sau torsiuni ($M_3, M_2, T$). Acest fenomen creeaza o rigidizare falsa a cadrelor principale, atragand forte taietoare ireale. In realitate, prinderile (guseele) acelor diagonale ar ceda casant la încovoiere înainte ca sectiunea sa preia acele eforturi.

### 24. Impingerile Pamantului si ale Apei (Earth & Hydrostatic Pressures)
*   **Ce se verifica:** Daca peretii de subsol/sprijin au definite corect încarcarile laterale triunghiulare sau trapezoidale din pamant (si apa, daca e cazul). Cel mai important: directia pe care actioneaza!
*   **Cum se verifica:** Selectezi peretii de subsol si afisezi Axele Locale. Incarcarea din pamant (`Assign > Area Loads > Surface Pressure` cu `Joint Patterns`) trebuie aplicata pe fetele corecte (*Top* sau *Bottom*) sau pe axa locala 3. Se verifica vizual încarcarea în 3D.
*   **Semnale de alarma:** Sagetile de presiune arata dinspre interiorul cladirii spre exterior (programul va considera ca subsolul este un bazin plin care trage de pereti în afara, nu pamantul care împinge în ei). Reactiuni laterale anormale la baza modelului.

### 25. Instabilitati Locale si Ill-Conditioned Matrix
*   **Ce se verifica:** Modul în care ai eliberat eforturile (Releases) la grinzile secundare. Daca eliberezi o grinda la ambele capete pentru moment încovoietor ($M_2, M_3$) ȘI pentru moment de torsiune ($T$), grinda respectiva se va putea roti liber (fara rezistenta) în jurul axului sau longitudinal, devenind un mecanism instabil.
*   **Cum se verifica:** Verifici vizual pe ecran `Display > Assigns > Frame > Releases`. Niciodata nu elibera torsiunea la *ambele* capete ale unei grinzi articulate. Lasa torsiunea fixata la unul dintre capete sau se foloseste partial fixity.
*   **Semnale de alarma:** La rulare, programul se blocheaza, dureaza anormal de mult sau afiseaza o fereastra pop-up cu *"Warning: Ill-conditioned matrix"* / *"Lost accuracy"*. Daca verifici deformata animata din greutate proprie, vei vedea o grinda care se roteste ca o elice la infinit sau un nod zburand în afara ecranului.

### 26. Separarea logică pe turnuri și asignarea diafragmelor (MULTI TOWER)

* **Ce se verifică:** Fiecare turn să fie modelat ca entitate clară: diafragme distincte pe pentru fiecare turn (`T1_Lxx`, `T2_Lxx` etc.), fără conectări accidentale între turnuri prin shell-uri, grinzi scurte “uitate”, puncte comune sau constrângeri rigide neintenționate. Dacă există podium comun, se verifică explicit unde turnurile sunt intenționat cuplate și unde trebuie să rămână independente. In general si podiumul (infra) se considera turn separat, poate fi diafragma rigida doar daca se verifica acest lucru prin calcul.
* **Cum se verifică:** `Assign > Shell > Diaphragm`, `Display > Show Assigns > Shell/Joint Diaphragms`, plus selectare pe stories și pe groups. Se recomandă definirea de **Group-uri separate pe fiecare turn** (T1, T2, T3) și a unui group distinct pentru podium/infrastructură.
* **Semnale de alarmă:** Două turnuri care ar trebui să fie separate apar cu **aceeași diafragmă** la același nivel; un rost seismic este “închis” în model de un element mic; apar reacții sau eforturi transferate între turnuri deși arhitectural nu există legătură. ETABS tratează distinct diafragmele rigide definite, deci o asignare greșită aici schimbă direct distribuția forțelor laterale.

### 27. Modelarea rosturilor seismice / separațiilor dintre turnuri (MULTI TOWER)

* **Ce se verifică:** Dacă rosturile dintre turnuri sunt modelate coerent: fără noduri comune, fără elemente care traversează rostul, fără meshing comun al shell-urilor peste rost. Dacă există legături reale (pasarele, grinzi de cuplare, dale comune), ele trebuie modelate explicit.
* **Cum se verifică:** Secțiuni în plan la fiecare nivel, zoom local în zonele de rost, `Analyze > Check Model`, plus export `$et` și control rapid al coordonatelor/nodurilor din zona separației. Se verifică și offset-urile rigide ale cadrelor din proximitatea rostului.
* **Semnale de alarmă:** Deplasările celor două turnuri ies aproape identice deși ar trebui să fie independente; apar eforturi mari într-o grindă de margine “de rost”; `Check Model` nu dă erori, dar există totuși shell-uri care se ating și fac transfer de rigiditate.

### 28. Continuitatea verticală a sistemului lateral pe fiecare turn (MULTI TOWER)

* **Ce se verifică:** Pentru fiecare turn separat: continuitatea pereților, nucleelor, stâlpilor majori și a diafragmelor până la fundație/podium. La multi-tower, o eroare frecventă este ca un perete sau nucleu să fie întrerupt accidental la un nivel de transfer sau la podium și sarcina laterală să se redistribuie artificial către alt turn sau către podium.
* **Cum se verifică:** Vederi pe elevație pentru fiecare group de turn, `Set Building View Options` cu afișare local axes și labels, plus control al secțiunilor/meshing-ului în zonele de transfer. Important ca peretii dintr-un tower sa aibe label uri diferite de Pier comparat cu alt tower.
* **Semnale de alarmă:** Salt brusc de rigiditate la un singur nivel al unui turn, dispariția unui perete din model la un etaj intermediar, apariția unui “soft story” local doar într-un turn fără justificare arhitecturală.

### 29. Cazurile seismice definite separat și coerent pe fiecare turn (MULTI TOWER)

* **Ce se verifică:** La multi-tower, dacă ai abordare cu seisme separate pe turnuri sau combinații pe turn + direcție principală/secundară, trebuie verificat ca denumirile, semnele și excentricitățile accidentale să fie consistente. Fiecare turn trebuie să aibă o logică clară de încărcare, mai ales dacă suprastructura este comună doar parțial prin podium.
* **Cum se verifică:** `Define > Load Patterns`, `Define > Load Cases`, control tabelar/export în text al definițiilor de load cases și combos.
* **Semnale de alarmă:** Două cazuri diferite pentru turnuri diferite dau exact aceleași rezultate; excentricitatea accidentală e aplicată doar unui turn și uitată la celelalte; sensurile +/− sunt inversate într-o parte a setului de combinații.

### 30. Interacțiunea prin podium / infrastructură comună (MULTI TOWER)

* **Ce se verifică:** Dacă podiumul sau infrastructura comună este modelată la rigiditatea corectă: nici prea rigidă (caz în care “sudează” artificial turnurile), nici prea flexibilă (caz în care decuplează nerealist). La turnuri pe același radier sau aceeași infrastructură, această zonă controlează cât de mult se transferă torsiune și forfecare între turnuri.
* **Cum se verifică:** Revizuire a grosimilor, a materialelor, a mesh-ului podiumului/radierului, a resorturilor de teren și a conexiunilor perete–placă–radier. Se verifică separat modelul de infrastructură și modul în care se leagă de fiecare turn.
* **Semnale de alarmă:** Podiumul preia aproape toată acțiunea laterală de legătură între turnuri; reacțiile pe fundație se mută neplauzibil de la un turn la altul; rigiditatea aparentă a unui turn depinde excesiv de existența celuilalt.