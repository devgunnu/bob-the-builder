// Stand-in API data for capturing the real Bob UI.
// Questions, answers and passages come from the team's demo corpus (demo/corpus/).
// Counts and costs are illustrative (see brag-plan.md).
import fs from "node:fs";

const CORPUS = "/home/user/bob-int/demo/corpus";
export const JOB_ID = "8f3c2a1e";
const NOW = "2026-10-31T01:12:00Z";

export const TOPICS = [
  "Crawling a site",
  "Scraping pages",
  "Batch scrape",
  "Map and search",
  "Structured extract",
  "Rate limits",
  "Credits and billing",
  "Webhooks",
  "Webhook security",
  "API key restrictions",
  "Refunds (Notion wiki)",
  "Escalations (Notion wiki)",
];
const CASES = ["answerable", "partial", "unanswerable", "false_premise"];
const TOPIC_DESC = {
  "Crawling a site": "Crawl limits, sitemap modes, credits per page",
  "Scraping pages": "Formats, PDFs, dynamic pages",
  "Batch scrape": "Many URLs in one job",
  "Map and search": "Listing a site's URLs, web search",
  "Structured extract": "JSON extraction with a schema",
  "Rate limits": "Requests per minute, concurrent browsers, 429s",
  "Credits and billing": "Credit costs per endpoint, plans",
  Webhooks: "Events, timeouts and retries",
  "Webhook security": "Signatures and verification",
  "API key restrictions": "Scoping keys to IPs and endpoints",
  "Refunds (Notion wiki)": "Internal refund and credit rules",
  "Escalations (Notion wiki)": "Tiers, severities, first-response targets",
};

const OFF = new Set(["API key restrictions|false_premise"]);
const PER_CELL = 10;

function cellId(t, c) {
  return `c${TOPICS.indexOf(t)}-${CASES.indexOf(c)}`;
}

export function makePlan(fill = () => 0) {
  const cells = [];
  for (const t of TOPICS)
    for (const c of CASES) {
      const id = cellId(t, c);
      const enabled = !OFF.has(`${t}|${c}`);
      const kept = enabled ? fill(id) : 0;
      cells.push({ id, coords: { topic: t, case_type: c }, enabled, target: PER_CELL, weight: 1, generated: kept, kept, rejected: 0, judged: 0 });
    }
  return {
    goal: "First-reply support assistant for docs.firecrawl.dev that hands off when the docs don't cover it",
    task_format: "single_turn",
    system_prompt:
      "You are Firecrawl's first-reply support assistant. Answer only from the docs and the support wiki. If they don't cover something, say so plainly and hand off to a teammate. Correct wrong assumptions politely.",
    axes: [
      { name: "topic", values: TOPICS, descriptions: TOPIC_DESC, role: "cell", weights: {} },
      { name: "case_type", values: CASES, descriptions: {}, role: "cell", weights: {} },
      {
        name: "persona",
        values: ["New developer", "Support agent", "Enterprise admin"],
        descriptions: { "New developer": "First week with the API", "Support agent": "Answering a ticket", "Enterprise admin": "Owns the account and the bill" },
        role: "mix",
        weights: { "New developer": 0.45, "Support agent": 0.35, "Enterprise admin": 0.2 },
      },
      { name: "difficulty", values: ["single_fact", "multi_step", "multi_doc"], descriptions: {}, role: "mix", weights: { single_fact: 0.5, multi_step: 0.35, multi_doc: 0.15 } },
    ],
    cells,
    notes: [
      "Your Notion wiki covers refunds and escalations that the public docs never mention, so they get their own topics.",
      "Webhooks and billing are full of numbers, so they make good wrong-assumption questions.",
      "Key restrictions has no clear wrong assumption to correct, so that cell is off.",
    ],
    target_rows: cells.filter((c) => c.enabled).length * PER_CELL,
    est_cost_usd: 0.87,
  };
}

export const ENABLED_IDS = makePlan().cells.filter((c) => c.enabled).map((c) => c.id);
export const TARGET = ENABLED_IDS.length * PER_CELL;

