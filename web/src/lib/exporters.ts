import type { Row } from "./types";

// Preset mappings follow .agents/CONTRACTS.md section 5.
export const PRESETS = {
  "modelforge-sft": { label: "ModelForge SFT", note: "prompt / completion" },
  "openai-chat": { label: "OpenAI chat", note: "messages[]" },
  alpaca: { label: "Alpaca", note: "instruction / input / output" },
  sharegpt: { label: "ShareGPT", note: "conversations[]" },
  "trl-dpo": { label: "TRL DPO", note: "prompt / chosen / rejected" },
  full: { label: "Full + provenance", note: "every field, with sources and checks" },
} as const;
export type PresetId = keyof typeof PRESETS;

export const FORMATS = {
  jsonl: { label: "JSONL", browser: true },
  json: { label: "JSON", browser: true },
  csv: { label: "CSV", browser: true },
  parquet: { label: "Parquet", browser: false },
  avro: { label: "Avro", browser: false },
  jsonb: { label: "Postgres JSONB (.sql)", browser: false },
} as const;
export type FormatId = keyof typeof FORMATS;

export function project(row: Row, preset: PresetId): Record<string, unknown> | null {
  switch (preset) {
    case "modelforge-sft":
      return row.kind === "sft" ? { prompt: row.prompt, completion: row.response } : null;
    case "openai-chat":
      return row.kind === "sft"
        ? { messages: [{ role: "user", content: row.prompt }, { role: "assistant", content: row.response }] }
        : null;
    case "alpaca":
      return row.kind === "sft" ? { instruction: row.prompt, input: "", output: row.response } : null;
    case "sharegpt":
      return row.kind === "sft"
        ? { conversations: [{ from: "human", value: row.prompt }, { from: "gpt", value: row.response }] }
        : null;
    case "trl-dpo":
      return row.kind === "dpo" ? { prompt: row.prompt, chosen: row.response, rejected: row.rejected } : null;
    case "full":
      return { ...row };
  }
}

function csvCell(v: unknown): string {
  const s = typeof v === "string" ? v : JSON.stringify(v ?? "");
  return `"${s.replace(/"/g, '""')}"`;
}

export function serialize(rows: Row[], preset: PresetId, format: FormatId): { body: string; count: number } {
  const out = rows.filter((r) => r.status === "verified").map((r) => project(r, preset)).filter((x): x is Record<string, unknown> => x !== null);
  if (format === "jsonl") return { body: out.map((o) => JSON.stringify(o)).join("\n") + "\n", count: out.length };
  if (format === "json") return { body: JSON.stringify(out, null, 2), count: out.length };
  if (format === "csv") {
    const keys = Array.from(new Set(out.flatMap((o) => Object.keys(o))));
    const lines = [keys.map(csvCell).join(","), ...out.map((o) => keys.map((k) => csvCell(o[k])).join(","))];
    return { body: "﻿" + lines.join("\r\n"), count: out.length };
  }
  throw new Error(`${format} is written by the backend`);
}

export function download(name: string, body: string, type: string) {
  const url = URL.createObjectURL(new Blob([body], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
