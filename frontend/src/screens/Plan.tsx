import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { motion } from "motion/react";
import { Loader2, Minus, Pencil, Play, Plus, RotateCcw, SlidersHorizontal, X } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Axis, Cell, Plan, StageName } from "../api/types";
import { useJobStream, type JobStream } from "../api/useJobStream";
import { AppShell } from "../components/AppShell";
import { Bob } from "../components/Bob";
import { Button, CASE_INFO, CaseHeader, ConfirmButton, ErrorBanner, Label, caseLabel, usd, useTitle } from "../components/ui";

function readingPose(stage: StageName | null): "read" | "think" {
  return ["fetch", "triage", "evidence"].includes(stage ?? "") ? "read" : "think";
}

const READ_STAGES: { id: StageName; label: string }[] = [
  { id: "fetch", label: "Fetching pages" },
  { id: "chunk", label: "Splitting into passages" },
  { id: "triage", label: "Sorting useful passages" },
  { id: "topics", label: "Finding topics" },
  { id: "evidence", label: "Collecting facts" },
  { id: "plan", label: "Drafting the plan" },
];

function ReadingView({ s, onCancel }: { s: JobStream; onCancel: () => void }) {
  const failed = s.status === "error" || s.status === "cancelled";
  const idx = Math.max(0, READ_STAGES.findIndex((x) => x.id === s.lastStage));
  const cur = READ_STAGES[idx];
  const p = s.lastStage ? s.stages[s.lastStage] : undefined;
  const within = p && p.total ? p.done / p.total : 0;
  const overall = (idx + within) / READ_STAGES.length;
  const facts = [
    [s.counts.docs, "docs"],
    [s.counts.chunks_kept, "useful passages"],
    [s.counts.topics, "topics"],
    [s.counts.evidence, "facts"],
  ].filter(([n]) => n) as [number, string][];

  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-4 py-12 text-center">
      <Bob pose={failed ? "idle" : readingPose(s.lastStage)} size={110} float={false} still />
      <h1 className="mt-4 font-display text-[26px] font-extrabold">{failed ? "Bob stopped reading" : "Bob is reading your sources"}</h1>
      <p className="mt-1 text-[14px] text-dim">{failed ? "See the error below." : `${cur.label}${p?.detail ? ` · ${p.detail}` : "…"}`}</p>
      {!failed && (
        <div className="mt-6 w-full">
          <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
            <motion.div className="h-full rounded-full bg-gradient-to-r from-bob-blue to-bob-mint" animate={{ width: `${Math.max(4, overall * 100)}%` }} transition={{ duration: 0.5 }} />
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-dim">
            <span>Step {idx + 1} of {READ_STAGES.length}</span>
            {facts.length > 0 && <span>{facts.map(([n, l]) => `${n.toLocaleString()} ${l}`).join(" · ")}</span>}
          </div>
        </div>
      )}
      <div className="mt-6 w-full space-y-2 text-left">
        {(s.error || s.status === "error") && <ErrorBanner error={s.error ?? "The job stopped with an error."} />}
        {s.logs.filter((l) => l.level !== "info").slice(-2).map((l, i) => (
          <div key={i} className="rounded-lg bg-bob-yellow/10 px-3 py-1.5 text-[12px] text-bob-yellow">{l.message}</div>
        ))}
      </div>
      {!failed && (
        <>
          <ConfirmButton className="mt-8" label="Cancel this job" confirm="Stop reading and cancel?" onConfirm={onCancel} />
        </>
      )}
    </div>
  );
}


