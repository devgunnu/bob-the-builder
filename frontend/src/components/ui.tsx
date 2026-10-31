import type { ButtonHTMLAttributes, ReactNode } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
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

export const usd = (n: number | undefined | null, digits?: number) =>
  n === undefined || n === null ? "–" : `$${n.toFixed(digits ?? (n < 1 ? 3 : 2))}`;

export const pct = (n: number | undefined | null) => (n === undefined || n === null ? "–" : `${Math.round(n * 100)}%`);

export const caseLabel = (c: string) => c.replace(/_/g, " ");