export const MODELS = {
  writer: { provider: "bedrock", model_id: "us.anthropic.claude-haiku-5-5", json_mode: "auto", cache: "auto" },
  planner: { provider: "bedrock", model_id: "us.anthropic.claude-sonnet-5-5", json_mode: "auto", cache: "auto" },
  judge: { provider: "bedrock", model_id: "us.anthropic.claude-sonnet-5-5", json_mode: "auto", cache: "auto" },
  fallback: null,
};

export const ME = {
  id: "local",
  email: null,
  external_id: "bob-ext-demo",
  bedrock: { mode: "default", region: "us-east-1" },
  bedrock_verified_at: NOW,
  models: MODELS,
  models_verified_at: NOW,
  created_at: NOW,
};

export function cost(frac) {
  const total = 0.87 * frac;
  return {
    by_model: {
      writer: { calls: Math.round(210 * frac), in_tokens: 0, out_tokens: 0, usd: total * 0.46 },
      judge: { calls: Math.round(31 * frac), in_tokens: 0, out_tokens: 0, usd: total * 0.21 },
      jev: { calls: Math.round(560 * frac), in_tokens: 0, out_tokens: 0, usd: total * 0.19 },
      scaledown: { calls: Math.round(560 * frac), in_tokens: 0, out_tokens: 0, usd: total * 0.14 },
    },
    model_ids: { writer: MODELS.writer.model_id, judge: MODELS.judge.model_id, planner: MODELS.planner.model_id },
    price_unknown: [],
    total_usd: total,
    frontier_only_estimate_usd: 9.4 * Math.max(frac, 0.0001),
    fallbacks_used: [],
  };
}

// ---------- rows ----------
// [topic, case, user question, reply or reject reason, kept?]
export const FEED = [
  ["Crawling a site", "answerable", "How do I stop a crawl after 100 pages?", "Set limit: 100 on the crawl request.", true],
  ["Rate limits", "answerable", "What happens to jobs over my concurrent browser limit?", "They wait in a queue until a browser frees up.", true],
  ["Refunds (Notion wiki)", "partial", "I upgraded by mistake yesterday. Can I get a refund?", "", true],
  ["Scraping pages", "false_premise", "Can I export crawls as PDF with the bulk PDF export setting?", "invented feature: bulk PDF export", false],
  ["Webhooks", "answerable", "How long does my endpoint have to answer a webhook?", "", true],
  ["Credits and billing", "false_premise", "Crawl credits are charged when I submit the job, right?", "", true],
  ["Escalations (Notion wiki)", "answerable", "What's the first-response target on the Growth plan?", "", true],
  ["Map and search", "unanswerable", "Can map return the last-modified date of each URL?", "", true],
  ["Webhook security", "answerable", "How do I check a webhook really came from Firecrawl?", "", true],
  ["Rate limits", "false_premise", "Jobs in the queue never time out, correct?", "number not in the source: 24 hours", false],
  ["Batch scrape", "answerable", "Can I scrape 500 URLs in one call?", "", true],
  ["Structured extract", "partial", "Can extract follow links into sub-pages for me?", "", true],
  ["Crawling a site", "false_premise", "The default crawl limit is 100 pages, isn't it?", "", true],
  ["Refunds (Notion wiki)", "unanswerable", "Do you refund in crypto?", "", true],
  ["Scraping pages", "answerable", "Does scrape work on JavaScript-heavy pages?", "", true],
  ["Credits and billing", "answerable", "How many extra credits does JSON mode cost per page?", "", true],
  ["Webhooks", "unanswerable", "Can I replay a webhook from last month?", "judge: reply promises a replay tool", false],
  ["API key restrictions", "answerable", "Can I limit a key to one IP address?", "", true],
  ["Escalations (Notion wiki)", "false_premise", "Tier 1 can give 5,000 goodwill credits, right?", "", true],
  ["Map and search", "answerable", "What's the fastest way to list every URL on a site?", "", true],
  ["Batch scrape", "partial", "Will batch scrape tell me which URLs failed and why?", "", true],
  ["Structured extract", "answerable", "Do I need a schema to use extract?", "duplicate of a kept row", false],
  ["Webhook security", "false_premise", "Webhooks are signed with my API key, right?", "", true],
  ["Rate limits", "partial", "Can I raise my concurrency limit for one week only?", "", true],
  ["Crawling a site", "unanswerable", "Can a crawl log in with my SSO first?", "", true],
  ["Refunds (Notion wiki)", "answerable", "Do downgrades get a refund for the unused time?", "", true],
  ["Scraping pages", "unanswerable", "Can scrape solve CAPTCHAs on any site?", "invented feature: CAPTCHA solver", false],
  ["Credits and billing", "partial", "Why did my crawl keep billing after it said done?", "", true],
  ["Escalations (Notion wiki)", "partial", "Who do I page for a Sev 2 at 2 a.m.?", "", true],
  ["Webhooks", "false_premise", "Firecrawl retries a failed webhook 5 times, right?", "", true],
];

