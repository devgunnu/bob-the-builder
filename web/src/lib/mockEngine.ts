// SIMULATED ENGINE. Stands in for the real backend (POST /jobs + event
// stream) until it is ready. Every row it produces is computed from one real
// source passage (ModelForge DEVELOPER_GUIDE.md, "PEFT Tier Logic", the same
// passage as .agents/research/08), so the numbers in the UI are internally
// consistent, but the run itself is a simulation. The UI shows a "Simulated"
// badge whenever this engine is in use.

import type {
  Capability,
  ChatMessage,
  Check,
  JobClient,
  JobEvent,
  JobSession,
  Row,
  SourceDoc,
  StageId,
  StageState,
  Stats,
} from "./types";

const SOURCE_DOC = "DEVELOPER_GUIDE.md";
const SOURCE_SECTION = "PEFT Tier Logic";
const SOURCE_TEXT = [
  "| Tier | Memory per Param | Triggered When |",
  "| full_finetune | 18 bytes | Very high VRAM (for small models) |",
  "| lora_bf16 | ~2 bytes (frozen) | 16+ GB adjusted VRAM |",
  "| qlora_8bit | ~1 byte (frozen) | 8-16 GB adjusted VRAM |",
  "| qlora_4bit | ~0.5 bytes (frozen) | Below 8 GB adjusted VRAM |",
].join("\n");

interface Tier {
  name: string;
  bytes: number;
  approx: boolean;
  trigger: string;
}

const TIERS: Tier[] = [
  { name: "full_finetune", bytes: 18, approx: false, trigger: "very high VRAM (for small models)" },
  { name: "lora_bf16", bytes: 2, approx: true, trigger: "16+ GB of adjusted VRAM" },
  { name: "qlora_8bit", bytes: 1, approx: true, trigger: "8 to 16 GB of adjusted VRAM" },
  { name: "qlora_4bit", bytes: 0.5, approx: true, trigger: "below 8 GB of adjusted VRAM" },
];

// Values strictly inside the documented bands (8 and 16 GB are ambiguous in
// the source, so they are never generated).
const VRAM = [2, 4, 6, 10, 12, 14, 20, 24, 32, 48, 80];
const SIZES = [0.5, 1, 1.5, 3, 7, 8, 13, 14, 32, 70];
const PERSONAS = ["beginner", "ML engineer", "laptop user", "terse", "non-native speaker"];

const WRITER_USD_PER_ROW = 0.00019; // cheap Writer model, ~600 in / 250 out tokens
const VERIFY_USD_PER_ROW = 0.00003; // Jev checks
const BASELINE_USD_PER_ROW = 0.014; // same row written + judged by a frontier model

function tierFor(vram: number): Tier {
  if (vram < 8) return TIERS[3];
  if (vram < 16) return TIERS[2];
  return TIERS[1];
}

function gb(n: number): string {
  return Number.isInteger(n) ? `${n}` : n.toFixed(1).replace(/\.0$/, "");
}

function pick<T>(xs: T[], r: () => number): T {
  return xs[Math.floor(r() * xs.length)];
}

// Small deterministic PRNG so a run looks the same every time.
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

function spanOf(needle: string): [number, number] {
  const i = SOURCE_TEXT.indexOf(needle);
  return i < 0 ? [0, 0] : [i, i + needle.length];
}

function phrase(persona: string, variants: Record<string, string>): string {
  return variants[persona] ?? variants.default;
}

const CAPABILITIES: Capability[] = [
  { id: "planner", title: "Pick a fine-tuning method for someone's GPU", detail: "New hardware setups, answer computed from the tier table", generator: "capacity_planner", estRows: 160, enabled: true },
  { id: "memory", title: "Estimate weight memory for any model size", detail: "Model size x bytes per parameter", generator: "memory_math", estRows: 90, enabled: true },
  { id: "compare", title: "Compare methods", detail: "Pairwise memory ratios and trade-offs", generator: "compare_methods", estRows: 40, enabled: true },
  { id: "abstain", title: "Say when the docs don't cover something", detail: "Plausible questions the source can't answer", generator: "abstain_unknown", estRows: 50, enabled: true },
  { id: "premise", title: "Correct wrong assumptions", detail: "Questions built on a false claim", generator: "false_premise", estRows: 40, enabled: true },
  { id: "format", title: "Follow output rules", detail: "JSON, bullet counts, word limits, each with a checker", generator: "constrained", estRows: 60, enabled: true },
  { id: "pairs", title: "Preference pairs", detail: "Good answer vs one with exactly one known flaw", generator: "preference_pairs", estRows: 60, enabled: false },
];

type Make = (r: () => number, persona: string) => Omit<Row, "id" | "status" | "costUsd" | "checks" | "persona">;

