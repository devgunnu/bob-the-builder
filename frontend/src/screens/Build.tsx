import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, CheckCircle2, Loader2, ShieldAlert, X, XCircle } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { CostSummary, Job, Row, RowEvent } from "../api/types";
import { useJobStream } from "../api/useJobStream";
import { AppShell } from "../components/AppShell";
import { Bob, type BobPose } from "../components/Bob";
import { ConfirmButton, Empty, ErrorBanner, caseLabel, usd, useTitle } from "../components/ui";
import { Heatgrid, toGridCells } from "../components/viz/Heatgrid";

// Time left from the recent rate of kept rows (visibility of system status).
function useEta(kept: number, target: number, finished: boolean): string | null {
  const samples = useRef<{ t: number; k: number }[]>([]);
  const now = Date.now();
  const list = samples.current;
  if (!list.length || list[list.length - 1].k !== kept) list.push({ t: now, k: kept });
  while (list.length > 2 && now - list[0].t > 90_000) list.shift();
  if (finished || list.length < 3 || kept >= target) return null;
  const first = list[0];
  const rate = (kept - first.k) / ((now - first.t) / 1000);
  if (rate <= 0) return null;
  const secs = (target - kept) / rate;
  if (secs < 60) return "under a minute left";
  return `about ${Math.round(secs / 60)} min left`;
}

const LLM_ROLES = new Set(["writer", "planner", "judge", "fallback"]);

function buildPose(stage: string | null, done: boolean, stopped: boolean): BobPose {
  if (done) return "hero";
  if (stopped) return "idle";
  if (stage === "generate") return "type";
  if (stage === "verify") return "stamp";
  if (stage === "export") return "carry";
  return "think";
}

// Cost per role, with the model id, "billed to your AWS account" for Bedrock roles and unknown-price badges.
function CostDetails({ cost, job }: { cost: CostSummary; job: Job | null }) {
  const roles = Object.keys(cost.by_model).sort((a, b) => Number(LLM_ROLES.has(b)) - Number(LLM_ROLES.has(a)));
  const provider = (r: string) => (job?.models as unknown as Record<string, { provider?: string } | null> | undefined)?.[r]?.provider ?? "bedrock";
  return (
    <ul className="mt-4 grid gap-1.5 border-t border-line pt-3 text-[12px] sm:grid-cols-2">
      {roles.map((r) => {
        const m = cost.by_model[r];
        const bedrock = LLM_ROLES.has(r) && provider(r) === "bedrock";
        return (
          <li key={r} className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-3 py-1.5">
            <span className="w-16 shrink-0 capitalize text-white/85">{r}</span>
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-dim" title={cost.model_ids[r]}>{cost.model_ids[r] ?? `${m.calls} calls`}</span>
            {cost.price_unknown.includes(r) ? (
              <span className="rounded bg-bob-yellow/10 px-1.5 text-[10.5px] text-bob-yellow">price unknown</span>
            ) : (
              <span className="font-mono text-white/80">{usd(m.usd)}</span>
            )}
            {bedrock && <span className="text-[10.5px] text-dim" title="Billed to your AWS account">AWS</span>}
          </li>
        );
      })}
      <li className="text-[11px] text-dim sm:col-span-2">Rows marked AWS run on Bedrock and are billed to your AWS account.</li>
    </ul>
  );
}

function topReasons(rows: RowEvent[]): [string, number][] {
  const m = new Map<string, number>();
  rows.filter((r) => r.verdict === "rejected").forEach((r) => {
    const k = (r.reject_reason ?? "unknown").slice(0, 70);
    m.set(k, (m.get(k) ?? 0) + 1);
  });
  return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
}

function rowEvent(row: Row): RowEvent {
  return {
    id: row.id,
    cell_id: row.cell_id,
    verdict: row.verdict,
    reject_reason: row.reject_reason,
    case_type: row.case_type,
    user_preview: row.messages.find((message) => message.role === "user")?.content ?? "",
    confidence: row.confidence,
    routed_to_judge: row.routed_to_judge,
  };
}

