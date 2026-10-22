import { useMemo, useState } from "react";
import { runCheck } from "../api";
import { useChecked } from "../useChecked";
import { flatten, useSelection } from "../useSelection";
import type { CheckReport, Issue, SectionCount, Severity } from "../types";
import BeltPicker from "../components/BeltPicker";
import ObjectTable from "../components/ObjectTable";
import SelectionBar from "../components/SelectionBar";

const SEV_LABEL: Record<Severity, string> = { error: "Eroare", warning: "Avertisment", info: "Info" };

interface Props {
  sections: SectionCount[];
  hasBelts: boolean | null;
  belts: string[];
  onHasBelts: (v: boolean) => void;
  onBelts: (v: string[]) => void;
}

export default function CheckTab({ sections, hasBelts, belts, onHasBelts, onBelts }: Props) {
  const [report, setReport] = useState<CheckReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Severity | "all">("all");
  const [open, setOpen] = useState<string | null>(null);
  const { select } = useSelection();

  const ready = hasBelts !== null && (!hasBelts || belts.length > 0);

  const run = async () => {
    setLoading(true);
    setError("");
    try {
      setReport(await runCheck(hasBelts ? belts : []));
      setOpen(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const issues = useMemo(
    () => (report?.issues ?? []).filter((i) => filter === "all" || i.severity === filter),
    [report, filter],
  );
  // doar problemele cu obiecte pot fi selectate in ETABS
  const selectable = useMemo(() => issues.filter((i) => i.objects.length > 0), [issues]);
  const keys = useMemo(() => selectable.map((i) => i.code), [selectable]);
  const { checked, toggle, setAll, count } = useChecked(keys);

  const clickIssue = (i: Issue) => {
    setOpen(open === i.code ? null : i.code);
    if (i.objects.length) void select(i.objects, i.message.slice(0, 70));
  };

  const pickedIssues = selectable.filter((i) => checked.has(i.code));
  const pickedObjects = flatten(pickedIssues.flatMap((i) => i.objects));
  const selectChecked = () => void select(pickedObjects, `${pickedIssues.length} probleme bifate`);

  const sevButton = (sev: Severity, text: string) => (
    <button className={`sev ${sev} ${filter === sev ? "on" : ""}`} onClick={() => setFilter(filter === sev ? "all" : sev)}>
      {text}
    </button>
  );

  return (
    <>
      <BeltPicker sections={sections} hasBelts={hasBelts} selected={belts} onHasBelts={onHasBelts} onSelected={onBelts} />
      <div className="actions">
        <button className="primary" disabled={!ready || loading} onClick={run}>
          {loading ? "Se verifică…" : "Rulează verificarea"}
        </button>
        {!ready && (
          <span className="muted">Răspunde la întrebarea despre centuri{hasBelts ? " și alege secțiunile" : ""}.</span>
        )}
      </div>
      {error && (
        <p className="banner error" role="alert">
          {error}
        </p>
      )}

      {report && (
        <section className="card" aria-live="polite">
          <div className="summary">
            <span className={`verdict ${report.ready ? "ok" : "bad"}`}>
              {report.ready ? "Model pregătit" : "Model nepregătit"}
            </span>
            {sevButton("error", `${report.counts.errors} erori`)}
            {sevButton("warning", `${report.counts.warnings} avertismente`)}
            {sevButton("info", `${report.counts.info} info`)}
          </div>
          <p className="hint">
            Clic pe o problemă o selectează în ETABS. Bifează mai multe probleme (sau obiecte din listă) pentru a le selecta
            odată.
          </p>
          <SelectionBar
            checked={count}
            total={selectable.length}
            noun="probleme"
            detail={`${pickedObjects.length} obiecte`}
            onAll={setAll}
            onSelect={selectChecked}
          />

          <ul className="issues">
            {issues.map((i) => (
              <li key={i.code} className={`issue ${i.severity}`}>
                <div className="issue-line">
                  <input
                    type="checkbox"
                    aria-label={`Bifează: ${i.message.slice(0, 40)}`}
                    disabled={i.objects.length === 0}
                    checked={checked.has(i.code)}
                    onChange={() => undefined}
                    onClick={(e) => toggle(keys.indexOf(i.code), e.shiftKey)}
                  />
                  <button className="issue-head" aria-expanded={open === i.code} onClick={() => clickIssue(i)}>
                    <span className={`badge ${i.severity}`}>{SEV_LABEL[i.severity]}</span>
                    <span className="msg">{i.message}</span>
                    {i.count > 0 && <span className="count">{i.count}</span>}
                  </button>
                </div>
                {open === i.code && (
                  <div className="issue-body">
                    {i.objects.length > 0 && (
                      <>
                        <ObjectTable objects={i.objects} />
                        {i.count > i.listed && (
                          <p className="muted">
                            Se afișează primele {i.listed} din {i.count}.
                          </p>
                        )}
                      </>
                    )}
                    {i.data && Object.keys(i.data).length > 0 && (
                      <pre className="data">{JSON.stringify(i.data, null, 1)}</pre>
                    )}
                  </div>
                )}
              </li>
            ))}
            {issues.length === 0 && <li className="muted">Nicio problemă în această categorie.</li>}
          </ul>
        </section>
      )}
    </>
  );
}
