import { useState } from "react";
import { CheckCircle2, Download, Lock, XCircle } from "lucide-react";
import type { Row } from "../../lib/types";
import { download, FORMATS, PRESETS, serialize, type FormatId, type PresetId } from "../../lib/exporters";
import { Bob } from "../Bob";
import { GEN_COLORS } from "./RowStream";

function SourceView({ row }: { row: Row }) {
  const { text, span } = row.source;
  const [a, b] = span;
  return (
    <pre className="scroll-thin overflow-x-auto whitespace-pre rounded-xl border border-line bg-void p-3 font-mono text-[11px] leading-relaxed text-white/45">
      {text.slice(0, a)}
      <mark className="rounded bg-bob-yellow/25 px-0.5 text-bob-yellow">{text.slice(a, b)}</mark>
      {text.slice(b)}
    </pre>
  );
}

function RowDetail({ row }: { row: Row }) {
  const ok = row.status === "verified";
  return (
    <div className="space-y-4">
      <div className={`flex items-start gap-2 rounded-xl p-2.5 text-[12.5px] ${ok ? "bg-bob-mint/10 text-bob-mint" : "bg-rose-400/10 text-rose-300"}`}>
        {ok ? <CheckCircle2 className="mt-px size-4 shrink-0" /> : <XCircle className="mt-px size-4 shrink-0" />}
        {ok ? "Passed every check. This row goes in the dataset." : `Rejected. ${row.rejectReason}`}
      </div>

      <section>
        <h4 className="mb-1 text-[11px] uppercase tracking-wider text-dim">Prompt</h4>
        <p className="text-[13.5px] leading-relaxed text-white">{row.prompt}</p>
      </section>
      <section>
        <h4 className="mb-1 text-[11px] uppercase tracking-wider text-dim">{row.kind === "dpo" ? "Chosen" : "Response"}</h4>
        <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-white/85">{row.response}</p>
      </section>
      {row.rejected && (
        <section>
          <h4 className="mb-1 text-[11px] uppercase tracking-wider text-rose-300/80">Rejected (one known flaw)</h4>
          <p className="text-[13.5px] leading-relaxed text-white/60">{row.rejected}</p>
        </section>
      )}

      <section>
        <h4 className="mb-1.5 text-[11px] uppercase tracking-wider text-dim">
          Source · <span className="normal-case tracking-normal">{row.source.doc} › {row.source.section}</span>
        </h4>
        <SourceView row={row} />
      </section>

      <section>
        <h4 className="mb-1.5 text-[11px] uppercase tracking-wider text-dim">Checks</h4>
        <ul className="space-y-1">
          {row.checks.map((c) => (
            <li key={c.name} className="flex items-center gap-2 text-[12.5px]">
              {c.passed ? <CheckCircle2 className="size-3.5 text-bob-mint" /> : <XCircle className="size-3.5 text-rose-400" />}
              <span className="text-white/85">{c.name}</span>
              <span className="ml-auto font-mono text-[11px] text-dim">{c.detail.startsWith("p =") ? c.detail : ""}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3 text-[11px] text-dim">
        <span className={`rounded-md px-1.5 py-px font-mono ${GEN_COLORS[row.generator] ?? ""}`}>{row.generator}</span>
        <span>persona: {row.persona}</span>
        <span className="ml-auto font-mono">${row.costUsd.toFixed(5)}</span>
      </div>
    </div>
  );
}

function ExportView({ rows }: { rows: Row[] }) {
  const [preset, setPreset] = useState<PresetId>("modelforge-sft");
  const [format, setFormat] = useState<FormatId>("jsonl");
  const verified = rows.filter((r) => r.status === "verified").length;
  const browser = FORMATS[format].browser;

  const go = () => {
    const { body } = serialize(rows, preset, format);
    const ext = format === "jsonl" ? "jsonl" : format;
    const type = format === "csv" ? "text/csv" : "application/json";
    download(`bob-${preset}.${ext}`, body, type);
  };

  return (
    <div className="space-y-4">
      <section>
        <h4 className="mb-1.5 text-[11px] uppercase tracking-wider text-dim">Preset</h4>
        <div className="space-y-1">
          {(Object.keys(PRESETS) as PresetId[]).map((p) => (
            <button
              key={p}
              onClick={() => setPreset(p)}
              className={`flex w-full items-center justify-between rounded-xl border px-3 py-2 text-left transition ${
                preset === p ? "border-bob-sky/60 bg-bob-blue/10" : "border-line hover:border-white/15"
              }`}
            >
              <span className="text-[13px] text-white">{PRESETS[p].label}</span>
              <span className="font-mono text-[10.5px] text-dim">{PRESETS[p].note}</span>
            </button>
          ))}
        </div>
      </section>
      <section>
        <h4 className="mb-1.5 text-[11px] uppercase tracking-wider text-dim">Format</h4>
        <div className="flex flex-wrap gap-1.5">
          {(Object.keys(FORMATS) as FormatId[]).map((f) => (
            <button
              key={f}
              onClick={() => setFormat(f)}
              className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 font-mono text-[11.5px] transition ${
                format === f ? "border-bob-yellow/70 bg-bob-yellow/10 text-bob-yellow" : "border-line text-white/70 hover:border-white/20"
              }`}
            >
              {!FORMATS[f].browser && <Lock className="size-3" />}
              {FORMATS[f].label}
            </button>
          ))}
        </div>
        {!browser && <p className="mt-2 text-[11.5px] text-dim">Written by the backend once it's connected.</p>}
      </section>
      <button
        onClick={go}
        disabled={!browser || verified === 0}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-bob-yellow py-2.5 font-display text-[15px] font-bold text-bob-navy transition hover:brightness-105 disabled:opacity-35"
      >
        <Download className="size-4" /> Download {verified.toLocaleString()} verified rows
      </button>
    </div>
  );
}

export type InspectorTab = "row" | "export";

export function Inspector({ row, rows, tab, onTab }: { row?: Row; rows: Row[]; tab: InspectorTab; onTab: (t: InspectorTab) => void }) {
  return (
    <div className="flex h-full min-h-0 flex-col rounded-2xl border border-line bg-panel">
      <div className="flex gap-1 border-b border-line px-3 py-2">
        {(["row", "export"] as InspectorTab[]).map((t) => (
          <button
            key={t}
            onClick={() => onTab(t)}
            className={`rounded-lg px-3 py-1 text-[12.5px] capitalize transition ${tab === t ? "bg-white/10 text-white" : "text-dim hover:text-white"}`}
          >
            {t === "row" ? "Inspect" : "Export"}
          </button>
        ))}
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4">
        {tab === "export" ? (
          <ExportView rows={rows} />
        ) : row ? (
          <RowDetail row={row} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <Bob pose="hero" size={130} />
            <p className="max-w-[240px] text-[12.5px] text-white/60">Click any row to see the exact text it came from and every check it passed.</p>
          </div>
        )}
      </div>
    </div>
  );
}
