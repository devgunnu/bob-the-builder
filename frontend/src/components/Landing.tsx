import { useEffect, type ReactNode } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform, type MotionValue } from "motion/react";
import { CheckCircle2, FileText, Globe, XCircle } from "lucide-react";
import { Bob } from "./Bob";
import { MemeCarousel } from "./MemeCarousel";

function DataCube({ size = 56, glow = false }: { size?: number; glow?: boolean }) {
  // Isometric cube in Bob's style: blue faces, a grid of light dots.
  const dots = (ox: number, oy: number, dx: [number, number], dy: [number, number], fill: string) =>
    Array.from({ length: 9 }, (_, k) => {
      const i = k % 3;
      const j = Math.floor(k / 3);
      return <circle key={k} cx={ox + (i + 1) * dx[0] + (j + 1) * dy[0]} cy={oy + (i + 1) * dx[1] + (j + 1) * dy[1]} r={2.3} fill={fill} />;
    });
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" className={glow ? "drop-shadow-[0_0_14px_rgba(77,139,255,0.8)]" : ""}>
      <polygon points="50,8 90,30 50,52 10,30" fill="#4d8bff" stroke="#0b1533" strokeWidth="4" strokeLinejoin="round" />
      <polygon points="10,30 50,52 50,94 10,72" fill="#1f5bff" stroke="#0b1533" strokeWidth="4" strokeLinejoin="round" />
      <polygon points="90,30 50,52 50,94 90,72" fill="#1846c9" stroke="#0b1533" strokeWidth="4" strokeLinejoin="round" />
      {dots(10, 30, [10, 5.5], [0, 10.5], "#63f0cf")}
      {dots(50, 52, [10, -5.5], [0, 10.5], "#cfe0ff")}
    </svg>
  );
}

function Chip({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-bob-navy/10 bg-white/90 px-3 py-2 font-mono text-[12px] text-bob-navy/75 shadow-[0_8px_24px_-12px_rgba(11,21,51,0.35)] backdrop-blur">
      {icon}
      {label}
    </div>
  );
}

function RowCard({ q, a, ok = true }: { q: string; a: string; ok?: boolean }) {
  return (
    <div className="w-60 rounded-2xl border border-bob-navy/10 bg-white/95 p-3 text-left shadow-[0_14px_40px_-18px_rgba(11,21,51,0.45)]">
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium">
        {ok ? (
          <span className="flex items-center gap-1 text-emerald-600">
            <CheckCircle2 className="size-3.5" /> verified against source
          </span>
        ) : (
          <span className="flex items-center gap-1 text-rose-500">
            <XCircle className="size-3.5" /> rejected: invented feature
          </span>
        )}
      </div>
      <p className="text-[12.5px] font-medium leading-snug text-bob-navy">{q}</p>
      <p className="mt-1 text-[12px] leading-snug text-bob-navy/60">{a}</p>
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: "yellow" | "mint" | "blue" }) {
  const tones = {
    yellow: "bg-bob-yellow text-bob-navy",
    mint: "bg-bob-mint text-bob-navy",
    blue: "bg-bob-blue text-white",
  };
  return <div className={`rounded-lg border-2 border-bob-navy px-2.5 py-1 font-mono text-[12px] font-medium ${tones[tone]}`}>{label}</div>;
}

function Pixel({ c, s = 12 }: { c: string; s?: number }) {
  return <div className="rounded-[3px]" style={{ width: s, height: s, background: c }} />;
}

function MemeCard() {
  return (
    <div className="w-56 rounded-2xl border border-bob-navy/10 bg-white/95 p-3 shadow-[0_14px_40px_-18px_rgba(11,21,51,0.45)]">
      <MemeCarousel compact />
    </div>
  );
}

interface FloaterSpec {
  x: string; // left %
  y: string; // top %
  depth: number; // parallax strength
  bob: number; // vertical drift px
  dur: number;
  rot?: number;
  hideSm?: boolean;
  node: ReactNode;
}

