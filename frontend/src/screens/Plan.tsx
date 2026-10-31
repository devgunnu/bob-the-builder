import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { motion } from "motion/react";
import { Check, Loader2, Pencil, Play, X } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Axis, Cell, Plan, StageName } from "../api/types";
import { useJobStream, type JobStream } from "../api/useJobStream";
import { AppShell } from "../components/AppShell";
import { Bob } from "../components/Bob";
import { MemeCarousel } from "../components/MemeCarousel";
import { Button, ErrorBanner, Label, Panel, caseLabel, usd } from "../components/ui";

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
  return (
    <div className="mx-auto grid max-w-5xl gap-4 px-4 py-6 lg:grid-cols-[1.2fr_1fr]">
      <Panel title="Reading your material" action={!failed && <Button tone="danger" className="!px-3 !py-1 text-[12px]" onClick={onCancel}>Cancel</Button>}>
        <div className="mb-3 text-[13px] text-dim">{s.detail || "Starting…"}</div>
        <ol className="space-y-2.5">
          {READ_STAGES.map((st, i) => {
            const p = s.stages[st.id];
            const idx = READ_STAGES.findIndex((x) => x.id === s.lastStage);
            const done = (p && p.total > 0 && p.done >= p.total) || (idx > i) || !!s.plan;
            const active = !done && s.lastStage === st.id;
            const ratio = p && p.total ? p.done / p.total : 0;
            return (
              <li key={st.id} className="flex items-center gap-3">
                <span className={`grid size-5 shrink-0 place-items-center rounded-full text-[10px] font-bold ${done ? "bg-bob-mint text-bob-navy" : active ? "bg-bob-blue text-white" : "bg-white/10 text-dim"}`}>
                  {done ? <Check className="size-3.5" /> : active ? <Loader2 className="size-3 animate-spin" /> : i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-[13px]">
                    <span className={done || active ? "text-white" : "text-dim"}>{st.label}</span>
                    {p && p.total > 0 && <span className="ml-auto font-mono text-[11px] text-dim">{p.done}/{p.total}</span>}
                  </div>
                  {active && (
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/5">
                      <motion.div className="h-full bg-bob-sky" animate={{ width: `${Math.max(6, ratio * 100)}%` }} />
                    </div>
                  )}
                  {active && p?.detail && <div className="mt-0.5 truncate text-[11.5px] text-dim">{p.detail}</div>}
                </div>
              </li>
            );
          })}
        </ol>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center sm:grid-cols-5">
          {(["docs", "chunks", "chunks_kept", "topics", "evidence"] as const).map((k) => (
            <div key={k} className="rounded-xl bg-white/[0.03] p-2">
              <div className="font-display text-[18px] font-bold">{(s.counts[k] ?? 0).toLocaleString()}</div>
              <div className="text-[10.5px] text-dim">{k.replace("_", " ")}</div>
            </div>
          ))}
        </div>
        {(s.error || s.status === "error") && <div className="mt-4"><ErrorBanner error={s.error ?? "The job stopped with an error."} /></div>}
        {s.logs.filter((l) => l.level !== "info").slice(-3).map((l, i) => (
          <div key={i} className="mt-2 rounded-lg bg-bob-yellow/10 px-3 py-1.5 text-[12px] text-bob-yellow">{l.message}</div>
        ))}
      </Panel>
      <div className="grid place-items-center rounded-2xl border border-line bg-panel p-6">
        <MemeCarousel />
      </div>
    </div>
  );
}

type Mode = "toggle" | "target";

