import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, CheckCircle2, Gavel, Loader2, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { RowEvent } from "../api/types";
import { useJobStream } from "../api/useJobStream";
import { AppShell } from "../components/AppShell";
import type { BobPose } from "../components/Bob";
import { MemeCarousel } from "../components/MemeCarousel";
import { Button, Empty, ErrorBanner, Panel, caseLabel, usd } from "../components/ui";
import { Heatgrid, toGridCells } from "../components/viz/Heatgrid";

function Counter({ label, value, tone = "text-white" }: { label: string; value: number | undefined; tone?: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel px-3 py-2.5">
      <div className="text-[11px] text-dim">{label}</div>
      <motion.div key={value} initial={{ opacity: 0.4, y: -3 }} animate={{ opacity: 1, y: 0 }} className={`font-display text-[22px] font-bold tabular-nums ${tone}`}>
        {(value ?? 0).toLocaleString()}
      </motion.div>
    </div>
  );
}

function RowFeed({ rows, jobId }: { rows: RowEvent[]; jobId: string }) {
  const [filter, setFilter] = useState<"all" | "kept" | "rejected">("all");
  const nav = useNavigate();
  const shown = filter === "all" ? rows : rows.filter((r) => r.verdict === filter);
  return (
    <Panel
      className="flex min-h-0 flex-col"
      title="Rows"
      action={
        <div className="flex gap-1">
          {(["all", "kept", "rejected"] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={`rounded-lg px-2.5 py-1 text-[12px] capitalize ${filter === f ? "bg-white/10 text-white" : "text-dim hover:text-white"}`}>
              {f}
            </button>
          ))}
        </div>
      }
    >
      {shown.length === 0 ? (
        <Empty>Rows appear here as they're verified.</Empty>
      ) : (
        <ul className="scroll-thin -m-2 max-h-[520px] overflow-y-auto">
          <AnimatePresence initial={false}>
            {shown.map((r) => (
              <motion.li
                key={r.id}
                initial={{ opacity: 0, y: -8, backgroundColor: r.verdict === "kept" ? "rgba(99,240,207,0.10)" : "rgba(251,113,133,0.12)" }}
                animate={{ opacity: 1, y: 0, backgroundColor: "rgba(0,0,0,0)" }}
                transition={{ duration: 0.45 }}
                className="rounded-xl"
              >
                <button onClick={() => nav(`/jobs/${jobId}/rows/${r.id}`)} className="flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left hover:bg-white/[0.04]">
                  {r.verdict === "kept" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-bob-mint" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-rose-400" />}
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-[13px] ${r.verdict === "rejected" ? "text-white/55" : "text-white/90"}`}>{r.user_preview}</span>
                    <span className="mt-0.5 flex items-center gap-2 text-[10.5px] text-dim">
                      <span className="rounded bg-white/[0.06] px-1.5 py-px capitalize">{caseLabel(r.case_type)}</span>
                      <span className="font-mono">conf {r.confidence.toFixed(2)}</span>
                      {r.routed_to_judge && <span className="flex items-center gap-0.5 text-bob-yellow"><Gavel className="size-3" /> judged</span>}
                      {r.reject_reason && <span className="truncate text-rose-300/85">{r.reject_reason}</span>}
                    </span>
                  </span>
                </button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </Panel>
  );
}

function RejectSummary({ rows }: { rows: RowEvent[] }) {
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    rows.filter((r) => r.verdict === "rejected").forEach((r) => {
      const k = (r.reject_reason ?? "unknown").split(":")[0].slice(0, 60);
      m.set(k, (m.get(k) ?? 0) + 1);
    });
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  }, [rows]);
  const max = counts[0]?.[1] ?? 1;
  return (
    <Panel title="Why rows were rejected" action={<span className="text-[11px] text-dim">last {rows.length} rows</span>}>
      {counts.length === 0 ? (
        <div className="text-[12.5px] text-dim">Nothing rejected yet.</div>
      ) : (
        <ul className="space-y-2">
          {counts.map(([k, n]) => (
            <li key={k}>
              <div className="flex justify-between text-[12px]"><span className="truncate text-white/85">{k}</span><span className="font-mono text-dim">{n}</span></div>
              <div className="mt-1 h-1 rounded-full bg-white/5"><div className="h-full rounded-full bg-rose-400/70" style={{ width: `${(n / max) * 100}%` }} /></div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export default function BuildScreen() {
  const { id } = useParams();
  const s = useJobStream(id);
  const [cancelErr, setCancelErr] = useState<ApiError | null>(null);
  const [cheer, setCheer] = useState(false);
  const done = s.status === "done";

  useEffect(() => {
    if (!done) return;
    setCheer(true);
    const t = window.setTimeout(() => setCheer(false), 4000);
    return () => window.clearTimeout(t);
  }, [done]);

  const pose: BobPose = cheer ? "cheer" : s.status === "error" ? "think" : ["building", "filling_gaps", "reporting"].includes(s.status ?? "") ? "think" : "idle";
  const plan = s.plan;
  const highlight = useMemo(() => new Set(s.round?.cells ?? []), [s.round]);
  const budget = s.job?.spec.budget_usd ?? 0;
  const spent = s.cost?.total_usd ?? 0;
  const fallbacks = s.cost?.fallbacks_used ?? [];
  const stageLine = s.lastStage && s.stages[s.lastStage];

  return (
    <AppShell pose={pose} title={s.job?.spec.goal}>
      <div className="mx-auto max-w-7xl space-y-3 px-4 py-4">
        <ErrorBanner error={s.loadError} title="Couldn't load this job" />
        <ErrorBanner error={s.error} title="The build hit an error" />
        <ErrorBanner error={cancelErr} />

        {/* status line */}
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-panel px-4 py-3">
          {done ? <CheckCircle2 className="size-5 text-bob-mint" /> : <Loader2 className="size-5 animate-spin text-bob-sky" />}
          <div className="min-w-0">
            <div className="text-[14px] font-medium capitalize">{(s.status ?? "connecting").replace(/_/g, " ")}{s.job && s.job.round > 0 ? ` · round ${s.round?.n ?? s.job.round}` : s.round ? ` · round ${s.round.n}` : ""}</div>
            <div className="truncate text-[12px] text-dim">
              {stageLine ? `${s.lastStage}: ${stageLine.done}/${stageLine.total}${stageLine.detail ? ` · ${stageLine.detail}` : ""}` : s.detail}
            </div>
          </div>
          {fallbacks.length > 0 && (
            <span title={fallbacks.join(", ")} className="flex items-center gap-1 rounded-full border border-bob-yellow/30 bg-bob-yellow/10 px-2.5 py-1 text-[11px] text-bob-yellow">
              <ShieldAlert className="size-3.5" /> fallback in use: {fallbacks.join(", ")}
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            {!done && s.status !== "error" && s.status !== "cancelled" && (
              <Button tone="danger" className="!px-3 !py-1.5 text-[12px]" onClick={() => api.cancel(id!).catch(setCancelErr)}>Cancel</Button>
            )}
            {(s.report || done) && (
              <Link to={`/jobs/${id}/report`} className="flex items-center gap-1.5 rounded-xl bg-bob-yellow px-3.5 py-1.5 font-display text-[14px] font-bold text-bob-navy">
                Open report <ArrowRight className="size-4" />
              </Link>
            )}
          </div>
        </div>

        <AnimatePresence>
          {s.round && s.round.n > 1 && (
            <motion.div key={s.round.n} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex items-center gap-2 rounded-xl border border-bob-yellow/30 bg-bob-yellow/10 px-4 py-2 text-[13px] text-bob-yellow">
              <RefreshCw className="size-4" />
              Round {s.round.n}: {s.round.reason} · {s.round.cells.length} cells · {s.round.planned} rows planned
            </motion.div>
          )}
        </AnimatePresence>

        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <Counter label="Generated" value={s.counts.candidates} />
          <Counter label="Kept" value={s.counts.kept} tone="text-bob-mint" />
          <Counter label="Rejected" value={s.counts.rejected} tone="text-rose-300" />
          <Counter label="Sent to judge" value={s.counts.judged} tone="text-bob-yellow" />
          <Counter label="Duplicates" value={s.counts.duplicates} tone="text-dim" />
        </div>

        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
          <Panel title="Coverage map" action={<span className="text-[11px] text-dim">kept / target per cell</span>}>
            {plan ? <Heatgrid axes={plan.axes} cells={toGridCells(s.cells)} highlight={highlight} /> : <Empty><MemeCarousel compact /></Empty>}
          </Panel>
          <div className="space-y-3">
            <Panel title="Cost">
              <div className="flex items-baseline gap-2">
                <span className="font-display text-[26px] font-bold tabular-nums">{usd(spent)}</span>
                <span className="text-[12px] text-dim">of {usd(budget, 2)}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5">
                <motion.div className={`h-full ${spent > budget * 0.9 ? "bg-bob-yellow" : "bg-bob-mint"}`} animate={{ width: `${budget ? Math.min(100, (spent / budget) * 100) : 0}%` }} />
              </div>
              <div className="mt-3 flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2 text-[12px]">
                <span className="text-dim">Frontier model writing and judging everything</span>
                <span className="font-mono text-bob-yellow">{usd(s.cost?.frontier_only_estimate_usd)}</span>
              </div>
              {s.cost && Object.keys(s.cost.by_model).length > 0 && (
                <ul className="mt-3 space-y-1 text-[11.5px]">
                  {Object.entries(s.cost.by_model).map(([k, m]) => (
                    <li key={k} className="flex justify-between text-dim"><span>{k} · {m.calls} calls</span><span className="font-mono">{usd(m.usd)}</span></li>
                  ))}
                </ul>
              )}
            </Panel>
            <RejectSummary rows={s.rows} />
          </div>
        </div>

        <RowFeed rows={s.rows} jobId={id!} />
      </div>
    </AppShell>
  );
}
