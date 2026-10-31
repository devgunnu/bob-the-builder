import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, CheckCircle2, Loader2, ShieldAlert, XCircle } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { RowEvent } from "../api/types";
import { useJobStream } from "../api/useJobStream";
import { AppShell } from "../components/AppShell";
import type { BobPose } from "../components/Bob";
import { MemeCarousel } from "../components/MemeCarousel";
import { Empty, ErrorBanner, caseLabel, usd } from "../components/ui";
import { Heatgrid, toGridCells } from "../components/viz/Heatgrid";

function topReasons(rows: RowEvent[]): [string, number][] {
  const m = new Map<string, number>();
  rows.filter((r) => r.verdict === "rejected").forEach((r) => {
    const k = (r.reject_reason ?? "unknown").slice(0, 70);
    m.set(k, (m.get(k) ?? 0) + 1);
  });
  return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
}

function RowFeed({ rows, jobId, kept, rejected }: { rows: RowEvent[]; jobId: string; kept: number; rejected: number }) {
  const [filter, setFilter] = useState<"kept" | "rejected">("kept");
  const nav = useNavigate();
  const shown = rows.filter((r) => r.verdict === filter);
  const reasons = filter === "rejected" ? topReasons(rows) : [];
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
        <ul className="scroll-thin max-h-[560px] overflow-y-auto px-1.5 pb-1.5">
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
      )}
    </section>
  );
}

export default function BuildScreen() {
  const { id } = useParams();
  const s = useJobStream(id);
  const [cancelErr, setCancelErr] = useState<ApiError | null>(null);
  const [cheer, setCheer] = useState(false);
  const [filters, setFilters] = useState(false);
  const done = s.status === "done";
  const stopped = s.status === "error" || s.status === "cancelled";

  useEffect(() => {
    if (!done) return;
    setCheer(true);
    const t = window.setTimeout(() => setCheer(false), 4000);
    return () => window.clearTimeout(t);
  }, [done]);

  const pose: BobPose = cheer ? "cheer" : done ? "idle" : "think";
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
  const costTitle = s.cost ? Object.entries(s.cost.by_model).map(([k, m]) => `${k}: ${usd(m.usd)} (${m.calls} calls)`).join("\n") : "";

  return (
    <AppShell pose={pose} title={s.job?.spec.goal}>
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <ErrorBanner error={s.loadError} title="Couldn't load this job" />
        <ErrorBanner error={s.error} title="The build hit an error" />
        <ErrorBanner error={cancelErr} />

        {/* one headline, one bar, one sentence */}
        <section className="rounded-2xl bg-panel p-5">
          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-0 flex-1">
              <div className="font-display text-[34px] font-extrabold leading-none tabular-nums">
                {kept.toLocaleString()} <span className="text-[18px] font-bold text-dim">of {target.toLocaleString()} rows kept</span>
              </div>
              <div className="mt-2 flex items-center gap-2 text-[13px] text-dim">
                {!done && !stopped && <Loader2 className="size-3.5 animate-spin text-bob-sky" />}
                <span className="truncate">{sentence}</span>
              </div>
            </div>
            <div className="text-right" title={costTitle}>
              <div className="font-display text-[22px] font-bold tabular-nums">{usd(spent)}</div>
              <div className="text-[11.5px] text-dim">frontier-only {usd(s.cost?.frontier_only_estimate_usd)}</div>
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
          {fallbacks.length > 0 && (
            <div className="mt-3 flex items-center gap-1.5 text-[12px] text-bob-yellow"><ShieldAlert className="size-3.5" /> Using a fallback: {fallbacks.join(", ")}</div>
          )}
        </section>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <section className="rounded-2xl bg-panel p-4">
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-display text-[16px] font-bold">Coverage</h2>
              {plan && (
                <button onClick={() => setFilters((v) => !v)} className="ml-auto text-[12px] text-dim hover:text-white">
                  {filters ? "Hide filters" : "Filter"}
                </button>
              )}
            </div>
            {plan ? <Heatgrid axes={plan.axes} cells={toGridCells(s.cells)} highlight={highlight} filters={filters} /> : <Empty><MemeCarousel compact /></Empty>}
          </section>
          <RowFeed rows={s.rows} jobId={id!} kept={kept} rejected={s.counts.rejected ?? 0} />
        </div>

        {!done && !stopped && (
          <div className="text-center">
            <button onClick={() => api.cancel(id!).catch(setCancelErr)} className="text-[12.5px] text-dim hover:text-rose-300">Cancel this job</button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
