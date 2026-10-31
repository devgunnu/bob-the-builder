import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { motion } from "motion/react";
import { Check, FileUp, Globe, Link2, Loader2, Plug, Search, Sprout, Trash2, X } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { BrowseItem, ConnectorState, SourceSpec, Toolkit } from "../api/types";
import { Bob } from "../components/Bob";
import { Button, ErrorBanner, Label, Panel } from "../components/ui";

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
    <div className="rounded-xl border border-line bg-white/[0.02] p-3">
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
  const [previewing, setPreviewing] = useState(false);
  const uploads = useUploads();
  const seeds = useUploads();
  const [connectors, setConnectors] = useState<ConnectorState[] | null>(null);
  const [connected, setConnected] = useState<Partial<Record<Toolkit, Connected>>>({});
  const [targetRows, setTargetRows] = useState(1000);
  const [budget, setBudget] = useState(10);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const firstFiles = useRef(initialFiles);

  useEffect(() => {
    api
      .connectors()
      .then(setConnectors)
      .catch((e) => setError(e));
    if (firstFiles.current.length) void uploads.add(firstFiles.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sources: SourceSpec[] = [];
  if (url.trim()) sources.push({ kind: "url", url: url.trim(), crawl_limit: crawlLimit });
  if (uploads.files.length) sources.push({ kind: "upload", upload_ids: uploads.files.map((f) => f.id) });
  for (const c of Object.values(connected)) {
    if (c && c.picked.length) sources.push({ kind: "composio", toolkit: c.toolkit, connected_account_id: c.account_id, scope: scopeFor(c.toolkit, c.picked) });
  }
  const ready = goal.trim().length > 3 && sources.length > 0;

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
      });
      nav(`/jobs/${job.id}/plan`);
    } catch (e) {
      setError(e as ApiError);
      setCreating(false);
    }
  };

  const doPreview = async () => {
    if (!url.trim()) return;
    setPreviewing(true);
    setError(null);
    try {
      setPreview((await api.previewSource({ kind: "url", url: url.trim(), crawl_limit: crawlLimit })).documents);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setPreviewing(false);
    }
  };

  const rise = (i: number) => ({
    initial: { opacity: 0, y: 20, filter: "blur(6px)" },
    animate: { opacity: 1, y: 0, filter: "blur(0px)" },
    transition: { duration: 0.55, delay: 0.25 + i * 0.08 },
  });

  return (
    <div className="mx-auto w-full max-w-5xl px-4 pb-16 pt-6">
      <motion.div {...rise(0)} className="mb-4 flex items-center gap-3">
        <Bob pose="idea" size={64} />
        <div>
          <h1 className="font-display text-[26px] font-extrabold leading-tight">Let's set up your dataset</h1>
          <p className="text-[13.5px] text-dim">Your goal is in the bar. Point Bob at the material it should learn from, then he'll draft a coverage plan.</p>
        </div>
      </motion.div>

      <div className="mb-6">{composer(create, uploads.add, creating)}</div>

      {error && (
        <div className="mb-4">
          <ErrorBanner error={error} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <motion.div {...rise(1)}>
            <Panel title={<span className="flex items-center gap-2"><Globe className="size-4 text-bob-sky" /> Website</span>}>
              <div className="flex flex-wrap gap-2">
                <div className="flex min-w-[220px] flex-1 items-center gap-2 rounded-xl border border-line px-3">
                  <Link2 className="size-4 text-dim" />
                  <input value={url} onChange={(e) => (setUrl(e.target.value), setPreview(null))} placeholder="https://docs.yourproduct.com" className="w-full bg-transparent py-2 text-[13.5px] outline-none placeholder:text-dim" />
                </div>
                <label className="flex items-center gap-1.5 rounded-xl border border-line px-2.5 text-[12px] text-dim">
                  pages
                  <input type="number" min={1} max={200} value={crawlLimit} onChange={(e) => setCrawlLimit(Math.max(1, Number(e.target.value) || 1))} className="w-12 bg-transparent text-white outline-none" />
                </label>
                <Button tone="ghost" onClick={doPreview} busy={previewing} disabled={!url.trim()}>
                  Preview
                </Button>
              </div>
              {preview && (
                <ul className="scroll-thin mt-3 max-h-48 space-y-1 overflow-y-auto">
                  {preview.map((d) => (
                    <li key={d.uri} className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-2.5 py-1.5 text-[12.5px]">
                      <span className="truncate text-white/85">{d.title || d.uri}</span>
                      <span className="ml-auto shrink-0 font-mono text-[11px] text-dim">{d.chars.toLocaleString()} chars</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </motion.div>

          <motion.div {...rise(2)}>
            <Panel title={<span className="flex items-center gap-2"><FileUp className="size-4 text-bob-mint" /> Files</span>}>
              <DropZone onFiles={uploads.add} busy={uploads.busy} label="Drop PDF, DOCX, Markdown, HTML, TXT or CSV, or click to choose" accept=".pdf,.docx,.md,.markdown,.html,.htm,.txt,.csv" />
              <FileList files={uploads.files} onRemove={uploads.remove} />
              {uploads.error && <div className="mt-2"><ErrorBanner error={uploads.error} title="Upload failed" /></div>}
            </Panel>
          </motion.div>

          <motion.div {...rise(3)}>
            <Panel title={<span className="flex items-center gap-2"><Plug className="size-4 text-bob-yellow" /> Connected apps</span>}>
              {connectors === null ? (
                <div className="flex items-center gap-2 text-[12.5px] text-dim"><Loader2 className="size-4 animate-spin" /> Loading connectors…</div>
              ) : connectors.length === 0 ? (
                <div className="text-[12.5px] text-dim">No connectors are configured on the server.</div>
              ) : (
                <div className="space-y-2">
                  {connectors.map((c) => (
                    <ConnectorRow
                      key={c.toolkit}
                      c={c}
                      connected={connected[c.toolkit] ?? (c.connected && c.account_id ? { toolkit: c.toolkit, account_id: c.account_id, picked: [] } : undefined)}
                      onConnected={(account) => setConnected((s) => ({ ...s, [c.toolkit]: { toolkit: c.toolkit, account_id: account, picked: [] } }))}
                      onPick={(items) =>
                        setConnected((s) => ({ ...s, [c.toolkit]: { toolkit: c.toolkit, account_id: s[c.toolkit]?.account_id ?? c.account_id ?? "", picked: items } }))
                      }
                    />
                  ))}
                </div>
              )}
            </Panel>
          </motion.div>
        </div>

        <div className="space-y-4">
          <motion.div {...rise(2)}>
            <Panel title="Size and budget">
              <Label>Rows to keep</Label>
              <div className="flex items-center gap-3">
                <input type="range" min={100} max={5000} step={100} value={targetRows} onChange={(e) => setTargetRows(Number(e.target.value))} className="flex-1 accent-[var(--color-bob-blue)]" />
                <input type="number" min={10} value={targetRows} onChange={(e) => setTargetRows(Math.max(10, Number(e.target.value) || 10))} className="w-20 rounded-lg border border-line bg-transparent px-2 py-1 text-right font-mono text-[13px] outline-none" />
              </div>
              <div className="mt-4">
                <Label>Budget (stops new writing at 95%)</Label>
                <div className="flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5">
                  <span className="text-dim">$</span>
                  <input type="number" min={1} step={1} value={budget} onChange={(e) => setBudget(Math.max(1, Number(e.target.value) || 1))} className="w-full bg-transparent font-mono text-[13px] outline-none" />
                </div>
              </div>
            </Panel>
          </motion.div>

          <motion.div {...rise(3)}>
            <Panel title={<span className="flex items-center gap-2"><Sprout className="size-4 text-bob-mint" /> Seed examples <span className="text-[11px] font-normal text-dim">optional</span></span>}>
              <p className="mb-2 text-[12.5px] text-dim">A JSONL or CSV of real examples. Bob uses them for style and tells you which topics they miss.</p>
              {seeds.files.length ? (
                <FileList files={seeds.files.slice(0, 1)} onRemove={seeds.remove} />
              ) : (
                <DropZone onFiles={(f) => seeds.add(f.slice(0, 1))} busy={seeds.busy} label="Drop seeds.jsonl or seeds.csv" accept=".jsonl,.csv" />
              )}
              {seeds.error && <div className="mt-2"><ErrorBanner error={seeds.error} title="Seed upload failed" /></div>}
            </Panel>
          </motion.div>

          <motion.div {...rise(4)} className="rounded-2xl border border-line bg-panel p-4">
            <div className="mb-3 space-y-1 text-[12.5px]">
              {(
                [
                  ["Goal", goal.trim().length > 3],
                  ["At least one source", sources.length > 0],
                ] as [string, boolean][]
              ).map(([l, ok]) => (
                <div key={l} className={`flex items-center gap-2 ${ok ? "text-bob-mint" : "text-dim"}`}>
                  {ok ? <Check className="size-3.5" /> : <X className="size-3.5" />} {l}
                </div>
              ))}
            </div>
            <Button tone="yellow" className="w-full py-2.5 text-[15px]" busy={creating} disabled={!ready} onClick={create}>
              Draft the plan
            </Button>
            <p className="mt-2 text-center text-[11.5px] text-dim">Bob reads everything first. Nothing is generated until you approve the plan.</p>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