const GENERATORS: Record<string, Make> = {
  capacity_planner: (r, persona) => {
    const v = pick(VRAM, r);
    const p = pick(SIZES, r);
    const t = tierFor(v);
    const weights = p * t.bytes;
    const prompt = phrase(persona, {
      beginner: `I'm new to this. My GPU has ${v} GB of memory and I want to fine-tune a ${gb(p)}B model. Which method should I use?`,
      "ML engineer": `Adjusted VRAM is ${v} GB, target model ${gb(p)}B params. Which PEFT tier applies, and what's the frozen-weight footprint?`,
      "laptop user": `fine-tuning on my laptop, ${v}gb vram, ${gb(p)}B model. what tier and will the weights fit?`,
      terse: `${v} GB VRAM, ${gb(p)}B model: tier?`,
      "non-native speaker": `Hello, I have ${v} GB memory on GPU. For ${gb(p)}B model, which method is correct please?`,
      default: `Which tier fits ${v} GB and a ${gb(p)}B model?`,
    });
    const fits = weights < v;
    const response = `${t.name}. ${v} GB falls in the band for ${t.trigger}. At ${t.approx ? "about " : ""}${gb(t.bytes)} ${t.bytes === 1 ? "byte" : "bytes"} per frozen parameter, the weights of a ${gb(p)}B model take ${t.approx ? "about " : ""}${gb(weights)} GB, which ${fits ? "is under" : "is over"} your ${v} GB. The table doesn't cover activation memory, so leave headroom.`;
    return { generator: "capacity_planner", kind: "sft", prompt, response, source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: spanOf(t.name) } };
  },
  memory_math: (r, persona) => {
    const p = pick(SIZES, r);
    const t = pick(TIERS, r);
    const w = p * t.bytes;
    const prompt = phrase(persona, {
      beginner: `How much memory do the weights of a ${gb(p)}B model need with ${t.name}?`,
      "ML engineer": `Frozen-weight memory for ${gb(p)}B params under ${t.name}?`,
      terse: `${gb(p)}B, ${t.name}: weight memory?`,
      default: `Roughly how many GB do a ${gb(p)}B model's weights use with ${t.name}?`,
    });
    const response = `${t.approx ? "About " : ""}${gb(w)} GB: ${gb(p)}B parameters x ${t.approx ? "about " : ""}${gb(t.bytes)} bytes each.`;
    return { generator: "memory_math", kind: "sft", prompt, response, source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: spanOf(t.name) } };
  },
  compare_methods: (r) => {
    const a = pick(TIERS, r);
    let b = pick(TIERS, r);
    if (b === a) b = TIERS[(TIERS.indexOf(a) + 1) % TIERS.length];
    const [hi, lo] = a.bytes >= b.bytes ? [a, b] : [b, a];
    const ratio = hi.bytes / lo.bytes;
    return {
      generator: "compare_methods",
      kind: "sft",
      prompt: `How many times more memory per parameter does ${hi.name} use than ${lo.name}?`,
      response: `About ${gb(ratio)}x: ${hi.approx ? "about " : ""}${gb(hi.bytes)} bytes vs ${lo.approx ? "about " : ""}${gb(lo.bytes)} bytes per parameter.`,
      source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: spanOf(hi.name) },
    };
  },
  abstain_unknown: (r, persona) => {
    const t = pick(TIERS, r);
    const q = pick([
      `How much slower is ${t.name} than full fine-tuning?`,
      `What accuracy do I lose with ${t.name}?`,
      `Does ${t.name} work on Apple Silicon?`,
      `Exactly how much VRAM triggers full_finetune?`,
    ], r);
    return {
      generator: "abstain_unknown",
      kind: "sft",
      prompt: persona === "terse" ? q.replace(/^How much |^What |^Does |^Exactly /, (m) => m) : q,
      response: `The PEFT tier table doesn't say. It only gives memory per parameter and when each tier is used. I'd check benchmarks for your model rather than guess.`,
      source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: [0, SOURCE_TEXT.indexOf("\n")] },
    };
  },
  false_premise: (r) => {
    const t = pick(TIERS.slice(1), r);
    const wrong = pick(TIERS.filter((x) => x !== t), r);
    return {
      generator: "false_premise",
      kind: "sft",
      prompt: `Why does ${t.name} use ${gb(wrong.bytes)} bytes per parameter?`,
      response: `It doesn't. ${t.name} uses about ${gb(t.bytes)} ${t.bytes === 1 ? "byte" : "bytes"} per frozen parameter. ${gb(wrong.bytes)} bytes is ${wrong.name}.`,
      source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: spanOf(t.name) },
    };
  },
  constrained: (r) => {
    const v = pick(VRAM, r);
    const t = tierFor(v);
    const mode = pick(["json", "bullets", "short"], r);
    if (mode === "json") {
      return {
        generator: "constrained",
        kind: "sft",
        prompt: `With ${v} GB of adjusted VRAM, which tier applies? Answer only as JSON with keys "tier" and "bytes_per_param".`,
        response: JSON.stringify({ tier: t.name, bytes_per_param: t.bytes }),
        source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: spanOf(t.name) },
      };
    }
    if (mode === "bullets") {
      return {
        generator: "constrained",
        kind: "sft",
        prompt: `In exactly 2 bullets: which tier for ${v} GB, and why?`,
        response: `- ${t.name}\n- ${v} GB is in the band for ${t.trigger}`,
        source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: spanOf(t.name) },
      };
    }
    return {
      generator: "constrained",
      kind: "sft",
      prompt: `Under 12 words: best tier for ${v} GB of VRAM?`,
      response: `${t.name}, since ${v} GB is ${t.trigger}.`,
      source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: spanOf(t.name) },
    };
  },
  preference_pairs: (r) => {
    const v = pick(VRAM, r);
    const t = tierFor(v);
    const wrong = pick(TIERS.filter((x) => x !== t && x.name !== "full_finetune"), r);
    return {
      generator: "preference_pairs",
      kind: "dpo",
      prompt: `Which PEFT tier should I use with ${v} GB of adjusted VRAM?`,
      response: `${t.name}: ${v} GB is ${t.trigger}.`,
      rejected: `${wrong.name}: ${v} GB is ${wrong.trigger}.`,
      source: { doc: SOURCE_DOC, section: SOURCE_SECTION, text: SOURCE_TEXT, span: spanOf(t.name) },
    };
  },
};

