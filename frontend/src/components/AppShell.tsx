import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useParams } from "react-router";
import { History, X } from "lucide-react";
import { api } from "../api/client";
import type { Health } from "../api/types";
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

const STEPS = [
  { to: "plan", label: "Plan" },
  { to: "build", label: "Build" },
  { to: "report", label: "Report" },
] as const;

export function AppShell({ pose = "idle", title, children }: { pose?: BobPose; title?: ReactNode; children: ReactNode }) {
  const { id } = useParams();
  return (
    <div className="flex h-full flex-col bg-void text-white">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-4">
        <Link to="/" className="flex items-center gap-2" aria-label="Bob home">
          <Bob pose={pose} size={34} float={false} />
          <span className="font-display text-[17px] font-extrabold tracking-tight">bob</span>
        </Link>
        {title && <span className="hidden min-w-0 truncate text-[13px] text-dim sm:block">/ {title}</span>}
        {id && (
          <nav className="ml-2 hidden items-center gap-1 rounded-xl border border-line p-0.5 sm:flex">
            {STEPS.map((s) => (
              <NavLink
                key={s.to}
                to={`/jobs/${id}/${s.to}`}
                className={({ isActive }) => `rounded-lg px-3 py-1 text-[12.5px] transition ${isActive ? "bg-white/10 text-white" : "text-dim hover:text-white"}`}
              >
                {s.label}
              </NavLink>
            ))}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-2">
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
