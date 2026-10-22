import { useState } from "react";
import { useVerifier } from "../useVerifier";
import type { CheckResult, CheckStatus, Phase, RuleInfo } from "../types";
import FindingView from "./FindingView";

const STATUS_TEXT: Record<CheckStatus | "none" | "todo", string> = {
  ok: "în regulă", info: "info", warning: "avertisment", error: "eroare", waived: "justificat",
  failed: "verificare defectă", skipped: "fără rezultate", none: "nerulat", todo: "neimplementat",
};

const CLASS_HELP: Record<string, string> = {
  A: "A · complet automat",
  B: "B · automat, cu parametri din Setări",
  C: "C · semi-automat: găsim candidații, confirmi tu",
  D: "D · vizual / manual",
};

export function ruleStatus(rule: RuleInfo, phase: Phase, results: Record<string, CheckResult>, manualDone: (id: string) => boolean) {
  const checks = rule.checks.filter((c) => c.phase === phase);
  const manual = rule.manual.filter((m) => m.phase === phase);
  if (checks.length === 0 && manual.length === 0) return "todo" as const;
  const rs = checks.map((c) => results[c.id]).filter(Boolean);
  const order: CheckStatus[] = ["failed", "error", "warning", "info", "waived", "skipped", "ok"];
  if (rs.length < checks.length) return checks.length && rs.length === 0 ? ("none" as const) : (rs.find((r) => r.status !== "ok")?.status ?? "none");
  const worst = order.find((s) => rs.some((r) => r.status === s));
  if (worst) return worst;
  return manual.some((m) => !manualDone(m.id)) ? ("none" as const) : ("ok" as const);
}

export default function RuleCard({ rule, phase }: { rule: RuleInfo; phase: Phase }) {
  const { results, state, setManual, run, running } = useVerifier();
  const [open, setOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const done = (id: string) => !!state?.manual[id]?.done;
  const status = ruleStatus(rule, phase, results, done);
  const checks = rule.checks.filter((c) => c.phase === phase);
  const manual = rule.manual.filter((m) => m.phase === phase);
  const rs = checks.map((c) => results[c.id]).filter(Boolean);
  const total = rs.flatMap((r) => r.findings).filter((f) => !f.waived).reduce((n, f) => n + Math.max(f.count, 1), 0);

  return (
    <section className={`rule ${status}`}>
      <button className="rule-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="rule-no">{rule.number}</span>
        <span className="rule-title">{rule.title}</span>
        <span className="cls" title={CLASS_HELP[rule.class]}>{rule.class}</span>
        <span className={`status ${status}`}>{STATUS_TEXT[status]}</span>
        {total > 0 && <span className="count">{total}</span>}
      </button>

      {open && (
        <div className="rule-body">
          {status === "todo" && <p className="muted">Verificarea automată pentru această fază nu e încă implementată (vezi planul).</p>}

          {checks.map((c) => {
            const r = results[c.id];
            return (
              <div key={c.id} className="check">
                <div className="check-head">
                  <strong>{c.title}</strong>
                  <button disabled={!!running} onClick={() => void run({ ids: [c.id] }, c.title)}>
                    {r ? "Rulează din nou" : "Rulează"}
                  </button>
                  {r && <span className="muted">{r.seconds}s</span>}
                </div>
                {r?.error && <p className="banner error">Verificarea a eșuat: {r.error}</p>}
                {r && r.findings.length === 0 && !r.error && <p className="ok-line">În regulă.</p>}
                <ul className="issues">{r?.findings.map((f) => <FindingView key={f.keys[0]} finding={f} />)}</ul>
              </div>
            );
          })}

          {manual.length > 0 && (
            <div className="check">
              <strong>Listă de control (vizual)</strong>
              <ul className="manual">
                {manual.map((m) => (
                  <li key={m.id}>
                    <label className="inline">
                      <input type="checkbox" checked={done(m.id)} onChange={(e) => void setManual(m.id, e.target.checked)} />
                      {m.text}
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button className="link" onClick={() => setHelp(!help)}>{help ? "Ascunde" : "Arată"} descrierea regulii</button>
          {help && (
            <dl className="help">
              {rule.what && (<><dt>Ce se verifică</dt><dd>{rule.what}</dd></>)}
              {rule.how && (<><dt>Cum se verifică</dt><dd>{rule.how}</dd></>)}
              {rule.alarms && (<><dt>Semnale de alarmă</dt><dd>{rule.alarms}</dd></>)}
              {rule.notes && (<><dt>Observație</dt><dd>{rule.notes}</dd></>)}
              <dt>Clasă</dt><dd>{CLASS_HELP[rule.class]}</dd>
            </dl>
          )}
        </div>
      )}
    </section>
  );
}
