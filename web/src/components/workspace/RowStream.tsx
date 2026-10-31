import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, XCircle } from "lucide-react";
import type { Row } from "../../lib/types";

export const GEN_COLORS: Record<string, string> = {
  capacity_planner: "bg-bob-blue/20 text-bob-sky",
  memory_math: "bg-bob-mint/15 text-bob-mint",
  compare_methods: "bg-violet-400/15 text-violet-300",
  abstain_unknown: "bg-bob-yellow/15 text-bob-yellow",
  false_premise: "bg-orange-400/15 text-orange-300",
  constrained: "bg-pink-400/15 text-pink-300",
  preference_pairs: "bg-cyan-400/15 text-cyan-300",
};

type Filter = "all" | "verified" | "rejected";
const SHOW = 120;

export function RowStream({ rows, selected, onSelect }: { rows: Row[]; selected?: string; onSelect: (r: Row) => void }) {
  const [filter, setFilter] = useState<Filter>("all");
  const visible = useMemo(() => {
    const out: Row[] = [];
    for (let i = rows.length - 1; i >= 0 && out.length < SHOW; i--) {
      if (filter === "all" || rows[i].status === filter) out.push(rows[i]);
    }
    return out;
  }, [rows, filter]);

  return (
    <div className="flex h-full min-h-0 flex-col rounded-2xl border border-line bg-panel">
      <div className="flex items-center gap-1 border-b border-line px-3 py-2">
        <span className="mr-auto font-display text-[15px] font-bold text-white">Rows</span>
        {(["all", "verified", "rejected"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-lg px-2.5 py-1 text-[12px] capitalize transition ${filter === f ? "bg-white/10 text-white" : "text-dim hover:text-white"}`}
          >
            {f}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <div className="grid flex-1 place-items-center p-6 text-center text-[13px] text-dim">Rows stream in here once you approve the plan.</div>
      ) : (
        <ul className="scroll-thin min-h-0 flex-1 overflow-y-auto p-2">
          <AnimatePresence initial={false}>
            {visible.map((r) => (
              <motion.li
                key={r.id}
                layout="position"
                initial={{ opacity: 0, y: -10, backgroundColor: r.status === "verified" ? "rgba(99,240,207,0.12)" : "rgba(251,113,133,0.14)" }}
                animate={{ opacity: 1, y: 0, backgroundColor: "rgba(0,0,0,0)" }}
                transition={{ duration: 0.5 }}
                className="rounded-xl"
              >
                <button
                  onClick={() => onSelect(r)}
                  className={`flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left transition hover:bg-white/[0.04] ${
                    selected === r.id ? "bg-white/[0.06] ring-1 ring-bob-sky/50" : ""
                  }`}
                >
                  {r.status === "verified" ? (
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-bob-mint" />
                  ) : (
                    <XCircle className="mt-0.5 size-4 shrink-0 text-rose-400" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-[13px] ${r.status === "rejected" ? "text-white/50 line-through decoration-rose-400/50" : "text-white/90"}`}>
                      {r.prompt}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1.5">
                      <span className={`rounded-md px-1.5 py-px font-mono text-[10px] ${GEN_COLORS[r.generator] ?? "bg-white/10 text-white/70"}`}>{r.generator}</span>
                      <span className="text-[10.5px] text-dim">{r.persona}</span>
                      {r.kind === "dpo" && <span className="text-[10.5px] text-cyan-300">pair</span>}
                      {r.rejectReason && <span className="truncate text-[10.5px] text-rose-300/80">{r.rejectReason}</span>}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-dim">#{r.id.slice(1)}</span>
                </button>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </div>
  );
}