const REJECT_REASONS = [
  "Unsupported claim: response mentions activation memory figures not in the source",
  "Locked value missing: computed answer was paraphrased away",
  "Near-duplicate of an earlier row (cosine 0.97)",
  "Constraint failed: 3 bullets where exactly 2 were required",
  "Question not answerable without seeing the document",
];

function checksFor(row: Pick<Row, "generator">, ok: boolean, r: () => number): Check[] {
  const p = ok ? 0.9 + r() * 0.09 : 0.2 + r() * 0.4;
  const base: Check[] = [
    { name: "Source span", passed: true, detail: "Cited text appears verbatim in the source" },
    { name: "Supported (Jev)", passed: ok, detail: `p = ${p.toFixed(2)}` },
    { name: "Locked answer present", passed: ok || r() > 0.5, detail: "Computed value appears in the response" },
  ];
  if (row.generator === "constrained") base.push({ name: "Format checker", passed: ok, detail: "Constraint verifier function" });
  if (row.generator === "abstain_unknown") base.push({ name: "Truly unanswerable", passed: true, detail: "No matching fact in the graph" });
  return base;
}

class Emitter {
  private fns = new Set<(e: JobEvent) => void>();
  on(fn: (e: JobEvent) => void) {
    this.fns.add(fn);
    return () => void this.fns.delete(fn);
  }
  emit(e: JobEvent) {
    for (const fn of this.fns) fn(e);
  }
}

let msgSeq = 0;
const mid = () => `m${++msgSeq}`;

class MockSession implements JobSession {
  private bus = new Emitter();
  private timers: number[] = [];
  private stats: Stats = { generated: 0, verified: 0, rejected: 0, costUsd: 0, baselineUsd: 0 };
  private r = rng(7);
  private caps = CAPABILITIES.map((c) => ({ ...c }));
  private prompt: string;
  private files: File[];

  constructor(prompt: string, files: File[]) {
    this.prompt = prompt;
    this.files = files;
    this.later(150, () => this.run());
  }

  subscribe(fn: (e: JobEvent) => void) {
    return this.bus.on(fn);
  }

  cancel() {
    this.timers.forEach((t) => window.clearTimeout(t));
    this.timers = [];
  }

  send(text: string) {
    this.bus.emit({ type: "message", message: { id: mid(), from: "user", text } });
    this.later(700, () =>
      this.say("Noted. In the real engine this goes to the Architect as a new instruction; in this simulated run I'll keep going with the current plan."),
    );
  }

  approve(ids: string[]) {
    const enabled = new Set(ids);
    this.caps = this.caps.map((c) => ({ ...c, enabled: enabled.has(c.id) }));
    this.stage("architect", "done");
    this.say(`Building ${ids.length} generators. Each one ships with its own checker, and every row is verified before it lands in your dataset.`);
    this.later(500, () => this.generate());
  }

  private later(ms: number, fn: () => void) {
    this.timers.push(window.setTimeout(fn, ms));
  }

  private say(text: string) {
    this.bus.emit({ type: "message", message: { id: mid(), from: "bob", text } });
  }

