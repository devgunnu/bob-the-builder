import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { motion } from "motion/react";
import { Download, Loader2, ThumbsDown, ThumbsUp } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { PresetInfo, Report, Row } from "../api/types";
import { useJobStream } from "../api/useJobStream";
import { AppShell } from "../components/AppShell";
import { Bob } from "../components/Bob";
import { Button, Empty, ErrorBanner, JobLoadError, Panel, caseLabel, checkLabel, pct, usd, useTitle } from "../components/ui";
import { Bars } from "../components/viz/Bars";
import { Heatgrid, type GridCell } from "../components/viz/Heatgrid";

function Stat({ label, value, sub, tone = "text-white" }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel px-3 py-2.5">
      <div className="text-[11px] text-dim">{label}</div>
      <div className={`font-display text-[22px] font-bold tabular-nums ${tone}`}>{value}</div>
      {sub && <div className="text-[10.5px] text-dim">{sub}</div>}
    </div>
  );
}

function SpotCheck({ jobId, report, onReport }: { jobId: string; report: Report; onReport: (r: Report) => void }) {
  const ids = report.sample_row_ids;
  const [i, setI] = useState(0);
  const [row, setRow] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!ids[i]) return;
    setRow(null);
    api.row(jobId, ids[i]).then(setRow).catch(setError);
  }, [jobId, ids, i]);

  const vote = async (ok: boolean) => {
    if (!row) return;
    setBusy(true);
    try {
      onReport(await api.spotCheck(jobId, row.id, ok));
      setI((n) => Math.min(ids.length, n + 1));
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  if (!ids.length) return <div className="text-[12.5px] text-dim">No sample rows in this report.</div>;
  if (i >= ids.length) return <div className="text-[13px] text-bob-mint">All {ids.length} sample rows checked. Thanks!</div>;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-[12px] text-dim">
        <span>Row {i + 1} of {ids.length}</span>
        <span>{report.spot_check.up ?? 0} up · {report.spot_check.down ?? 0} down</span>
      </div>
      <ErrorBanner error={error} />
      {!row ? (
        <div className="grid place-items-center py-8 text-dim"><Loader2 className="size-5 animate-spin" /></div>
      ) : (
        <div className="space-y-2">
          {row.messages.filter((m) => m.role !== "system").map((m, k) => (
            <div key={k} className={`rounded-xl px-3 py-2 text-[13px] leading-relaxed ${m.role === "user" ? "bg-bob-blue/20 text-white" : "border border-line bg-panel-2 text-white/85"}`}>{m.content}</div>
          ))}
          <div className="flex gap-2 pt-1">
            <Button tone="ghost" className="flex-1" busy={busy} onClick={() => vote(false)}><ThumbsDown className="size-4 text-rose-300" /> Wrong</Button>
            <Button tone="ghost" className="flex-1" busy={busy} onClick={() => vote(true)}><ThumbsUp className="size-4 text-bob-mint" /> Good</Button>
          </div>
          <Link to={`/jobs/${jobId}/rows/${row.id}`} className="block text-center text-[11.5px] text-dim hover:text-white">See sources and checks</Link>
        </div>
      )}
    </div>
  );
}

