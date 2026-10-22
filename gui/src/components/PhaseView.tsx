import { useMemo, useState } from "react";
import { useVerifier } from "../useVerifier";
import type { Phase } from "../types";
import RuleCard, { ruleStatus } from "./RuleCard";

const PHASE_TEXT: Record<Phase, { title: string; run: string }> = {
  pre: { title: "Model nerulat", run: "Rulează verificările modelului nerulat" },
  post: { title: "Model rulat", run: "Rulează verificările modelului rulat" },
};

const BAD = new Set(["error", "warning", "failed"]);

export default function PhaseView({ phase }: { phase: Phase }) {
  const { catalog, state, results, running, run, error, analysis, startAnalysis } = useVerifier();
  const [zone, setZone] = useState("z1");

  const rules = useMemo(
    () => (catalog?.rules ?? []).filter((r) => r.phases.includes(phase)).sort((a, b) => a.number - b.number),
    [catalog, phase],
  );
  const done = (id: string) => !!state?.manual[id]?.done;

  const zoneInfo = useMemo(() => {
    const info: Record<string, { bad: number; ran: boolean; todo: number }> = {};
    for (const z of catalog?.zones ?? []) info[z.id] = { bad: 0, ran: false, todo: 0 };
    for (const r of rules) {
      const s = ruleStatus(r, phase, results, done);
      const z = info[r.zone];
      if (!z) continue;
      if (BAD.has(s)) z.bad += 1;
      if (s !== "none" && s !== "todo") z.ran = true;
      if (s === "todo") z.todo += 1;
    }
    return info;
  }, [catalog, rules, results, phase, state]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!catalog) return <p className="muted">Se încarcă catalogul de reguli…</p>;
  const zoneRules = rules.filter((r) => r.zone === zone);
  const analyzing = analysis.state === "running";
  const busy = !!running || analyzing;

  return (
    <>
      {analyzing && (
        <p className="banner" role="status">
          Se rulează analiza în ETABS ({Math.floor((analysis.elapsed ?? 0) / 60)}:{String(Math.floor((analysis.elapsed ?? 0) % 60)).padStart(2, "0")}) —
          {analysis.by === "auto" ? " pornită automat de aplicație." : " pornită din aplicație."} Interfața se reîncarcă singură la final.
        </p>
      )}
      {!analyzing && analysis.state === "error" && <p className="banner error" role="alert">Analiza a eșuat: {analysis.message}</p>}
      {!analyzing && analysis.state === "done" && analysis.by && <p className="muted">{analysis.message}</p>}
      {phase === "post" && state && !state.analyzed && !analyzing && (
        <div className="banner">
          <p>Modelul nu are rezultate (nu este analizat), deci verificările pe model rulat sunt sărite.</p>
          <p className="hint">
            Poți rula analiza chiar din aplicație (cazurile marcate „Run” în ETABS; modelul se salvează cu rezultate; durează de la secunde la minute).
            Sau activează în Setări „rulează automat analiza”.
          </p>
          <button
            className="primary"
            onClick={() => {
              if (window.confirm("Aplicația va rula analiza modelului în ETABS (cazurile marcate „Run”) și va salva rezultatele în fișierul modelului. Continui?")) void startAnalysis();
            }}
          >
            Rulează analiza în ETABS
          </button>
        </div>
      )}
      <div className="actions">
        <button className="primary" disabled={busy} onClick={() => void run({ phase }, PHASE_TEXT[phase].title)}>
          {busy ? `Se rulează: ${running}…` : PHASE_TEXT[phase].run}
        </button>
        <button disabled={busy} onClick={() => void run({ phase, reload: true }, "reîncărcare")}>
          Reîncarcă modelul și rulează
        </button>
        <a
          className={`btn ${Object.keys(results).length ? "" : "disabled"}`}
          href={Object.keys(results).length ? "/api/v/report" : undefined}
          download
          title="Raport HTML în română, cu justificări"
        >
          Exportă raport HTML
        </a>
        <span className="muted">{state ? `${state.waivers} justificări salvate lângă model` : ""}</span>
      </div>
      {error && <p className="banner error" role="alert">{error}</p>}

      <div className="layout">
        <nav className="zones" aria-label="Zone">
          {catalog.zones.map((z) => {
            const i = zoneInfo[z.id];
            return (
              <button key={z.id} className={`zone ${zone === z.id ? "on" : ""}`} onClick={() => setZone(z.id)} aria-current={zone === z.id}>
                <span>{z.title}</span>
                {i?.bad > 0 ? <span className="count bad">{i.bad}</span> : i?.ran ? <span className="dot ok" aria-label="fără probleme" /> : null}
              </button>
            );
          })}
        </nav>
        <div className="zone-body">
          <div className="zone-head">
            <h2>{catalog.zones.find((z) => z.id === zone)?.title}</h2>
            <button disabled={busy} onClick={() => void run({ phase, zones: [zone] }, catalog.zones.find((z) => z.id === zone)?.title ?? "")}>
              Rulează zona
            </button>
          </div>
          {zoneRules.length === 0 && <p className="muted">Nicio regulă în această zonă pentru această fază.</p>}
          {zoneRules.map((r) => <RuleCard key={`${phase}-${r.number}`} rule={r} phase={phase} />)}
        </div>
      </div>
    </>
  );
}
