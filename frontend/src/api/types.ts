// Exact mirror of .agents/CONTRACTS.md section 2 (backend/bob/core/models.py).
// Do not add fields that are not in the contract. Datetimes arrive as ISO strings.

// ---------- sources ----------
export type SourceKind = "upload" | "url" | "composio";
export type Toolkit = "notion" | "confluence" | "jira" | "googledrive";

export interface SourceSpec {
  kind: SourceKind;
  url?: string | null;
  crawl_limit?: number;
  toolkit?: Toolkit | null;
  connected_account_id?: string | null;
  scope?: Record<string, unknown>;
  upload_ids?: string[];
}

export interface Document {
  id: string;
  source_kind: SourceKind;
  uri: string;
  title: string;
  text: string;
  content_hash: string;
  metadata: Record<string, unknown>;
  fetched_at: string;
}

// ---------- reading ----------
export interface Chunk {
  id: string;
  doc_id: string;
  uri: string;
  heading: string | null;
  text: string;
  start: number;
  end: number;
  n_tokens: number;
  kept: boolean;
  drop_reason: string | null;
  triage: Record<string, number | string>;
  topic_id: string | null;
}

export type EvidenceKind = "feature" | "setting" | "number" | "entity" | "procedure" | "limit" | "definition" | "url";

export interface Evidence {
  id: string;
  chunk_id: string;
  doc_id: string;
  kind: EvidenceKind;
  name: string;
  value: string | null;
  span_text: string;
  start: number;
  end: number;
  confidence: number;
}

export interface Topic {
  id: string;
  name: string;
  description: string;
  chunk_ids: string[];
  brief: string;
}

// ---------- plan / coverage map ----------
export const CASE_TYPES = ["answerable", "partial", "unanswerable", "false_premise"] as const;
export const DIFFICULTIES = ["single_fact", "multi_step", "multi_doc"] as const;
export type CaseType = (typeof CASE_TYPES)[number];
export type Difficulty = (typeof DIFFICULTIES)[number];

export type AxisName = "topic" | "persona" | "case_type" | "difficulty";

export interface Axis {
  name: AxisName;
  values: string[];
  descriptions: Record<string, string>;
  role: "cell" | "mix"; // "cell": forms cells (CELL_AXES); "mix": values rotate inside each cell
  weights: Record<string, number>; // mix axes only: value -> share of rows
}

export interface Cell {
  id: string;
  coords: Record<string, string>;
  enabled: boolean;
  target: number;
  weight: number;
  generated: number;
  kept: number;
  rejected: number;
  judged: number;
  mix_weights?: Record<string, Record<string, number>>; // gap rounds: boosted shares per mix axis
  mix_kept?: Record<string, Record<string, number>>; // kept rows per mix axis value
}

export interface Plan {
  goal: string;
  task_format: "single_turn" | "multi_turn";
  system_prompt: string;
  axes: Axis[];
  cells: Cell[];
  notes: string[];
  target_rows: number;
  est_cost_usd: number;
}

export interface Control {
  state: "approved" | "cancel" | null;
  plan: Plan | null;
}

// ---------- models (D33, CONTRACTS section 14) ----------
export interface ModelConfig {
  provider: "bedrock" | "openai_compatible";
  model_id: string;
  base_url?: string | null;
  api_key_set?: boolean;
  json_mode?: "auto" | "tool" | "native" | "prompt";
  cache?: "auto" | "off";
  price_in_per_m?: number | null;
  price_out_per_m?: number | null;
}

export interface ModelRoles {
  writer: ModelConfig;
  planner: ModelConfig;
  judge: ModelConfig;
  fallback?: ModelConfig | null;
}
export const MODEL_ROLES = ["writer", "planner", "judge", "fallback"] as const;
export type ModelRole = (typeof MODEL_ROLES)[number];

// ---------- users + Bedrock access ----------
export interface BedrockAccess {
  mode: "default" | "assume_role";
  role_arn?: string | null;
  external_id?: string | null;
  region: string;
}

export interface UserProfile {
  id: string;
  email: string | null;
  external_id: string;
  bedrock: BedrockAccess | null;
  bedrock_verified_at: string | null;
  models: ModelRoles;
  models_verified_at: string | null;
  created_at: string;
}

// ---------- job ----------
export interface JobOptions {
  cell_axes?: string[] | null;
  max_cells?: number | null;
  case_mix?: Record<string, number> | null;
  keep_p?: number | null;
  reject_p?: number | null;
  audit_rate?: number | null;
  max_rounds?: number | null;
  overgen?: number | null;
  dpo_mode?: "synthesize" | "pair" | "off" | null;
  dpo_rate?: number | null;
  numbers_allow_user?: "all" | "false_premise" | "none" | null;
  extract_exempt_absent?: boolean | null;
  models?: ModelRoles | null;
}

export interface JobSpec {
  goal: string;
  sources: SourceSpec[];
  seed_upload_id?: string | null;
  target_rows?: number;
  budget_usd?: number;
  preset?: string;
  formats?: string[];
  probe_model?: string | null;
  options?: JobOptions;
}

export type JobStatus =
  | "created"
  | "ingesting"
  | "reading"
  | "planning"
  | "awaiting_approval"
  | "building"
  | "filling_gaps"
  | "reporting"
  | "done"
  | "error"
  | "cancelled";

export interface ModelCost {
  calls: number;
  in_tokens: number;
  out_tokens: number;
  usd: number;
}

