import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { motion } from "motion/react";
import { Check, FileUp, Globe, Link2, Loader2, Plug, Search, SlidersHorizontal, Trash2, X } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { BrowseItem, ConnectorState, JobOptions, ModelRoles, SourceSpec, Toolkit, UserProfile } from "../api/types";
import { CASE_TYPES } from "../api/types";
import { ModelsEditor } from "../components/ModelsEditor";
import { Button, ErrorBanner, Label, caseLabel, useTitle } from "../components/ui";
import billing from "../../../demo/smoke/billing.md?raw";
import rateLimits from "../../../demo/smoke/rate-limits.md?raw";
import webhooks from "../../../demo/smoke/webhooks-overview.md?raw";

const TOOLKIT_LABEL: Record<Toolkit, string> = { notion: "Notion", confluence: "Confluence", jira: "Jira", googledrive: "Google Drive" };

// Composio scope keys per toolkit. Notion follows CONTRACTS section 2's example
// ({"page_ids": [...]}); the others are proposals for G2 (see CHANGES_REQUESTED).
function scopeFor(toolkit: Toolkit, items: BrowseItem[]): Record<string, unknown> {
  const ids = items.map((i) => i.id);
  if (toolkit === "notion" || toolkit === "confluence") return { page_ids: ids };
  if (toolkit === "googledrive") return { file_ids: ids };
  return { project_keys: items.filter((i) => i.kind === "project").map((i) => i.id), issue_keys: items.filter((i) => i.kind !== "project").map((i) => i.id) };
}

const kb = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

interface Uploaded {
  id: string;
  name: string;
  bytes: number;
}