function ExportPanel({ jobId, files, defaultPreset }: { jobId: string; files: Record<string, string>; defaultPreset?: string }) {
  const [presets, setPresets] = useState<PresetInfo[] | null>(null);
  const [preset, setPreset] = useState(defaultPreset ?? "openai-chat");
  const [formats, setFormats] = useState<string[]>(["jsonl"]);
  const [out, setOut] = useState<Record<string, string>>(files);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => setOut((o) => ({ ...files, ...o })), [files]);
  useEffect(() => {
    api.presets().then(setPresets).catch(setError);
  }, []);
  const current = presets?.find((p) => p.name === preset);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.export(jobId, preset, formats);
      setOut((o) => ({ ...o, ...r.files }));
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <ErrorBanner error={error} title="Export failed" />
      {presets === null ? (
        <div className="flex items-center gap-2 text-[12.5px] text-dim"><Loader2 className="size-4 animate-spin" /> Loading presets…</div>
      ) : (
        <>
          <div className="space-y-1">
            {presets.map((p) => (
              <button
                key={p.name}
                onClick={() => (setPreset(p.name), setFormats((f) => f.filter((x) => p.formats.includes(x)).length ? f.filter((x) => p.formats.includes(x)) : [p.formats[0]]))}
                className={`w-full rounded-xl border px-3 py-2 text-left transition ${preset === p.name ? "border-bob-sky/60 bg-bob-blue/10" : "border-line hover:border-white/15"}`}
              >
                <div className="font-mono text-[12.5px] text-white">{p.name}</div>
                <div className="text-[11.5px] text-dim">{p.description}</div>
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(current?.formats ?? []).map((f) => (
              <button
                key={f}
                onClick={() => setFormats((x) => (x.includes(f) ? x.filter((y) => y !== f) : [...x, f]))}
                className={`rounded-lg border px-2.5 py-1 font-mono text-[11.5px] ${formats.includes(f) ? "border-bob-yellow/70 bg-bob-yellow/10 text-bob-yellow" : "border-line text-white/70"}`}
              >
                {f}
              </button>
            ))}
          </div>
          <Button tone="yellow" className="w-full" busy={busy} disabled={!formats.length} onClick={run}>Export {preset}</Button>
        </>
      )}
      {Object.keys(out).length > 0 && (
        <ul className="space-y-1 border-t border-line pt-3">
          {Object.keys(out).sort().map((name) => (
            <li key={name}>
              <button onClick={() => api.download(jobId, name).catch(setError)} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12.5px] text-white/85 hover:bg-white/5">
                <Download className="size-3.5 text-bob-mint" /> <span className="truncate font-mono">{name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function QuickDownload({ jobId, files, preset }: { jobId: string; files: Record<string, string>; preset: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  // dataset.zip holds both splits (train + eval), provenance and the manifest: the whole dataset.
  const existing = Object.keys(files).find((n) => n === `${preset}/dataset.zip`);
  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.export(jobId, preset, ["jsonl"]);
      const name = Object.keys(r.files).find((n) => n.endsWith("/dataset.zip")) ?? Object.keys(r.files)[0];
      if (name) await api.download(jobId, name);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-1 sm:items-end">
      <Button tone="yellow" className="w-full px-5 py-3 text-[16px] sm:w-auto" busy={busy} onClick={existing ? () => api.download(jobId, existing).catch(setError) : go}>
        <Download className="size-4" /> Download dataset
      </Button>
      <span className="text-[11px] text-dim">{preset} · train + eval JSONL, in one .zip</span>
      {error && <ErrorBanner error={error} title="Download failed" />}
    </div>
  );
}

type RTab = "coverage" | "quality" | "spot" | "export";

export default function ReportScreen() {
  const { id } = useParams();
  const s = useJobStream(id);
  const r = s.report;
  const [tab, setTab] = useState<RTab>("coverage");
  useTitle("Report");

  const coverageCells: GridCell[] = useMemo(
    () => (r ? r.coverage.map((c) => ({ id: c.cell_id, coords: c.coords, enabled: true, target: c.target, kept: c.kept, rejected: c.rejected, generated: c.kept + c.rejected, judged: 0 })) : []),
    [r],
  );
  const covered = r ? r.coverage.filter((c) => c.kept >= c.target).length : 0;
  const kept = r ? r.coverage.reduce((a, c) => a + c.kept, 0) : 0;
  const cost = s.cost ?? s.job?.cost;
  const ratio = cost && cost.total_usd > 0 ? cost.frontier_only_estimate_usd / cost.total_usd : 0;
  const preset = s.job?.spec.preset ?? "openai-chat";

  const TABS: [RTab, string][] = [
    ["coverage", "Coverage"],
    ["quality", "Quality"],
    ["spot", `Spot-check${r?.spot_check.n ? ` ${r.spot_check.up ?? 0}/${r.spot_check.n}` : ""}`],
    ["export", "Other formats"],
  ];

  if (s.loadError)
    return (
      <AppShell pose="idle" step="report">
        <JobLoadError error={s.loadError} />
      </AppShell>
    );

  return (
    <AppShell pose={r ? "hero" : "idle"} title={s.job?.spec.goal} step="report" status={s.status} hasReport={!!r}>
      <div className="mx-auto max-w-5xl px-4 py-8">
        {!r ? (
          <Empty>
            <Bob pose="idle" size={110} float={false} still />
            <p className="mt-2">The report appears when the build finishes. <Link to={`/jobs/${id}/build`} className="text-bob-sky hover:underline">Watch the build</Link></p>
          </Empty>
        ) : (
          <>
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-5">
              <Bob pose="hero" size={88} float={false} still className="hidden shrink-0 sm:block" />
              <div className="min-w-0 flex-1">
                <h1 className="font-display text-[26px] font-extrabold leading-tight sm:text-[30px]">{kept.toLocaleString()} verified rows are ready</h1>
                <p className="mt-1 text-[14px] text-white/70">
                  {covered} of {r.coverage.length} cells hit their target · {pct(r.judge_rate)} needed the judge · cost {usd(cost?.total_usd)}
                  {ratio ? ` (frontier-only ${usd(cost?.frontier_only_estimate_usd)}, ${ratio.toFixed(0)}x more)` : ""}
                </p>
              </div>
              <QuickDownload jobId={id!} files={s.files} preset={preset} />
            </motion.div>
            {(s.status === "done" || s.status === "error" || s.status === "cancelled") && <Resync jobId={id!} />}

            <div className="mb-4 flex gap-1 rounded-2xl bg-panel p-1.5" role="tablist">
              {TABS.map(([t, label]) => (
                <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`flex-1 rounded-xl py-2 text-[13px] transition ${tab === t ? "bg-white/[0.08] text-white" : "text-dim hover:text-white"}`}>
                  {label}
                </button>
              ))}
            </div>

            {tab === "coverage" && (
              <div className="space-y-4">
                <section className="rounded-2xl bg-panel p-4">
                  {s.plan ? <Heatgrid axes={s.plan.axes} cells={coverageCells} /> : <div className="text-[12.5px] text-dim">Plan not available.</div>}
                </section>
                {Object.keys(r.mix_coverage ?? {}).length > 0 && (
                  <div className="grid gap-4 md:grid-cols-2">
                    {Object.entries(r.mix_coverage).map(([axis, vals]) => (
                      <Panel key={axis} title={axis === "persona" ? "Who asks" : axis === "difficulty" ? "How hard" : axis}>
                        <Bars data={Object.entries(vals).map(([k, v]) => [caseLabel(k), v] as [string, number]).sort((a, b) => b[1] - a[1])} format={(v) => `${v.toLocaleString()} rows`} tone="bg-bob-sky/70" />
                      </Panel>
                    ))}
                  </div>
                )}
              </div>
            )}

            {tab === "quality" && (
              <div className="grid gap-4 md:grid-cols-2">
                <Panel title="Pass rate by check">
                  <Bars data={Object.entries(r.pass_rate_by_check).map(([k, v]) => [checkLabel(k), v] as [string, number]).sort((a, b) => a[1] - b[1])} format={(v) => pct(v)} max={1} />
                </Panel>
                <Panel title="Why rows were rejected">
                  <Bars data={Object.entries(r.reject_reasons).map(([k, v]) => [checkLabel(k), v] as [string, number]).sort((a, b) => b[1] - a[1])} tone="bg-rose-400/70" />
                  <div className="mt-3 text-[12px] text-dim">{r.duplicates_removed.toLocaleString()} duplicates removed</div>
                </Panel>
                <Panel title="Judge">
                  <div className="grid grid-cols-2 gap-2">
                    <Stat label="Sent to the judge" value={pct(r.judge_rate)} tone="text-bob-yellow" />
                    <Stat label="Agreed with Jev" value={pct(r.judge_agreement)} />
                  </div>
                </Panel>
                <Panel title="Rounds">
                  <table className="w-full text-[12.5px]">
                    <thead><tr className="text-left text-[11px] text-dim"><th className="pb-1 font-medium">Round</th><th className="pb-1 font-medium">Cells</th><th className="pb-1 text-right font-medium">Kept</th></tr></thead>
                    <tbody>
                      {r.rounds.map((x) => (
                        <tr key={x.n} className="border-t border-line"><td className="py-1.5">{x.n}</td><td>{x.cells}</td><td className="text-right font-mono">{x.kept.toLocaleString()}</td></tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="mt-3 text-[12px] text-dim">Reply length: p50 {r.token_stats.p50 ?? "–"} · p95 {r.token_stats.p95 ?? "–"} · max {r.token_stats.max ?? "–"} tokens</div>
                </Panel>
              </div>
            )}

            {tab === "spot" && (
              <section className="mx-auto max-w-2xl rounded-2xl bg-panel p-5">
                <p className="mb-4 text-[13px] text-dim">Read a few rows and say if they're right. Your answers update the report and measure how accurate Jev was on this job.</p>
                <SpotCheck jobId={id!} report={r} onReport={s.setReport} />
              </section>
            )}

            {tab === "export" && (
              <section className="mx-auto max-w-2xl rounded-2xl bg-panel p-5">
                <ExportPanel jobId={id!} files={s.files} defaultPreset={preset} />
              </section>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

/** Re-fetch the sources and re-check the rows they changed (POST /jobs/{id}/resync). A quiet link, not a second primary action. */
function Resync({ jobId }: { jobId: string }) {
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.resync(jobId);
      nav(`/jobs/${jobId}/build`);
    } catch (e) {
      setError(e as ApiError);
      setBusy(false);
    }
  };
  return (
    <div className="-mt-3 mb-5 text-[12.5px] text-dim">
      Docs changed since this run?{" "}
      <button onClick={run} disabled={busy} className="inline-flex items-center gap-1 text-bob-sky hover:underline disabled:opacity-50">
        {busy && <Loader2 className="size-3 animate-spin" />} Check the sources again
      </button>
      <span className="hidden sm:inline"> · Bob re-checks only the rows whose sources changed.</span>
      {error && <div className="mt-2"><ErrorBanner error={error} title="Couldn't start the re-check" /></div>}
    </div>
  );
}
