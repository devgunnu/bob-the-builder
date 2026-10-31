import { useEffect, useMemo, useState, type ReactNode } from "react";
import { motion } from "motion/react";
import { FlaskConical, Layers, MessageSquare, ScanSearch } from "lucide-react";
import type { JobClient, Row } from "../../lib/types";
import { useJob } from "../../lib/useJob";
import { Bob, type BobPose } from "../Bob";
import { MemeCarousel } from "../MemeCarousel";
import { ChatPanel } from "./ChatPanel";
import { Inspector, type InspectorTab } from "./Inspector";
import { StageRail, StatTiles } from "./Pipeline";
import { RowStream } from "./RowStream";

interface WorkspaceProps {
  client: JobClient;
  simulated: boolean;
  prompt: string;
  files: File[];
  renderComposer: (onSend: (t: string) => void) => ReactNode;
}

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 24, filter: "blur(6px)" },
  animate: { opacity: 1, y: 0, filter: "blur(0px)" },
  transition: { duration: 0.6, delay, ease: [0.2, 0.8, 0.2, 1] as const },
});

type MobileTab = "chat" | "rows" | "inspect";

export function Workspace({ client, simulated, prompt, files, renderComposer }: WorkspaceProps) {
  const job = useJob(client, prompt, files);
  const [selected, setSelected] = useState<Row | undefined>();
  const [tab, setTab] = useState<InspectorTab>("row");
  const [mobile, setMobile] = useState<MobileTab>("chat");
  const [cheering, setCheering] = useState(false);

  useEffect(() => {
    if (!job.done) return;
    setCheering(true);
    const t = window.setTimeout(() => setCheering(false), 4200);
    return () => window.clearTimeout(t);
  }, [job.done]);

  const waitingApproval = job.messages.some((m) => "card" in m && m.card === "architect" && !m.approved);
  const working = Object.values(job.stages).some((s) => s.state === "active");
  const pose: BobPose = cheering ? "cheer" : waitingApproval ? "idea" : working ? "think" : "idle";
  const title = useMemo(() => (prompt.length > 64 ? prompt.slice(0, 62) + "…" : prompt), [prompt]);

  const select = (r: Row) => {
    setSelected(r);
    setTab("row");
    setMobile("inspect");
  };
  const toExport = () => {
    setTab("export");
    setMobile("inspect");
  };

  const chat = (
    <ChatPanel messages={job.messages} pose={pose} onApprove={job.approve} onExport={toExport} composer={renderComposer(job.send)} />
  );

  return (
    <div className="flex h-full flex-col bg-void text-white">
      {/* top bar */}
      <motion.header {...rise(0.1)} className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-4">
        <Bob pose={pose} size={34} float={false} />
        <span className="font-display text-[17px] font-extrabold tracking-tight">bob</span>
        <span className="hidden truncate text-[13px] text-dim sm:block">/ {title}</span>
        <div className="ml-auto flex items-center gap-2">
          {simulated && (
            <span title="Running on the simulated engine until the backend is connected" className="flex items-center gap-1 rounded-full border border-bob-yellow/30 bg-bob-yellow/10 px-2.5 py-1 text-[11px] text-bob-yellow">
              <FlaskConical className="size-3" /> Simulated
            </span>
          )}
          <span className="rounded-full border border-line px-2.5 py-1 font-mono text-[11px] text-dim">
            {job.stats.verified.toLocaleString()} rows
          </span>
        </div>
      </motion.header>

      {/* desktop: 3 columns */}
      <div className="hidden min-h-0 flex-1 gap-3 p-3 lg:grid lg:grid-cols-[380px_minmax(0,1fr)_360px]">
        <motion.aside {...rise(0)} className="min-h-0 rounded-2xl border border-line bg-panel">
          {chat}
        </motion.aside>
        <div className="flex min-h-0 flex-col gap-3">
          <motion.div {...rise(0.2)}>
            <StageRail stages={job.stages} />
          </motion.div>
          <motion.div {...rise(0.28)}>
            <StatTiles stats={job.stats} />
          </motion.div>
          <motion.div {...rise(0.36)} className="min-h-0 flex-1">
            {job.rows.length === 0 && waitingApproval ? (
              <div className="grid h-full place-items-center rounded-2xl border border-line bg-panel">
                <MemeCarousel />
              </div>
            ) : (
              <RowStream rows={job.rows} selected={selected?.id} onSelect={select} />
            )}
          </motion.div>
        </div>
        <motion.div {...rise(0.44)} className="min-h-0">
          <Inspector row={selected} rows={job.rows} tab={tab} onTab={setTab} />
        </motion.div>
      </div>

      {/* mobile / tablet: tabs */}
      <div className="flex min-h-0 flex-1 flex-col lg:hidden">
        <div className="min-h-0 flex-1 p-3">
          {mobile === "chat" && <div className="h-full rounded-2xl border border-line bg-panel">{chat}</div>}
          {mobile === "rows" && (
            <div className="flex h-full flex-col gap-3">
              <StageRail stages={job.stages} />
              <StatTiles stats={job.stats} />
              <div className="min-h-0 flex-1">
                <RowStream rows={job.rows} selected={selected?.id} onSelect={select} />
              </div>
            </div>
          )}
          {mobile === "inspect" && <Inspector row={selected} rows={job.rows} tab={tab} onTab={setTab} />}
        </div>
        <nav className="grid grid-cols-3 border-t border-line">
          {([
            ["chat", "Chat", MessageSquare],
            ["rows", "Rows", Layers],
            ["inspect", "Inspect", ScanSearch],
          ] as const).map(([id, label, Icon]) => (
            <button key={id} onClick={() => setMobile(id)} className={`flex flex-col items-center gap-0.5 py-2 text-[11px] ${mobile === id ? "text-bob-sky" : "text-dim"}`}>
              <Icon className="size-5" />
              {label}
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
