import { motion } from "motion/react";
import { Check } from "lucide-react";
import { STAGES, type StageId, type Stats } from "../../lib/types";
import type { StageView } from "../../lib/useJob";

export function StageRail({ stages }: { stages: Record<StageId, StageView> }) {
  const current = STAGES.find((s) => stages[s.id].state === "active");
  const allDone = STAGES.every((s) => stages[s.id].state === "done");
  return (
    <div>
      <div className="grid grid-cols-8 gap-1.5">
        {STAGES.map((s, i) => {
          const v = stages[s.id];
          const active = v.state === "active";
          const done = v.state === "done";
          return (
            <div
              key={s.id}
              title={s.hint}
              className={`relative min-w-0 rounded-xl border px-2 py-2 transition-colors ${
                active ? "border-bob-sky/60 bg-bob-blue/10" : done ? "border-bob-mint/25 bg-bob-mint/[0.04]" : "border-line bg-white/[0.015]"
              }`}
            >
              {active && <div className="absolute inset-0 animate-pulse rounded-xl shadow-[0_0_22px_-6px] shadow-bob-blue" />}
              <div className="relative flex items-center gap-1.5">
                <span
                  className={`grid size-4 shrink-0 place-items-center rounded-full text-[9px] font-bold ${
                    done ? "bg-bob-mint text-bob-navy" : active ? "bg-bob-blue text-white" : "bg-white/10 text-dim"
                  }`}
                >
                  {done ? <Check className="size-3" /> : i + 1}
                </span>
                <div className="h-0.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <motion.div
                    className={`h-full ${done ? "bg-bob-mint/70" : "bg-bob-sky"}`}
                    animate={{ width: done ? "100%" : active ? `${Math.max(8, (v.progress ?? 0.35) * 100)}%` : "0%" }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
              </div>
              <div className={`relative mt-1.5 truncate text-[12px] font-medium ${done || active ? "text-white" : "text-dim"}`}>{s.label}</div>
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 h-4 truncate px-1 text-[11.5px] text-dim">
        {allDone ? "All stages complete." : current ? <><span className="text-white/80">{current.label}:</span> {current.hint.toLowerCase()}…</> : "Waiting for your go-ahead."}
      </div>
    </div>
  );
}

function Tile({ label, value, sub, tone = "white" }: { label: string; value: string; sub?: string; tone?: "white" | "mint" | "rose" | "yellow" }) {
  const tones = { white: "text-white", mint: "text-bob-mint", rose: "text-rose-300", yellow: "text-bob-yellow" };
  return (
    <div className="rounded-xl border border-line bg-panel px-3 py-2.5">
      <div className="text-[11px] text-dim">{label}</div>
      <div className={`font-display text-[22px] font-bold leading-tight tabular-nums ${tones[tone]}`}>{value}</div>
      {sub && <div className="text-[10.5px] text-dim">{sub}</div>}
    </div>
  );
}

export function StatTiles({ stats }: { stats: Stats }) {
  const rejPct = stats.generated ? Math.round((stats.rejected / stats.generated) * 100) : 0;
  const mult = stats.costUsd > 0 ? Math.round(stats.baselineUsd / stats.costUsd) : 0;
  return (
    <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
      <Tile label="Verified rows" value={stats.verified.toLocaleString()} sub={`${stats.generated.toLocaleString()} generated`} tone="mint" />
      <Tile label="Rejected" value={stats.rejected.toLocaleString()} sub={`${rejPct}% failed a check`} tone="rose" />
      <Tile label="Spent" value={`$${stats.costUsd.toFixed(3)}`} sub="Writer + verification" />
      <Tile label="Frontier-only estimate" value={`$${stats.baselineUsd.toFixed(2)}`} sub={mult ? `${mult}x more` : "same rows, one big model"} tone="yellow" />
    </div>
  );
}
