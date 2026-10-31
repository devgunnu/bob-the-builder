// Captures the real Bob frontend frame by frame (30 fps) with a frozen clock.
// Usage: node capture.mjs <outDir> [maxSeconds]
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
import fs from "node:fs";
import * as F from "./fixtures.mjs";

const OUT = process.argv[2] ?? "frames";
const MAX_S = Number(process.argv[3] ?? 39.5);
const FPS = 30;
const W = 1600, H = 900, DPR = 1.5;
fs.mkdirSync(OUT, { recursive: true });

// Capture time c = video time - 4.63. Times below are video seconds; converted with V().
const V = (t) => t - 4.63;

// ---------- build stream (virtual ms after the build screen connects) ----------
function buildEvents() {
  const ev = [];
  const ids = F.ENABLED_IDS;
  const speed = Object.fromEntries(ids.map((id, i) => [id, 0.7 + (((i * 37) % 23) / 23) * 0.75]));
  const lag = new Set(ids.filter((_, i) => i % 6 === 2).slice(0, 7)); // filled in the gap round
  const DONE = 9400, R2 = 5600;
  const ease = (x) => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 2.2);
  ev.push({ at: 0, event: "job.status", data: { status: "building", detail: "" } });
  ev.push({ at: 0, event: "round", data: { n: 1, reason: "first pass", cells: [], planned: F.TARGET } });
  let prev = {};
  for (let at = 150; at <= 9000; at += 150) {
    const f = ease(at / 8800);
    let kept = 0;
    for (const id of ids) {
      let k = Math.min(10, Math.floor(10 * f * speed[id] * 1.25));
      if (lag.has(id)) k = at < R2 ? Math.min(k, 4) : Math.min(10, 4 + Math.floor(((at - R2) / (8800 - R2)) * 7));
      if (at >= 8800) k = 10;
      kept += k;
      if (k !== prev[id]) {
        const rej = Math.round(k * 0.14 + (k > 3 ? 1 : 0));
        ev.push({ at, event: "cell.update", data: { cell_id: id, generated: k + rej, kept: k, rejected: rej, judged: Math.floor(k / 7), target: 10 } });
        prev[id] = k;
      }
    }
    ev.push({ at, event: "counts", data: { kept, rejected: Math.round(kept * 0.12), generated: Math.round(kept * 1.12) } });
    ev.push({ at, event: "cost", data: F.cost(kept / F.TARGET) });
    const stage = at % 600 < 300 ? "generate" : "verify";
    ev.push({ at, event: "stage.progress", data: { stage, done: kept, total: F.TARGET, detail: at < R2 ? `round 1 · ${kept} of ${F.TARGET}` : `round 2 · ${kept} of ${F.TARGET}` } });
    if (at === R2) ev.push({ at, event: "round", data: { n: 2, reason: "thin cells", cells: [...lag], planned: 42 } });
  }
  // rows: about one every 150 ms; the proof row is the last kept row
  const feed = F.FEED.slice(0, -1);
  let n = 0;
  for (let at = 120; at <= 8700; at += 150) {
    const item = feed[n % feed.length];
    ev.push({ at, event: "row", data: F.rowEvent(n, item) });
    n++;
  }
  ev.push({ at: 8850, event: "row", data: F.rowEvent(999, F.FEED[F.FEED.length - 1], F.PROOF_ID) });
  ev.push({ at: DONE, event: "report.ready", data: F.report() });
  ev.push({ at: DONE, event: "files.ready", data: { files: F.FILES } });
  ev.push({ at: DONE, event: "job.status", data: { status: "done", detail: "" } });
  return ev.sort((a, b) => a.at - b.at);
}

