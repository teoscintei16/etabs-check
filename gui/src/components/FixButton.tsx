import { useState } from "react";
import * as api from "../api";
import { useVerifier } from "../useVerifier";
import type { FixOffer, FixPreview } from "../types";

/** Reparatie cu un click: previzualizare -> confirmare (+ reanaliza optionala) -> aplicare; anulabila din mesajul de dupa. */
export default function FixButton({ fix }: { fix: FixOffer }) {
  const { refresh, clearResults } = useVerifier();
  const [preview, setPreview] = useState<FixPreview | null>(null);
  const [analyze, setAnalyze] = useState(true);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ id: number; analyzing: boolean } | null>(null);
  const [err, setErr] = useState("");

  const guard = async (fn: () => Promise<void>) => {
    setBusy(true);
    setErr("");
    try {
      await fn();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const open = () => guard(async () => setPreview(await api.fixPreview(fix.id, fix.args)));
  const apply = () =>
    guard(async () => {
      const r = await api.fixApply(fix.id, fix.args, analyze);
      setDone({ id: r.id, analyzing: r.analyzing });
      setPreview(null);
      clearResults();
      await refresh();
    });
  const undo = () =>
    guard(async () => {
      if (!done) return;
      await api.fixUndo(done.id);
      setDone(null);
      clearResults();
      await refresh();
    });

  if (done)
    return (
      <div className="fix">
        <span className="muted">Reparația a fost aplicată{done.analyzing ? " și analiza a pornit" : ""}. Rulează din nou verificările.</span>
        <button disabled={busy || done.analyzing} onClick={() => void undo()}>
          Anulează reparația
        </button>
        {err && <span className="error-text">{err}</span>}
      </div>
    );
  if (!preview)
    return (
      <div className="fix">
        <button className="primary" disabled={busy} onClick={() => void open()}>
          {fix.label}
        </button>
        {err && <span className="error-text">{err}</span>}
      </div>
    );
  return (
    <div className="fix preview">
      <b>{preview.title}</b>
      <ul>
        {preview.changes.map((c, i) => (
          <li key={i}>
            {c.what}: <s>{String(c.before)}</s> → <b>{String(c.after)}</b>
          </li>
        ))}
      </ul>
      {preview.warnings.map((w, i) => (
        <p key={i} className="muted">⚠ {w}</p>
      ))}
      {preview.unlocks && (
        <label>
          <input type="checkbox" checked={analyze} onChange={(e) => setAnalyze(e.target.checked)} /> Rulează analiza după aplicare (fără cazurile neliniare)
        </label>
      )}
      <div className="waive">
        <button className="primary" disabled={busy} onClick={() => void apply()}>
          Aplică în model
        </button>
        <button disabled={busy} onClick={() => setPreview(null)}>
          Renunță
        </button>
      </div>
      {err && <span className="error-text">{err}</span>}
    </div>
  );
}
