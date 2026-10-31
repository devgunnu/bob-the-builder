// Mirrors .agents/CONTRACTS.md so the UI can switch from the simulated
// engine to the real API without reshaping data.

export type StageId =
  | "ingest"
  | "triage"
  | "extract"
  | "architect"
  | "generate"
  | "write"
  | "verify"
  | "export";

export interface Stage {
  id: StageId;
  label: string;
  hint: string;
}

export const STAGES: Stage[] = [
  { id: "ingest", label: "Ingest", hint: "Read files and pages" },
  { id: "triage", label: "Triage", hint: "Jev drops boilerplate" },
  { id: "extract", label: "Extract", hint: "Facts with source spans" },
  { id: "architect", label: "Architect", hint: "Design generators" },
  { id: "generate", label: "Generate", hint: "Run generators" },
  { id: "write", label: "Write", hint: "Phrase rows naturally" },
  { id: "verify", label: "Verify", hint: "Check every row" },
  { id: "export", label: "Export", hint: "Formats and presets" },
];

export type StageState = "pending" | "active" | "done";

export interface SourceDoc {
  id: string;
  name: string;
  kind: "pdf" | "url" | "md" | "csv" | "txt";
  pages: number;
  kept: number;
}

export interface Capability {
  id: string;
  title: string;
  detail: string;
  generator: string;
  estRows: number;
  enabled: boolean;
}

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
}

export interface Row {
  id: string;
  generator: string;
  kind: "sft" | "dpo";
  persona: string;
  prompt: string;
  response: string;
  rejected?: string;
  source: { doc: string; section: string; text: string; span: [number, number] };
  checks: Check[];
  status: "verified" | "rejected";
  rejectReason?: string;
  costUsd: number;
}

export interface Stats {
  generated: number;
  verified: number;
  rejected: number;
  costUsd: number;
  baselineUsd: number;
}

export type ChatMessage =
  | { id: string; from: "user"; text: string }
  | { id: string; from: "bob"; text: string }
  | { id: string; from: "bob"; card: "sources"; sources: SourceDoc[] }
  | { id: string; from: "bob"; card: "architect"; capabilities: Capability[]; approved: boolean }
  | { id: string; from: "bob"; card: "done"; stats: Stats };

export type JobEvent =
  | { type: "stage"; stage: StageId; state: StageState; progress?: number }
  | { type: "message"; message: ChatMessage }
  | { type: "row"; row: Row }
  | { type: "stats"; stats: Stats }
  | { type: "done" };

export interface JobSession {
  subscribe(fn: (e: JobEvent) => void): () => void;
  approve(capabilityIds: string[]): void;
  send(text: string): void;
  cancel(): void;
}

export interface JobClient {
  start(input: { prompt: string; files: File[] }): JobSession;
}
