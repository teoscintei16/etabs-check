import { useState } from "react";
import * as api from "../api";
import { useVerifier } from "../useVerifier";
import type { FixOffer, FixPreview, FixRows } from "../types";

type Row = Record<string, string | number | boolean>;

/** Reparatie cu un click: previzualizare (cu intrari si randuri editabile) -> confirmare (+ reanaliza optionala) -> aplicare; anulabila. */
export default function FixButton({ fix }: { fix: FixOffer }) {
  const { refresh, clearResults } = useVerifier();
  const [preview, setPreview] = useState<FixPreview | null>(null);
  const [values, setValues] = useState<Record<string, number>>({});
  const [rows, setRows] = useState<Row[]>([]);
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
  const buildArgs = (): Record<string, unknown> => {
    const args: Record<string, unknown> = { ...fix.args, ...values };
    if (preview?.rows) args[preview.rows.key] = rows.filter((r) => r.include);
    return args;
  };
  const load = (p: FixPreview) => {
    setPreview(p);
    if (p.rows) setRows(p.rows.items);
  };
  const open = () =>
    guard(async () => {
      const p = await api.fixPreview(fix.id, fix.args);
      setValues(Object.fromEntries((p.inputs ?? []).map((i) => [i.key, i.value])));
      load(p);
    });
  const refreshPreview = () =>
    guard(async () => {
      const p = await api.fixPreview(fix.id, { ...buildArgs() });
      setPreview((old) => (old ? { ...old, changes: p.changes, warnings: p.warnings } : p));
    });
  const apply = () =>
    guard(async () => {
      const r = await api.fixApply(fix.id, buildArgs(), analyze);
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
  const edit = (i: number, key: string, v: string | number | boolean) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, [key]: v } : r)));
  const picked = rows.filter((r) => r.include).length;

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
      {(preview.inputs ?? []).map((i) => (
        <label key={i.key} className="fix-input">
          {i.label}
          <input
            type="number"
            step="any"
            value={values[i.key] ?? i.value}
            onChange={(e) => setValues({ ...values, [i.key]: Number(e.target.value) })}
            onBlur={() => void refreshPreview()}
          />
          {i.unit}
        </label>
      ))}
      {preview.changes.length > 0 && (
        <ul>
          {preview.changes.map((c, i) => (
            <li key={i}>
              {c.what}: <s>{String(c.before)}</s> → <b>{String(c.after)}</b>
            </li>
          ))}
        </ul>
      )}
      {preview.rows && <RowsTable spec={preview.rows} rows={rows} edit={edit} />}
      {preview.warnings.map((w, i) => (
        <p key={i} className="muted">
          ⚠ {w}
        </p>
      ))}
      {preview.unlocks && (
        <label>
          <input type="checkbox" checked={analyze} onChange={(e) => setAnalyze(e.target.checked)} /> Rulează analiza după aplicare (fără cazurile neliniare)
        </label>
      )}
      <div className="waive">
        <button className="primary" disabled={busy || (!!preview.rows && picked === 0)} onClick={() => void apply()}>
          {preview.rows ? `Aplică în model (${picked})` : "Aplică în model"}
        </button>
        <button disabled={busy} onClick={() => setPreview(null)}>
          Renunță
        </button>
      </div>
      {err && <span className="error-text">{err}</span>}
    </div>
  );
}

function RowsTable({ spec, rows, edit }: { spec: FixRows; rows: Row[]; edit: (i: number, key: string, v: string | number | boolean) => void }) {
  const all = rows.every((r) => r.include);
  return (
    <div className="fix-rows">
      <table>
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                aria-label="Toate"
                checked={all}
                onChange={(e) => rows.forEach((_, i) => edit(i, "include", e.target.checked))}
              />
            </th>
            {spec.columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={r.include ? "" : "off"}>
              <td>
                <input type="checkbox" checked={!!r.include} onChange={(e) => edit(i, "include", e.target.checked)} aria-label="Include" />
              </td>
              {spec.columns.map((c) => (
                <td key={c.key}>
                  {c.edit === "number" ? (
                    <input type="number" step="any" value={String(r[c.key])} onChange={(e) => edit(i, c.key, Number(e.target.value))} />
                  ) : c.edit === "select" ? (
                    <select value={String(r[c.key])} onChange={(e) => edit(i, c.key, e.target.value)}>
                      {(c.options ?? []).map((o) => (
                        <option key={o}>{o}</option>
                      ))}
                    </select>
                  ) : (
                    String(r[c.key] ?? "")
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