function planEvents() {
  const st = (at, stage, done, total, detail) => ({ at, event: "stage.progress", data: { stage, done, total, detail } });
  return [
    { at: 0, event: "job.status", data: { status: "reading", detail: "" } },
    st(80, "fetch", 31, 31, "31 pages"),
    { at: 120, event: "counts", data: { docs: 31 } },
    st(320, "chunk", 1, 1, ""),
    st(520, "triage", 412, 486, "412 of 486 passages"),
    { at: 600, event: "counts", data: { docs: 31, chunks_kept: 412 } },
    st(800, "topics", 12, 12, "12 topics"),
    { at: 850, event: "counts", data: { docs: 31, chunks_kept: 412, topics: 12 } },
    st(1050, "evidence", 1286, 1286, "1,286 facts"),
    { at: 1100, event: "counts", data: { docs: 31, chunks_kept: 412, topics: 12, evidence: 1286 } },
    st(1350, "plan", 0, 1, ""),
    { at: 1750, event: "plan.ready", data: F.makePlan() },
    { at: 1750, event: "job.status", data: { status: "awaiting_approval", detail: "" } },
  ];
}

// ---------- API state ----------
let phase = "plan";
function jobNow() {
  if (phase === "plan") return F.job("reading");
  if (phase === "build") return F.job("building", { plan: F.makePlan() });
  return F.job("done", { plan: F.makePlan(() => 10), report: F.report(), files: F.FILES, cost: F.cost(1), counts: { kept: F.TARGET, rejected: 56 } });
}

const ok = (route, body) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

async function api(route) {
  const url = new URL(route.request().url());
  const p = url.pathname.replace(/^\/api/, "");
  const m = route.request().method();
  if (p === "/config/public") return ok(route, { auth: "none" });
  if (p === "/health") return ok(route, { keys: { bedrock: "ok", jev: "ok", scaledown: "ok", firecrawl: "ok", composio: "ok" } });
  if (p === "/me") return ok(route, F.ME);
  if (p === "/connectors") return ok(route, [
    { toolkit: "notion", connected: true, account_id: "ca_demo" },
    { toolkit: "confluence", connected: false },
    { toolkit: "jira", connected: false },
    { toolkit: "googledrive", connected: false },
  ]);
  if (p.startsWith("/connectors/notion/browse")) return ok(route, F.NOTION_PAGES);
  if (p === "/jobs" && m === "POST") { phase = "plan"; return ok(route, F.job("created")); }
  if (p === "/jobs") return ok(route, [jobNow()]);
  if (p === `/jobs/${F.JOB_ID}` ) return ok(route, jobNow());
  if (p === `/jobs/${F.JOB_ID}/plan` && m === "PUT") { phase = "build"; return ok(route, F.job("building", { plan: F.makePlan() })); }
  if (p === `/jobs/${F.JOB_ID}/rows/${F.PROOF_ID}`) return ok(route, F.PROOF_ROW);
  if (p.startsWith(`/jobs/${F.JOB_ID}/rows`)) return ok(route, { total: 0, rows: [] });
  if (p === "/presets") return ok(route, F.PRESETS);
  return ok(route, {});
}