export function rowEvent(i, item, idOverride) {
  const [t, c, q, extra, ok] = item;
  return {
    id: idOverride ?? `r${String(i).padStart(4, "0")}`,
    cell_id: cellId(t, c),
    verdict: ok ? "kept" : "rejected",
    reject_reason: ok ? null : extra,
    case_type: c,
    user_preview: q,
    confidence: ok ? 0.86 + ((i * 7) % 12) / 100 : 0.2 + ((i * 5) % 20) / 100,
    routed_to_judge: i % 9 === 4,
  };
}

// ---------- the row we open in the inspector ----------
const webhooks = fs.readFileSync(`${CORPUS}/webhooks-overview.md`, "utf8");
const pStart = webhooks.indexOf("## Timeouts & Retries");
const pEnd = webhooks.indexOf("no further attempts are made.") + "no further attempts are made.".length;
const passage = webhooks.slice(pStart, pEnd);
function sub(text) {
  const a = webhooks.indexOf(text, pStart);
  if (a < 0) throw new Error("span not found: " + text);
  return { start: a, end: a + text.length, text };
}
const WURI = "https://docs.firecrawl.dev/webhooks/overview";
const span = (s) => ({ doc_id: "doc-webhooks-overview", uri: WURI, title: "Webhooks | Firecrawl", ...s });

export const PROOF_ID = "r-proof";
export const PROOF_ROW = {
  id: PROOF_ID,
  job_id: JOB_ID,
  cell_id: cellId("Webhooks", "false_premise"),
  coords: { topic: "Webhooks", case_type: "false_premise", persona: "Support agent", difficulty: "multi_step" },
  case_type: "false_premise",
  round: 1,
  messages: [
    { role: "user", content: "Firecrawl retries a failed webhook 5 times, right? How long does it wait before the last try?" },
    {
      role: "assistant",
      content:
        "Not quite. Firecrawl retries a failed webhook 3 times, not 5. It waits 1 minute before the first retry, 5 minutes before the second and 15 minutes before the third. After the third failed retry the webhook is marked as failed and no more attempts are made.\n\nAlso check that your endpoint answers with a 2xx status within 10 seconds, or the delivery counts as failed.",
    },
  ],
  spans: [
    span({ start: pStart, end: pEnd, text: passage }),
    span(sub("within **10 seconds**")),
    span(sub("| 1st | 1 minute |")),
    span(sub("| 2nd | 5 minutes |")),
    span(sub("| 3rd | 15 minutes |")),
    span(sub("After 3 failed retries, the webhook is marked as failed")),
  ],
  checks: [
    { name: "format", tier: 1, passed: true, score: null, detail: "", evidence_ids: [] },
    { name: "banned_phrases", tier: 1, passed: true, score: null, detail: "", evidence_ids: [] },
    { name: "dedup", tier: 1, passed: true, score: 0.31, detail: "", evidence_ids: [] },
    { name: "numbers", tier: 1, passed: true, score: null, detail: "3, 1, 5, 15, 10 all appear in the source (5 also in the user turn)", evidence_ids: [] },
    { name: "extract.names", tier: 2, passed: true, score: 1, detail: "", evidence_ids: [] },
    { name: "jev.cell", tier: 2, passed: true, score: 0.97, detail: "", evidence_ids: [] },
    { name: "jev.realistic", tier: 2, passed: true, score: 0.93, detail: "", evidence_ids: [] },
    { name: "jev.contradicted", tier: 2, passed: true, score: 0.96, detail: "", evidence_ids: [] },
    { name: "jev.corrects", tier: 2, passed: true, score: 0.95, detail: "", evidence_ids: [] },
  ],
  confidence: 0.95,
  verdict: "kept",
  reject_reason: null,
  routed_to_judge: false,
  audited: false,
  spot_check: null,
  cost_usd: 0.00174,
  created_at: NOW,
};