const FLOATERS: FloaterSpec[] = [
  { x: "8%", y: "12%", depth: 26, bob: 12, dur: 6, rot: -6, node: <DataCube size={70} glow /> },
  { x: "80%", y: "9%", depth: 18, bob: 10, dur: 7, rot: 8, hideSm: true, node: <Chip icon={<Globe className="size-3.5 text-bob-blue" />} label="docs.firecrawl.dev" /> },
  { x: "70%", y: "24%", depth: 30, bob: 16, dur: 8, rot: 3, hideSm: true, node: <RowCard q="How do I stop a crawl at 50 pages?" a="Set limit: 50 on the crawl request." /> },
  { x: "5%", y: "58%", depth: 22, bob: 14, dur: 7.5, rot: -3, hideSm: true, node: <RowCard q="Is there a setting for webhook retries?" a="Our docs don't cover that. I'll hand you to a teammate." /> },
  { x: "14%", y: "36%", depth: 12, bob: 8, dur: 5.5, rot: -10, hideSm: true, node: <Chip icon={<FileText className="size-3.5 text-rose-500" />} label="Notion · Support FAQ" /> },
  { x: "77%", y: "40%", depth: 22, bob: 10, dur: 7.5, rot: 4, hideSm: true, node: <MemeCard /> },
  { x: "76%", y: "74%", depth: 20, bob: 10, dur: 7, rot: -4, hideSm: true, node: <RowCard ok={false} q="Can I export crawls as PDF?" a="Yes, use the bulk PDF export setting." /> },
  { x: "30%", y: "80%", depth: 16, bob: 9, dur: 6, rot: 6, node: <Badge label="train.jsonl" tone="yellow" /> },
  { x: "56%", y: "86%", depth: 26, bob: 11, dur: 6.8, rot: -8, node: <Badge label=".parquet" tone="mint" /> },
  { x: "40%", y: "8%", depth: 14, bob: 8, dur: 5.8, rot: 4, hideSm: true, node: <Badge label="openai-chat" tone="blue" /> },
  { x: "62%", y: "6%", depth: 10, bob: 6, dur: 5, node: <Pixel c="#63f0cf" s={14} /> },
  { x: "24%", y: "22%", depth: 28, bob: 10, dur: 6, node: <Pixel c="#1f5bff" s={10} /> },
  { x: "92%", y: "34%", depth: 12, bob: 7, dur: 5.4, node: <Pixel c="#ffc82e" s={12} /> },
  { x: "20%", y: "70%", depth: 24, bob: 9, dur: 6.4, node: <Pixel c="#63f0cf" s={9} /> },
  { x: "48%", y: "72%", depth: 8, bob: 6, dur: 7, hideSm: true, node: <Pixel c="#4d8bff" s={8} /> },
  { x: "88%", y: "84%", depth: 30, bob: 14, dur: 7.2, rot: -4, node: <Bob pose="cheer" size={120} float={false} /> },
  { x: "2%", y: "84%", depth: 14, bob: 8, dur: 6, rot: 10, hideSm: true, node: <DataCube size={38} /> },
];

function Floater({ spec, mx, my, index }: { spec: FloaterSpec; mx: MotionValue<number>; my: MotionValue<number>; index: number }) {
  const reduce = useReducedMotion();
  const px = useTransform(mx, (v) => v * spec.depth);
  const py = useTransform(my, (v) => v * spec.depth);
  // Direction away from the centre, for the scatter on exit.
  const cx = parseFloat(spec.x) - 50;
  const cy = parseFloat(spec.y) - 50;
  const len = Math.hypot(cx, cy) || 1;

  return (
    <motion.div
      className={`absolute ${spec.hideSm ? "hidden md:block" : ""}`}
      style={{ left: spec.x, top: spec.y, x: px, y: py }}
      initial={{ opacity: 0, scale: 0.6 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{
        opacity: 0,
        scale: 0.4,
        x: (cx / len) * 600,
        y: (cy / len) * 600,
        filter: "blur(8px)",
        transition: { duration: 0.7, ease: [0.6, 0, 0.8, 0.4], delay: index * 0.012 },
      }}
      transition={{ duration: 0.8, delay: 0.15 + index * 0.05, ease: "backOut" }}
    >
      <motion.div
        animate={reduce ? undefined : { y: [0, -spec.bob, 0], rotate: [spec.rot ?? 0, (spec.rot ?? 0) + 2, spec.rot ?? 0] }}
        transition={{ duration: spec.dur, repeat: Infinity, ease: "easeInOut", delay: index * 0.3 }}
      >
        {spec.node}
      </motion.div>
    </motion.div>
  );
}

export function LandingField() {
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const sx = useSpring(mx, { stiffness: 40, damping: 18 });
  const sy = useSpring(my, { stiffness: 40, damping: 18 });

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      mx.set(e.clientX / window.innerWidth - 0.5);
      my.set(e.clientY / window.innerHeight - 0.5);
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, [mx, my]);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {FLOATERS.map((f, i) => (
        <Floater key={i} spec={f} mx={sx} my={sy} index={i} />
      ))}
    </div>
  );
}

export function LandingBackdrop() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <div className="dot-grid absolute inset-0" />
      <div className="absolute left-1/2 top-1/2 size-[900px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(77,139,255,0.18),transparent_60%)]" />
      <div className="absolute -left-40 -top-40 size-[520px] rounded-full bg-[radial-gradient(circle,rgba(99,240,207,0.22),transparent_65%)]" />
      <div className="absolute -bottom-48 -right-40 size-[560px] rounded-full bg-[radial-gradient(circle,rgba(255,200,46,0.22),transparent_65%)]" />
    </div>
  );
}

export function LandingHeader({ sleeping = false }: { sleeping?: boolean }) {
  return (
    <motion.div
      className="mb-7 flex flex-col items-center text-center"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -40, scale: 0.9, transition: { duration: 0.45 } }}
      transition={{ duration: 0.7, delay: 0.1 }}
    >
      <Bob pose={sleeping ? "sleep" : "wave"} size={150} float={!sleeping} />
      <h1 className="mt-1 font-display text-[34px] font-extrabold leading-none tracking-tight text-bob-navy sm:text-[44px]">
        What should Bob build?
      </h1>
      <p className="mt-3 max-w-md text-[15px] text-bob-navy/60">
        Point him at your docs. He builds a fine-tuning dataset where every row is checked against its source.
      </p>
    </motion.div>
  );
}
