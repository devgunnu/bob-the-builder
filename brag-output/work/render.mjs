// Renders compositor.html frame by frame. Usage: node render.mjs <outDir> [t1,t2,...]  (no list = full 60 s at 30 fps)
import { createRequire } from "node:module";
import fs from "node:fs";
const { chromium } = createRequire(import.meta.url)("playwright");
const OUT = process.argv[2] ?? "out";
const list = process.argv[3] ? process.argv[3].split(",").map(Number) : null;
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on("pageerror", (e) => console.error("pageerror", e.message));
await page.goto("file://" + process.cwd() + "/compositor.html");
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(500);
const times = list ?? Array.from({ length: 1800 }, (_, i) => i / 30);
const t0 = Date.now();
for (const [i, t] of times.entries()) {
  await page.evaluate((t) => window.render(t), t);
  const name = list ? `t${t.toFixed(2)}.jpg` : `f${String(i).padStart(5, "0")}.jpg`;
  await page.screenshot({ path: `${OUT}/${name}`, type: "jpeg", quality: 93 });
  if (!list && i % 150 === 0) console.log(`frame ${i} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
await browser.close();
console.log("done");