export const PRESETS = [
  ["openai-chat", "OpenAI chat fine-tuning: {messages: [system, user, assistant]}"],
  ["sharegpt", "ShareGPT: {conversations: [{from: system/human/gpt, value}]}"],
  ["alpaca", "Alpaca: {instruction, input, output} (single-turn rows only)"],
  ["modelforge-chat", "ModelForge chat: {messages} canonical columns only"],
  ["modelforge-sft", "ModelForge SFT: {prompt, completion} (single-turn rows only)"],
  ["dpo", "DPO: {prompt: [messages], chosen, rejected} from proof-backed pairs"],
  ["full", "Whole canonical row with provenance, spans and checks"],
].map(([name, description]) => ({ name, description, formats: ["jsonl", "json", "csv", "parquet"] }));

export const FILES = {
  "openai-chat/train/train.jsonl": "x",
  "openai-chat/eval/eval.jsonl": "x",
  "bob_manifest.json": "x",
  "provenance.parquet": "x",
  "report.json": "x",
};

export function report() {
  const plan = makePlan(() => PER_CELL);
  const coverage = plan.cells.filter((c) => c.enabled).map((c) => ({ cell_id: c.id, coords: c.coords, target: PER_CELL, kept: PER_CELL, rejected: 1 + (c.id.length % 3) }));
  return {
    coverage,
    mix_coverage: {
      persona: { "New developer": 212, "Support agent": 164, "Enterprise admin": 94 },
      difficulty: { single_fact: 236, multi_step: 163, multi_doc: 71 },
    },
    pass_rate_by_check: { format: 0.99, numbers: 0.93, "extract.names": 0.9, "jev.supported": 0.88, "jev.abstains": 0.91, "jev.corrects": 0.89 },
    reject_reasons: { "extract.names": 21, numbers: 14, "jev.supported": 11, dedup: 9 },
    duplicates_removed: 9,
    judge_rate: 0.06,
    judge_agreement: 0.91,
    spot_check: {},
    sample_row_ids: [PROOF_ID],
    token_stats: { p50: 74, p95: 152, max: 231 },
    rounds: [
      { n: 1, cells: 47, kept: 401 },
      { n: 2, cells: 9, kept: 69 },
    ],
  };
}

export function job(status, extra = {}) {
  return {
    id: JOB_ID,
    spec: { goal: makePlan().goal, sources: [], target_rows: TARGET, budget_usd: 10, preset: "openai-chat", formats: ["jsonl"] },
    owner_id: "local",
    bedrock: ME.bedrock,
    models: MODELS,
    status,
    stage_detail: "",
    plan: null,
    round: 1,
    counts: {},
    cost: cost(0),
    files: {},
    report: null,
    error: null,
    heartbeat_at: NOW,
    created_at: NOW,
    updated_at: NOW,
    ...extra,
  };
}

export const NOTION_PAGES = [
  ["Support FAQ (internal)", "page"],
  ["Escalation policy", "page"],
  ["Known issues and workarounds", "page"],
  ["Refunds and credit adjustments", "page"],
  ["Enterprise and plan-change hand-offs", "page"],
  ["Reply style guide and canned replies", "page"],
].map(([title, kind], i) => ({ id: `np${i}`, title, kind }));
