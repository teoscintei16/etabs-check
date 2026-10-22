"""Verificari vizuale / manuale (clasa D): lista de control cu casete 'verificat', salvata langa model."""

MANUAL_ITEMS = [
    {"id": "m2_deformata", "rule": 2, "phase": "post",
     "text": "Vedere laterală / formă deformată la seism: fără artefacte de mișcare la planșeele de infrastructură și radier."},
    {"id": "m3_diaphragm_extent", "rule": 3, "phase": "pre",
     "text": "Display > Diaphragm Extent: nodurile esențiale fac parte din diafragmă; planșeele sunt împărțite simplu la intersecția cu grinzile."},
    {"id": "m4_pier_spandrel", "rule": 4, "phase": "pre",
     "text": "Afișați Pier Labels și Spandrel Labels: pereții compuși din mai multe felii au același label."},
    {"id": "m5_check_model", "rule": 5, "phase": "pre",
     "text": "Analyze > Check Model cu toleranța dorită (ex. 1 mm): fără mesaje „Area overlaps Area” sau „Points are too close”."},
    {"id": "m11_eliberari", "rule": 11, "phase": "pre",
     "text": "Display > Assigns > Frame > Releases: articulațiile apar doar unde sunt intenționate."},
    {"id": "m14_axe_locale", "rule": 14, "phase": "pre",
     "text": "Local Axes pentru Frames și Areas: axele (roșu=1, verde=2, albastru=3) sunt orientate logic și consecvent."},
    {"id": "m16_descarcare", "rule": 16, "phase": "pre",
     "text": "Direcția de descărcare a planșeelor deck/ribbed/prefabricate (Span Direction) este către grinzile/pereții de reazem."},
    {"id": "m24_presiuni", "rule": 24, "phase": "pre",
     "text": "Presiunile pământului/apei: săgețile arată dinspre exterior spre interiorul clădirii, pe fața corectă a peretelui."},
    {"id": "m30_podium", "rule": 30, "phase": "pre",
     "text": "Podium/infrastructură comună: grosimi, materiale, mesh și conexiuni perete–placă–radier; rigiditatea nu „sudează” și nu decuplează turnurile."},
]
