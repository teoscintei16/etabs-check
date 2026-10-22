import type { AnalysisStatus, Catalog, CheckResult, Phase, VState, ObjRef, SectionCount, Status } from "./types";

async function call<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, body === undefined ? undefined : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch { /* raspuns fara JSON */ }
    throw new Error(String(detail));
  }
  return res.json() as Promise<T>;
}

export const getStatus = () => call<Status>("/api/status");
export const getSections = () => call<SectionCount[]>("/api/sections");

/** Selecteaza in ETABS barele si peretii din lista (tipurile necunoscute sunt ignorate).
 *  clear=false adauga la selectia curenta din ETABS in loc sa o inlocuiasca. */
export const selectInEtabs = (objects: ObjRef[], clear = true) =>
  call<{ selected: number; failed: string[] }>("/api/select", {
    clear,
    objects: objects.filter((o) => ["frame", "wall", "area", "joint"].includes(o.type)).map((o) => ({ type: o.type, name: o.name })),
  });

// ---------------------------------------------------------------- verificator
const put = async <T,>(url: string, body: unknown): Promise<T> => {
  const res = await fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(res.statusText);
  return res.json() as Promise<T>;
};

export const getCatalog = () => call<Catalog>("/api/v/catalog");
export const getVState = () => call<VState>("/api/v/state");
export const runVerifier = (req: { phase?: Phase; zones?: string[]; ids?: string[]; reload?: boolean }) =>
  call<{ file: string; analyzed: boolean; results: CheckResult[] }>("/api/v/run", req);
export const saveSettings = (s: { belts?: { has: boolean | null; sections: string[] }; params?: Record<string, unknown>; project?: Record<string, unknown> }) =>
  put<unknown>("/api/v/settings", s);
export const waive = (keys: string[], note: string) => call<{ ok: boolean }>("/api/v/waive", { keys, note });
export const unwaive = (keys: string[]) => call<{ ok: boolean }>("/api/v/unwaive", { keys });
export const setManual = (id: string, done: boolean, note = "") => call<{ ok: boolean }>("/api/v/manual", { id, done, note });

export interface RunSummary {
  id: string;
  phase: Phase;
  analyzed: boolean;
  counts: { error: number; warning: number; info: number };
  waived: number;
}
export interface Comparison {
  a: string | null;
  b: string;
  phase: Phase;
  checks: { check: string; rezolvate: number; noi: number; ramase: number; exemple_rezolvate: string[]; exemple_noi: string[] }[];
  totals: { rezolvate: number; noi: number; ramase: number };
}
export const getHistory = () => call<RunSummary[]>("/api/v/history");
export const getComparison = (b: string) => call<Comparison>(`/api/v/compare?b=${encodeURIComponent(b)}`);

export const getAnalysisStatus = () => call<AnalysisStatus>("/api/v/analyze/status");
export const startAnalysis = () => call<{ started: boolean }>("/api/v/analyze", {});

export const fixPreview = (fix: string, args: Record<string, unknown>) => call<import("./types").FixPreview>("/api/v/fix/preview", { fix, args });
export const fixApply = (fix: string, args: Record<string, unknown>, analyze: boolean) =>
  call<{ id: number; changes: unknown[]; analyzing: boolean }>("/api/v/fix/apply", { fix, args, analyze });
export const fixUndo = (id: number) => call<{ undone: number }>(`/api/v/fix/undo/${id}`, {});