function RowFeed({ rows, jobId, kept, rejected }: { rows: RowEvent[]; jobId: string; kept: number; rejected: number }) {
  const [filter, setFilter] = useState<"kept" | "rejected">("kept");
  const [older, setOlder] = useState<RowEvent[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlder, setHasOlder] = useState(true);
  const [olderError, setOlderError] = useState<ApiError | null>(null);
  const nav = useNavigate();
  const recent = rows.filter((r) => r.verdict === filter);
  const recentIds = new Set(rows.map((row) => row.id));
  const shown = [...recent, ...older.filter((row) => !recentIds.has(row.id))];
  const reasons = filter === "rejected" ? topReasons(rows) : [];

  useEffect(() => {
    setOlder([]);
    setHasOlder(true);
    setOlderError(null);
  }, [filter]);

  const loadOlder = async () => {
    setLoadingOlder(true);
    setOlderError(null);
    try {
      const page = await api.rows(jobId, { verdict: filter, offset: recent.length + older.length, limit: 100 });
      const known = new Set([...rows, ...older].map((row) => row.id));
      const additions = page.rows.map(rowEvent).filter((row) => !known.has(row.id));
      setOlder((current) => [...current, ...additions]);
      setHasOlder(recent.length + older.length + page.rows.length < page.total);
    } catch (error) {
      setOlderError(error as ApiError);
    } finally {
      setLoadingOlder(false);
    }
  };
  return (
    <section className="flex min-h-0 flex-col rounded-2xl bg-panel">
      <div className="flex gap-1 p-1.5" role="tablist">
        {(
          [
            ["kept", `Kept ${kept.toLocaleString()}`],
            ["rejected", `Rejected ${rejected.toLocaleString()}`],
          ] as const
        ).map(([f, label]) => (
          <button
            key={f}
            role="tab"
            aria-selected={filter === f}
            onClick={() => setFilter(f)}
            className={`flex-1 rounded-xl py-2 text-[13px] transition ${filter === f ? "bg-white/[0.08] text-white" : "text-dim hover:text-white"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {reasons.length > 0 && (
        <div className="space-y-1 px-4 pb-2 pt-1">
          <div className="text-[11px] text-dim">Most common reasons</div>
          {reasons.map(([k, n]) => (
            <div key={k} className="flex gap-2 text-[12px]"><span className="truncate text-rose-200/90">{k}</span><span className="ml-auto font-mono text-dim">{n}</span></div>
          ))}
        </div>
      )}
      {shown.length === 0 ? (
        <Empty>{filter === "kept" ? "Verified rows appear here." : "Nothing rejected yet."}</Empty>
      ) : (
        <div className="scroll-thin max-h-[560px] overflow-y-auto px-1.5 pb-1.5">
          <ul>
            <AnimatePresence initial={false}>
              {shown.map((r) => (
                <motion.li
                  key={r.id}
                  initial={{ opacity: 0, y: -8, backgroundColor: r.verdict === "kept" ? "rgba(99,240,207,0.10)" : "rgba(251,113,133,0.12)" }}
                  animate={{ opacity: 1, y: 0, backgroundColor: "rgba(0,0,0,0)" }}
                  transition={{ duration: 0.45 }}
                  className="rounded-xl"
                >
                  <button onClick={() => nav(`/jobs/${jobId}/rows/${r.id}`)} className="flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2.5 text-left hover:bg-white/[0.04]">
                    {r.verdict === "kept" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-bob-mint" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-rose-400" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] text-white/90">{r.user_preview}</span>
                      <span className="mt-0.5 block truncate text-[11.5px] text-dim">
                        {caseLabel(r.case_type)}
                        {r.routed_to_judge && " · checked by the judge"}
                        {r.reject_reason && <span className="text-rose-300/85"> · {r.reject_reason}</span>}
                      </span>
                    </span>
                  </button>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
          {hasOlder && (
            <button onClick={() => void loadOlder()} disabled={loadingOlder} className="mx-auto my-2 block rounded-lg px-3 py-1.5 text-[12px] text-dim hover:bg-white/[0.05] hover:text-white disabled:opacity-50">
              {loadingOlder ? "Loading older rows…" : "Load older rows"}
            </button>
          )}
          {olderError && <div className="px-2 pb-2"><ErrorBanner error={olderError} /></div>}
        </div>
      )}
    </section>
  );
}

function CellDrawer({ jobId, cellId, label, onClose }: { jobId: string; cellId: string; label: string; onClose: () => void }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    setError(null);
    api
      .rows(jobId, { cell_id: cellId, limit: 100 })
      .then((page) => {
        if (!controller.signal.aborted) {
          setRows(page.rows);
          setTotal(page.total);
        }
      })
      .catch((requestError) => !controller.signal.aborted && setError(requestError as ApiError));
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      controller.abort();
      window.removeEventListener("keydown", onKey);
    };
  }, [cellId, jobId, onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/45" onMouseDown={onClose}>
      <aside role="dialog" aria-modal="true" aria-label={`${label} rows`} className="flex h-full w-full max-w-md flex-col border-l border-line bg-panel shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] text-dim">Rows in this cell</p>
            <h2 className="truncate font-display text-[18px] font-bold">{label}</h2>
          </div>
          <button onClick={onClose} aria-label="Close rows" className="grid size-8 shrink-0 place-items-center rounded-lg text-dim hover:bg-white/[0.06] hover:text-white">
            <X className="size-4" />
          </button>
        </div>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-3">
          {error && <ErrorBanner error={error} />}
          {!rows && !error && <div className="grid h-28 place-items-center text-dim"><Loader2 className="size-5 animate-spin" /></div>}
          {rows?.length === 0 && <Empty>No rows in this cell yet.</Empty>}
          {rows && rows.length > 0 && (
            <>
              <p className="mb-2 px-2 text-[11px] text-dim">{total.toLocaleString()} rows</p>
              <ul className="space-y-1">
                {rows.map((row) => {
                  const preview = row.messages.find((message) => message.role === "user")?.content ?? "";
                  return (
                    <li key={row.id}>
                      <Link to={`/jobs/${jobId}/rows/${row.id}`} onClick={onClose} className="block rounded-xl px-3 py-2.5 hover:bg-white/[0.05]">
                        <span className="block truncate text-[13px] text-white/90">{preview}</span>
                        <span className={`mt-0.5 block text-[11.5px] ${row.verdict === "kept" ? "text-bob-mint" : "text-rose-300"}`}>{row.verdict === "kept" ? "Kept" : row.reject_reason ?? "Rejected"}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
              {total > rows.length && <p className="mt-3 px-2 text-[11px] text-dim">Showing the newest {rows.length.toLocaleString()} rows.</p>}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

export default function BuildScreen() {
  const { id } = useParams();
  const s = useJobStream(id);
  const [cancelErr, setCancelErr] = useState<ApiError | null>(null);
  const [cheer, setCheer] = useState(false);
  const [drawerCell, setDrawerCell] = useState<{ id: string; label: string } | null>(null);
  const done = s.status === "done";
  const stopped = s.status === "error" || s.status === "cancelled";

  useEffect(() => {
    if (!done) return;
    setCheer(true);
    const t = window.setTimeout(() => setCheer(false), 4000);
    return () => window.clearTimeout(t);
  }, [done]);

  const pose: BobPose = cheer ? "cheer" : buildPose(s.lastStage, done, stopped);
  const plan = s.plan;
  const highlight = useMemo(() => new Set(s.round?.cells ?? []), [s.round]);
  const kept = s.counts.kept ?? 0;
  const target = plan?.target_rows ?? s.job?.spec.target_rows ?? 0;
  const spent = s.cost?.total_usd ?? 0;
  const fallbacks = s.cost?.fallbacks_used ?? [];
  const stage = s.lastStage && s.stages[s.lastStage];
  const sentence = done
    ? "All done. Every kept row passed its checks."
    : stopped
      ? `Stopped: ${s.status}.`
      : s.round && s.round.n > 1
        ? `Round ${s.round.n}: filling ${s.round.cells.length} cells that need more rows.`
        : stage
          ? `${s.lastStage === "verify" ? "Checking rows" : s.lastStage === "generate" ? "Writing rows" : `Working on ${s.lastStage}`}${stage.detail ? ` · ${stage.detail}` : ""}`
          : s.detail || "Starting…";
  const eta = useEta(kept, target, done || stopped);
  useTitle(done ? "Build done" : `Building ${kept}/${target}`);
  const [costOpen, setCostOpen] = useState(false);
  const ids = s.cost?.model_ids ?? {};
  const judgeIsWriter = !!ids.judge && ids.judge === ids.writer;

  return (
    <AppShell pose={pose} title={s.job?.spec.goal} step="build" status={s.status} hasReport={!!s.report}>
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <ErrorBanner error={s.loadError} title="Couldn't load this job" />
        <ErrorBanner error={s.error} title="The build hit an error" />
        <ErrorBanner error={cancelErr} />

        {/* one headline, one bar, one sentence */}
        <section className="rounded-2xl bg-panel p-5">
          <div className="flex flex-wrap items-center gap-4">
            <Bob pose={pose} size={64} float={false} still className="hidden shrink-0 sm:block" />
            <div className="min-w-0 flex-1">
              <div className="font-display text-[34px] font-extrabold leading-none tabular-nums">
                {kept.toLocaleString()} <span className="text-[18px] font-bold text-dim">of {target.toLocaleString()} rows kept</span>
              </div>
              <div className="mt-2 flex items-center gap-2 text-[13px] text-dim">
                {!done && !stopped && <Loader2 className="size-3.5 animate-spin text-bob-sky" />}
                <span className="truncate">{sentence}</span>
                {eta && <span className="shrink-0 text-white/60">· {eta}</span>}
              </div>
            </div>
            <div className="text-right">
              <div className="font-display text-[22px] font-bold tabular-nums">{usd(spent)}</div>
              <button onClick={() => setCostOpen((v) => !v)} aria-expanded={costOpen} className="text-[11.5px] text-dim hover:text-white">
                frontier-only {usd(s.cost?.frontier_only_estimate_usd)} · {costOpen ? "hide" : "details"}
              </button>
            </div>
            {done || s.report ? (
              <Link to={`/jobs/${id}/report`} className="flex items-center gap-1.5 rounded-xl bg-bob-yellow px-4 py-2.5 font-display text-[15px] font-bold text-bob-navy">
                See the report <ArrowRight className="size-4" />
              </Link>
            ) : null}
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/[0.06]">
            <motion.div className="h-full rounded-full bg-gradient-to-r from-bob-blue to-bob-mint" animate={{ width: `${target ? Math.min(100, (kept / target) * 100) : 0}%` }} transition={{ duration: 0.6 }} />
          </div>
          {costOpen && s.cost && <CostDetails cost={s.cost} job={s.job} />}
          {judgeIsWriter && (
            <div className="mt-3 flex items-center gap-1.5 text-[12px] text-bob-yellow"><ShieldAlert className="size-3.5" /> The judge uses the same model as the writer, so it may miss the writer's own mistakes.</div>
          )}
          {fallbacks.length > 0 && (
            <div className="mt-3 flex items-center gap-1.5 text-[12px] text-bob-yellow"><ShieldAlert className="size-3.5" /> Using a fallback: {fallbacks.join(", ")}</div>
          )}
        </section>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <section className="rounded-2xl bg-panel p-4">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-display text-[16px] font-bold">Coverage</h2>

            </div>
            {plan ? (
              <Heatgrid
                axes={plan.axes}
                cells={toGridCells(s.cells)}
                highlight={highlight}
                onCellClick={(topic, caseType, matches) => {
                  const cell = matches[0];
                  if (cell) setDrawerCell({ id: cell.id, label: `${topic} · ${caseLabel(caseType)}` });
                }}
              />
            ) : <Empty>The coverage map appears once the plan is approved.</Empty>}
          </section>
          <RowFeed rows={s.rows} jobId={id!} kept={kept} rejected={s.counts.rejected ?? 0} />
        </div>

        {!done && !stopped && (
          <div className="text-center">
            <ConfirmButton label="Cancel this job" confirm="Stop building? Rows kept so far stay saved." onConfirm={() => api.cancel(id!).catch(setCancelErr)} />
          </div>
        )}
      </div>
      {drawerCell && <CellDrawer jobId={id!} cellId={drawerCell.id} label={drawerCell.label} onClose={() => setDrawerCell(null)} />}
    </AppShell>
  );
}
