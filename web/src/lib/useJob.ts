import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, JobClient, JobSession, Row, StageId, StageState, Stats } from "./types";
import { STAGES } from "./types";

export interface StageView {
  state: StageState;
  progress?: number;
}

const EMPTY_STATS: Stats = { generated: 0, verified: 0, rejected: 0, costUsd: 0, baselineUsd: 0 };

export function useJob(client: JobClient, prompt: string, files: File[]) {
  const session = useRef<JobSession | null>(null);
  const [stages, setStages] = useState<Record<StageId, StageView>>(
    () => Object.fromEntries(STAGES.map((s) => [s.id, { state: "pending" }])) as Record<StageId, StageView>,
  );
  const [messages, setMessages] = useState<ChatMessage[]>([{ id: "u0", from: "user", text: prompt }]);
  const [rows, setRows] = useState<Row[]>([]);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [done, setDone] = useState(false);

  useEffect(() => {
    const s = client.start({ prompt, files });
    session.current = s;
    // Rows arrive fast; batch them per animation frame.
    let pending: Row[] = [];
    let raf = 0;
    const flush = () => {
      raf = 0;
      const batch = pending;
      pending = [];
      setRows((r) => [...r, ...batch]);
    };
    const off = s.subscribe((e) => {
      switch (e.type) {
        case "stage":
          setStages((st) => ({ ...st, [e.stage]: { state: e.state, progress: e.progress } }));
          break;
        case "message":
          setMessages((m) => [...m, e.message]);
          break;
        case "row":
          pending.push(e.row);
          if (!raf) raf = requestAnimationFrame(flush);
          break;
        case "stats":
          setStats(e.stats);
          break;
        case "done":
          setDone(true);
          break;
      }
    });
    return () => {
      off();
      s.cancel();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [client, prompt, files]);

  const approve = useCallback((ids: string[]) => {
    setMessages((m) => m.map((x) => ("card" in x && x.card === "architect" ? { ...x, approved: true } : x)));
    session.current?.approve(ids);
  }, []);

  const send = useCallback((text: string) => session.current?.send(text), []);

  return { stages, messages, rows, stats, done, approve, send };
}
