import { motion } from "motion/react";

export function Bars({ data, format = (v) => String(v), max, tone = "bg-bob-mint" }: { data: [string, number][]; format?: (v: number) => string; max?: number; tone?: string }) {
  const m = max ?? Math.max(1, ...data.map((d) => d[1]));
  if (!data.length) return <div className="text-[12.5px] text-dim">No data yet.</div>;
  return (
    <ul className="space-y-2">
      {data.map(([k, v]) => (
        <li key={k}>
          <div className="flex justify-between gap-3 text-[12px]">
            <span className="truncate text-white/85">{k}</span>
            <span className="shrink-0 font-mono text-dim">{format(v)}</span>
          </div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/5">
            <motion.div className={`h-full rounded-full ${tone}`} initial={{ width: 0 }} animate={{ width: `${(v / m) * 100}%` }} transition={{ duration: 0.8, ease: "easeOut" }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
