import { useEffect, useState } from "react";
import { getComparison, getHistory, type Comparison, type RunSummary } from "../api";
import { useVerifier } from "../useVerifier";

const PHASE = { pre: "Model nerulat", post: "Model rulat" } as const;
const fmt = (id: string) => id.replace("T", " ").replace(/#\d+$/, "");

/** Istoricul rularilor complete (salvat langa .EDB) si compararea cu rularea anterioara. */
export default function HistoryView() {
  const { results, catalog } = useVerifier();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [cmp, setCmp] = useState<Comparison | null>(null);
  const [error, setError] = useState("");
  const title = (id: string) => catalog?.rules.flatMap((r) => r.checks).find((c) => c.id === id)?.title ?? id;

  useEffect(() => {
    getHistory().then(setRuns).catch((e: Error) => setError(e.message));
  }, [results]);

  const toggle = async (id: string) => {
    if (open === id) return setOpen(null);
    setOpen(id);
    setCmp(null);
    try {
      setCmp(await getComparison(id));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <section className="card">
      <h2>Istoric rulări</h2>
      <p className="muted">
        Se salvează o înregistrare la fiecare rulare completă a unei faze (lângă fișierul .EDB). Alege o rulare pentru a o compara cu cea dinaintea ei.
      </p>
      {error && <p className="banner error">{error}</p>}
      {runs && runs.length === 0 && <p className="muted">Nicio rulare salvată încă. Rulează „verificările modelului nerulat/rulat”.</p>}
      <ul className="issues">
        {[...(runs ?? [])].reverse().map((r) => (
          <li key={r.id} className="issue info">
            <button className="issue-head" aria-expanded={open === r.id} onClick={() => void toggle(r.id)}>
              <span className="msg">
                {fmt(r.id)} · {PHASE[r.phase]}
              </span>
              <span className="badge error">{r.counts.error} erori</span>
              <span className="badge warning">{r.counts.warning} avert.</span>
              <span className="badge info">{r.counts.info} info</span>
              {r.waived > 0 && <span className="badge waived">{r.waived} justificate</span>}
            </button>
            {open === r.id && (
              <div className="issue-body">
                {!cmp && <p className="muted">Se compară…</p>}
                {cmp && !cmp.a && <p className="muted">Aceasta e prima rulare a fazei: nu există o rulare anterioară de comparat.</p>}
                {cmp?.a && (
                  <>
                    <p>
                      Față de {fmt(cmp.a)}: <b>{cmp.totals.rezolvate}</b> rezolvate · <b>{cmp.totals.noi}</b> noi · <b>{cmp.totals.ramase}</b> rămase.
                    </p>
                    {cmp.checks.length > 0 && (
                      <table className="objects">
                        <thead>
                          <tr>
                            <th>Verificare</th>
                            <th>Rezolvate</th>
                            <th>Noi</th>
                            <th>Rămase</th>
                          </tr>
                        </thead>
                        <tbody>
                          {cmp.checks.map((c) => (
                            <tr key={c.check}>
                              <td>{title(c.check)}</td>
                              <td>{c.rezolvate}</td>
                              <td>{c.noi}</td>
                              <td>{c.ramase}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