  private card(message: ChatMessage) {
    this.bus.emit({ type: "message", message });
  }

  private stage(stage: StageId, state: StageState, progress?: number) {
    this.bus.emit({ type: "stage", stage, state, progress });
  }

  private sources(): SourceDoc[] {
    const docs: SourceDoc[] = [];
    const url = this.prompt.match(/https?:\/\/[^\s]+|[a-z0-9-]+\.[a-z]{2,}(?:\/[^\s]*)?/i)?.[0];
    if (url) docs.push({ id: "u1", name: url.replace(/^https?:\/\//, ""), kind: "url", pages: 18, kept: 14 });
    this.files.forEach((f, i) => {
      const ext = (f.name.split(".").pop() ?? "txt").toLowerCase();
      const kind: SourceDoc["kind"] = ext === "pdf" ? "pdf" : ext === "csv" ? "csv" : ext === "md" ? "md" : "txt";
      docs.push({ id: `f${i}`, name: f.name, kind, pages: 6 + ((f.size >> 10) % 20), kept: 4 + ((f.size >> 11) % 12) });
    });
    docs.push({ id: "sample", name: `${SOURCE_DOC} (sample corpus)`, kind: "md", pages: 24, kept: 17 });
    return docs;
  }

  private run() {
    this.say("On it. Reading your sources first.");
    this.stage("ingest", "active");
    const docs = this.sources();
    this.later(900, () => {
      this.card({ id: mid(), from: "bob", card: "sources", sources: docs });
      this.stage("ingest", "done");
      this.stage("triage", "active");
    });
    this.later(2100, () => {
      const pages = docs.reduce((a, d) => a + d.pages, 0);
      const kept = docs.reduce((a, d) => a + d.kept, 0);
      this.stage("triage", "done");
      this.say(`Jev kept ${kept} of ${pages} chunks. The rest were navigation, legal boilerplate and repeats.`);
      this.stage("extract", "active");
    });
    this.later(3400, () => {
      this.stage("extract", "done");
      this.say("Pulled 64 facts, each tied to the exact text it came from. One snag: 16 GB appears in two bands of the PEFT table, so I won't generate questions right at that edge.");
      this.stage("architect", "active");
    });
    this.later(4800, () => {
      this.card({ id: mid(), from: "bob", card: "architect", capabilities: this.caps, approved: false });
    });
  }

  private generate() {
    const active = this.caps.filter((c) => c.enabled);
    const target = active.reduce((a, c) => a + c.estRows, 0);
    this.stage("generate", "active", 0);
    this.stage("write", "active", 0);
    this.stage("verify", "active", 0);
    const weights = active.map((c) => c.estRows);
    const total = weights.reduce((a, b) => a + b, 0);
    let n = 0;
    const tick = () => {
      const batch = 3;
      for (let k = 0; k < batch && n < target; k++, n++) {
        let x = this.r() * total;
        let cap = active[0];
        for (let j = 0; j < active.length; j++) {
          x -= weights[j];
          if (x <= 0) {
            cap = active[j];
            break;
          }
        }
        const persona = pick(PERSONAS, this.r);
        const base = GENERATORS[cap.generator](this.r, persona);
        const ok = this.r() > 0.085;
        const row: Row = {
          ...base,
          id: `r${n + 1}`,
          persona,
          status: ok ? "verified" : "rejected",
          rejectReason: ok ? undefined : pick(REJECT_REASONS, this.r),
          checks: checksFor(base, ok, this.r),
          costUsd: WRITER_USD_PER_ROW + VERIFY_USD_PER_ROW,
        };
        this.stats = {
          generated: this.stats.generated + 1,
          verified: this.stats.verified + (ok ? 1 : 0),
          rejected: this.stats.rejected + (ok ? 0 : 1),
          costUsd: this.stats.costUsd + row.costUsd,
          baselineUsd: this.stats.baselineUsd + BASELINE_USD_PER_ROW,
        };
        this.bus.emit({ type: "row", row });
      }
      const prog = n / target;
      this.stage("generate", prog >= 1 ? "done" : "active", prog);
      this.stage("write", prog >= 1 ? "done" : "active", prog);
      this.stage("verify", prog >= 1 ? "done" : "active", prog);
      this.bus.emit({ type: "stats", stats: this.stats });
      if (n < target) this.later(90, tick);
      else this.finish();
    };
    tick();
  }

  private finish() {
    this.stage("export", "active");
    this.later(800, () => {
      this.stage("export", "done");
      this.card({ id: mid(), from: "bob", card: "done", stats: this.stats });
      this.bus.emit({ type: "done" });
    });
  }
}

export const mockClient: JobClient = {
  start: ({ prompt, files }) => new MockSession(prompt, files),
};