function PlanGrid({ plan, setCells, mode }: { plan: Plan; setCells: (fn: (c: Cell[]) => Cell[]) => void; mode: Mode }) {
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
      <div className="mb-2 flex flex-wrap items-center gap-3">
        {sel("persona", persona, setPersona, personas)}
        {sel("difficulty", diff, setDiff, diffs)}
        <span className="ml-auto text-[11.5px] text-dim">{mode === "toggle" ? "Click a cell, row or column to turn it on or off" : "Click a cell to set the target for each matching cell"}</span>
      </div>
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
                          onClick={() => (mode === "toggle" ? toggle(t, cs) : setEditing(key))}
                          disabled={!m.length}
                          className={`h-9 w-full rounded-lg font-mono text-[11.5px] transition ${
                            !m.length ? "opacity-20" : on.length ? "bg-bob-blue/25 text-white ring-1 ring-bob-sky/40 hover:bg-bob-blue/35" : "bg-[repeating-linear-gradient(45deg,rgba(255,255,255,0.04)_0_4px,transparent_4px_8px)] text-dim hover:text-white"
                          } ${partial ? "ring-dashed" : ""}`}
                          title={`${m.length} cells · ${on.length} on · ${sum} rows`}
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
  const [mode, setMode] = useState<Mode>("toggle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const original = useMemo(() => s.plan!.cells.filter((c) => c.enabled).reduce((a, c) => a + c.target, 0) || 1, [s.plan]);
  const enabledTarget = draft.cells.filter((c) => c.enabled).reduce((a, c) => a + c.target, 0);
  const est = (draft.est_cost_usd * enabledTarget) / original;
  const budget = s.job?.spec.budget_usd ?? 10;
  const locked = s.status !== "awaiting_approval";

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
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Bob pose="idea" size={56} />
        <div className="min-w-0">
          <h1 className="font-display text-[24px] font-extrabold leading-tight">The coverage plan</h1>
          <p className="truncate text-[13px] text-dim">{draft.goal}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {locked ? (
            <Link to={`/jobs/${jobId}/build`} className="rounded-xl bg-bob-blue px-4 py-2 text-[13.5px]">Plan approved, open the build</Link>
          ) : (
            <Button tone="yellow" className="px-5 py-2.5 text-[15px]" busy={busy} disabled={enabledTarget === 0} onClick={start}>
              <Play className="size-4" /> Start building {enabledTarget.toLocaleString()} rows
            </Button>
          )}
        </div>
      </div>
      {error && <div className="mb-4"><ErrorBanner error={error} title="Couldn't start the build" /></div>}

      <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)_300px]">
        <Panel title="Axes">
          <div className="space-y-4">
            {draft.axes.map((a) => (
              <AxisEditor key={a.name} axis={a} plan={draft} update={setDraft} />
            ))}
          </div>
        </Panel>

        <Panel
          title="Topic × case type"
          action={
            <div className="flex rounded-lg border border-line p-0.5 text-[12px]">
              {(["toggle", "target"] as Mode[]).map((m) => (
                <button key={m} onClick={() => setMode(m)} className={`rounded-md px-2.5 py-0.5 ${mode === m ? "bg-white/10 text-white" : "text-dim"}`}>
                  {m === "toggle" ? "On / off" : "Targets"}
                </button>
              ))}
            </div>
          }
        >
          <PlanGrid plan={draft} mode={mode} setCells={(fn) => setDraft((d) => ({ ...d, cells: fn(d.cells) }))} />
        </Panel>

        <div className="space-y-4">
          <Panel title="Estimate">
            <div className="flex items-baseline gap-2">
              <span className="font-display text-[28px] font-bold">{usd(est, 2)}</span>
              <span className="text-[12.5px] text-dim">of {usd(budget, 2)} budget</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5">
              <div className={`h-full ${est > budget ? "bg-rose-400" : "bg-bob-mint"}`} style={{ width: `${Math.min(100, (est / budget) * 100)}%` }} />
            </div>
            <div className="mt-2 text-[12px] text-dim">
              {enabledTarget.toLocaleString()} rows across {draft.cells.filter((c) => c.enabled).length} cells. Planner estimate, scaled to your edits.
            </div>
            {est > budget && <div className="mt-2 text-[12px] text-rose-300">Over budget: Bob stops writing at 95% of the budget.</div>}
          </Panel>
          {draft.notes.length > 0 && (
            <Panel title="Notes from the Planner">
              <ul className="space-y-2 text-[13px] text-white/85">
                {draft.notes.map((n, i) => (
                  <li key={i} className="flex gap-2"><span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-bob-yellow" />{n}</li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="System prompt">
            <textarea
              value={draft.system_prompt}
              disabled={locked}
              onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })}
              rows={6}
              className="scroll-thin w-full resize-y rounded-lg border border-line bg-panel-2 p-2 text-[12.5px] leading-relaxed outline-none"
            />
            <div className="mt-1 text-[11px] text-dim">Ships in every exported row.</div>
          </Panel>
        </div>
      </div>
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
