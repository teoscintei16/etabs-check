export interface Status {
  connected: boolean;
  file?: string;
  analyzed?: boolean;
  error?: string;
}

export interface SectionCount {
  name: string;
  count: number;
}

export type Severity = "error" | "warning" | "info";

export interface ObjRef {
  type: "frame" | "wall" | "chain" | string;
  name: string;
  label?: string;
  story?: string;
  section?: string;
  role?: string;
  thickness?: number;
  length?: number;
  frames?: ObjRef[];
}

export interface Issue {
  code: string;
  severity: Severity;
  message: string;
  count: number;
  listed: number;
  data: Record<string, unknown>;
  objects: ObjRef[];
}

export interface CheckReport {
  model_file: string;
  ready: boolean;
  counts: { errors: number; warnings: number; info: number };
  issues: Issue[];
}

export interface SupportInfo {
  node: string;
  station: number;
  kind: string;
  offset_before: number;
  offset_after: number;
  elements: string[];
  fixed_end: boolean;
}

export interface SpanInfo {
  index: number;
  s0: number;
  s1: number;
  length: number;
  clear_length: number;
  cantilever: boolean;
  sections: string[];
  section_change: boolean;
}

export interface ChainMember {
  frame: string;
  label: string;
  section: string;
  s0: number;
  s1: number;
}

export interface Chain {
  id: string;
  kind: "beam" | "belt";
  story: string;
  length: number;
  continuity: "continuous" | "single_span";
  members: ChainMember[];
  supports: SupportInfo[];
  spans: SpanInfo[];
  warnings: string[];
}

export interface DetectResult {
  chains_total: number;
  chains_selected: number;
  chains: Chain[];
  belts_total: number;
  belts_selected: number;
  belts: Chain[];
  on_wall: { frames: string[]; sections: string[]; story: string; length: number; wall_length: number }[];
  stories: string[];
  warnings: { code: string; message: string; objects: ObjRef[]; data?: Record<string, unknown> }[];
}

export interface Selector {
  sections: string[];
  exclude_sections: string[];
  stories: string[];
  min_length: number | null;
  match: "any" | "all";
  continuity: "any" | "continuous" | "single_span";
}

// ---------------------------------------------------------------- verificator (nerulat / rulat)
export type Phase = "pre" | "post";
export type AutoClass = "A" | "B" | "C" | "D";

export interface ParamDef {
  name: string;
  default: number | string | boolean | null;
  label: string;
  unit: string;
  kind?: "number" | "choice" | "story" | "stories" | "text";
  options?: string[];
}

export interface RuleCheck {
  id: string;
  phase: Phase;
  title: string;
  params: ParamDef[];
}

export interface ManualItem {
  id: string;
  rule: number;
  phase: Phase;
  text: string;
}

export interface RuleInfo {
  number: number;
  title: string;
  what: string;
  how: string;
  alarms: string;
  notes: string;
  zone: string;
  phases: Phase[];
  class: AutoClass;
  checks: RuleCheck[];
  manual: ManualItem[];
}

export interface Zone {
  id: string;
  title: string;
}

export interface Catalog {
  zones: Zone[];
  rules: RuleInfo[];
  project_params: ParamDef[];
}

export interface FindingResult {
  severity: Severity;
  message: string;
  count: number;
  data: Record<string, unknown>;
  objects: ObjRef[];
  fix?: FixOffer | null;
  keys: string[];
  waived: boolean;
  waiver_note: string;
}

export type CheckStatus = Severity | "ok" | "waived" | "failed" | "skipped";

export interface CheckResult {
  id: string;
  rule: number;
  phase: Phase;
  zone: string;
  title: string;
  findings: FindingResult[];
  error: string | null;
  seconds: number;
  status: CheckStatus;
}

export interface VState {
  file: string;
  analyzed: boolean;
  sidecar: string;
  belts: { has: boolean | null; sections: string[] };
  params: Record<string, number | string | boolean>;
  project: Record<string, number | string | string[] | null>;
  stories: string[];
  manual: Record<string, { done: boolean; note: string; date: string }>;
  waivers: number;
  sections: SectionCount[];
}

export interface AnalysisStatus {
  state: "idle" | "running" | "done" | "error";
  elapsed?: number;
  duration?: number | null;
  message: string;
  by: string;
}

export interface FixOffer {
  id: string;
  label: string;
  args: Record<string, unknown>;
}

export interface FixPreview {
  title: string;
  changes: { what: string; before: unknown; after: unknown }[];
  warnings: string[];
  unlocks: boolean;
  inputs?: { key: string; label: string; value: number; unit: string }[];
  rows?: FixRows;
}

export interface FixRows {
  key: string;
  title: string;
  columns: { key: string; label: string; edit?: "number" | "select"; options?: string[] }[];
  items: Record<string, string | number | boolean>[];
}
