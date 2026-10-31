import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { ArrowUp, Paperclip, X } from "lucide-react";

export const SUGGESTIONS = [
  "Turn docs.convex.dev into a support assistant that never invents an API",
  "Build 5,000 Q&A rows from my product manual, with sources",
  "Make preference pairs that teach my model to say “that isn't documented”",
  "Generate JSON extraction examples from these invoices",
  "Train a small model to answer in our support team's style",
  "Create multi-turn chats from our API reference, verified row by row",
];

// Types a suggestion, holds it, erases it, moves to the next.
function useGhostText(active: boolean) {
  const reduce = useReducedMotion();
  const [idx, setIdx] = useState(0);
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<"typing" | "hold" | "erasing">("typing");

  useEffect(() => {
    if (!active) return;
    const full = SUGGESTIONS[idx];
    if (reduce) {
      setText(full);
      const t = window.setTimeout(() => setIdx((i) => (i + 1) % SUGGESTIONS.length), 3500);
      return () => window.clearTimeout(t);
    }
    let t: number;
    if (phase === "typing") {
      if (text.length < full.length) t = window.setTimeout(() => setText(full.slice(0, text.length + 1)), 28 + Math.random() * 40);
      else t = window.setTimeout(() => setPhase("hold"), 0);
    } else if (phase === "hold") {
      t = window.setTimeout(() => setPhase("erasing"), 2200);
    } else {
      if (text.length > 0) t = window.setTimeout(() => setText(text.slice(0, -2)), 14);
      else
        t = window.setTimeout(() => {
          setIdx((i) => (i + 1) % SUGGESTIONS.length);
          setPhase("typing");
        }, 250);
    }
    return () => window.clearTimeout(t);
  }, [active, idx, text, phase, reduce]);

  return { ghost: text, full: SUGGESTIONS[idx] };
}

interface ComposerProps {
  variant: "landing" | "workspace";
  intensity?: "calm" | "bright";
  locked?: string;
  disabled?: boolean;
  onSubmit: (text: string, files: File[]) => void;
}

export function Composer({ variant, intensity = "calm", locked, disabled, onSubmit }: ComposerProps) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const showGhost = variant === "landing" && !value && !locked;
  const { ghost, full } = useGhostText(showGhost);
  const dark = variant === "workspace";

  useEffect(() => {
    if (!locked) inputRef.current?.focus();
  }, [locked, variant]);

  const submit = () => {
    if (disabled || locked) return;
    const text = value.trim() || (variant === "landing" ? full : "");
    if (!text) return;
    onSubmit(text, files);
    setValue("");
    setFiles([]);
  };

  return (
    <motion.div
      layoutId="composer"
      transition={{ type: "spring", stiffness: 120, damping: 22, mass: 1 }}
      className={variant === "landing" ? "relative w-full max-w-[680px]" : "relative w-full"}
    >
      {/* glow halo */}
      <motion.div
        aria-hidden
        className="glow-ring absolute -inset-[2px] rounded-[22px]"
        animate={{ opacity: intensity === "bright" ? 1 : dark ? 0.55 : 0.85 }}
        transition={{ duration: 0.6 }}
      />
      <motion.div
        aria-hidden
        className="glow-ring absolute -inset-3 rounded-[30px] blur-2xl"
        animate={{ opacity: intensity === "bright" ? 0.9 : dark ? 0.18 : 0.45 }}
        transition={{ duration: 0.6 }}
      />

      <div
        className={`relative flex items-center gap-2 rounded-[20px] px-3 py-2.5 transition-colors duration-500 ${
          locked ? "bg-[#070a14] text-white" : dark ? "bg-panel-2 text-white" : "bg-white text-bob-navy"
        }`}
      >
        <button
          type="button"
          aria-label="Attach files"
          onClick={() => fileRef.current?.click()}
          disabled={!!locked}
          className={`grid size-10 shrink-0 place-items-center rounded-xl transition ${
            dark || locked ? "text-dim hover:bg-white/5 hover:text-white" : "text-bob-navy/50 hover:bg-bob-navy/5 hover:text-bob-navy"
          }`}
        >
          <Paperclip className="size-5" />
        </button>
        <input
          ref={fileRef}
          type="file"
          multiple
          hidden
          onChange={(e) => setFiles((f) => [...f, ...Array.from(e.target.files ?? [])])}
        />

        <div className="relative min-w-0 flex-1">
          {locked ? (
            <div className="truncate py-2 text-[17px]">{locked}</div>
          ) : (
            <>
              <input
                ref={inputRef}
                value={value}
                disabled={disabled}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submit();
                  if ((e.key === "Tab" || e.key === "ArrowRight") && showGhost) {
                    e.preventDefault();
                    setValue(full);
                  }
                }}
                aria-label={variant === "landing" ? "Tell Bob what to build" : "Message Bob"}
                placeholder={variant === "workspace" ? "Ask Bob to change the plan, add sources, or export…" : ""}
                className={`w-full bg-transparent py-2 outline-none ${
                  variant === "landing" ? "text-[17px]" : "text-[15px]"
                } ${dark ? "placeholder:text-dim" : ""}`}
              />
              {showGhost && (
                <div className="pointer-events-none absolute inset-0 flex items-center overflow-hidden text-[17px] text-bob-navy/35">
                  <span className="caret truncate">{ghost}</span>
                </div>
              )}
            </>
          )}
        </div>

        {variant === "landing" && showGhost && (
          <kbd className="hidden shrink-0 rounded-md border border-bob-navy/10 px-1.5 py-0.5 font-mono text-[11px] text-bob-navy/40 sm:block">
            Tab
          </kbd>
        )}

        <button
          type="button"
          onClick={submit}
          aria-label="Send"
          disabled={disabled || !!locked}
          className="grid size-10 shrink-0 place-items-center rounded-xl bg-bob-blue text-white shadow-[0_6px_20px_-6px] shadow-bob-blue transition hover:brightness-110 active:scale-95 disabled:opacity-40"
        >
          <ArrowUp className="size-5" />
        </button>
      </div>

      {files.length > 0 && !locked && (
        <div className="absolute left-2 top-full mt-2 flex flex-wrap gap-1.5">
          {files.map((f, i) => (
            <span
              key={i}
              className={`flex items-center gap-1 rounded-full px-2.5 py-1 font-mono text-[11px] ${
                dark ? "bg-white/5 text-white/80" : "bg-white text-bob-navy/70 shadow-sm"
              }`}
            >
              {f.name}
              <button aria-label={`Remove ${f.name}`} onClick={() => setFiles((xs) => xs.filter((_, j) => j !== i))}>
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </motion.div>
  );
}
