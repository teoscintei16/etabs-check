import { useCallback, useEffect, useState } from "react";
import { getStatus } from "./api";
import PhaseView from "./components/PhaseView";
import HistoryView from "./components/HistoryView";
import SettingsView from "./components/SettingsView";
import { SelectionProvider, useSelection } from "./useSelection";
import { VerifierProvider, useVerifier } from "./useVerifier";
import type { Status } from "./types";

type Tab = "pre" | "post" | "history" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "pre", label: "Model nerulat" },
  { id: "post", label: "Model rulat" },
  { id: "history", label: "Istoric" },
  { id: "settings", label: "Setări" },
];

function Shell() {
  const [status, setStatus] = useState<Status | null>(null);
  const [tab, setTab] = useState<Tab>("pre");
  const { message, busy, additive, setAdditive } = useSelection();
  const { refresh } = useVerifier();

  const connect = useCallback(async () => {
    setStatus(null);
    try {
      const s = await getStatus();
      setStatus(s);
      if (s.connected) await refresh();
    } catch (e) {
      setStatus({ connected: false, error: (e as Error).message });
    }
  }, [refresh]);

  useEffect(() => {
    void connect();
  }, [connect]);

  return (
    <div className="app">
      <header className="top">
        <h1>ETABS Beams · Verificator de model</h1>
        <div className="conn" role="status">
          {status === null && <span className="muted">Se conectează…</span>}
          {status?.connected && (
            <>
              <span className="dot ok" aria-hidden />
              <span className="file" title={status.file}>{status.file?.split("\\").pop()}</span>
              <span className={`pill ${status.analyzed ? "ok" : "bad"}`}>{status.analyzed ? "rulat" : "nerulat"}</span>
            </>
          )}
          {status && !status.connected && (
            <>
              <span className="dot bad" aria-hidden />
              <span>ETABS nu e conectat{status.error ? `: ${status.error}` : ""}</span>
            </>
          )}
          <button onClick={connect}>Reconectează</button>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main>
        {status?.connected ? (
          tab === "settings" ? <SettingsView /> : tab === "history" ? <HistoryView /> : <PhaseView key={tab} phase={tab} />
        ) : (
          <p className="banner">Pornește ETABS cu modelul deschis, apoi apasă „Reconectează”.</p>
        )}
      </main>

      <footer className="statusbar">
        <span aria-live="polite">
          {busy ? "Se selectează în ETABS…" : message || "Clic pe o constatare pentru a-i selecta obiectele în ETABS."}
        </span>
        <label className="inline">
          <input type="checkbox" checked={additive} onChange={(e) => setAdditive(e.target.checked)} />
          Adaugă la selecția din ETABS
        </label>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <SelectionProvider>
      <VerifierProvider>
        <Shell />
      </VerifierProvider>
    </SelectionProvider>
  );
}
