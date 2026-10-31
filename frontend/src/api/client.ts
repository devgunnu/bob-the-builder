// Typed client and SSE helper for the Bob API.

import { fetchEventSource } from "@microsoft/fetch-event-source";
import type {
  AvailableModels,
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
    if (status === 412 && /hosting/i.test(message)) this.fix = { label: "Model settings", to: "/account#models" };
    if (status === 412 && /model/i.test(message)) this.fix = { label: "Verify models", to: "/account#models" };
  }
}

// Plain-language versions of the contract's error strings.
function friendly(status: number, error: string): string {
  if (status === 412 && /hosting aws/i.test(error)) return "Bob could not access the hosting account's AWS services.";
  if (status === 412 && /hosting models/i.test(error)) return "Bob could not verify the configured models.";
  if (status === 412 && /model/i.test(error)) return "Verify your models before starting a job.";
  if (status === 429) return "You already have a job running. Wait for it to finish, then try again.";
  if (status === 409 && /approv/i.test(error)) return "This plan was already started or the job has stopped.";
  if (status === 409) return "The job is still running. Try again when it finishes.";
  return error;
}

async function request<T>(path: string, init: RequestInit = {}, raw = false): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      headers: {
        ...(init.body instanceof FormData || init.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...init.headers,
      },
    });
  } catch (e) {
    throw new ApiError(0, "Can't reach the Bob API. Is the backend running?", undefined, String(e));
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

// API Gateway / Lambda take 6 MB per request; leave room for the multipart overhead.
const BATCH_LIMIT_BYTES = 5 * 1024 * 1024;

interface Presigned {
  upload_id: string;
  put_url: string;
  method: string;
  headers: Record<string, string>;
  name: string;
  bytes: number;
}

async function uploadDirect(file: File): Promise<{ id: string; name: string; bytes: number }> {
  const p = await request<Presigned>("/uploads/presign", { method: "POST", ...json({ name: file.name, bytes: file.size, content_type: file.type || null }) });
  const init: RequestInit = { method: p.method || "PUT", body: file, headers: p.headers };
  if (p.put_url.startsWith(API_BASE + "/")) {
    // Local mode: our own API receives the bytes, so it needs the Authorization header.
    await request<unknown>(p.put_url.slice(API_BASE.length), init);
  } else {
    // aws: a presigned S3 URL. No Authorization header (S3 would reject the request).
    let res: Response;
    try {
      res = await fetch(p.put_url, init);
    } catch (e) {
      throw new ApiError(0, `Couldn't upload ${file.name}.`, "s3", String(e));
    }
    if (!res.ok) throw new ApiError(res.status, `Couldn't upload ${file.name}.`, "s3", (await res.text()).slice(0, 300));
  }
  return { id: p.upload_id, name: p.name, bytes: p.bytes };
}
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
  availableModels: () => request<AvailableModels>("/me/models/available"),
  verifyModels: () => request<{ ok: boolean; roles: Record<string, string> }>("/me/models/verify", { method: "POST" }),
  /** Small files go up in multipart batches under the 6 MB request limit; bigger ones
   *  through POST /uploads/presign and a direct PUT (S3 in aws mode, this API locally). */
  async upload(files: File[]): Promise<UploadResult> {
    const out: UploadResult = { upload_ids: [], files: [] };
    const add = (r: UploadResult) => (out.upload_ids.push(...r.upload_ids), out.files.push(...r.files));
    let batch: File[] = [];
    let size = 0;
    const flush = async () => {
      if (!batch.length) return;
      const fd = new FormData();
      batch.forEach((f) => fd.append("files", f));
      add(await request<UploadResult>("/uploads", { method: "POST", body: fd }));
      batch = [];
      size = 0;
    };
    for (const f of files) {
      if (f.size > BATCH_LIMIT_BYTES) {
        const one = await uploadDirect(f);
        add({ upload_ids: [one.id], files: [one] });
        continue;
      }
      if (size + f.size > BATCH_LIMIT_BYTES) await flush();
      batch.push(f);
      size += f.size;
    }
    await flush();
    return out;
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
  /** The newest `n` rows (the API pages oldest first), newest first; `before` skips rows already shown. */
  async newestRows(id: string, q: { verdict?: "kept" | "rejected"; cell_id?: string }, n: number, before = 0) {
    const head = await api.rows(id, { ...q, offset: 0, limit: 1 });
    const end = Math.max(0, head.total - before);
    const start = Math.max(0, end - n);
    if (end === 0) return { total: head.total, rows: [] as Row[], more: false };
    const page = await api.rows(id, { ...q, offset: start, limit: Math.min(200, end - start) });
    return { total: page.total, rows: [...page.rows].reverse(), more: start > 0 };
  },
  row: (id: string, rowId: string) => request<Row>(`/jobs/${id}/rows/${rowId}`),
  spotCheck: (id: string, rowId: string, ok: boolean) =>
    request<Report>(`/jobs/${id}/rows/${rowId}/spot-check`, { method: "POST", ...json({ ok }) }),
  export: (id: string, preset: string, formats: string[]) =>
    request<{ files: Record<string, string> }>(`/jobs/${id}/export`, { method: "POST", ...json({ preset, formats }) }),
  /** Download URL for a generated file. */
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
 * Subscribe to a job's SSE stream. Each reconnect sends Last-Event-ID. Events are
 * de-duplicated by id. The stream closes only on done, error or cancelled.
 */
class StreamClosed extends Error {}

export function subscribeJob(jobId: string, onEvent: (e: BobEvent, id: number) => void, onError?: (e: unknown) => void) {
  const ctrl = new AbortController();
  let lastId = -1;
  const known = new Set<string>(EVENT_TYPES);

  void fetchEventSource(`${API_BASE}/jobs/${jobId}/events`, {
    signal: ctrl.signal,
    openWhenHidden: true,
    // Send the last seen event on reconnect.
    fetch: async (input, init) => {
      const headers = new Headers(init?.headers);
      if (lastId >= 0) headers.set("Last-Event-ID", String(lastId));
      return fetch(input, { ...init, headers });
    },
    async onopen(res) {
      // 4xx (unknown job) will not heal on retry; 5xx and network errors may.
      if (res.status >= 400 && res.status < 500) throw new StreamClosed(`stream ${res.status}`);
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
      if (e.type === "error" || e.type === "done" || (e.type === "job.status" && TERMINAL.has(e.data.status))) ctrl.abort();
    },
    onerror(err) {
      onError?.(err);
      if (err instanceof StreamClosed) throw err; // stop retrying
      return 1000; // retry after 1 s (matches the server's retry: 1000)
    },
  }).catch(() => undefined); // a stopped stream was already reported through onError

  return () => ctrl.abort();
}
