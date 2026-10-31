// Typed client: one function per route in .agents/CONTRACTS.md section 6,
// plus an SSE helper that reconnects and de-duplicates replayed events.

import type {
  BobEvent,
  BrowseItem,
  ConnectorState,
  Health,
  Job,
  JobSpec,
  Plan,
  PresetInfo,
  Report,
  Row,
  SourceSpec,
  Toolkit,
  UploadResult,
} from "./types";
import { EVENT_TYPES } from "./types";

export const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").replace(/\/$/, "") + "/api";

export class ApiError extends Error {
  status: number;
  provider?: string;
  detail?: string;
  constructor(status: number, message: string, provider?: string, detail?: string) {
    super(message);
    this.status = status;
    this.provider = provider;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      headers: init.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
    });
  } catch (e) {
    throw new ApiError(0, `Can't reach the Bob API at ${API_BASE}. Is the backend running?`, undefined, String(e));
  }
  if (!res.ok) {
    let body: { error?: string; provider?: string; detail?: string } = {};
    try {
      body = await res.json();
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, body.error ?? `${res.status} ${res.statusText}`, body.provider, body.detail);
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });

export const api = {
  upload(files: File[]) {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<UploadResult>("/uploads", { method: "POST", body: fd });
  },
  connectors: () => request<ConnectorState[]>("/connectors"),
  connect: (toolkit: Toolkit, redirect_url: string) =>
    request<{ auth_url: string; connection_id: string }>(`/connectors/${toolkit}/connect`, { method: "POST", ...json({ redirect_url }) }),
  connectorStatus: (toolkit: Toolkit, connection_id: string) =>
    request<{ connected: boolean; account_id: string }>(`/connectors/${toolkit}/status?connection_id=${encodeURIComponent(connection_id)}`),
  browse: (toolkit: Toolkit, account_id: string, q = "") =>
    request<BrowseItem[]>(`/connectors/${toolkit}/browse?account_id=${encodeURIComponent(account_id)}&q=${encodeURIComponent(q)}`),
  previewSource: (spec: SourceSpec) =>
    request<{ documents: { uri: string; title: string; chars: number }[] }>("/sources/preview", { method: "POST", ...json(spec) }),
  createJob: (spec: JobSpec) => request<Job>("/jobs", { method: "POST", ...json(spec) }),
  listJobs: () => request<Job[]>("/jobs"),
  getJob: (id: string) => request<Job>(`/jobs/${id}`),
  approvePlan: (id: string, plan: Plan) => request<Job>(`/jobs/${id}/plan`, { method: "PUT", ...json(plan) }),
  cancel: (id: string) => request<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
  rows(id: string, q: { verdict?: "kept" | "rejected"; cell_id?: string; offset?: number; limit?: number } = {}) {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return request<{ total: number; rows: Row[] }>(`/jobs/${id}/rows?${p}`);
  },
  row: (id: string, rowId: string) => request<Row>(`/jobs/${id}/rows/${rowId}`),
  spotCheck: (id: string, rowId: string, ok: boolean) =>
    request<Report>(`/jobs/${id}/rows/${rowId}/spot-check`, { method: "POST", ...json({ ok }) }),
  export: (id: string, preset: string, formats: string[]) =>
    request<{ files: Record<string, string> }>(`/jobs/${id}/export`, { method: "POST", ...json({ preset, formats }) }),
  fileUrl: (id: string, name: string) => `${API_BASE}/jobs/${id}/files/${encodeURIComponent(name)}`,
  resync: (id: string) => request<Job>(`/jobs/${id}/resync`, { method: "POST" }),
  presets: () => request<PresetInfo[]>("/presets"),
  health: () => request<Health>("/health"),
};

/**
 * Subscribe to a job's SSE stream. EventSource reconnects on its own and
 * sends Last-Event-ID; the server replays from there. Events are still
 * de-duplicated by id, because replay can resend ids we already handled
 * (for example after this hook remounts).
 */
export function subscribeJob(jobId: string, onEvent: (e: BobEvent, id: number) => void, onError?: (e: Event) => void) {
  const es = new EventSource(`${API_BASE}/jobs/${jobId}/events`);
  let lastId = -1;
  const handler = (type: BobEvent["type"]) => (msg: MessageEvent) => {
    const id = Number(msg.lastEventId);
    if (Number.isFinite(id)) {
      if (id <= lastId) return;
      lastId = id;
    }
    let data: unknown;
    try {
      data = JSON.parse(msg.data);
    } catch {
      return;
    }
    onEvent({ type, data } as BobEvent, id);
  };
  for (const t of EVENT_TYPES) es.addEventListener(t, handler(t) as EventListener);
  if (onError) es.onerror = onError;
  return () => es.close();
}
