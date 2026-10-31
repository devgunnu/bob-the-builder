import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArrowLeft, CheckCircle2, ExternalLink, Gavel, Loader2, ScanEye, XCircle } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { CheckResult, Job, Row, SpanRef } from "../api/types";
import { AppShell } from "../components/AppShell";
import { ErrorBanner, Panel, caseLabel, checkLabel, usd, useTitle } from "../components/ui";



const TIER_LABEL = { 1: "code", 2: "Jev + ScaleDown", 3: "judge" } as const;

function Span({ s }: { s: SpanRef }) {
  // CONTRACTS: start/end are offsets in the document; when they fall inside
  // the span text, highlight that slice, otherwise the whole span is the citation.
  const inside = s.start >= 0 && s.end > s.start && s.end <= s.text.length;
  const [a, b] = inside ? [s.start, s.end] : [0, s.text.length];
  const external = /^https?:\/\//.test(s.uri);
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
      <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-white/50">
        {s.text.slice(0, a)}
        <mark className="rounded bg-bob-yellow/20 px-0.5 text-bob-yellow">{s.text.slice(a, b)}</mark>
        {s.text.slice(b)}
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
                <Panel title={`Source${row.spans.length === 1 ? "" : "s"}`} action={<span className="text-[11px] text-dim">{row.spans.length} cited</span>}>
                  {notInDocs && (
                    <div className="mb-3 rounded-lg bg-bob-yellow/10 px-3 py-2 text-[12.5px] text-bob-yellow">
                      Not in the docs: {notInDocs.detail}
                    </div>
                  )}
                  <div className="space-y-2">
                    {row.spans.length === 0 ? <div className="text-[12.5px] text-dim">No supporting spans recorded for this row.</div> : row.spans.map((s, i) => <Span key={i} s={s} />)}
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
