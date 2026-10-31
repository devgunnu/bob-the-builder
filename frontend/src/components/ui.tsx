import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, BookCheck, BookOpen, Loader2, SearchX, ShieldQuestion, type LucideIcon } from "lucide-react";
import { Link } from "react-router";
import type { ApiError } from "../api/client";

export function Panel({ title, action, children, className = "" }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-line bg-panel ${className}`}>
      {(title || action) && (
        <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
          <h3 className="font-display text-[15px] font-bold text-white">{title}</h3>
          <div className="ml-auto">{action}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

type Tone = "primary" | "yellow" | "ghost" | "danger";
export function Button({ tone = "primary", busy, children, className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone; busy?: boolean }) {
  const tones: Record<Tone, string> = {
    primary: "bg-bob-blue text-white hover:brightness-110",
    yellow: "bg-bob-yellow text-bob-navy font-display font-bold hover:brightness-105 shadow-[0_8px_30px_-12px] shadow-bob-yellow",
    ghost: "border border-line text-white/80 hover:border-white/20 hover:text-white",
    danger: "border border-rose-400/30 text-rose-300 hover:bg-rose-400/10",
  };
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-[13.5px] transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 ${tones[tone]} ${className}`}
    >
      {busy && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  );
}

export function ErrorBanner({ error, title = "Something went wrong" }: { error: ApiError | Error | string | null | undefined; title?: string }) {
  if (!error) return null;
  const e = typeof error === "string" ? { message: error } : (error as ApiError);
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-rose-400/30 bg-rose-400/10 px-3.5 py-2.5 text-[13px] text-rose-200">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-300" />
      <div className="min-w-0">
        <div className="font-medium text-rose-100">
          {title}
          {"provider" in e && e.provider ? ` (${e.provider})` : ""}
        </div>
        <div className="break-words text-rose-200/90">{e.message}</div>
        {"detail" in e && e.detail && <div className="mt-0.5 break-words font-mono text-[11px] text-rose-200/60">{e.detail}</div>}
        {"fix" in e && e.fix && (
          <Link to={e.fix.to} className="mt-1.5 inline-block rounded-lg bg-white/10 px-2.5 py-1 text-[12.5px] text-white hover:bg-white/15">{e.fix.label} →</Link>
        )}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="grid place-items-center p-8 text-center text-[13px] text-dim">{children}</div>;
}

export function Label({ children }: { children: ReactNode }) {
  return <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-dim">{children}</div>;
}

// $0.31, $4.10, $0.004: two decimals unless the amount is under ten cents.
export const usd = (n: number | undefined | null, digits?: number) =>
  n === undefined || n === null ? "–" : `$${n.toFixed(digits ?? (n > 0 && n < 0.1 ? 3 : 2))}`;

export const pct = (n: number | undefined | null) => (n === undefined || n === null ? "–" : `${Math.round(n * 100)}%`);

export const caseLabel = (c: string) => CASE_INFO[c]?.label ?? DIFF_LABEL[c] ?? c.replace(/_/g, " ");

// Plain-language names for CONTRACTS case types and difficulties, so nobody has to learn our jargon.
export const CASE_INFO: Record<string, { label: string; hint: string; icon: LucideIcon; tone: string }> = {
  answerable: { label: "Answered by docs", hint: "The docs fully answer the question.", icon: BookCheck, tone: "text-bob-mint" },
  partial: { label: "Partly covered", hint: "The docs answer part of it; the reply says what's missing.", icon: BookOpen, tone: "text-bob-sky" },
  unanswerable: { label: "Not in docs", hint: "The docs don't cover it; the reply says so and hands off.", icon: SearchX, tone: "text-bob-yellow" },
  false_premise: { label: "Wrong assumption", hint: "The user assumes something false; the reply corrects it.", icon: ShieldQuestion, tone: "text-orange-300" },
};
export const DIFF_LABEL: Record<string, string> = { single_fact: "One fact", multi_step: "A few steps", multi_doc: "Across pages" };

export function CaseHeader({ c }: { c: string }) {
  const info = CASE_INFO[c];
  if (!info) return <span className="capitalize">{caseLabel(c)}</span>;
  const Icon = info.icon;
  return (
    <span className="flex items-center gap-1.5" title={info.hint}>
      <Icon className={`size-3.5 shrink-0 ${info.tone}`} />
      <span className="leading-tight">{info.label}</span>
    </span>
  );
}

/** Two-step button for actions that can't be undone (error prevention). */
export function ConfirmButton({ label, confirm, onConfirm, className = "" }: { label: string; confirm: string; onConfirm: () => void; className?: string }) {
  const [asking, setAsking] = useState(false);
  useEffect(() => {
    if (!asking) return;
    const t = window.setTimeout(() => setAsking(false), 5000);
    return () => window.clearTimeout(t);
  }, [asking]);
  if (!asking)
    return (
      <button onClick={() => setAsking(true)} className={`text-[12.5px] text-dim hover:text-rose-300 ${className}`}>
        {label}
      </button>
    );
  return (
    <span className={`inline-flex items-center gap-2 text-[12.5px] ${className}`}>
      <span className="text-white/80">{confirm}</span>
      <button onClick={() => (setAsking(false), onConfirm())} className="rounded-lg bg-rose-500/80 px-2.5 py-1 text-white hover:bg-rose-500">Yes, stop</button>
      <button onClick={() => setAsking(false)} className="rounded-lg px-2.5 py-1 text-dim hover:text-white">Keep going</button>
    </span>
  );
}

export function useTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · Bob` : "Bob the Builder";
  }, [title]);
}
