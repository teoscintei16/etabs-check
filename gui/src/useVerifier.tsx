import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import * as api from "./api";
import type { AnalysisStatus, Catalog, CheckResult, Phase, VState } from "./types";

interface VerifierCtx {
  catalog: Catalog | null;
  state: VState | null;
  results: Record<string, CheckResult>;
  analysis: AnalysisStatus;
  startAnalysis: () => Promise<void>;
  running: string;          // eticheta operatiei in curs ("" = liber)
  error: string;
  refresh: () => Promise<void>;
  clearResults: () => void;
  run: (req: { phase?: Phase; zones?: string[]; ids?: string[]; reload?: boolean }, label: string) => Promise<void>;
  saveBelts: (has: boolean | null, sections: string[]) => Promise<void>;
  saveParam: (key: string, value: number | string | boolean) => Promise<void>;
  saveProject: (key: string, value: number | string | string[] | null) => Promise<void>;
  waive: (keys: string[], note: string) => Promise<void>;
  unwaive: (keys: string[]) => Promise<void>;
  setManual: (id: string, done: boolean) => Promise<void>;
}

const Ctx = createContext<VerifierCtx | null>(null);

export function VerifierProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [state, setState] = useState<VState | null>(null);
  const [results, setResults] = useState<Record<string, CheckResult>>({});
  const [running, setRunning] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisStatus>({ state: "idle", message: "", by: "" });
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      setCatalog(await api.getCatalog());
      setState(await api.getVState());
    } catch (e) {
      setState(null);
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // starea analizei se citeste fara COM, deci merge si cat analiza blocheaza ETABS
  const wasRunning = useRef(false);
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const s = await api.getAnalysisStatus();
        if (stop) return;
        setAnalysis(s);
        if (wasRunning.current && s.state !== "running") {
          setResults({});
          void refresh();
        }
        wasRunning.current = s.state === "running";
        timer = setTimeout(poll, s.state === "running" ? 2000 : 6000);
      } catch {
        timer = setTimeout(poll, 8000);
      }
    };
    void poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [refresh]);

  const clearResults = useCallback(() => setResults({}), []);

  const startAnalysis = useCallback(async () => {
    setError("");
    try {
      await api.startAnalysis();
      setAnalysis({ state: "running", message: "Se pornește analiza…", by: "manual", elapsed: 0 });
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const run: VerifierCtx["run"] = useCallback(async (req, label) => {
    setRunning(label);
    setError("");
    try {
      const r = await api.runVerifier(req);
      setResults((prev) => {
        const next = { ...prev };
        for (const x of r.results) next[x.id] = x;
        return next;
      });
      setState((s) => (s ? { ...s, analyzed: r.analyzed } : s));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning("");
    }
  }, []);

  const guarded = useCallback(async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      setState(await api.getVState());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  // actualizari optimiste: interfata raspunde imediat, apoi se sincronizeaza cu serverul
  const saveBelts = useCallback(async (has: boolean | null, sections: string[]) => {
    setState((s) => (s ? { ...s, belts: { has, sections } } : s));
    await guarded(() => api.saveSettings({ belts: { has, sections } }));
  }, [guarded]);
  const saveParam = useCallback(async (key: string, value: number | string | boolean) => {
    setState((s) => (s ? { ...s, params: { ...s.params, [key]: value } } : s));
    await guarded(() => api.saveSettings({ params: { [key]: value } }));
  }, [guarded]);
  const saveProject = useCallback(async (key: string, value: number | string | string[] | null) => {
    setState((s) => (s ? { ...s, project: { ...s.project, [key]: value } } : s));
    await guarded(() => api.saveSettings({ project: { [key]: value } }));
  }, [guarded]);
  const setManual = useCallback(async (id: string, done: boolean) => {
    setState((s) => {
      if (!s) return s;
      const manual = { ...s.manual };
      if (done) manual[id] = { done: true, note: "", date: "" }; else delete manual[id];
      return { ...s, manual };
    });
    await guarded(() => api.setManual(id, done));
  }, [guarded]);

  // justificarile modifica doar marcajul din rezultatele deja calculate (nu reruleaza verificarea)
  const patchWaived = useCallback((keys: string[], waived: boolean, note: string) => {
    setResults((prev) => {
      const next: Record<string, CheckResult> = {};
      for (const [id, r] of Object.entries(prev)) {
        const findings = r.findings.map((f) =>
          f.keys.every((k) => keys.includes(k)) ? { ...f, waived, waiver_note: waived ? note : "" } : f,
        );
        const active = findings.filter((f) => !f.waived);
        const order = ["error", "warning", "info"] as const;
        const status = r.error ? "failed"
          : active.length === 0 ? (findings.length ? "waived" : "ok")
          : order.find((s) => active.some((f) => f.severity === s))!;
        next[id] = { ...r, findings, status };
      }
      return next;
    });
  }, []);

  const waive = useCallback(async (keys: string[], note: string) => {
    await guarded(() => api.waive(keys, note));
    patchWaived(keys, true, note);
  }, [guarded, patchWaived]);
  const unwaive = useCallback(async (keys: string[]) => {
    await guarded(() => api.unwaive(keys));
    patchWaived(keys, false, "");
  }, [guarded, patchWaived]);

  const value = useMemo(
    () => ({ catalog, state, results, analysis, startAnalysis, running, error, refresh, clearResults, run, saveBelts, saveParam, saveProject, waive, unwaive, setManual }),
    [catalog, state, results, analysis, startAnalysis, running, error, refresh, clearResults, run, saveBelts, saveParam, saveProject, waive, unwaive, setManual],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useVerifier(): VerifierCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("VerifierProvider lipsa");
  return c;
}
