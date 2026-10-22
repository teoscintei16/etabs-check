import { useState } from "react";
import { useSelection } from "../useSelection";
import { useVerifier } from "../useVerifier";
import type { FindingResult } from "../types";
import ObjectTable from "./ObjectTable";

const SEV_LABEL = { error: "Eroare", warning: "Avertisment", info: "Info" } as const;

/** O constatare: mesaj, obiecte (selectie multipla in ETABS) si justificare. */
export default function FindingView({ finding }: { finding: FindingResult }) {
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState("");
  const { select } = useSelection();
  const { waive, unwaive } = useVerifier();
  const f = finding;

  const toggle = () => {
    setOpen(!open);
    if (f.objects.length) void select(f.objects, f.message.slice(0, 70));
  };

  return (
    <li className={`issue ${f.severity} ${f.waived ? "waived" : ""}`}>
      <button className="issue-head" aria-expanded={open} onClick={toggle}>
        <span className={`badge ${f.severity}`}>{SEV_LABEL[f.severity]}</span>
        <span className="msg">{f.message}</span>
        {f.waived && <span className="badge waived">justificat</span>}
        {f.count > 0 && <span className="count">{f.count}</span>}
      </button>
      {open && (
        <div className="issue-body">
          {f.objects.length > 0 && (
            <>
              <ObjectTable objects={f.objects} />
              {f.count > f.objects.length && (
                <p className="muted">
                  Se afișează primele {f.objects.length} din {f.count}.
                </p>
              )}
            </>
          )}
          {Object.keys(f.data).length > 0 && <pre className="data">{JSON.stringify(f.data, null, 1)}</pre>}
          <div className="waive">
            {f.waived ? (
              <>
                <span className="muted">Justificat: {f.waiver_note || "(fără notă)"}</span>
                <button onClick={() => void unwaive(f.keys)}>Anulează justificarea</button>
              </>
            ) : asking ? (
              <>
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Motivul (ex. intenționat)" aria-label="Motiv" />
                <button className="primary" onClick={() => { void waive(f.keys, note); setAsking(false); }}>
                  Salvează
                </button>
                <button onClick={() => setAsking(false)}>Renunță</button>
              </>
            ) : (
              <button onClick={() => setAsking(true)}>Justifică (accept)</button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
