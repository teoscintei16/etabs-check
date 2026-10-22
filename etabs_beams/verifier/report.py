"""Raport HTML (in romana) al verificarilor: constatari, justificari, parametri, lista de control, comparatie cu rularea anterioara."""
from __future__ import annotations

import html
import json
from datetime import datetime

from .rules import ZONES

SEV = {"error": "Eroare", "warning": "Avertisment", "info": "Informație"}
STATUS = {"ok": "în regulă", "info": "informație", "warning": "avertisment", "error": "eroare", "waived": "justificat",
          "failed": "verificare defectă", "skipped": "fără rezultate"}
PHASE = {"pre": "Model nerulat", "post": "Model rulat"}

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:32px auto;max-width:1000px;color:#1c1b19;line-height:1.45;padding:0 16px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:32px 0 8px;border-bottom:2px solid #e8e6dc;padding-bottom:4px}
h3{font-size:16px;margin:20px 0 6px}.muted{color:#6b6a63}.small{font-size:13px}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:600;margin-left:6px}
.error{background:#f8e6e1;color:#9c2f20}.warning{background:#f6ecd6;color:#7a4d0c}.info{background:#e6eef5;color:#2f5a85}
.ok{background:#e8eedd;color:#46592f}.waived,.skipped{background:#eee;color:#555}.failed{background:#f8e6e1;color:#9c2f20}
table{border-collapse:collapse;width:100%;margin:6px 0 12px;font-size:13px}th,td{border:1px solid #ddd;padding:4px 8px;text-align:left;vertical-align:top}
th{background:#f4f2ea}.rule{border:1px solid #e0ddd0;border-left:5px solid #ccc;border-radius:6px;padding:8px 12px;margin:10px 0;page-break-inside:avoid}
.rule.error{border-left-color:#c0432f}.rule.warning{border-left-color:#c9962a}.rule.info{border-left-color:#4f7fae}.rule.ok{border-left-color:#6b8a43}
.finding{margin:8px 0;padding:6px 10px;background:#faf9f5;border-radius:6px}.just{background:#f0efe8;border:1px dashed #aaa;padding:4px 8px;margin-top:4px;font-size:13px}
.kpi{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}.kpi div{border:1px solid #ddd;border-radius:8px;padding:8px 16px;text-align:center}.kpi b{display:block;font-size:22px}
details{margin:4px 0}pre{background:#f4f2ea;padding:6px;font-size:12px;overflow:auto;max-height:240px}
@media print{body{margin:0}.rule{page-break-inside:avoid}}
"""


KIND = {"frame": "Bară", "wall": "Perete", "area": "Arie", "joint": "Nod", "material": "Material", "loadpattern": "Tipar încărcare",
        "loadcase": "Caz încărcare", "pier": "Pier", "diaphragm": "Diafragmă", "spring": "Arc", "section": "Secțiune", "function": "Funcție",
        "masssource": "Sursă de masă", "mesh": "Mesh"}


def esc(x) -> str:
    return html.escape(str(x))


def _obj_table(objs: list[dict], limit: int = 60) -> str:
    if not objs:
        return ""
    rows = "".join(
        f"<tr><td>{esc(KIND.get(o.get('type', ''), o.get('type', '')))}</td><td>{esc(o.get('label', ''))}</td><td>{esc(o.get('name', ''))}</td>"
        f"<td>{esc(o.get('story', ''))}</td><td>{esc(o.get('section', ''))}</td></tr>" for o in objs[:limit])
    more = f"<p class='muted small'>… și încă {len(objs) - limit} obiecte (lista completă în aplicație).</p>" if len(objs) > limit else ""
    return f"<table><tr><th>Tip</th><th>Etichetă ETABS</th><th>Nume unic</th><th>Etaj</th><th>Secțiune</th></tr>{rows}</table>{more}"


def _status_of(result: dict) -> str:
    return result["status"]


def build_html(*, catalog: dict, results: dict[str, dict], model_file: str, analyzed: bool, project: dict, belts: dict,
               params: dict, manual: dict, waivers: list[dict], comparison: dict | None, analysis_log: list[dict] | None = None) -> str:
    rules = {r["number"]: r for r in catalog["rules"]}
    zone_title = dict((z["id"], z["title"]) for z in catalog["zones"])
    waiver_by_key = {w["key"]: w for w in waivers}
    # numaratori
    active = {"error": 0, "warning": 0, "info": 0}
    n_waived = 0
    for r in results.values():
        for f in r["findings"]:
            if f["waived"]:
                n_waived += 1
            else:
                active[f["severity"]] += 1
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    out = [f"<!doctype html><html lang='ro'><head><meta charset='utf-8'><title>Raport verificare model ETABS</title><style>{CSS}</style></head><body>"]
    out.append("<h1>Raport de verificare a modelului ETABS</h1>")
    out.append(f"<p class='muted'>Fișier: <b>{esc(model_file)}</b><br>Generat: {now} · Starea modelului: {'rulat (cu rezultate)' if analyzed else 'nerulat'}</p>")
    out.append("<div class='kpi'>"
               f"<div><b>{active['error']}</b>erori</div><div><b>{active['warning']}</b>avertismente</div>"
               f"<div><b>{active['info']}</b>informații</div><div><b>{n_waived}</b>justificate</div></div>")
    verdict = "NEPREGĂTIT" if active["error"] else ("PREGĂTIT, cu avertismente" if active["warning"] else "PREGĂTIT")
    out.append(f"<p><b>Verdict:</b> {verdict}</p>")

    # parametri
    out.append("<h2>Parametrii proiectului și setări</h2>")
    if project:
        names = {p["name"]: p["label"] for p in catalog.get("project_params", [])}
        out.append("<table><tr><th>Parametru</th><th>Valoare</th></tr>" + "".join(
            f"<tr><td>{esc(names.get(k, k))}</td><td>{esc(', '.join(v) if isinstance(v, list) else v)}</td></tr>" for k, v in project.items()) + "</table>")
    else:
        out.append("<p class='muted'>Niciun parametru de proiect introdus (verificările care îi cer au fost sărite).</p>")
    out.append(f"<p class='small'>Centuri (dummy): {'da — ' + esc(', '.join(belts.get('sections', []))) if belts.get('has') else 'nedeclarate / nu există'}.</p>")
    if params:
        out.append("<p class='small'>Praguri modificate: " + "; ".join(f"{esc(k)} = {esc(v)}" for k, v in params.items()) + ".</p>")

    if analysis_log:
        last = analysis_log[-1]
        out.append(f"<p class='small'>Analiza a fost rulată din aplicație la {esc(last['date'])} "
                   f"({'automat' if last.get('by') == 'auto' else 'la cerere'}), în {esc(last['seconds'])} s.</p>")
    # comparatie
    if comparison and comparison.get("a"):
        t = comparison["totals"]
        out.append(f"<h2>Comparație cu rularea anterioară</h2><p>Față de {esc(comparison['a'])}: <b>{t['rezolvate']}</b> rezolvate, "
                   f"<b>{t['noi']}</b> noi, <b>{t['ramase']}</b> rămase.</p>")
        if comparison["checks"]:
            out.append("<table><tr><th>Verificare</th><th>Rezolvate</th><th>Noi</th><th>Rămase</th></tr>" + "".join(
                f"<tr><td>{esc(c['check'])}</td><td>{c['rezolvate']}</td><td>{c['noi']}</td><td>{c['ramase']}</td></tr>" for c in comparison["checks"]) + "</table>")

    # pe zone / reguli
    for phase in ("pre", "post"):
        in_phase = {i: r for i, r in results.items() if r["phase"] == phase}
        if not in_phase:
            continue
        out.append(f"<h2>{PHASE[phase]}</h2>")
        for zid, ztitle in ((z["id"], z["title"]) for z in catalog["zones"]):
            zr = [r for r in in_phase.values() if r["zone"] == zid]
            if not zr:
                continue
            out.append(f"<h3>{esc(ztitle)}</h3>")
            for num in sorted({r["rule"] for r in zr}):
                rule = rules[num]
                rs = [r for r in zr if r["rule"] == num]
                order = ["failed", "error", "warning", "info", "waived", "skipped", "ok"]
                worst = next((s for s in order if any(_status_of(r) == s for r in rs)), "ok")
                out.append(f"<div class='rule {worst}'><b>{num}. {esc(rule['title'])}</b><span class='pill {worst}'>{STATUS[worst]}</span>"
                           f"<span class='pill ok'>clasa {esc(rule['class'])}</span>")
                for r in rs:
                    out.append(f"<h4 style='margin:10px 0 2px;font-size:14px'>{esc(r['title'])} <span class='pill {r['status']}'>{STATUS[r['status']]}</span></h4>")
                    if r.get("error"):
                        out.append(f"<p class='error pill'>Verificarea a eșuat: {esc(r['error'])}</p>")
                    if not r["findings"] and r["status"] == "ok":
                        out.append("<p class='muted small'>Nicio problemă.</p>")
                    for f in r["findings"]:
                        w = waiver_by_key.get(f["keys"][0]) if f["waived"] else None
                        out.append(f"<div class='finding'><span class='pill {f['severity']}'>{SEV[f['severity']]}</span> {esc(f['message'])}"
                                   + (f" <span class='muted'>({f['count']} obiecte)</span>" if f["count"] else ""))
                        out.append(_obj_table(f["objects"]))
                        if f["data"]:
                            out.append(f"<details><summary class='small'>Date</summary><pre>{esc(json.dumps(f['data'], ensure_ascii=False, indent=1)[:4000])}</pre></details>")
                        if f["waived"]:
                            note = f["waiver_note"] or "(fără notă)"
                            when = f" · {esc(w['date'])}" if w and w.get("date") else ""
                            out.append(f"<div class='just'><b>Justificare:</b> {esc(note)}{when}</div>")
                        out.append("</div>")
                # lista de control
                man = [m for m in rule["manual"] if m["phase"] == phase]
                if man:
                    out.append("<p class='small'><b>Listă de control (vizual):</b></p><ul class='small'>" + "".join(
                        f"<li>{'☑' if manual.get(m['id'], {}).get('done') else '☐'} {esc(m['text'])}"
                        + (f" <span class='muted'>(verificat {esc(manual[m['id']].get('date', ''))})</span>" if manual.get(m['id'], {}).get('done') else "") + "</li>"
                        for m in man) + "</ul>")
                out.append("</div>")

    # justificari
    if waivers:
        out.append("<h2>Justificări acceptate</h2><table><tr><th>Verificare / obiect</th><th>Motiv</th><th>Data</th></tr>" + "".join(
            f"<tr><td>{esc(w['key'])}</td><td>{esc(w.get('note') or '(fără notă)')}</td><td>{esc(w.get('date', ''))}</td></tr>" for w in waivers[:300]) + "</table>")
    # reguli fara verificari automate
    missing = [r for r in catalog["rules"] if not r["checks"]]
    if missing:
        out.append("<h2>Reguli fără verificare automată</h2><p class='small muted'>" + "; ".join(f"{r['number']}. {esc(r['title'])}" for r in missing) + "</p>")
    out.append("<p class='muted small'>Raport generat de ETABS Beams — verificator de model. Aplicația nu modifică modelul.</p></body></html>")
    return "".join(out)
