import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { motion } from "motion/react";
import { Loader2, Pencil, Play, SlidersHorizontal, X } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Axis, Cell, Plan, StageName } from "../api/types";
import { useJobStream, type JobStream } from "../api/useJobStream";
import { AppShell } from "../components/AppShell";
import { Bob } from "../components/Bob";
import { MemeCarousel } from "../components/MemeCarousel";
import { Button, ErrorBanner, Label, caseLabel, usd } from "../components/ui";

const READ_STAGES: { id: StageName; label: string }[] = [
  { id: "fetch", label: "Fetch sources" },
  { id: "chunk", label: "Chunk and filter" },
  { id: "triage", label: "Jev triage" },
  { id: "topics", label: "Find topics" },
  { id: "evidence", label: "Extract evidence" },
  { id: "plan", label: "Draft the plan" },
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
      {failed ? <Bob pose="idle" size={140} /> : <MemeCarousel />}
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
          <button onClick={onCancel} className="mt-8 text-[12.5px] text-dim hover:text-rose-300">Cancel this job</button>
        </>
      )}
    </div>
  );
}


function PlanGrid({ plan, setCells, showFilters }: { plan: Plan; setCells: (fn: (c: Cell[]) => Cell[]) => void; showFilters: boolean }) {
  const topics = plan.axes.find((a) => a.name === "topic")?.values ?? [];
  const cases = plan.axes.find((a) => a.name === "case_type")?.values ?? [];
  const personas = plan.axes.find((a) => a.name === "persona")?.values ?? [];
  const diffs = plan.axes.find((a) => a.name === "difficulty")?.values ?? [];
  const [persona, setPersona] = useState("");
  const [diff, setDiff] = useState("");
  const [editing, setEditing] = useState<string | null>(null);

  const match = (c: Cell, t?: string, cs?: string) =>
    (!t || c.coords.topic === t) && (!cs || c.coords.case_type === cs) && (!persona || c.coords.persona === persona) && (!diff || c.coords.difficulty === diff);

  const toggle = (t?: string, cs?: string) =>
    setCells((cells) => {
      const sel = cells.filter((c) => match(c, t, cs));
      const turnOn = sel.some((c) => !c.enabled);
      return cells.map((c) => (match(c, t, cs) ? { ...c, enabled: turnOn } : c));
    });

  const setTarget = (t: string, cs: string, v: number) => setCells((cells) => cells.map((c) => (match(c, t, cs) ? { ...c, target: Math.max(0, v) } : c)));

  const sel = (label: string, value: string, set: (v: string) => void, values: string[]) =>
    values.length > 1 && (
      <label className="flex items-center gap-1.5 text-[12px] text-dim">
        {label}
        <select value={value} onChange={(e) => set(e.target.value)} className="rounded-lg border border-line bg-panel-2 px-2 py-1 text-white outline-none">
          <option value="">all</option>
          {values.map((v) => <option key={v} value={v}>{caseLabel(v)}</option>)}
        </select>
      </label>
    );

  return (
    <div>
      {showFilters && (
        <div className="mb-2 flex flex-wrap items-center gap-3">
          {sel("persona", persona, setPersona, personas)}
          {sel("difficulty", diff, setDiff, diffs)}
        </div>
      )}
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full table-fixed border-separate" style={{ borderSpacing: 4 }}>
          <colgroup>
            <col className="w-[34%] sm:w-[26%]" />
          </colgroup>
          <thead>
            <tr>
              <th />
              {cases.map((c) => (
                <th key={c} className="p-0">
                  <button onClick={() => toggle(undefined, c)} className="w-full rounded-md px-1 pb-1 text-left text-[11px] font-medium capitalize text-dim hover:text-white">{caseLabel(c)}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {topics.map((t) => (
              <tr key={t}>
                <th className="max-w-[200px] p-0 pr-2 text-left">
                  <button onClick={() => toggle(t)} title={plan.axes.find((a) => a.name === "topic")?.descriptions[t] ?? t} className="w-full truncate text-left text-[12px] font-medium text-white/80 hover:text-white">{t}</button>
                </th>
                {cases.map((cs) => {
                  const m = plan.cells.filter((c) => match(c, t, cs));
                  const on = m.filter((c) => c.enabled);
                  const sum = on.reduce((a, c) => a + c.target, 0);
                  const key = `${t}|${cs}`;
                  const partial = on.length > 0 && on.length < m.length;
                  return (
                    <td key={cs} className="p-0">
                      {editing === key ? (
                        <input
                          autoFocus
                          type="number"
                          min={0}
                          defaultValue={on[0]?.target ?? m[0]?.target ?? 0}
                          onBlur={(e) => (setTarget(t, cs, Number(e.target.value) || 0), setEditing(null))}
                          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                          className="h-9 w-full rounded-lg border border-bob-yellow bg-panel-2 text-center font-mono text-[12px] outline-none"
                        />
                      ) : (
                        <button
                          onClick={() => toggle(t, cs)}
                          onDoubleClick={() => setEditing(key)}
                          disabled={!m.length}
                          className={`h-10 w-full rounded-lg font-mono text-[12px] transition ${
                            !m.length ? "opacity-20" : on.length ? "bg-bob-blue/30 text-white hover:bg-bob-blue/45" : "bg-white/[0.02] text-dim/60 hover:text-white"
                          }`}
                          title={`${sum} rows · click to turn ${on.length ? "off" : "on"} · double-click to change rows`}
                        >
                          {on.length ? sum : "off"}
                          {partial && <span className="ml-1 text-[9px] text-bob-yellow">{on.length}/{m.length}</span>}
                        </button>
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

function AxisEditor({ axis, plan, update }: { axis: Axis; plan: Plan; update: (p: Plan) => void }) {
  const [edit, setEdit] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const editable = axis.name === "persona";
  const activeValues = new Set(plan.cells.filter((c) => c.enabled).map((c) => c.coords[axis.name]));

  const toggleValue = (v: string) => {
    const on = activeValues.has(v);
    update({ ...plan, cells: plan.cells.map((c) => (c.coords[axis.name] === v ? { ...c, enabled: !on } : c)) });
  };

  const save = (old: string) => {
    const nv = name.trim() || old;
    const axes = plan.axes.map((a) => {
      if (a.name !== axis.name) return a;
      const descriptions = { ...a.descriptions };
      delete descriptions[old];
      descriptions[nv] = desc;
      return { ...a, values: a.values.map((x) => (x === old ? nv : x)), descriptions };
    });
    // Rename in place: cell ids stay stable (CONTRACTS / G3 pitfall).
    const cells = plan.cells.map((c) => (c.coords[axis.name] === old ? { ...c, coords: { ...c.coords, [axis.name]: nv } } : c));
    update({ ...plan, axes, cells });
    setEdit(null);
  };

  const remove = (v: string) => {
    const axes = plan.axes.map((a) => (a.name === axis.name ? { ...a, values: a.values.filter((x) => x !== v) } : a));
    const cells = plan.cells.map((c) => (c.coords[axis.name] === v ? { ...c, enabled: false } : c));
    update({ ...plan, axes, cells });
  };

  return (
    <div>
      <Label>{{ topic: "Topics", persona: "Personas", case_type: "Case types", difficulty: "Difficulty" }[axis.name]}</Label>
      <div className="flex flex-wrap gap-1.5">
        {axis.values.map((v) =>
          edit === v ? (
            <div key={v} className="w-full space-y-1.5 rounded-xl border border-bob-yellow/40 p-2">
              <input value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1 text-[12.5px] outline-none" />
              <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="One line about who this is" className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1 text-[12px] outline-none placeholder:text-dim" />
              <div className="flex gap-1.5">
                <Button className="!px-2.5 !py-1 text-[12px]" onClick={() => save(v)}>Save</Button>
                <Button tone="ghost" className="!px-2.5 !py-1 text-[12px]" onClick={() => setEdit(null)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <span
              key={v}
              title={axis.descriptions[v]}
              className={`group flex items-center gap-1 rounded-full border px-2.5 py-1 text-[12px] transition ${activeValues.has(v) ? "border-bob-sky/40 bg-bob-blue/10 text-white" : "border-line text-dim line-through"}`}
            >
              <button onClick={() => toggleValue(v)}>{caseLabel(v)}</button>
              {editable && (
                <>
                  <button aria-label={`Edit ${v}`} onClick={() => (setEdit(v), setName(v), setDesc(axis.descriptions[v] ?? ""))} className="text-dim opacity-60 hover:text-white group-hover:opacity-100"><Pencil className="size-3" /></button>
                  <button aria-label={`Remove ${v}`} onClick={() => remove(v)} className="text-dim opacity-60 hover:text-rose-300 group-hover:opacity-100"><X className="size-3" /></button>
                </>
              )}
            </span>
          ),
        )}
      </div>
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
  const count = (axis: string) => new Set(on.map((c) => c.coords[axis])).size;

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

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[28px] font-extrabold leading-tight">Here's the plan</h1>
          <p className="mt-1 text-[14.5px] text-white/75">
            Bob will write <b className="text-white">{enabledTarget.toLocaleString()} rows</b> across {count("topic")} topics, {count("persona")} kinds of user and {count("case_type")} kinds of question, for about{" "}
            <b className={est > budget ? "text-rose-300" : "text-white"}>{usd(est, 2)}</b> of your {usd(budget, 2)} budget.
          </p>
        </div>
        {locked ? (
          <Link to={`/jobs/${jobId}/build`} className="rounded-xl bg-bob-blue px-4 py-2.5 text-[14px]">Open the build</Link>
        ) : (
          <Button tone="yellow" className="px-6 py-3 text-[16px]" busy={busy} disabled={enabledTarget === 0} onClick={start}>
            <Play className="size-4" /> Start building
          </Button>
        )}
      </div>
      {error && <div className="mb-4"><ErrorBanner error={error} title="Couldn't start the build" /></div>}

      {draft.notes.length > 0 && (
        <div className="mb-4 flex gap-3 rounded-2xl bg-bob-yellow/[0.07] px-4 py-3">
          <Bob pose="idea" size={40} float={false} />
          <ul className="space-y-1 text-[13.5px] text-white/85">
            {draft.notes.slice(0, 3).map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}

      <section className="rounded-2xl bg-panel p-4">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="font-display text-[16px] font-bold">What Bob will write</h2>
          <span className="ml-auto text-[11.5px] text-dim">Click to turn on or off · double-click to change rows</span>
        </div>
        <PlanGrid plan={draft} showFilters={advanced} setCells={(fn) => setDraft((d) => ({ ...d, cells: fn(d.cells) }))} />
        {est > budget && <div className="mt-3 text-[12.5px] text-rose-300">This is over budget. Bob stops writing at 95% of the budget, or turn off some cells.</div>}
      </section>

      <button onClick={() => setAdvanced((v) => !v)} className="mt-5 flex items-center gap-2 text-[13px] text-dim hover:text-white">
        <SlidersHorizontal className="size-4" /> {advanced ? "Hide" : "Fine-tune"} personas, difficulty and the system prompt
      </button>
      {advanced && (
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          <section className="space-y-4 rounded-2xl bg-panel p-4">
            {draft.axes.filter((a) => a.name === "persona" || a.name === "difficulty").map((a) => (
              <AxisEditor key={a.name} axis={a} plan={draft} update={setDraft} />
            ))}
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
    </div>
  );
}

export default function PlanScreen() {
  const { id } = useParams();
  const s = useJobStream(id);
  const [cancelError, setCancelError] = useState<ApiError | null>(null);
  useEffect(() => setCancelError(null), [id]);

  return (
    <AppShell pose={s.plan ? "idea" : "think"} title={s.job?.spec.goal}>
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