function PlanGrid({ plan, setCells }: { plan: Plan; setCells: (fn: (c: Cell[]) => Cell[]) => void }) {
  const topics = plan.axes.find((a) => a.name === "topic")?.values ?? [];
  const cases = plan.axes.find((a) => a.name === "case_type")?.values ?? [];
  const [open, setOpen] = useState<string | null>(null);

  const match = (c: Cell, t?: string, cs?: string) => (!t || c.coords.topic === t) && (!cs || c.coords.case_type === cs);
  const setOn = (on: boolean, t?: string, cs?: string) => setCells((cells) => cells.map((c) => (match(c, t, cs) ? { ...c, enabled: on } : c)));
  const toggle = (t?: string, cs?: string) =>
    setCells((cells) => {
      const turnOn = cells.filter((c) => match(c, t, cs)).some((c) => !c.enabled);
      return cells.map((c) => (match(c, t, cs) ? { ...c, enabled: turnOn } : c));
    });
  const setPer = (t: string, cs: string, v: number) => setCells((cells) => cells.map((c) => (match(c, t, cs) ? { ...c, target: Math.max(1, v) } : c)));

  return (
    <div onKeyDown={(e) => e.key === "Escape" && setOpen(null)}>
      <div className="scroll-thin overflow-x-auto pb-1 md:overflow-visible">
        <table className="w-full min-w-[520px] table-fixed border-separate" style={{ borderSpacing: 6 }}>
          <colgroup>
            <col className="w-[24%]" />
          </colgroup>
          <thead>
            <tr>
              <th />
              {cases.map((c) => (
                <th key={c} className="p-0">
                  <button onClick={() => toggle(undefined, c)} title={`${CASE_INFO[c]?.hint ?? ""} Click to turn the whole column on or off.`} className="w-full rounded-md px-1 pb-1 text-left text-[11.5px] font-medium text-white/70 hover:text-white">
                    <CaseHeader c={c} />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {topics.map((t) => (
              <tr key={t}>
                <th className="p-0 pr-2 text-left">
                  <button onClick={() => toggle(t)} title={`${plan.axes.find((a) => a.name === "topic")?.descriptions[t] ?? t}. Click to turn the whole row on or off.`} className="w-full truncate text-left text-[13px] font-medium text-white/85 hover:text-white">{t}</button>
                </th>
                {cases.map((cs) => {
                  const m = plan.cells.filter((c) => match(c, t, cs));
                  const on = m.filter((c) => c.enabled);
                  const sum = on.reduce((a, c) => a + c.target, 0);
                  const key = `${t}|${cs}`;
                  const per = (on[0] ?? m[0])?.target ?? 0;
                  return (
                    <td key={cs} className="relative p-0">
                      <button
                        onClick={() => setOpen(open === key ? null : key)}
                        disabled={!m.length}
                        aria-expanded={open === key}
                        aria-label={`${t}, ${caseLabel(cs)}: ${on.length ? `${sum} rows` : "off"}`}
                        className={`h-11 w-full rounded-xl text-[13px] transition ${
                          !m.length ? "opacity-20" : on.length ? "bg-bob-blue/25 text-white hover:bg-bob-blue/40" : "border border-dashed border-white/10 text-dim hover:text-white"
                        } ${open === key ? "ring-2 ring-bob-sky" : ""}`}
                      >
                        {on.length ? <span className="font-medium tabular-nums">{sum}</span> : <span className="text-[11.5px]">off</span>}
                      </button>
                      {open === key && (
                        <div role="dialog" aria-label={`${t}, ${caseLabel(cs)}`} className="absolute left-1/2 top-full z-20 mt-2 w-56 -translate-x-1/2 rounded-2xl border border-line bg-panel-2 p-3 text-left shadow-2xl shadow-black/60">
                          <div className="mb-2 text-[12px] text-dim">{t} · {caseLabel(cs)}</div>
                          <label className="flex items-center justify-between text-[13px]">
                            Include
                            <button
                              role="switch"
                              aria-checked={on.length > 0}
                              onClick={() => setOn(on.length === 0, t, cs)}
                              className={`relative h-5 w-9 rounded-full transition ${on.length ? "bg-bob-mint" : "bg-white/15"}`}
                            >
                              <span className={`absolute top-0.5 size-4 rounded-full bg-white transition-all ${on.length ? "left-[18px]" : "left-0.5"}`} />
                            </button>
                          </label>
                          <div className={`mt-3 flex items-center justify-between text-[13px] ${on.length ? "" : "pointer-events-none opacity-40"}`}>
                            <span>Rows</span>
                            <span className="flex items-center gap-1">
                              <button aria-label="Fewer rows" onClick={() => setPer(t, cs, per - 5)} className="grid size-7 place-items-center rounded-lg bg-white/5 hover:bg-white/10"><Minus className="size-3.5" /></button>
                              <span className="w-8 text-center tabular-nums">{per}</span>
                              <button aria-label="More rows" onClick={() => setPer(t, cs, per + 5)} className="grid size-7 place-items-center rounded-lg bg-white/5 hover:bg-white/10"><Plus className="size-3.5" /></button>
                            </span>
                          </div>
                          <button onClick={() => setOpen(null)} className="mt-3 w-full rounded-lg bg-white/5 py-1.5 text-[12.5px] text-white/80 hover:bg-white/10">Done</button>
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MixEditor({ axis, plan, update, locked }: { axis: Axis; plan: Plan; update: (p: Plan) => void; locked: boolean }) {
  const [edit, setEdit] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const editable = axis.name === "persona" && !locked;
  const w = (v: string) => axis.weights[v] ?? 1;
  const total = axis.values.reduce((a, v) => a + w(v), 0) || 1;

  const patch = (fn: (a: Axis) => Axis) => update({ ...plan, axes: plan.axes.map((a) => (a.name === axis.name ? fn(a) : a)) });
  const setShare = (v: string, pctVal: number) => {
    // Set this value's share, scale the others to fill the rest.
    const others = axis.values.filter((x) => x !== v);
    const otherSum = others.reduce((a, x) => a + w(x), 0) || 1;
    const p = Math.min(100, Math.max(0, pctVal)) / 100;
    const weights: Record<string, number> = { [v]: p };
    others.forEach((x) => (weights[x] = others.length ? ((1 - p) * w(x)) / otherSum : 0));
    patch((a) => ({ ...a, weights }));
  };
  const save = (old: string) => {
    const nv = name.trim() || old;
    patch((a) => {
      const descriptions = { ...a.descriptions };
      const weights = { ...a.weights };
      delete descriptions[old];
      descriptions[nv] = desc;
      if (old in weights) {
        weights[nv] = weights[old];
        if (nv !== old) delete weights[old];
      }
      return { ...a, values: a.values.map((x) => (x === old ? nv : x)), descriptions, weights };
    });
    setEdit(null);
  };
  const remove = (v: string) =>
    patch((a) => {
      const weights = { ...a.weights };
      delete weights[v];
      return { ...a, values: a.values.filter((x) => x !== v), weights };
    });

  return (
    <div>
      <Label>{axis.name === "persona" ? "Who asks" : "How hard"}</Label>
      <ul className="space-y-1.5">
        {axis.values.map((v) => {
          const share = Math.round((w(v) / total) * 100);
          return edit === v ? (
            <li key={v} className="space-y-1.5 rounded-xl border border-bob-yellow/40 p-2">
              <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Name" className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1 text-[12.5px] outline-none" />
              <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="One line about who this is" aria-label="Description" className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1 text-[12px] outline-none placeholder:text-dim" />
              <div className="flex gap-1.5">
                <Button className="!px-2.5 !py-1 text-[12px]" onClick={() => save(v)}>Save</Button>
                <Button tone="ghost" className="!px-2.5 !py-1 text-[12px]" onClick={() => setEdit(null)}>Cancel</Button>
              </div>
            </li>
          ) : (
            <li key={v} className="group flex items-center gap-2 rounded-xl bg-white/[0.03] px-2.5 py-1.5">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-white/90">{caseLabel(v)}</span>
                {axis.descriptions[v] && <span className="block truncate text-[11px] text-dim">{axis.descriptions[v]}</span>}
              </span>
              <input
                type="range"
                min={0}
                max={100}
                value={share}
                disabled={locked}
                onChange={(e) => setShare(v, Number(e.target.value))}
                aria-label={`${v} share`}
                className="w-20 accent-[var(--color-bob-blue)]"
              />
              <span className="w-9 text-right font-mono text-[12px] tabular-nums text-white/80">{share}%</span>
              {editable && (
                <>
                  <button aria-label={`Edit ${v}`} onClick={() => (setEdit(v), setName(v), setDesc(axis.descriptions[v] ?? ""))} className="text-dim opacity-60 hover:text-white group-hover:opacity-100"><Pencil className="size-3.5" /></button>
                  {axis.values.length > 1 && <button aria-label={`Remove ${v}`} onClick={() => remove(v)} className="text-dim opacity-60 hover:text-rose-300 group-hover:opacity-100"><X className="size-3.5" /></button>}
                </>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function PlanEditor({ s, jobId }: { s: JobStream; jobId: string }) {
  const nav = useNavigate();
  const [draft, setDraft] = useState<Plan>(() => structuredClone(s.plan!));
  const [advanced, setAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const original = useMemo(() => s.plan!.cells.filter((c) => c.enabled).reduce((a, c) => a + c.target, 0) || 1, [s.plan]);
  const on = draft.cells.filter((c) => c.enabled);
  const enabledTarget = on.reduce((a, c) => a + c.target, 0);
  const est = (draft.est_cost_usd * enabledTarget) / original;
  const budget = s.job?.spec.budget_usd ?? 10;
  const locked = s.status !== "awaiting_approval";
  const count = (axis: string) =>
    draft.axes.find((a) => a.name === axis)?.role === "mix"
      ? draft.axes.find((a) => a.name === axis)?.values.length ?? 0
      : new Set(on.map((c) => c.coords[axis])).size;
  const edited = useMemo(() => JSON.stringify(draft) !== JSON.stringify(s.plan), [draft, s.plan]);
  useTitle("Plan");

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.approvePlan(jobId, { ...draft, target_rows: enabledTarget });
      nav(`/jobs/${jobId}/build`);
    } catch (e) {
      setError(e as ApiError);
      setBusy(false);
    }
  };

  const action = locked ? (
    <Link to={`/jobs/${jobId}/build`} className="block rounded-xl bg-bob-blue px-4 py-2.5 text-center text-[14px]">Open the build</Link>
  ) : (
    <Button tone="yellow" className="w-full px-6 py-3 text-[16px]" busy={busy} disabled={enabledTarget === 0} onClick={start}>
      <Play className="size-4" /> Start building
    </Button>
  );

  return (
    <div className="mx-auto max-w-4xl px-4 pt-8 pb-4 sm:pb-8">
      <div className="mb-6 flex flex-wrap items-end gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[24px] font-extrabold leading-tight sm:text-[28px]">Here's the plan</h1>
          <p className="mt-1 text-[14.5px] text-white/75">
            Bob will write <b className="text-white">{enabledTarget.toLocaleString()} rows</b> across {count("topic")} topics, {count("persona")} kinds of user and {count("case_type")} kinds of question, for about{" "}
            <b className={est > budget ? "text-rose-300" : "text-white"}>{usd(est, 2)}</b> of your {usd(budget, 2)} budget.
          </p>
        </div>
        <div className="hidden sm:block">{action}</div>
      </div>
      {error && <div className="mb-4"><ErrorBanner error={error} title="Couldn't start the build" /></div>}

      {draft.notes.length > 0 && (
        <div className="mb-4 flex gap-3 rounded-2xl bg-bob-yellow/[0.07] px-4 py-3">
          <Bob pose="idea" size={40} float={false} still />
          <ul className="space-y-1 text-[13.5px] text-white/85">
            {draft.notes.slice(0, 3).map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}

      <section className="rounded-2xl bg-panel p-4">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="font-display text-[16px] font-bold">What Bob will write</h2>
          <span className="ml-auto text-[11.5px] text-dim">Click a cell to change it · click a row or column name to switch it all</span>
        </div>
        <PlanGrid plan={draft} setCells={(fn) => setDraft((d) => ({ ...d, cells: fn(d.cells) }))} />
        <div className="mt-3 flex items-center gap-3 text-[12px] text-dim">
          <span className="flex items-center gap-1.5"><span className="size-3 rounded bg-bob-blue/40" /> included</span>
          <span className="flex items-center gap-1.5"><span className="size-3 rounded border border-dashed border-white/25" /> off</span>
          {edited && !locked && (
            <button onClick={() => setDraft(structuredClone(s.plan!))} className="ml-auto flex items-center gap-1 text-bob-sky hover:underline"><RotateCcw className="size-3.5" /> Reset to Bob's plan</button>
          )}
        </div>
        {est > budget && <div className="mt-3 text-[12.5px] text-rose-300">This is over budget. Bob stops writing at 95% of the budget, or turn off some cells.</div>}
      </section>

      <button onClick={() => setAdvanced((v) => !v)} className="mt-5 flex items-center gap-2 text-[13px] text-dim hover:text-white">
        <SlidersHorizontal className="size-4" /> {advanced ? "Hide" : "Fine-tune"} who asks, how hard, and the system prompt
      </button>
      {advanced && (
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <section className="space-y-4 rounded-2xl bg-panel p-4">
            {draft.axes.filter((a) => a.role === "mix").map((a) => (
              <MixEditor key={a.name} axis={a} plan={draft} update={setDraft} locked={locked} />
            ))}
            <p className="text-[11.5px] text-dim">These mix inside every cell of the grid.</p>
          </section>
          <section className="rounded-2xl bg-panel p-4">
            <Label>System prompt (ships in every row)</Label>
            <textarea
              value={draft.system_prompt}
              disabled={locked}
              onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })}
              rows={7}
              className="scroll-thin w-full resize-y rounded-lg border border-line bg-panel-2 p-2 text-[12.5px] leading-relaxed outline-none"
            />
          </section>
        </div>
      )}
      <div className="sticky bottom-0 -mx-4 mt-6 border-t border-line bg-void/90 px-4 py-3 backdrop-blur sm:hidden">{action}</div>
    </div>
  );
}

export default function PlanScreen() {
  const { id } = useParams();
  const s = useJobStream(id);
  const [cancelError, setCancelError] = useState<ApiError | null>(null);
  useEffect(() => setCancelError(null), [id]);

  return (
    <AppShell pose={s.plan ? "idea" : readingPose(s.lastStage)} title={s.job?.spec.goal} step="plan" status={s.status} hasReport={!!s.report}>
      {s.loadError ? (
        <div className="mx-auto max-w-3xl p-6"><ErrorBanner error={s.loadError} title="Couldn't load this job" /></div>
      ) : s.plan ? (
        <PlanEditor key={s.plan.cells.length} s={s} jobId={id!} />
      ) : !s.job ? (
        <div className="grid h-full place-items-center text-dim"><Loader2 className="size-6 animate-spin" /></div>
      ) : (
        <>
          <ReadingView s={s} onCancel={() => api.cancel(id!).catch(setCancelError)} />
          {cancelError && <div className="mx-auto max-w-5xl px-4"><ErrorBanner error={cancelError} /></div>}
        </>
      )}
    </AppShell>
  );
}
