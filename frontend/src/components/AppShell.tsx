import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { Check, FileCheck2, Hammer, History, Link2, Map, X } from "lucide-react";
import { api } from "../api/client";
import type { Health, JobStatus } from "../api/types";
import { Bob, type BobPose } from "./Bob";

// Quiet by default: nothing when every provider is healthy, one chip when something is wrong.
function HealthChips() {
  const [h, setH] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .health()
        .then((x) => alive && (setH(x), setDown(false)))
        .catch(() => alive && setDown(true));
    load();
    const t = window.setInterval(load, 60_000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, []);
  if (down) return <span className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2.5 py-1 text-[11px] text-rose-300">API offline</span>;
  if (!h) return null;
  const bad = Object.entries(h.keys).filter(([, v]) => v !== "ok");
  if (!bad.length) return <span title="All services are reachable" className="size-2 rounded-full bg-bob-mint/80" />;
  return (
    <span title={bad.map(([k, v]) => `${k}: ${v}`).join("\n")} className="flex items-center gap-1 rounded-full border border-rose-400/30 bg-rose-400/10 px-2.5 py-1 text-[11px] text-rose-300">
      <X className="size-3" /> {bad.map(([k]) => k).join(", ")} unavailable
    </span>
  );
}

type Step = "sources" | "plan" | "build" | "report";
const STEPS: { id: Step; label: string; icon: typeof Link2 }[] = [
  { id: "sources", label: "Sources", icon: Link2 },
  { id: "plan", label: "Plan", icon: Map },
  { id: "build", label: "Build", icon: Hammer },
  { id: "report", label: "Report", icon: FileCheck2 },
];

// Which steps the job has reached, so later steps are never opened empty.
function reached(status: JobStatus | null | undefined, hasReport: boolean): Record<Step, boolean> {
  const building = ["building", "filling_gaps", "reporting", "done"].includes(status ?? "");
  return { sources: true, plan: !!status, build: building, report: hasReport || status === "reporting" || status === "done" };
}

function Journey({ current, status, hasReport }: { current: Step; status?: JobStatus | null; hasReport?: boolean }) {
  const { id } = useParams();
  const ok = reached(status, !!hasReport);
  const idx = STEPS.findIndex((s) => s.id === current);
  return (
    <nav aria-label="Progress" className="flex items-center gap-1">
      {STEPS.map((s, i) => {
        const Icon = s.icon;
        const done = i < idx;
        const here = i === idx;
        const enabled = s.id === "sources" ? false : id && ok[s.id];
        const pill = (
          <span
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12.5px] transition ${
              here ? "bg-bob-blue text-white" : done ? "text-bob-mint" : enabled ? "text-white/70 hover:bg-white/5 hover:text-white" : "text-white/25"
            }`}
          >
            {done ? <Check className="size-3.5" /> : <Icon className="size-3.5" />}
            <span className="hidden md:inline">{s.label}</span>
          </span>
        );
        return (
          <span key={s.id} className="flex items-center gap-1">
            {i > 0 && <span className={`h-px w-3 sm:w-5 ${i <= idx ? "bg-bob-mint/50" : "bg-white/10"}`} />}
            {enabled && !here ? (
              <Link to={`/jobs/${id}/${s.id}`} aria-label={s.label}>{pill}</Link>
            ) : (
              <span aria-current={here ? "step" : undefined} aria-label={s.label}>{pill}</span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

interface ShellProps {
  pose?: BobPose;
  title?: ReactNode;
  step?: Step;
  status?: JobStatus | null;
  hasReport?: boolean;
  children: ReactNode;
}

export function AppShell({ pose = "idle", title, step, status, hasReport, children }: ShellProps) {
  return (
    <div className="flex h-full flex-col bg-void text-white">
      <header className="grid h-14 shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-line px-4">
        <div className="flex min-w-0 items-center gap-2">
          <Link to="/" className="flex shrink-0 items-center gap-2" aria-label="Bob home">
            <Bob pose={pose} size={34} float={false} still />
            <span className="font-display text-[17px] font-extrabold tracking-tight">bob</span>
          </Link>
          {title && <span className="hidden min-w-0 truncate text-[13px] text-dim lg:block">/ {title}</span>}
        </div>
        {step ? <Journey current={step} status={status} hasReport={hasReport} /> : <span />}
        <div className="flex items-center justify-end gap-2">
          <HealthChips />
          <Link to="/jobs" title="Your jobs" aria-label="Your jobs" className="grid size-8 place-items-center rounded-full text-dim hover:bg-white/5 hover:text-white">
            <History className="size-4" />
          </Link>
        </div>
      </header>
      <main className="scroll-thin min-h-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