function useUploads() {
  const [files, setFiles] = useState<Uploaded[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const add = async (picked: File[]) => {
    if (!picked.length) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.upload(picked);
      setFiles((f) => [...f, ...r.files]);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  return { files, busy, error, add, remove: (id: string) => setFiles((f) => f.filter((x) => x.id !== id)) };
}

function DropZone({ onFiles, busy, label, accept }: { onFiles: (f: File[]) => void; busy: boolean; label: string; accept?: string }) {
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  return (
    <button
      type="button"
      onClick={() => ref.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onFiles(Array.from(e.dataTransfer.files));
      }}
      className={`flex w-full flex-col items-center gap-1.5 rounded-xl border border-dashed px-4 py-5 text-[13px] transition ${
        over ? "border-bob-mint bg-bob-mint/5 text-white" : "border-white/15 text-dim hover:border-white/30 hover:text-white"
      }`}
    >
      {busy ? <Loader2 className="size-5 animate-spin" /> : <FileUp className="size-5" />}
      {label}
      <input ref={ref} type="file" multiple hidden accept={accept} onChange={(e) => (onFiles(Array.from(e.target.files ?? [])), (e.target.value = ""))} />
    </button>
  );
}

function FileList({ files, onRemove }: { files: Uploaded[]; onRemove: (id: string) => void }) {
  if (!files.length) return null;
  return (
    <ul className="mt-2 space-y-1">
      {files.map((f) => (
        <li key={f.id} className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-2.5 py-1.5 text-[12.5px]">
          <span className="truncate font-mono text-white/85">{f.name}</span>
          <span className="ml-auto shrink-0 text-[11px] text-dim">{kb(f.bytes)}</span>
          <button aria-label={`Remove ${f.name}`} onClick={() => onRemove(f.id)} className="text-dim hover:text-rose-300">
            <Trash2 className="size-3.5" />
          </button>
        </li>
      ))}
    </ul>
  );
}

interface Connected {
  toolkit: Toolkit;
  account_id: string;
  picked: BrowseItem[];
}

function ConnectorRow({ c, connected, onConnected, onPick }: { c: ConnectorState; connected?: Connected; onConnected: (account: string) => void; onPick: (items: BrowseItem[]) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<BrowseItem[] | null>(null);
  const [browsing, setBrowsing] = useState(false);
  const account = connected?.account_id ?? (c.connected ? c.account_id : undefined);

  const connect = async () => {
    // Open the popup inside the click handler so blockers allow it.
    const popup = window.open("", "bob-oauth", "width=520,height=720");
    setBusy(true);
    setError(null);
    try {
      const { auth_url, connection_id } = await api.connect(c.toolkit, `${window.location.origin}/oauth/callback`);
      if (popup) popup.location.href = auth_url;
      else window.open(auth_url, "_blank");
      const until = Date.now() + 180_000;
      while (Date.now() < until) {
        await new Promise((r) => setTimeout(r, 2000));
        const st = await api.connectorStatus(c.toolkit, connection_id);
        if (st.connected) {
          onConnected(st.account_id);
          popup?.close();
          return;
        }
      }
      throw new Error("Timed out waiting for the connection. Try again.");
    } catch (e) {
      popup?.close();
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  const browse = async (query = q) => {
    if (!account) return;
    setBrowsing(true);
    setError(null);
    try {
      setItems(await api.browse(c.toolkit, account, query));
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBrowsing(false);
    }
  };

  useEffect(() => {
    if (account && items === null) void browse("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account]);

  const picked = new Set(connected?.picked.map((p) => p.id));
  const toggle = (it: BrowseItem) => {
    const cur = connected?.picked ?? [];
    onPick(picked.has(it.id) ? cur.filter((p) => p.id !== it.id) : [...cur, it]);
  };

  return (
    <div className="rounded-xl bg-white/[0.03] p-3">
      <div className="flex items-center gap-2">
        <Plug className="size-4 text-bob-sky" />
        <span className="text-[13.5px] font-medium text-white">{TOOLKIT_LABEL[c.toolkit]}</span>
        {account ? (
          <span className="ml-auto flex items-center gap-1 text-[12px] text-bob-mint">
            <Check className="size-3.5" /> connected
          </span>
        ) : (
          <Button tone="ghost" className="ml-auto !px-3 !py-1 text-[12px]" busy={busy} onClick={connect}>
            Connect
          </Button>
        )}
      </div>
      {error && (
        <div className="mt-2">
          <ErrorBanner error={error} title={`${TOOLKIT_LABEL[c.toolkit]} connection failed`} />
        </div>
      )}
      {account && (
        <div className="mt-2.5">
          <div className="flex items-center gap-2 rounded-lg border border-line px-2.5">
            <Search className="size-3.5 text-dim" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && browse()}
              placeholder={`Search ${TOOLKIT_LABEL[c.toolkit]}…`}
              className="w-full bg-transparent py-1.5 text-[12.5px] outline-none placeholder:text-dim"
            />
            {browsing && <Loader2 className="size-3.5 animate-spin text-dim" />}
          </div>
          <ul className="scroll-thin mt-1.5 max-h-44 space-y-0.5 overflow-y-auto">
            {items?.length === 0 && <li className="px-2 py-1.5 text-[12px] text-dim">Nothing found.</li>}
            {items?.map((it) => (
              <li key={it.id}>
                <button
                  onClick={() => toggle(it)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12.5px] transition ${picked.has(it.id) ? "bg-bob-blue/15 text-white" : "text-white/75 hover:bg-white/5"}`}
                >
                  <span className={`grid size-3.5 shrink-0 place-items-center rounded ${picked.has(it.id) ? "bg-bob-blue" : "border border-white/25"}`}>
                    {picked.has(it.id) && <Check className="size-2.5" />}
                  </span>
                  <span className="truncate">{it.title}</span>
                  <span className="ml-auto shrink-0 text-[10.5px] text-dim">{it.kind}</span>
                </button>
              </li>
            ))}
          </ul>
          {!!connected?.picked.length && <div className="mt-1.5 text-[11.5px] text-bob-mint">{connected.picked.length} selected</div>}
        </div>
      )}
    </div>
  );
}

type Tab = "website" | "files" | "apps";

const URL_RE = /(?:https?:\/\/)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:\/[^\s)]*)?/i;
const withScheme = (u: string) => (/^https?:\/\//i.test(u) ? u : `https://${u}`);

export function SetupScreen({ goal, composer, initialFiles = [] }: { goal: string; composer: (create: () => void, onFiles: (f: File[]) => void, busy: boolean) => ReactNode; initialFiles?: File[] }) {
  const nav = useNavigate();
  const [url, setUrl] = useState(() => {
    const m = goal.match(URL_RE)?.[0];
    return m ? withScheme(m) : "";
  });
  const [crawlLimit, setCrawlLimit] = useState(25);
  const [preview, setPreview] = useState<{ uri: string; title: string; chars: number }[] | null>(null);
  const [capped, setCapped] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<ApiError | null>(null);
  const uploads = useUploads();
  const seeds = useUploads();
  const [connectors, setConnectors] = useState<ConnectorState[] | null>(null);
  const [connectorsError, setConnectorsError] = useState<ApiError | null>(null);
  const [connected, setConnected] = useState<Partial<Record<Toolkit, Connected>>>({});
  const [targetRows, setTargetRows] = useState(60);
  const [budget, setBudget] = useState(2);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [tab, setTab] = useState<Tab>(() => (goal.match(URL_RE) || !initialFiles.length ? "website" : "files"));
  const [showOptions, setShowOptions] = useState(false);
  const [me, setMe] = useState<UserProfile | null>(null);
  const [opts, setOpts] = useState<JobOptions>({});
  const [overrideModels, setOverrideModels] = useState(false);
  useTitle("New dataset");
  const firstFiles = useRef(initialFiles);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [error]);

  useEffect(() => {
    api.me().then(setMe).catch(() => undefined);
    api
      .connectors()
      .then(setConnectors)
      .catch((e) => (setConnectorsError(e), setConnectors([])));
    if (firstFiles.current.length) void uploads.add(firstFiles.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sources: SourceSpec[] = [];
  if (url.trim()) sources.push({ kind: "url", url: url.trim(), crawl_limit: crawlLimit });
  if (uploads.files.length) sources.push({ kind: "upload", upload_ids: uploads.files.map((f) => f.id) });
  for (const c of Object.values(connected)) {
    if (c && c.picked.length) sources.push({ kind: "composio", toolkit: c.toolkit, connected_account_id: c.account_id, scope: scopeFor(c.toolkit, c.picked) });
  }
  const ready = goal.trim().length > 3 && sources.length > 0 && !uploads.busy;

  const create = async () => {
    if (!ready) {
      setError(new ApiError(0, sources.length ? "Describe the goal in a few words." : "Add at least one source: a website, a file, or a connected app."));
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const job = await api.createJob({
        goal: goal.trim(),
        sources,
        seed_upload_id: seeds.files[0]?.id ?? null,
        target_rows: targetRows,
        budget_usd: budget,
        options: cleanOptions(opts, overrideModels),
      });
      nav(`/jobs/${job.id}/plan`);
    } catch (e) {
      setError(e as ApiError);
      setCreating(false);
    }
  };

  const addSample = () => {
    setTab("files");
    void uploads.add([
      new File([billing], "billing.md", { type: "text/markdown" }),
      new File([rateLimits], "rate-limits.md", { type: "text/markdown" }),
      new File([webhooks], "webhooks-overview.md", { type: "text/markdown" }),
    ]);
  };

  const doPreview = async () => {
    if (!url.trim()) return;
    setPreviewing(true);
    setPreviewError(null);
    try {
      const r = await api.previewSource({ kind: "url", url: url.trim(), crawl_limit: crawlLimit });
      setPreview(r.documents);
      setCapped(r.capped);
    } catch (e) {
      setPreviewError(e as ApiError);
    } finally {
      setPreviewing(false);
    }
  };

  const rise = (i: number) => ({
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    transition: { duration: 0.3, delay: 0.15 + i * 0.05 },
  });

  const pickedApps = Object.values(connected).filter((c): c is Connected => !!c && c.picked.length > 0);
  const added: { key: string; label: string; remove: () => void }[] = [
    ...(url.trim() ? [{ key: "url", label: url.replace(/^https?:\/\//, ""), remove: () => (setUrl(""), setPreview(null), setPreviewError(null)) }] : []),
    ...(uploads.files.length ? [{ key: "files", label: `${uploads.files.length} file${uploads.files.length > 1 ? "s" : ""}`, remove: () => uploads.files.forEach((f) => uploads.remove(f.id)) }] : []),
    ...pickedApps.map((c) => ({
      key: c.toolkit,
      label: `${TOOLKIT_LABEL[c.toolkit]} · ${c.picked.length} item${c.picked.length > 1 ? "s" : ""}`,
      remove: () => setConnected((x) => ({ ...x, [c.toolkit]: { ...c, picked: [] } })),
    })),
  ];

  const TABS: { id: Tab; label: string; hint: string; tone: string; icon: ReactNode }[] = [
    { id: "website", label: "Website", hint: "A docs or help site", tone: "bg-bob-blue/25 text-bob-sky", icon: <Globe className="size-4" /> },
    { id: "files", label: "Files", hint: "PDF, Markdown, CSV…", tone: "bg-bob-mint/20 text-bob-mint", icon: <FileUp className="size-4" /> },
    { id: "apps", label: "Apps", hint: "Notion, Jira, Drive…", tone: "bg-bob-yellow/20 text-bob-yellow", icon: <Plug className="size-4" /> },
  ];

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-16 pt-8">
      <motion.div {...rise(0)} className="mb-5 text-center">
        <h1 className="font-display text-[28px] font-extrabold leading-tight">Where should Bob look?</h1>
        <p className="mt-1 text-[14px] text-dim">Add the material your dataset should come from.</p>
      </motion.div>

      <div className="mb-6">{composer(create, uploads.add, creating)}</div>

      {!uploads.files.length && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line px-4 py-3 text-[13px] text-dim">
          <span>Don't have documents handy? Try Bob with sample support docs.</span>
          <Button tone="ghost" busy={uploads.busy} onClick={addSample}>Use sample docs</Button>
        </div>
      )}

      <motion.section {...rise(1)} className="rounded-2xl bg-panel p-1.5">
        <div className="grid grid-cols-3 gap-1.5" role="tablist">
          {TABS.map((t) => {
            const n = t.id === "website" ? (url.trim() ? 1 : 0) : t.id === "files" ? uploads.files.length : pickedApps.reduce((a, c) => a + c.picked.length, 0);
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={`relative flex flex-col items-center gap-1.5 rounded-xl px-2 py-3 text-center transition ${tab === t.id ? "bg-white/[0.08] text-white" : "text-dim hover:bg-white/[0.03] hover:text-white"}`}
              >
                <span className={`grid size-9 place-items-center rounded-full ${tab === t.id ? t.tone : "bg-white/5"}`}>{t.icon}</span>
                <span className="text-[13.5px] font-medium">{t.label}</span>
                <span className="hidden text-[11px] text-dim sm:block">{t.hint}</span>
                {n > 0 && <span className="absolute right-2 top-2 grid min-w-5 place-items-center rounded-full bg-bob-mint px-1 text-[10.5px] font-bold text-bob-navy">{n}</span>}
              </button>
            );
          })}
        </div>

        <div className="p-3">
          {tab === "website" && (
            <div>
              <div className="flex items-center gap-2 rounded-xl border border-line px-3">
                <Link2 className="size-4 text-dim" />
                <input
                  value={url}
                  onChange={(e) => (setUrl(e.target.value), setPreview(null), setPreviewError(null))}
                  placeholder="https://docs.yourproduct.com"
                  className="w-full bg-transparent py-2.5 text-[14px] outline-none placeholder:text-dim"
                />
              </div>
              {url.trim() && !URL_RE.test(url.trim()) && <div className="mt-1.5 text-[12px] text-bob-yellow">That doesn't look like a web address yet, for example docs.yourproduct.com</div>}
              <div className="mt-2 flex items-center gap-3 text-[12px] text-dim">
                <span>
                  Reads up to{" "}
                  <input type="number" min={1} max={200} value={crawlLimit} onChange={(e) => setCrawlLimit(Math.max(1, Number(e.target.value) || 1))} className="w-10 border-b border-white/20 bg-transparent text-center text-white outline-none" /> pages
                </span>
                {url.trim() && (
                  <button onClick={doPreview} disabled={previewing} className="ml-auto flex items-center gap-1 text-bob-sky hover:underline disabled:opacity-50">
                    {previewing && <Loader2 className="size-3 animate-spin" />} Preview pages
                  </button>
                )}
              </div>
              {previewError && <div className="mt-2"><ErrorBanner error={previewError} title="Couldn't preview this site" /></div>}
              {preview && capped && <div className="mt-2 text-[12px] text-dim">Showing the first pages only. The job reads up to {crawlLimit}.</div>}
              {preview && (
                <ul className="scroll-thin mt-2 max-h-40 space-y-0.5 overflow-y-auto">
                  {preview.map((d) => (
                    <li key={d.uri} className="flex items-center gap-2 px-1 py-1 text-[12.5px]">
                      <span className="truncate text-white/80">{d.title || d.uri}</span>
                      <span className="ml-auto shrink-0 font-mono text-[11px] text-dim">{d.chars.toLocaleString()} chars</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {tab === "files" && (
            <div>
              <DropZone onFiles={uploads.add} busy={uploads.busy} label="Drop PDF, DOCX, Markdown, HTML, TXT or CSV" accept=".pdf,.docx,.md,.markdown,.html,.htm,.txt,.csv" />
              <FileList files={uploads.files} onRemove={uploads.remove} />
              {uploads.error && <div className="mt-2"><ErrorBanner error={uploads.error} title="Upload failed" /></div>}
            </div>
          )}

          {tab === "apps" &&
            (connectorsError ? (
              <ErrorBanner error={connectorsError} title="Connected apps are unavailable" />
            ) : connectors === null ? (
              <div className="flex items-center gap-2 py-2 text-[12.5px] text-dim"><Loader2 className="size-4 animate-spin" /> Loading connectors…</div>
            ) : connectors.length === 0 ? (
              <div className="py-2 text-[12.5px] text-dim">No connectors are configured on the server.</div>
            ) : (
              <div className="space-y-2">
                {connectors.map((c) => (
                  <ConnectorRow
                    key={c.toolkit}
                    c={c}
                    connected={connected[c.toolkit] ?? (c.connected && c.account_id ? { toolkit: c.toolkit, account_id: c.account_id, picked: [] } : undefined)}
                    onConnected={(account) => setConnected((x) => ({ ...x, [c.toolkit]: { toolkit: c.toolkit, account_id: account, picked: [] } }))}
                    onPick={(items) => setConnected((x) => ({ ...x, [c.toolkit]: { toolkit: c.toolkit, account_id: x[c.toolkit]?.account_id ?? c.account_id ?? "", picked: items } }))}
                  />
                ))}
              </div>
            ))}
        </div>
      </motion.section>

      {/* what's been added, at a glance */}
      <motion.div {...rise(2)} className="mt-3 flex min-h-7 flex-wrap items-center gap-1.5">
        {added.length === 0 ? (
          <span className="text-[12.5px] text-dim">No sources yet.</span>
        ) : (
          added.map((a) => (
            <span key={a.key} className="flex items-center gap-1.5 rounded-full bg-bob-mint/10 px-2.5 py-1 text-[12px] text-bob-mint">
              <Check className="size-3" /> {a.label}
              <button aria-label={`Remove ${a.label}`} onClick={a.remove} className="text-bob-mint/60 hover:text-white"><X className="size-3" /></button>
            </span>
          ))
        )}
      </motion.div>

      {/* options: one line until opened */}
      <motion.div {...rise(3)} className="mt-6 border-t border-line pt-4">
        <button onClick={() => setShowOptions((v) => !v)} className="flex w-full items-center gap-2 text-left text-[13px] text-dim hover:text-white">
          <SlidersHorizontal className="size-4" />
          <span>
            <span className="text-white/85">{targetRows.toLocaleString()} rows</span> · ${budget} budget · {seeds.files.length ? "1 seed file" : "no seed examples"}
          </span>
          <span className="ml-auto text-bob-sky">{showOptions ? "Done" : "Change"}</span>
        </button>
        {showOptions && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <Label>Rows to keep</Label>
              <div className="flex items-center gap-3">
                <input type="range" min={10} max={5000} step={10} value={targetRows} onChange={(e) => setTargetRows(Number(e.target.value))} className="flex-1 accent-[var(--color-bob-blue)]" />
                <input type="number" min={10} value={targetRows} onChange={(e) => setTargetRows(Math.max(10, Number(e.target.value) || 10))} className="w-20 rounded-lg border border-line bg-transparent px-2 py-1 text-right font-mono text-[13px] outline-none" />
              </div>
            </div>
            <div>
              <Label>Budget (Bob stops writing at 95%)</Label>
              <div className="flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5">
                <span className="text-dim">$</span>
                <input type="number" min={1} step={1} value={budget} onChange={(e) => setBudget(Math.max(1, Number(e.target.value) || 1))} className="w-full bg-transparent font-mono text-[13px] outline-none" />
              </div>
            </div>
            <div className="sm:col-span-2">
              <Label>Seed examples (optional JSONL or CSV of real examples)</Label>
              {seeds.files.length ? (
                <FileList files={seeds.files.slice(0, 1)} onRemove={seeds.remove} />
              ) : (
                <DropZone onFiles={(f) => seeds.add(f.slice(0, 1))} busy={seeds.busy} label="Drop seeds.jsonl or seeds.csv" accept=".jsonl,.csv" />
              )}
              {seeds.error && <div className="mt-2"><ErrorBanner error={seeds.error} title="Seed upload failed" /></div>}
            </div>
            <details className="group sm:col-span-2">
              <summary className="cursor-pointer list-none text-[13px] text-dim hover:text-white">
                <span className="group-open:hidden">Show advanced options</span><span className="hidden group-open:inline">Hide advanced options</span>
                <span className="ml-2 text-[11.5px]">Empty fields use the defaults.</span>
              </summary>
              <AdvancedOptions opts={opts} setOpts={setOpts} me={me} overrideModels={overrideModels} setOverrideModels={setOverrideModels} />
            </details>
          </div>
        )}
      </motion.div>

      <motion.div {...rise(4)} className="mt-6">
        {/* next to the button, so the reason is on screen wherever the user pressed it */}
        {error && (
          <div ref={errorRef} className="mb-3 scroll-mt-4">
            <ErrorBanner error={error} title={error.status === 412 ? "One step before you start" : error.status === 0 ? "Almost ready" : "Couldn't draft the plan"} />
          </div>
        )}
        <Button tone="yellow" className="w-full py-3 text-[16px]" busy={creating} disabled={!ready} onClick={create}>
          Draft the plan
        </Button>
        <p className="mt-2 text-center text-[12px] text-dim">
          {ready ? "Bob reads everything first. Nothing is written until you approve the plan." : "Add a website, file or app to continue."}
        </p>
      </motion.div>
    </div>
  );
}

/** Only send the fields the user actually set (CONTRACTS: empty = config or profile default). */
function cleanOptions(o: JobOptions, withModels: boolean): JobOptions {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(o)) {
    if (k === "models") continue;
    if (v === undefined || v === null || v === "" || (typeof v === "object" && !Array.isArray(v) && !Object.keys(v as object).length)) continue;
    out[k] = v;
  }
  if (withModels && o.models) out.models = o.models;
  return out as JobOptions;
}

function NumField({ label, value, onChange, step = 1, min = 0, max }: { label: string; value: number | null | undefined; onChange: (v: number | null) => void; step?: number; min?: number; max?: number }) {
  return (
    <label className="block">
      <Label>{label}</Label>
      <input
        type="number"
        step={step}
        min={min}
        max={max}
        value={value ?? ""}
        placeholder="default"
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        className="w-full rounded-lg border border-line bg-transparent px-2 py-1.5 font-mono text-[12.5px] outline-none placeholder:font-sans placeholder:text-dim"
      />
    </label>
  );
}

function AdvancedOptions({
  opts,
  setOpts,
  me,
  overrideModels,
  setOverrideModels,
}: {
  opts: JobOptions;
  setOpts: (o: JobOptions) => void;
  me: UserProfile | null;
  overrideModels: boolean;
  setOverrideModels: (v: boolean) => void;
}) {
  const set = <K extends keyof JobOptions>(k: K, v: JobOptions[K]) => setOpts({ ...opts, [k]: v });
  const mix = opts.case_mix ?? {};
  const sel = (label: string, k: "dpo_mode" | "numbers_allow_user", values: string[]) => (
    <label className="block">
      <Label>{label}</Label>
      <select value={(opts[k] as string | null | undefined) ?? ""} onChange={(e) => set(k, (e.target.value || null) as never)} className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1.5 text-[13px] outline-none">
        <option value="">default</option>
        {values.map((v) => <option key={v}>{v}</option>)}
      </select>
    </label>
  );
  return (
    <div className="mt-3 space-y-4 rounded-xl bg-white/[0.02] p-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block sm:col-span-2">
          <Label>Cell axes</Label>
          <input
            value={(opts.cell_axes ?? []).join(", ")}
            onChange={(e) => set("cell_axes", e.target.value.trim() ? e.target.value.split(",").map((x) => x.trim()).filter(Boolean) : null)}
            placeholder="default (topic, case_type)"
            className="w-full rounded-lg border border-line bg-transparent px-2 py-1.5 font-mono text-[12.5px] outline-none placeholder:font-sans placeholder:text-dim"
          />
        </label>
        <NumField label="Max cells" value={opts.max_cells} onChange={(v) => set("max_cells", v)} min={1} />
        <NumField label="Keep if checks ≥" value={opts.keep_p} onChange={(v) => set("keep_p", v)} step={0.05} max={1} />
        <NumField label="Reject if checks <" value={opts.reject_p} onChange={(v) => set("reject_p", v)} step={0.05} max={1} />
        <NumField label="Audit share" value={opts.audit_rate} onChange={(v) => set("audit_rate", v)} step={0.01} max={1} />
        <NumField label="Max rounds" value={opts.max_rounds} onChange={(v) => set("max_rounds", v)} min={1} />
        <NumField label="Over-generate ×" value={opts.overgen} onChange={(v) => set("overgen", v)} step={0.1} min={1} />
        <NumField label="DPO share" value={opts.dpo_rate} onChange={(v) => set("dpo_rate", v)} step={0.05} max={1} />
        {sel("Preference pairs", "dpo_mode", ["synthesize", "pair", "off"])}
        {sel("Numbers from the user turn", "numbers_allow_user", ["all", "false_premise", "none"])}
        <label className="block">
          <Label>Skip name check for absent topic</Label>
          <select
            value={opts.extract_exempt_absent === undefined || opts.extract_exempt_absent === null ? "" : String(opts.extract_exempt_absent)}
            onChange={(e) => set("extract_exempt_absent", e.target.value === "" ? null : e.target.value === "true")}
            className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1.5 text-[13px] outline-none"
          >
            <option value="">default</option>
            <option value="true">yes</option>
            <option value="false">no</option>
          </select>
        </label>
      </div>
      <div>
        <Label>Case mix (share of rows per kind of question)</Label>
        <div className="grid gap-2 sm:grid-cols-4">
          {CASE_TYPES.map((c) => (
            <NumField
              key={c}
              label={caseLabel(c)}
              value={mix[c]}
              step={0.05}
              max={1}
              onChange={(v) => {
                const next = { ...mix };
                if (v === null) delete next[c];
                else next[c] = v;
                set("case_mix", Object.keys(next).length ? next : null);
              }}
            />
          ))}
        </div>
      </div>
      <div>
        <label className="flex items-center gap-2 text-[13px] text-white/85">
          <input type="checkbox" checked={overrideModels} onChange={(e) => (setOverrideModels(e.target.checked), e.target.checked && !opts.models && me && set("models", structuredClone(me.models) as ModelRoles))} />
          Use different models for this job only
        </label>
        {overrideModels && opts.models && <div className="mt-2"><ModelsEditor value={opts.models} onChange={(m) => set("models", m)} /></div>}
      </div>
    </div>
  );
}