// ---------- in-page helpers (run before the app loads) ----------
const INIT = ({ plan, build }) => {
  // deterministic randomness
  let seed = 7;
  Math.random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  // force motion to animate in JS (driven by the fake clock), not WAAPI
  delete Element.prototype.animate;

  // CSS animations follow virtual time
  const born = new WeakMap();
  window.__syncAnims = (vt) => {
    for (const a of document.getAnimations()) {
      if (!born.has(a)) born.set(a, vt);
      try { a.pause(); a.currentTime = vt - born.get(a); } catch {}
    }
  };

  // scripted SSE: each connection gets the next schedule, timed by the fake clock
  const schedules = [plan, build];
  let conn = 0;
  const realFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : input.url;
    if (!url.includes("/events")) return realFetch(input, init);
    const list = schedules[conn++] ?? [];
    let id = conn * 10000;
    const enc = new TextEncoder();
    const body = new ReadableStream({
      start(ctrl) {
        const t0 = Date.now();
        for (const e of list) {
          setTimeout(() => {
            try { ctrl.enqueue(enc.encode(`id: ${id++}\nevent: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)); } catch {}
          }, Math.max(0, e.at - (Date.now() - t0)));
        }
        init?.signal?.addEventListener("abort", () => { try { ctrl.close(); } catch {} });
      },
    });
    return Promise.resolve(new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }));
  };

  // fake cursor + click ring
  window.addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div");
    c.id = "__cursor";
    c.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;opacity:0;will-change:transform";
    c.innerHTML = `<div id="__ring" style="position:absolute;left:-22px;top:-22px;width:44px;height:44px;border-radius:50%;border:3px solid #ffc82e;opacity:0"></div>
      <svg width="30" height="30" viewBox="0 0 24 24" style="filter:drop-shadow(0 3px 6px rgba(0,0,0,.55))"><path d="M4 2l15 11.5-6.6.9 3.9 7.4-2.9 1.5-3.9-7.5L4 20z" fill="#fff" stroke="#0b1533" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
    document.body.appendChild(c);
  });
  window.__cursor = (x, y, op, ring) => {
    const c = document.getElementById("__cursor");
    if (!c) return;
    c.style.opacity = String(op);
    c.style.transform = `translate(${x}px,${y}px)`;
    const r = document.getElementById("__ring");
    r.style.opacity = String(ring > 0 && ring < 1 ? 1 - ring : 0);
    r.style.transform = `scale(${0.4 + ring * 1.3})`;
  };
  // find a visible element by text (and optional selector)
  window.__find = (text, sel = "button,a,input,[role=tab]") => {
    const els = [...document.querySelectorAll(sel)].filter((e) => {
      const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && (!text || (e.textContent || e.placeholder || e.getAttribute("aria-label") || "").includes(text));
    });
    return els[0] || null;
  };
  window.__box = (text, sel) => {
    const e = window.__find(text, sel);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return { x: r.left + Math.min(r.width / 2, 60), y: r.top + r.height / 2 };
  };
  window.__click = (text, sel) => { const e = window.__find(text, sel); if (e) e.click(); return !!e; };
  window.__type = (sel, value) => {
    const e = document.querySelector(sel);
    if (!e) return false;
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    set.call(e, value);
    e.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  };
  window.__scrollMain = (y) => { const m = document.querySelector("main"); if (m) m.scrollTop = y; };
};

// ---------- the action timeline (video seconds) ----------
const URL_SEL = 'input[placeholder="https://docs.yourproduct.com"]';
const URL_TEXT = "docs.firecrawl.dev";
const ACTIONS = [
  { t: 7.95, key: "Enter" },
  { t: 12.0, move: [URL_TEXT ? "" : "", URL_SEL], typeFrom: 11.55, typeTo: 12.6 },
  { t: 13.25, click: ["Apps", "[role=tab]"] },
  { t: 13.95, click: ["Support FAQ (internal)", "button"] },
  { t: 14.45, click: ["Escalation policy", "button"] },
  { t: 15.15, click: ["Draft the plan", "button"] },
  { t: 21.25, click: ["Start building", "button"] },
  { t: 32.55, click: ["Firecrawl retries a failed webhook 5 times", "button"] },
  { t: 35.6, click: ["checks passed", "button"] },
  { t: 39.3, click: ["", 'a[aria-label="Report"]'] },
  { t: 41.35, click: ["Other formats", "[role=tab]"] },
];
const MOVE_S = 0.6;
const scrollAct = { from: 14.55, to: 15.0 };
const easeIO = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: DPR });
const page = await ctx.newPage();
page.on("pageerror", (e) => console.error("pageerror:", e.message));
await ctx.route("**/api/**", api);
await page.addInitScript(INIT, { plan: planEvents(), build: buildEvents() });
const T0 = new Date("2026-10-31T01:12:00Z").getTime();
await page.clock.install({ time: T0 });
await page.goto("http://localhost:5173/", { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
// preroll: let the landing settle and the ghost text type part of the suggestion
await page.waitForTimeout(2600);
const startFake = await page.evaluate(() => Date.now());
await page.clock.pauseAt(startFake + 50);

let cur = { x: W * 0.62, y: H * 0.78 }, move = null, ring = -1, cursorOn = 0;
const done = new Set();
let vtPrev = 0;
const frames = Math.round(MAX_S * FPS);
const t0 = Date.now();
for (let f = 0; f < frames; f++) {
  const c = f / FPS; // capture seconds
  const vt = Math.round(c * 1000);
  if (vt > vtPrev) await page.clock.runFor(vt - vtPrev);
  vtPrev = vt;
  await page.waitForTimeout(4);

  const video = c + 4.63;
  for (const [i, a] of ACTIONS.entries()) {
    if (a.key && !done.has(i) && video >= a.t) {
      await page.evaluate(() => { const e = document.querySelector('input[aria-label="Tell Bob what to build"]'); e?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
      done.add(i);
    }
    const target = a.click ?? a.move;
    if (target && !done.has(i + "m") && video >= a.t - MOVE_S - (a.typeFrom ? a.t - a.typeFrom : 0)) {
      const box = await page.evaluate(([t, s]) => window.__box(t, s), target);
      if (box) { move = { from: { ...cur }, to: box, target, t0: video, t1: video + MOVE_S }; done.add(i + "m"); }
    }
    if (a.typeFrom && video >= a.typeFrom && video <= a.typeTo + 0.05) {
      const k = Math.min(URL_TEXT.length, Math.ceil(((video - a.typeFrom) / (a.typeTo - a.typeFrom)) * URL_TEXT.length));
      await page.evaluate(([s, v]) => window.__type(s, v), [URL_SEL, URL_TEXT.slice(0, k)]);
    }
    if (a.click && !done.has(i) && video >= a.t) {
      const okc = await page.evaluate(([t, s]) => window.__click(t, s), a.click);
      if (!okc) console.error("click target missing at", video.toFixed(2), a.click);
      ring = video;
      done.add(i);
    }
  }
  if (scrollAct && video >= scrollAct.from && video <= scrollAct.to + 0.05) {
    const k = easeIO(Math.min(1, (video - scrollAct.from) / (scrollAct.to - scrollAct.from)));
    await page.evaluate((k) => { const m = document.querySelector("main"); if (m) m.scrollTop = k * (m.scrollHeight - m.clientHeight); }, k);
  }
  if (move && video <= move.t1 + 0.4) {
    const live = await page.evaluate(([t, s]) => window.__box(t, s), move.target);
    if (live) move.to = live;
  }
  if (move) {
    const k = easeIO(Math.min(1, Math.max(0, (video - move.t0) / (move.t1 - move.t0))));
    cur = { x: move.from.x + (move.to.x - move.from.x) * k, y: move.from.y + (move.to.y - move.from.y) * k };
  }
  // cursor shows from the Setup screen onward
  cursorOn = video > 10.9 ? Math.min(1, (video - 10.9) / 0.3) : 0;
  const rk = ring > 0 ? (video - ring) / 0.45 : -1;
  await page.evaluate(([x, y, o, r, t]) => { window.__syncAnims(t); window.__cursor(x, y, o, r); }, [cur.x, cur.y, cursorOn, rk, vt]);
  if (video >= 39.0 && phase !== "done") phase = "done";
  if (video >= 32.4 && phase === "build") phase = "done";
  await page.screenshot({ path: `${OUT}/f${String(f).padStart(5, "0")}.jpg`, type: "jpeg", quality: 90 });
  if (f % 60 === 0) console.log(`frame ${f}/${frames} video ${video.toFixed(2)}s  ${((Date.now() - t0) / 1000).toFixed(0)}s elapsed`);
}
await browser.close();
console.log("done");
