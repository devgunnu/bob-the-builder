import { useMemo, useState } from "react";
import { motion } from "motion/react";
import type { Axis, Cell } from "../../api/types";
import { CaseHeader, caseLabel } from "../ui";

// Persona and difficulty are mix axes inside each cell (D29); this grid never facets by them.

export interface GridCell {
  coords: Record<string, string>;
  enabled: boolean;
  target: number;
  kept: number;
  generated: number;
  rejected: number;
  judged: number;
  id: string;
}

export function toGridCells(cells: Record<string, Cell> | Cell[]): GridCell[] {
  return (Array.isArray(cells) ? cells : Object.values(cells)).map((c) => ({ ...c }));
}

// Sequential scale: navy -> blue -> mint as kept / target goes 0 -> 1.
function fill(r: number): string {
  const stops = [
    [15, 26, 58],
    [31, 91, 255],
    [99, 240, 207],
  ];
  const t = Math.max(0, Math.min(1, r)) * 2;
  const i = Math.min(1, Math.floor(t));
  const f = t - i;
  const [a, b] = [stops[i], stops[i + 1]];
  const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${c[0]} ${c[1]} ${c[2]})`;
}

interface HeatgridProps {
  axes: Axis[];
  cells: GridCell[];
  highlight?: Set<string>;
  onCellClick?: (topic: string, caseType: string, matches: GridCell[]) => void;
  compact?: boolean;
}

export function Heatgrid({ axes, cells, highlight, onCellClick, compact }: HeatgridProps) {
  const topics = axes.find((a) => a.name === "topic")?.values ?? [];
  const cases = axes.find((a) => a.name === "case_type")?.values ?? [];
  const [hover, setHover] = useState<{ t: string; c: string } | null>(null);

  const agg = useMemo(() => {
    const m = new Map<string, { cells: GridCell[]; target: number; kept: number; generated: number; rejected: number; judged: number; enabled: number; hot: boolean }>();
    for (const c of cells) {
      const k = `${c.coords.topic}|${c.coords.case_type}`;
      const a = m.get(k) ?? { cells: [], target: 0, kept: 0, generated: 0, rejected: 0, judged: 0, enabled: 0, hot: false };
      a.cells.push(c);
      if (c.enabled) {
        a.enabled++;
        a.target += c.target;
        a.kept += c.kept;
        a.generated += c.generated;
        a.rejected += c.rejected;
        a.judged += c.judged;
      }
      if (highlight?.has(c.id)) a.hot = true;
      m.set(k, a);
    }
    return m;
  }, [cells, highlight]);

  if (!topics.length || !cases.length) return null;
  const h = hover ? agg.get(`${hover.t}|${hover.c}`) : undefined;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <div className="ml-auto flex items-center gap-1.5 text-[10.5px] text-dim">
          0%
          <span className="h-2 w-20 rounded-full" style={{ background: `linear-gradient(90deg, ${fill(0)}, ${fill(0.5)}, ${fill(1)})` }} />
          100% of target
        </div>
      </div>
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full min-w-[480px] table-fixed border-separate" style={{ borderSpacing: compact ? 3 : 4 }}>
          <colgroup>
            <col className="w-[34%] sm:w-[26%]" />
          </colgroup>
          <thead>
            <tr>
              <th />
              {cases.map((c) => (
                <th key={c} className="px-1 pb-1 text-left text-[11.5px] font-medium text-white/70">
                  <CaseHeader c={c} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {topics.map((t) => (
              <tr key={t}>
                <th className="max-w-[180px] truncate pr-2 text-left text-[12px] font-medium text-white/80" title={t}>
                  {t}
                </th>
                {cases.map((c) => {
                  const a = agg.get(`${t}|${c}`);
                  const disabled = !a || a.enabled === 0;
                  const ratio = a && a.target ? a.kept / a.target : 0;
                  return (
                    <td key={c} className="p-0">
                      <motion.button
                        type="button"
                        onMouseEnter={() => setHover({ t, c })}
                        onMouseLeave={() => setHover(null)}
                        onFocus={() => setHover({ t, c })}
                        onClick={() => a && onCellClick?.(t, c, a.cells)}
                        aria-label={`${t}, ${caseLabel(c)}: ${disabled ? "off" : `${a?.kept} of ${a?.target} kept`}`}
                        animate={{ backgroundColor: disabled ? "rgba(255,255,255,0.02)" : fill(ratio) }}
                        transition={{ duration: 0.5 }}
                        className={`relative flex w-full items-center justify-center rounded-lg font-mono text-[11px] ${compact ? "h-7" : "h-9"} ${
                          disabled ? "bg-[repeating-linear-gradient(45deg,rgba(255,255,255,0.04)_0_4px,transparent_4px_8px)] text-dim" : ratio > 0.55 ? "text-bob-navy" : "text-white/85"
                        } ${a?.hot ? "ring-2 ring-bob-yellow ring-offset-1 ring-offset-panel" : ""} ${onCellClick ? "cursor-pointer" : "cursor-default"}`}
                      >
                        {disabled ? "off" : `${a?.kept}/${a?.target}`}
                      </motion.button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 h-5 text-[11.5px] text-dim" aria-live="polite">
        {hover && h ? (
          <>
            <span className="text-white/85">{hover.t} · {caseLabel(hover.c)}</span>
            {h.enabled ? ` · generated ${h.generated} · kept ${h.kept} · rejected ${h.rejected} · judged ${h.judged} · target ${h.target}` : " · turned off"}
            {h.hot && <span className="text-bob-yellow"> · in this gap round</span>}
          </>
        ) : (
          ""
        )}
      </div>
    </div>
  );
}
