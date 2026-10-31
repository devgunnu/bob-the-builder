// Typed client: one function per route in .agents/CONTRACTS.md section 6, with
// the bearer token on every call (D27), plus an authenticated SSE helper (section 8).

import { fetchEventSource } from "@microsoft/fetch-event-source";
import { authHeader, onUnauthorized } from "../auth/session";
import type {
  AwsSetup,
  BedrockAccess,
  BobEvent,
  BrowseItem,
  ConnectorState,
  Health,
  Job,
  JobSpec,
  ModelRoles,
  Plan,
  PresetInfo,
  PreviewResult,
  Report,
  Row,
  SourceSpec,
  Toolkit,
  UploadResult,
  UserProfile,
} from "./types";
import { EVENT_TYPES } from "./types";

// Same origin everywhere: CloudFront in production, the Vite proxy in dev.
export const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  provider?: string;
  detail?: string;
  /** Where the user can fix it, for 412 errors (CONTRACTS section 14). */
  fix?: { label: string; to: string };
  constructor(status: number, message: string, provider?: string, detail?: string) {
    super(message);
    this.status = status;
    this.provider = provider;
    this.detail = detail;
    if (status === 412 && /aws/i.test(message)) this.fix = { label: "Connect AWS", to: "/account#aws" };
    if (status === 412 && /model/i.test(message)) this.fix = { label: "Verify models", to: "/account#models" };
  }
}

// Plain-language versions of the contract's error strings.
function friendly(status: number, error: string): string {
  if (status === 412 && /aws/i.test(error)) return "Connect your AWS account before starting a job.";
  if (status === 412 && /model/i.test(error)) return "Verify your models before starting a job.";
  if (status === 429) return "You already have a job running. Wait for it to finish, then try again.";
  return error;
}

async function request<T>(path: string, init: RequestInit = {}, raw = false): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      headers: {
        ...(init.body instanceof FormData || init.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(await authHeader()),
        ...init.headers,
      },
    });
  } catch (e) {
    throw new ApiError(0, "Can't reach the Bob API. Is the backend running?", undefined, String(e));
  }
  if (res.status === 401) {
    void onUnauthorized();
    throw new ApiError(401, "Please sign in again.");
  }
  if (!res.ok) {
    let body: { error?: string; provider?: string; detail?: string } = {};
    try {
      body = await res.json();
    } catch {
      /* non-JSON error */
    }
    const msg = body.error ?? `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, friendly(res.status, msg), body.provider, body.detail);
  }
  return (raw ? res : await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });
// File names are paths like "openai-chat/train/train.jsonl": keep the slashes.
const filePath = (name: string) => name.split("/").map(encodeURIComponent).join("/");

export const api = {
  ping: () => request<{ ok: boolean }>("/ping"),
  me: () => request<UserProfile>("/me"),
  awsSetup: () => request<AwsSetup>("/me/aws/setup"),
  async downloadTemplate() {
    const res = await request<Response>("/me/aws/template", {}, true);
    saveBlob(await res.blob(), "bedrock-role.yaml");
  },
  saveAws: (access: BedrockAccess) => request<UserProfile>("/me/aws", { method: "PUT", ...json(access) }),
  verifyAws: () => request<{ ok: boolean; error?: string }>("/me/aws/verify", { method: "POST" }),
  saveModels: (roles: ModelRoles, api_keys?: Record<string, string>) =>
    request<UserProfile>("/me/models", { method: "PUT", ...json(api_keys && Object.keys(api_keys).length ? { ...roles, api_keys } : roles) }),
  verifyModels: () => request<{ ok: boolean; roles: Record<string, string> }>("/me/models/verify", { method: "POST" }),
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
  previewSource: (spec: SourceSpec) => request<PreviewResult>("/sources/preview", { method: "POST", ...json(spec) }),
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
  /** Signed download URL (a plain link can't send the auth header). */
  fileUrl: (id: string, name: string) => request<{ url: string }>(`/jobs/${id}/files/${filePath(name)}/url`).then((r) => r.url),
  async download(id: string, name: string) {
    const url = await api.fileUrl(id, name);
    const a = document.createElement("a");
    a.href = url;
    a.download = name.split("/").pop() ?? name;
    a.rel = "noopener";
    a.click();
  },
  resync: (id: string) => request<Job>(`/jobs/${id}/resync`, { method: "POST" }),
  presets: () => request<PresetInfo[]>("/presets"),
  health: () => request<Health>("/health"),
};

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const TERMINAL = new Set(["done", "error", "cancelled"]);

/**
 * Subscribe to a job's SSE stream with the auth header (EventSource can't send
 * one). Each (re)connect gets a fresh token and sends Last-Event-ID. Events are
 * de-duplicated by id. The stream closes only on done, error or cancelled.
 */
export function subscribeJob(jobId: string, onEvent: (e: BobEvent, id: number) => void, onError?: (e: unknown) => void) {
  const ctrl = new AbortController();
  let lastId = -1;
  const known = new Set<string>(EVENT_TYPES);

  void fetchEventSource(`${API_BASE}/jobs/${jobId}/events`, {
    signal: ctrl.signal,
    openWhenHidden: true,
    // A custom fetch so every reconnect gets a fresh token and our Last-Event-ID.
    fetch: async (input, init) => {
      const headers = new Headers(init?.headers);
      for (const [k, v] of Object.entries(await authHeader())) headers.set(k, v);
      if (lastId >= 0) headers.set("Last-Event-ID", String(lastId));
      return fetch(input, { ...init, headers });
    },
    async onopen(res) {
      if (res.status === 401) {
        void onUnauthorized();
        throw new Error("sign in required");
      }
      if (!res.ok) throw new Error(`stream ${res.status}`);
    },
    onmessage(msg) {
      if (!known.has(msg.event)) return; // ": ping" comments and unknown types
      const id = Number(msg.id);
      if (Number.isFinite(id) && msg.id !== "") {
        if (id <= lastId) return;
        lastId = id;
      }
      let data: unknown;
      try {
        data = JSON.parse(msg.data);
      } catch {
        return;
      }
      const e = { type: msg.event, data } as BobEvent;
      onEvent(e, id);
      if (e.type === "error" || (e.type === "job.status" && TERMINAL.has(e.data.status))) ctrl.abort();
    },
    onerror(err) {
      onError?.(err);
      if (String(err).includes("sign in required")) throw err; // stop retrying
      return 1000; // retry after 1 s (matches the server's retry: 1000)
    },
  });

  return () => ctrl.abort();
}