export interface CostSummary {
  by_model: Record<string, ModelCost>;
  by_purpose?: Record<string, ModelCost>; // triage, verify, evidence, topics, ...
  model_ids: Record<string, string>; // role -> model id
  price_unknown: string[]; // roles whose model has no known price
  total_usd: number;
  frontier_only_estimate_usd: number;
  fallbacks_used: string[];
}

export interface Job {
  id: string;
  spec: JobSpec;
  owner_id: string;
  bedrock: BedrockAccess | null;
  models: ModelRoles;
  status: JobStatus;
  stage_detail: string;
  plan: Plan | null;
  round: number;
  counts: Record<string, number>;
  cost: CostSummary;
  files: Record<string, string>;
  report: Report | null;
  error: string | null;
  heartbeat_at: string | null;
  created_at: string;
  updated_at: string;
}

// ---------- generation + verification ----------
export interface Message {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface Candidate {
  id: string;
  job_id: string;
  cell_id: string;
  round: number;
  case_type: string;
  coords: Record<string, string>;
  messages: Message[];
  chunk_ids: string[];
  premise_evidence_id: string | null;
  absent_topic: string | null;
  writer_model: string;
  cost_usd: number;
}

export interface CheckResult {
  name: string;
  tier: 1 | 2 | 3;
  passed: boolean;
  score: number | null;
  detail: string;
  evidence_ids: string[];
}

export interface SpanRef {
  doc_id: string;
  uri: string;
  title: string;
  start: number;
  end: number;
  text: string;
}

export interface Row {
  id: string;
  job_id: string;
  cell_id: string;
  coords: Record<string, string>;
  case_type: string;
  round: number;
  messages: Message[];
  spans: SpanRef[];
  checks: CheckResult[];
  confidence: number;
  verdict: "kept" | "rejected";
  reject_reason: string | null;
  routed_to_judge: boolean;
  audited: boolean;
  spot_check: boolean | null;
  cost_usd: number;
  created_at: string;
  chunk_ids?: string[];
  absent_topic?: string | null;
  premise_evidence_id?: string | null;
}

export interface DPOPair {
  id: string;
  row_id: string;
  mode: "synthesized" | "natural";
  prompt: Message[];
  chosen: string;
  rejected: string;
  rejection_reason: string;
  rejected_checks: string[];
}

export interface Report {
  coverage: { cell_id: string; coords: Record<string, string>; target: number; kept: number; rejected: number }[];
  mix_coverage: Record<string, Record<string, number>>; // mix axis -> value -> kept rows
  pass_rate_by_check: Record<string, number>;
  reject_reasons: Record<string, number>;
  duplicates_removed: number;
  judge_rate: number;
  judge_agreement: number | null;
  spot_check: { n?: number; up?: number; down?: number; jev_accuracy?: number };
  sample_row_ids: string[];
  token_stats: { p50?: number; p95?: number; max?: number };
  rounds: { n: number; cells: number; kept: number; [k: string]: unknown }[];
}

// ---------- HTTP payloads (CONTRACTS section 6) ----------
export interface UploadResult {
  upload_ids: string[];
  files: { id: string; name: string; bytes: number }[];
}
export interface ConnectorState {
  toolkit: Toolkit;
  connected: boolean;
  account_id?: string;
}
export interface BrowseItem {
  id: string;
  title: string;
  kind: string;
}
export interface PreviewResult {
  documents: { uri: string; title: string; chars: number }[];
  capped: boolean;
}
export interface AwsSetup {
  bob_account_id: string | null; // null when the server can't tell (no BOB_ACCOUNT_ID, no STS)
  external_id: string;
  template_url: string;
  cli_command: string;
}
export interface AvailableModel {
  id: string;
  name: string;
  provider: string | null;
  kind: "inference_profile" | "foundation_model";
  on_demand: boolean;
}
export interface AvailableModels {
  region: string;
  models: AvailableModel[];
}
export interface PresetInfo {
  name: string;
  formats: string[];
  description: string;
}
export type HealthState = "ok" | string;
export interface Health {
  keys: Record<"bedrock" | "jev" | "scaledown" | "firecrawl" | "composio", HealthState>;
}

// ---------- SSE events (CONTRACTS section 8) ----------
export type StageName = "fetch" | "chunk" | "triage" | "topics" | "evidence" | "plan" | "generate" | "verify" | "export";

export interface RowEvent {
  id: string;
  cell_id: string;
  verdict: "kept" | "rejected";
  reject_reason: string | null;
  case_type: string;
  user_preview: string;
  confidence: number;
  routed_to_judge: boolean;
}

export interface CellUpdate {
  cell_id: string;
  generated: number;
  kept: number;
  rejected: number;
  judged: number;
  target: number;
}

export type BobEvent =
  | { type: "job.status"; data: { status: JobStatus; detail: string } }
  | { type: "stage.progress"; data: { stage: StageName; done: number; total: number; detail: string } }
  | { type: "counts"; data: Record<string, number> }
  | { type: "cost"; data: CostSummary }
  | { type: "plan.ready"; data: Plan }
  | { type: "cell.update"; data: CellUpdate }
  | { type: "row"; data: RowEvent }
  | { type: "round"; data: { n: number; reason: string; cells: string[]; planned: number } }
  | { type: "report.ready"; data: Report }
  | { type: "files.ready"; data: { files: Record<string, string> } }
  | { type: "log"; data: { level: string; message: string } }
  | { type: "error"; data: { message: string } }
  | { type: "done"; data: { files: Record<string, string> } };

export const EVENT_TYPES: BobEvent["type"][] = [
  "job.status",
  "stage.progress",
  "counts",
  "cost",
  "plan.ready",
  "cell.update",
  "row",
  "round",
  "report.ready",
  "files.ready",
  "log",
  "error",
  "done",
];
