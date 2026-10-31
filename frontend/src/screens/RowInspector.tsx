import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArrowLeft, CheckCircle2, ExternalLink, Gavel, Loader2, ScanEye, XCircle } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { CheckResult, Job, Row, SpanRef } from "../api/types";
import { AppShell } from "../components/AppShell";
import { ErrorBanner, Panel, caseLabel, checkLabel, usd, useTitle } from "../components/ui";



const TIER_LABEL = { 1: "code", 2: "Jev + ScaleDown", 3: "judge" } as const;

interface Passage {
  span: SpanRef;
  marks: [number, number][]; // highlighted slices of span.text
}

/**
 * Row.spans holds the cited passages (chunks) and the extracted facts (evidence spans),
 * both with offsets into the source document. Show each passage once and highlight the
 * facts inside it. A fact outside every passage shows on its own.
 */
export function groupSpans(spans: SpanRef[]): Passage[] {
  const sorted = [...spans].sort((a, b) => b.end - b.start - (a.end - a.start));
  const out: Passage[] = [];
  for (const s of sorted) {
    const host = out.find((p) => p.span.doc_id === s.doc_id && s.start >= p.span.start && s.end <= p.span.end);
    if (!host) {
      out.push({ span: s, marks: [] });
      continue;
    }
    // Offsets first; fall back to a text search when the passage text was normalized.
    let a = s.start - host.span.start;
    if (host.span.text.slice(a, a + s.text.length) !== s.text) a = host.span.text.indexOf(s.text);
    if (a >= 0) host.marks.push([a, a + s.text.length]);
  }
  for (const p of out) p.marks.sort((x, y) => x[0] - y[0]);
  return out.sort((x, y) => x.span.doc_id.localeCompare(y.span.doc_id) || x.span.start - y.span.start);
}

function Span({ p }: { p: Passage }) {
  const s = p.span;
  const external = /^https?:\/\//.test(s.uri);
  const parts: { text: string; mark: boolean }[] = [];
  let at = 0;
  for (const [a, b] of p.marks) {
    if (a < at) continue; // overlapping facts: keep the first
    if (a > at) parts.push({ text: s.text.slice(at, a), mark: false });
    parts.push({ text: s.text.slice(a, b), mark: true });
    at = b;
  }
  if (at < s.text.length) parts.push({ text: s.text.slice(at), mark: false });
  return (
    <div className="rounded-xl border border-line bg-void p-3">
      <div className="mb-1.5 flex items-center gap-2 text-[12px]">
        <span className="truncate font-medium text-white/85">{s.title || s.uri}</span>
        {external ? (
          <a href={s.uri} target="_blank" rel="noreferrer" className="ml-auto flex shrink-0 items-center gap-1 text-bob-sky hover:underline">
            open <ExternalLink className="size-3" />
          </a>
        ) : (
          <span className="ml-auto shrink-0 font-mono text-[10.5px] text-dim">{s.uri}</span>
        )}
      </div>
      <p className={`scroll-thin max-h-64 overflow-y-auto whitespace-pre-wrap text-[12.5px] leading-relaxed ${p.marks.length ? "text-white/50" : "text-white/75"}`}>
        {parts.map((x, i) => (x.mark ? <mark key={i} className="rounded bg-bob-yellow/20 px-0.5 text-bob-yellow">{x.text}</mark> : <span key={i}>{x.text}</span>))}
      </p>
    </div>
  );
}

function CheckItem({ c }: { c: CheckResult }) {
  return (
    <li className="py-1.5">
      <div className="flex items-center gap-2 text-[13px]">
        {c.passed ? <CheckCircle2 className="size-4 shrink-0 text-bob-mint" /> : <XCircle className="size-4 shrink-0 text-rose-400" />}
        <span className="text-white/90">{checkLabel(c.name)}</span>
        <span className="ml-auto text-[10.5px] text-dim">{TIER_LABEL[c.tier]}</span>
        {c.score !== null && <span className="font-mono text-[11px] text-dim">{c.score.toFixed(2)}</span>}
      </div>
      {c.detail && !c.passed && <div className="ml-6 mt-0.5 text-[12px] text-rose-300/90">{c.detail}</div>}
    </li>
  );
}

// Failed checks always show; passed checks collapse into one line.
function Checks({ checks }: { checks: CheckResult[] }) {
  const [open, setOpen] = useState(false);
  const sorted = [...checks].sort((a, b) => a.tier - b.tier);
  const failed = sorted.filter((c) => !c.passed);
  const passed = sorted.filter((c) => c.passed);
  return (
    <div>
      {failed.length > 0 && <ul className="mb-2">{failed.map((c) => <CheckItem key={c.name} c={c} />)}</ul>}
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center gap-2 rounded-lg bg-bob-mint/[0.07] px-3 py-2 text-left text-[13px] text-bob-mint">
        <CheckCircle2 className="size-4" />
        {failed.length ? `${passed.length} other checks passed` : `All ${passed.length} checks passed`}
        <span className="ml-auto text-[12px] text-dim">{open ? "Hide" : "Show"}</span>
      </button>
      {open && <ul className="mt-1 px-1">{passed.map((c) => <CheckItem key={c.name} c={c} />)}</ul>}
    </div>
  );
}

