import { useState } from "react";
import { useVerifier } from "../useVerifier";
import BeltPicker from "./BeltPicker";

/** Setari: centuri (dummy) si parametrii verificarilor. Se salveaza lânga fisierul .EDB. */
export default function SettingsView() {
  const { catalog, state, saveBelts, saveParam, saveProject } = useVerifier();
  const [draft, setDraft] = useState<Record<string, string>>({});
  if (!catalog || !state) return <p className="muted">Se încarcă…</p>;

  const withParams = catalog.rules.flatMap((r) => r.checks.filter((c) => c.params.length > 0).map((c) => ({ rule: r, check: c })));

  const commit = (key: string, raw: string, isNumber: boolean) => {
    if (!(key in draft)) return;               // nimic modificat: nu salvam valorile implicite in fisierul modelului
    const v = isNumber ? Number(raw.replace(",", ".")) : raw;
    if (isNumber && Number.isNaN(v)) return;
    void saveParam(key, v);
    setDraft((d) => { const n = { ...d }; delete n[key]; return n; });
  };

  return (
    <>
      <BeltPicker
        sections={state.sections}
        hasBelts={state.belts.has}
        selected={state.belts.sections}
        onHasBelts={(v) => void saveBelts(v, v ? state.belts.sections : [])}
        onSelected={(s) => void saveBelts(true, s)}
      />

      <section className="card">
        <h2>Parametri proiect</h2>
        <p className="muted">
          Valorile proiectului (acțiune seismică, infrastructură) pe care le compară verificările cu ce e în model. Lasă gol dacă nu se aplică;
          verificările care le cer vor afișa ce lipsește.
        </p>
        {(catalog.project_params ?? []).map((p) => {
          const key = `project.${p.name}`;
          const stored = state.project?.[p.name];
          const cur = key in draft ? draft[key] : stored == null || Array.isArray(stored) ? (p.default == null ? "" : String(p.default)) : String(stored);
          const unit = p.unit ? <span className="muted">{p.unit}</span> : null;
          return (
            <label key={key} className="param">
              <span>{p.label}</span>
              <span className="param-input">
                {p.kind === "stories" ? (
                  <span className="chips">
                    {state.stories.map((s) => {
                      const cur = Array.isArray(state.project?.[p.name]) ? (state.project[p.name] as string[]) : [];
                      const on = cur.includes(s);
                      const next = on ? cur.filter((x) => x !== s) : [...cur, s];
                      return (
                        <label key={s} className={`chip ${on ? "on" : ""}`}>
                          <input type="checkbox" checked={on} onChange={() => void saveProject(p.name, next.length ? next : null)} />
                          {s}
                        </label>
                      );
                    })}
                  </span>
                ) : p.kind === "choice" || p.kind === "story" ? (
                  <select value={cur} onChange={(e) => void saveProject(p.name, e.target.value || null)}>
                    <option value="">(nesetat)</option>
                    {(p.kind === "story" ? state.stories : p.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    value={cur}
                    inputMode="decimal"
                    onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                    onBlur={(e) => {
                      if (!(key in draft)) return;
                      const raw = e.target.value.replace(",", ".").trim();
                      const v = raw === "" ? null : Number(raw);
                      if (v === null || !Number.isNaN(v)) void saveProject(p.name, v);
                      setDraft((d) => { const n = { ...d }; delete n[key]; return n; });
                    }}
                    onKeyDown={(e) => (e.key === "Enter" ? (e.target as HTMLInputElement).blur() : undefined)}
                  />
                )}
                {unit}
              </span>
              <span className="muted">{p.default != null ? `implicit: ${String(p.default)}` : ""}</span>
            </label>
          );
        })}
      </section>

      <section className="card">
        <h2>Parametri verificări</h2>
        <p className="muted">Valorile se salvează lângă model. După modificare, rulează din nou verificarea.</p>
        {withParams.length === 0 && <p className="muted">Nicio verificare cu parametri încă.</p>}
        {withParams.map(({ rule, check }) => (
          <fieldset key={check.id} className="params">
            <legend>Regula {rule.number} · {check.title}</legend>
            {check.params.map((p) => {
              const key = `${check.id}.${p.name}`;
              const cur = key in draft ? draft[key] : String(state.params[key] ?? p.default);
              const isNumber = typeof p.default === "number";
              return (
                <label key={key} className="param">
                  <span>{p.label}</span>
                  <span className="param-input">
                    <input
                      value={cur}
                      inputMode={isNumber ? "decimal" : "text"}
                      onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                      onBlur={(e) => commit(key, e.target.value, isNumber)}
                      onKeyDown={(e) => (e.key === "Enter" ? (e.target as HTMLInputElement).blur() : undefined)}
                    />
                    {p.unit && <span className="muted">{p.unit}</span>}
                  </span>
                  <span className="muted">implicit: {String(p.default)}</span>
                </label>
              );
            })}
          </fieldset>
        ))}
      </section>

      <section className="card">
        <h2>Fișier de setări</h2>
        <p className="muted mono">{state.sidecar}</p>
      </section>
    </>
  );
}
