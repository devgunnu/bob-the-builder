import { useState } from "react";
import { AlertTriangle, ChevronDown } from "lucide-react";
import { MODEL_ROLES, type AvailableModel, type ModelConfig, type ModelRole, type ModelRoles } from "../api/types";
import { Label } from "./ui";

const ROLE_INFO: Record<ModelRole, { title: string; hint: string }> = {
  writer: { title: "Writer", hint: "Writes every row. A fast, cheap model works best." },
  planner: { title: "Planner", hint: "Drafts the coverage plan once per job." },
  judge: { title: "Judge", hint: "Reviews only the rows where the checks disagree." },
  fallback: { title: "Fallback", hint: "Used if a checker is down. Empty means the writer model." },
};

const blank = (): ModelConfig => ({ provider: "bedrock", model_id: "" });

/** One row per LLM role (D33). Model ids are free text; no vendor list is hard-coded. */
export function ModelsEditor({
  value,
  onChange,
  keys,
  onKeys,
  results,
  options,
}: {
  value: ModelRoles;
  onChange: (v: ModelRoles) => void;
  keys?: Record<string, string>;
  onKeys?: (k: Record<string, string>) => void;
  results?: Record<string, string> | null;
  /** P1 model picker: ids from GET /me/models/available, offered as suggestions (free text still works). */
  options?: AvailableModel[] | null;
}) {
  const [open, setOpen] = useState<ModelRole | null>(null);
  const set = (role: ModelRole, patch: Partial<ModelConfig> | null) => {
    if (role === "fallback" && patch === null) return onChange({ ...value, fallback: null });
    const cur = (value[role] ?? blank()) as ModelConfig;
    onChange({ ...value, [role]: { ...cur, ...patch } });
  };
  const sameModel = value.judge?.model_id && value.judge.model_id === value.writer?.model_id;

  return (
    <div className="space-y-2">
      {options && options.length > 0 && (
        <datalist id="bob-models">
          {options.map((o) => <option key={o.id} value={o.id}>{o.name}{o.kind === "inference_profile" ? " (inference profile)" : ""}</option>)}
        </datalist>
      )}
      {MODEL_ROLES.map((role) => {
        const m = value[role] ?? null;
        const r = results?.[role];
        return (
          <div key={role} className="rounded-xl bg-white/[0.03] p-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="w-28 shrink-0">
                <div className="text-[13.5px] font-medium text-white">{ROLE_INFO[role].title}</div>
                <div className="text-[11px] leading-snug text-dim">{ROLE_INFO[role].hint}</div>
              </div>
              <input
                value={m?.model_id ?? ""}
                onChange={(e) => (role === "fallback" && !e.target.value ? set(role, null) : set(role, { model_id: e.target.value }))}
                placeholder={role === "fallback" ? "Same as writer" : "Model id or inference profile"}
                aria-label={`${ROLE_INFO[role].title} model id`}
                list={options?.length ? "bob-models" : undefined}
                className="min-w-[200px] flex-1 rounded-lg border border-line bg-transparent px-3 py-2 font-mono text-[12.5px] outline-none placeholder:font-sans placeholder:text-dim"
              />
              {r && <span className={`text-[12px] ${r === "ok" ? "text-bob-mint" : "text-rose-300"}`}>{r === "ok" ? "✓ works" : "✕ failed"}</span>}
              <button onClick={() => setOpen(open === role ? null : role)} aria-expanded={open === role} className="flex items-center gap-1 text-[12px] text-dim hover:text-white">
                More <ChevronDown className={`size-3.5 transition ${open === role ? "rotate-180" : ""}`} />
              </button>
            </div>
            {r && r !== "ok" && <div className="mt-2 rounded-lg bg-rose-400/10 px-2.5 py-1.5 font-mono text-[11.5px] text-rose-200">{r}</div>}
            {open === role && m && (
              <div className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2">
                <div>
                  <Label>Provider</Label>
                  <select value={m.provider} onChange={(e) => set(role, { provider: e.target.value as ModelConfig["provider"] })} className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1.5 text-[13px] outline-none">
                    <option value="bedrock">Amazon Bedrock (your AWS account)</option>
                    <option value="openai_compatible">OpenAI-compatible endpoint</option>
                  </select>
                </div>
                {m.provider === "openai_compatible" && (
                  <>
                    <div>
                      <Label>Base URL</Label>
                      <input value={m.base_url ?? ""} onChange={(e) => set(role, { base_url: e.target.value || null })} placeholder="https://…/v1" className="w-full rounded-lg border border-line bg-transparent px-2 py-1.5 font-mono text-[12.5px] outline-none" />
                    </div>
                    <div className="sm:col-span-2">
                      <Label>API key {m.api_key_set && !keys?.[role] && <span className="normal-case tracking-normal text-bob-mint">· key set</span>}</Label>
                      <input
                        type="password"
                        autoComplete="off"
                        value={keys?.[role] ?? ""}
                        onChange={(e) => onKeys?.({ ...(keys ?? {}), [role]: e.target.value })}
                        placeholder={m.api_key_set ? "Leave empty to keep the saved key" : "Paste a key"}
                        className="w-full rounded-lg border border-line bg-transparent px-2 py-1.5 font-mono text-[12.5px] outline-none placeholder:font-sans"
                      />
                    </div>
                  </>
                )}
                <div>
                  <Label>JSON output</Label>
                  <select value={m.json_mode ?? "auto"} onChange={(e) => set(role, { json_mode: e.target.value as ModelConfig["json_mode"] })} className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1.5 text-[13px] outline-none">
                    {["auto", "tool", "native", "prompt"].map((x) => <option key={x}>{x}</option>)}
                  </select>
                </div>
                <div>
                  <Label>Prompt caching</Label>
                  <select value={m.cache ?? "auto"} onChange={(e) => set(role, { cache: e.target.value as ModelConfig["cache"] })} className="w-full rounded-lg border border-line bg-panel-2 px-2 py-1.5 text-[13px] outline-none">
                    <option value="auto">auto</option>
                    <option value="off">off</option>
                  </select>
                </div>
                {(["price_in_per_m", "price_out_per_m"] as const).map((k) => (
                  <div key={k}>
                    <Label>{k === "price_in_per_m" ? "Input $ per M tokens" : "Output $ per M tokens"}</Label>
                    <input
                      type="number"
                      min={0}
                      step="0.01"
                      value={m[k] ?? ""}
                      onChange={(e) => set(role, { [k]: e.target.value === "" ? null : Number(e.target.value) })}
                      placeholder="Known price"
                      className="w-full rounded-lg border border-line bg-transparent px-2 py-1.5 font-mono text-[12.5px] outline-none placeholder:font-sans"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
      {sameModel && (
        <div className="flex items-start gap-2 rounded-lg bg-bob-yellow/10 px-3 py-2 text-[12.5px] text-bob-yellow">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> The judge uses the same model as the writer, so it may miss the writer's own mistakes. A different, stronger model is safer.
        </div>
      )}
    </div>
  );
}
