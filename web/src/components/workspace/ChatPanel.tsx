import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, FileText, Globe, Hammer, Sheet, Sparkles } from "lucide-react";
import type { Capability, ChatMessage, SourceDoc, Stats } from "../../lib/types";
import { Bob, type BobPose } from "../Bob";

const usd = (n: number) => `$${n < 1 ? n.toFixed(3) : n.toFixed(2)}`;

function SourceIcon({ kind }: { kind: SourceDoc["kind"] }) {
  if (kind === "url") return <Globe className="size-4 text-bob-sky" />;
  if (kind === "csv") return <Sheet className="size-4 text-bob-mint" />;
  return <FileText className="size-4 text-rose-300" />;
}

function SourcesCard({ sources }: { sources: SourceDoc[] }) {
  return (
    <div className="space-y-2">
      <p className="text-[13px] text-white/80">Here's what I'm reading:</p>
      {sources.map((s) => (
        <div key={s.id} className="rounded-xl border border-line bg-white/[0.03] p-2.5">
          <div className="flex items-center gap-2 text-[13px]">
            <SourceIcon kind={s.kind} />
            <span className="truncate font-mono text-[12px] text-white/90">{s.name}</span>
            <span className="ml-auto shrink-0 text-[11px] text-dim">{s.pages} chunks</span>
          </div>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/5">
            <motion.div
              className="h-full rounded-full bg-bob-mint"
              initial={{ width: 0 }}
              animate={{ width: `${(s.kept / s.pages) * 100}%` }}
              transition={{ duration: 1.1, delay: 0.9, ease: "easeOut" }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function ArchitectCard({ capabilities, approved, onApprove }: { capabilities: Capability[]; approved: boolean; onApprove: (ids: string[]) => void }) {
  const [on, setOn] = useState<Record<string, boolean>>(() => Object.fromEntries(capabilities.map((c) => [c.id, c.enabled])));
  const total = capabilities.filter((c) => on[c.id]).reduce((a, c) => a + c.estRows, 0);
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-[13px] font-medium text-bob-yellow">
        <Sparkles className="size-4" /> Plan from the Architect
      </div>
      <p className="mb-2.5 text-[13px] text-white/80">A model trained on this corpus should be able to:</p>
      <ul className="space-y-1.5">
        {capabilities.map((c) => (
          <li key={c.id}>
            <button
              disabled={approved}
              onClick={() => setOn((s) => ({ ...s, [c.id]: !s[c.id] }))}
              className={`flex w-full items-start gap-2.5 rounded-xl border p-2.5 text-left transition ${
                on[c.id] ? "border-bob-blue/50 bg-bob-blue/10" : "border-line bg-white/[0.02] opacity-60"
              } ${approved ? "cursor-default" : "hover:border-bob-sky/60"}`}
            >
              <span className={`mt-0.5 grid size-4 shrink-0 place-items-center rounded ${on[c.id] ? "bg-bob-blue" : "border border-white/20"}`}>
                {on[c.id] && <Check className="size-3 text-white" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-medium text-white">{c.title}</span>
                <span className="block text-[11.5px] text-dim">{c.detail}</span>
              </span>
              <span className="shrink-0 font-mono text-[11px] text-dim">~{c.estRows}</span>
            </button>
          </li>
        ))}
      </ul>
      {approved ? (
        <div className="mt-3 flex items-center gap-1.5 text-[12px] text-bob-mint">
          <Check className="size-4" /> Approved. Building.
        </div>
      ) : (
        <button
          onClick={() => onApprove(capabilities.filter((c) => on[c.id]).map((c) => c.id))}
          disabled={total === 0}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-bob-yellow py-2.5 font-display text-[15px] font-bold text-bob-navy shadow-[0_8px_30px_-10px] shadow-bob-yellow transition hover:brightness-105 active:scale-[0.98] disabled:opacity-40"
        >
          <Hammer className="size-4" /> Build ~{total} rows
        </button>
      )}
    </div>
  );
}

function DoneCard({ stats, onExport }: { stats: Stats; onExport: () => void }) {
  const mult = stats.costUsd > 0 ? Math.round(stats.baselineUsd / stats.costUsd) : 0;
  return (
    <div>
      <p className="text-[13px] text-white/90">
        Done. <b className="text-white">{stats.verified}</b> rows passed every check, and I threw out <b className="text-white">{stats.rejected}</b>.
      </p>
      <div className="mt-2.5 grid grid-cols-2 gap-2 text-[12px]">
        <div className="rounded-lg bg-white/[0.04] p-2">
          <div className="text-dim">Spent</div>
          <div className="font-mono text-white">{usd(stats.costUsd)}</div>
        </div>
        <div className="rounded-lg bg-white/[0.04] p-2">
          <div className="text-dim">Frontier-only estimate</div>
          <div className="font-mono text-white">
            {usd(stats.baselineUsd)} <span className="text-bob-mint">({mult}x)</span>
          </div>
        </div>
      </div>
      <button onClick={onExport} className="mt-3 w-full rounded-xl bg-bob-blue py-2 text-[13px] font-medium text-white transition hover:brightness-110">
        Export dataset
      </button>
    </div>
  );
}

function Bubble({ from, children, avatar }: { from: "user" | "bob"; children: ReactNode; avatar?: ReactNode }) {
  if (from === "user")
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-bob-blue px-3.5 py-2.5 text-[13.5px] leading-relaxed text-white">{children}</div>
      </div>
    );
  return (
    <div className="flex gap-2">
      <div className="size-9 shrink-0">{avatar}</div>
      <div className="min-w-0 max-w-[88%] flex-1 rounded-2xl rounded-tl-md border border-line bg-panel-2 px-3.5 py-2.5 text-[13.5px] leading-relaxed text-white/85">
        {children}
      </div>
    </div>
  );
}

interface ChatPanelProps {
  messages: ChatMessage[];
  pose: BobPose;
  onApprove: (ids: string[]) => void;
  onExport: () => void;
  composer: ReactNode;
}

export function ChatPanel({ messages, pose, onApprove, onExport, composer }: ChatPanelProps) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);
  const lastBob = [...messages].reverse().find((m) => m.from === "bob")?.id;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="scroll-thin min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pb-4 pt-4">
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div key={m.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
              <Bubble
                from={m.from}
                avatar={m.id === lastBob ? <Bob pose={pose} size={36} float={false} /> : <Bob pose="idle" size={36} float={false} />}
              >
                {"text" in m && m.text}
                {"card" in m && m.card === "sources" && <SourcesCard sources={m.sources} />}
                {"card" in m && m.card === "architect" && <ArchitectCard capabilities={m.capabilities} approved={m.approved} onApprove={onApprove} />}
                {"card" in m && m.card === "done" && <DoneCard stats={m.stats} onExport={onExport} />}
              </Bubble>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={end} />
      </div>
      <div className="px-4 pb-4 pt-2">{composer}</div>
    </div>
  );
}
