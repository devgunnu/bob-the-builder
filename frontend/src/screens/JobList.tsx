import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Plus } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Job, JobStatus } from "../api/types";
import { AppShell } from "../components/AppShell";
import { Bob } from "../components/Bob";
import { Empty, ErrorBanner, usd } from "../components/ui";

const STATUS_TONE: Partial<Record<JobStatus, string>> = {
  done: "text-bob-mint border-bob-mint/30",
  error: "text-rose-300 border-rose-400/30",
  cancelled: "text-dim border-line",
  awaiting_approval: "text-bob-yellow border-bob-yellow/30",
};

export function routeFor(job: Job): string {
  if (job.status === "done" || job.status === "reporting") return `/jobs/${job.id}/report`;
  if (["building", "filling_gaps"].includes(job.status)) return `/jobs/${job.id}/build`;
  return `/jobs/${job.id}/plan`;
}

export default function JobList() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    api.listJobs().then(setJobs).catch(setError);
  }, []);

  return (
    <AppShell title="Jobs">
      <div className="mx-auto max-w-4xl px-4 py-6">
        <div className="mb-4 flex items-center gap-3">
          <h1 className="font-display text-[26px] font-extrabold">Jobs</h1>
          <Link to="/" className="ml-auto flex items-center gap-1.5 rounded-xl bg-bob-blue px-3.5 py-2 text-[13px] hover:brightness-110">
            <Plus className="size-4" /> New dataset
          </Link>
        </div>
        <ErrorBanner error={error} title="Couldn't load jobs" />
        {jobs === null && !error && <Empty>Loading…</Empty>}
        {jobs?.length === 0 && (
          <Empty>
            <Bob pose="wave" size={120} />
            <p className="mt-2">No jobs yet. Start one from the home page.</p>
          </Empty>
        )}
        <ul className="space-y-2">
          {jobs?.map((j) => (
            <li key={j.id}>
              <Link to={routeFor(j)} className="flex items-center gap-3 rounded-2xl border border-line bg-panel px-4 py-3 transition hover:border-white/15">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[14px] text-white">{j.spec.goal}</div>
                  <div className="mt-0.5 text-[11.5px] text-dim">
                    {new Date(j.created_at).toLocaleString()} · {(j.counts.kept ?? 0).toLocaleString()} kept · {usd(j.cost?.total_usd)}
                  </div>
                </div>
                <span className={`rounded-full border px-2.5 py-0.5 text-[11px] ${STATUS_TONE[j.status] ?? "border-bob-sky/30 text-bob-sky"}`}>{j.status.replace(/_/g, " ")}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </AppShell>
  );
}