export default function RowInspector() {
  const { id, rowId } = useParams();
  const [row, setRow] = useState<Row | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const nav = useNavigate();
  useTitle("Row");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && nav(`/jobs/${id}/build`);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [id, nav]);
  useEffect(() => {
    setRow(null);
    api.row(id!, rowId!).then(setRow).catch(setError);
  }, [id, rowId]);
  // The tracker shows where the job really is (a done job keeps Report open).
  useEffect(() => {
    api.getJob(id!).then(setJob).catch(() => undefined);
  }, [id]);

  const kept = row?.verdict === "kept";
  const notInDocs = row?.checks.find((c) => c.name === "jev.not_in_docs");
  const passages = useMemo(() => groupSpans(row?.spans ?? []), [row]);

  return (
    <AppShell pose={row ? (kept ? "idea" : "think") : "think"} title={job?.spec.goal ?? "Row"} step="build" status={job?.status ?? null} hasReport={!!job?.report}>
      <div className="mx-auto max-w-6xl px-4 py-5">
        <Link to={`/jobs/${id}/build`} className="mb-3 inline-flex items-center gap-1 text-[12.5px] text-dim hover:text-white">
          <ArrowLeft className="size-4" /> Back to the build <kbd className="ml-1 rounded border border-line px-1 font-mono text-[10px]">Esc</kbd>
        </Link>
        <ErrorBanner error={error} title="Couldn't load this row" />
        {!row && !error && <div className="grid place-items-center py-20 text-dim"><Loader2 className="size-6 animate-spin" /></div>}
        {row && (
          <>
            <div className={`mb-4 flex flex-wrap items-center gap-2 rounded-2xl border px-4 py-3 ${kept ? "border-bob-mint/30 bg-bob-mint/[0.06]" : "border-rose-400/30 bg-rose-400/[0.06]"}`}>
              {kept ? <CheckCircle2 className="size-5 text-bob-mint" /> : <XCircle className="size-5 text-rose-400" />}
              <span className="font-display text-[17px] font-bold">{kept ? "Kept" : "Rejected"}</span>
              {!kept && row.reject_reason && <span className="text-[13px] text-rose-200">{row.reject_reason}</span>}
              <div className="ml-auto flex flex-wrap items-center gap-1.5 text-[11.5px]">
                <span className="text-dim">{Object.values(row.coords).map(caseLabel).join(" · ")}</span>
                {row.routed_to_judge && <span className="flex items-center gap-1 rounded-full border border-bob-yellow/30 px-2 py-0.5 text-bob-yellow"><Gavel className="size-3" /> judged</span>}
                {row.audited && <span className="flex items-center gap-1 rounded-full border border-bob-sky/30 px-2 py-0.5 text-bob-sky"><ScanEye className="size-3" /> audited</span>}
                <span className="rounded-full border border-line px-2 py-0.5 font-mono text-dim">conf {row.confidence.toFixed(2)}</span>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
              <div className="space-y-4">
                <Panel title="Conversation">
                  <div className="space-y-2.5">
                    {row.messages.map((m, i) => (
                      <div key={i} className={m.role === "user" ? "flex justify-end" : "flex"}>
                        <div className={`max-w-[88%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed ${m.role === "user" ? "rounded-br-md bg-bob-blue text-white" : m.role === "assistant" ? "rounded-tl-md border border-line bg-panel-2 text-white/90" : "w-full border border-dashed border-line text-[12px] text-dim"}`}>
                          {m.content}
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>
                <Panel title={`Source${passages.length === 1 ? "" : "s"}`} action={<span className="text-[11px] text-dim">{passages.length} cited</span>}>
                  {notInDocs && (
                    <div className="mb-3 rounded-lg bg-bob-yellow/10 px-3 py-2 text-[12.5px] text-bob-yellow">
                      Not in the docs: {notInDocs.detail}
                    </div>
                  )}
                  <div className="space-y-2">
                    {passages.length === 0 ? <div className="text-[12.5px] text-dim">No supporting passages recorded for this row.</div> : passages.map((p, i) => <Span key={i} p={p} />)}
                  </div>
                </Panel>
              </div>
              <Panel title="Checks" action={<span className="font-mono text-[11px] text-dim">{usd(row.cost_usd, 5)}</span>}>
                <Checks checks={row.checks} />
              </Panel>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
