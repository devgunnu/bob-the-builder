import { useEffect, useState } from "react";
import { api, ApiError, subscribeJob } from "./client";
import type { BobEvent, Cell, CellUpdate, CostSummary, Job, JobStatus, Plan, Report, RowEvent, StageName } from "./types";

export interface StageProgress {
  done: number;
  total: number;
  detail: string;
}

export interface JobStream {
  job: Job | null;
  status: JobStatus | null;
  detail: string;
  stages: Partial<Record<StageName, StageProgress>>;
  lastStage: StageName | null;
  counts: Record<string, number>;
  cost: CostSummary | null;
  plan: Plan | null;
  cells: Record<string, Cell>;
  rows: RowEvent[];
  round: { n: number; reason: string; cells: string[]; planned: number } | null;
  report: Report | null;
  files: Record<string, string>;
  logs: { level: string; message: string }[];
  error: string | null;
  loadError: ApiError | null;
  connected: boolean;
}

const FEED_CAP = 200;

function cellsFrom(plan: Plan | null): Record<string, Cell> {
  return plan ? Object.fromEntries(plan.cells.map((c) => [c.id, c])) : {};
}

export function useJobStream(jobId: string | undefined): JobStream & { setReport: (r: Report) => void; setJob: (j: Job) => void } {
  const [s, setS] = useState<JobStream>({
    job: null,
    status: null,
    detail: "",
    stages: {},
    lastStage: null,
    counts: {},
    cost: null,
    plan: null,
    cells: {},
    rows: [],
    round: null,
    report: null,
    files: {},
    logs: [],
    error: null,
    loadError: null,
    connected: false,
  });

  useEffect(() => {
    if (!jobId) return;
    let alive = true;

    api
      .getJob(jobId)
      .then((job) => {
        if (!alive) return;
        setS((p) => ({
          ...p,
          job,
          status: p.status ?? job.status,
          detail: p.detail || job.stage_detail,
          counts: Object.keys(p.counts).length ? p.counts : job.counts,
          cost: p.cost ?? job.cost,
          plan: p.plan ?? job.plan,
          cells: Object.keys(p.cells).length ? p.cells : cellsFrom(job.plan),
          report: p.report ?? job.report,
          files: Object.keys(p.files).length ? p.files : job.files,
          error: p.error ?? job.error,
        }));
      })
      .catch((e: ApiError) => alive && setS((p) => ({ ...p, loadError: e })));

    const apply = (e: BobEvent) =>
      setS((p) => {
        switch (e.type) {
          case "job.status":
            return { ...p, status: e.data.status, detail: e.data.detail, connected: true };
          case "stage.progress":
            return {
              ...p,
              lastStage: e.data.stage,
              stages: { ...p.stages, [e.data.stage]: { done: e.data.done, total: e.data.total, detail: e.data.detail } },
            };
          case "counts":
            return { ...p, counts: e.data };
          case "cost":
            return { ...p, cost: e.data };
          case "plan.ready":
            return { ...p, plan: e.data, cells: cellsFrom(e.data) };
          case "cell.update": {
            const u: CellUpdate = e.data;
            const prev = p.cells[u.cell_id];
            if (!prev) return p;
            return { ...p, cells: { ...p.cells, [u.cell_id]: { ...prev, ...u } } };
          }
          case "row": {
            // a re-checked row (resync) replaces its older entry
            const rows = [e.data, ...p.rows.filter((r) => r.id !== e.data.id)];
            if (rows.length > FEED_CAP) rows.length = FEED_CAP;
            return { ...p, rows };
          }
          case "round":
            return { ...p, round: e.data };
          case "report.ready":
            return { ...p, report: e.data };
          case "files.ready":
          case "done":
            return { ...p, files: e.data.files };
          case "log":
            return { ...p, logs: [...p.logs.slice(-49), e.data] };
          case "error":
            return { ...p, error: e.data.message };
        }
      });

    const close = subscribeJob(
      jobId,
      (e) => {
        if (!alive) return;
        apply(e); // replays are de-duplicated by event id in subscribeJob; a repeated row id replaces the old entry
      },
      () => alive && setS((p) => ({ ...p, connected: false })),
    );
    return () => {
      alive = false;
      close();
    };
  }, [jobId]);

  return {
    ...s,
    setReport: (r) => setS((p) => ({ ...p, report: r })),
    setJob: (j) => setS((p) => ({ ...p, job: j, status: j.status, plan: j.plan ?? p.plan })),
  };
}
