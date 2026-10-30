# Research 04: Hackathon Stack, Partner Fit, and Build Plan

> Source: research agent, 2026-10-30. Docs domains for Photon and Firecrawl were blocked in the research sandbox; code was verified against GitHub READMEs and doc snippets. Re-verify Photon `attachment()` / `richlink()` signatures before 5pm. Spectrum is "early preview", so pin versions.

## 1. Partner fit and prizes

| Prize | Fit | Realistic? |
|---|---|---|
| Photon, $1k "Best iMessage Agent You Can Text" | "Text Bob a URL, get back a fine-tuning dataset link + .jsonl attachment." Tangible, demos live on a phone, not another chatbot. | Strongest target. A May 2026 Photon update says it doubles hackathon prizes won with its SDK (confirm tonight). |
| Anthropic, $10k credits for top 3 | Claude Haiku does generation and judging. Pitch: "1,000-example SFT set for about $0.50 to $2." | Plausible. Depends on overall demo polish. |
| Firecrawl, Convex, Bolt | No named prizes. Use where useful and name them in the demo. | Goodwill. |
| Mercury, HeyPCB, Nebula | No meaningful fit. | Skip. |

### Firecrawl (URL or site as corpus)
```python
from firecrawl import Firecrawl
from firecrawl.types import ScrapeOptions
fc = Firecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])
doc = fc.scrape(url, formats=["markdown"])          # doc.markdown
job = fc.crawl(url, limit=15, scrape_options=ScrapeOptions(formats=["markdown"]), poll_interval=2)
pages = [d.markdown for d in job.data]              # verify attribute on installed version
urls = fc.map(url)                                  # cheap URL discovery
```
Gotchas: `crawl()` blocks, so use `start_crawl()` + status polling for live progress. Each page costs credits; cap `limit` at 10 to 20. `CrawlJobTimeoutError` carries `job_id`. Keep `onlyMainContent` on (default) to strip nav boilerplate. Pre-crawl the demo site and cache markdown on disk.

### Convex (realtime progress + file storage)
```python
from convex import ConvexClient
cx = ConvexClient(os.environ["CONVEX_URL"])
cx.mutation("jobs:progress", {"jobId": jid, "stage": "generating", "done": 120.0, "total": 400.0, "secret": S})
```
- Frontend: `npm i convex`, `npx convex dev`, `useQuery(api.jobs.get, {jobId})` gives live updates.
- Storage: mutation returns `ctx.storage.generateUploadUrl()`; Python POSTs bytes and gets a `storageId`; `ctx.storage.getUrl()` yields a public download link (what iMessage sends back).
- Gotchas: Python calls public functions only (guard with a shared secret arg). Docs are about 1 MB max, arrays 8,192 elements, so never store a whole dataset in a document. Send floats for `v.number()`. Actions time out at 10 min with tight memory, so keep the heavy pipeline in Python.

### Photon Spectrum (text a URL, get a dataset)
TypeScript only (Python planned), so run a small Bun sidecar. `bun add spectrum-ts`; get `PROJECT_ID` / `PROJECT_SECRET` at app.photon.codes. Provision the managed iMessage line before 5pm.
```ts
import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
const app = await Spectrum({ projectId: process.env.PROJECT_ID, projectSecret: process.env.PROJECT_SECRET,
  providers: [imessage.config()], signal: AbortSignal.timeout(10_000) });
for await (const [space, message] of app.messages) {
  if (message.content.type !== "text") continue;            // verify content shape in docs
  const url = message.content.text.match(/https?:\/\/\S+/)?.[0];
  await space.responding(async () => {
    if (!url) return message.reply("Text me a URL + optional 'qa 200' / 'dpo 50'");
    await message.reply(`On it, crawling ${url}`);
    const { jobId } = await (await fetch(`${API}/jobs`, {method:"POST", body: JSON.stringify({url, source:"imessage"})})).json();
    const res = await pollUntilDone(jobId);
    await message.reply(`Done: ${res.n} examples, $${res.cost}. Download: ${res.url}\nPreview: ${res.sample}`);
  });
}
```
Gotchas: managed provider needs no Mac or tunnel. `attachment()` takes a path or Buffer. Ack immediately (jobs take 30 to 90s). Delivery is not replayed, so make jobs idempotent per message id. Demo from a phone that is not the laptop's iMessage account.

### Anthropic (Claude Haiku for generation + judging)
- PRICING CORRECTION (see research 03, official page): use Claude Haiku 5.5 at $0.10 in / $0.50 out per M tokens ($0.05 / $0.25 batch). The figures in this section were computed for Haiku 4.5 ($1 in / $5 out per M), so real costs are about 10x lower. Haiku 4.5: cache reads $0.10/M; Batch API 50% off but async (do not use live; pitch it as "production cheap mode").
- Cost math: about 600 in + 250 out tokens per example is about $0.0019/example, so 1k examples is about $1.90 (about $0.95 batched). Show a live cost counter.
- Use tool use / structured outputs for JSON. Use Haiku as a judge (faithfulness 1 to 5, drop below 4).
- DPO trick: chosen is grounded in the chunk; rejected is generated without the chunk or told to be subtly vague.
- Gotchas: new orgs have low RPM. `asyncio.Semaphore(8)`, backoff on 429, cap demo jobs at 100 to 200 examples. Pool team credits.

### Bolt
Optional: scaffold landing/upload UI in about 20 minutes, export to repo, wire Convex manually. Do not run the app inside Bolt's WebContainer.

## 2. Output format libraries

Canonical internal row: `{id, task, messages:[{role,content}], prompt, response, chosen, rejected, source_url, chunk_id, score}`. Every exporter is a projection of it.

| Format | Library | Notes |
|---|---|---|
| JSONL / JSON | `json` or `orjson` | `ensure_ascii=False`. |
| Parquet | `pyarrow` | Explicit schema; `messages: list<struct<role,content>>`; `compression="zstd"`. Inference breaks on null `chosen`, so always pass schema. |
| Avro | `fastavro` | Explicit schema; optional fields `["null","string"]` with `default: null`; `codec="deflate"`; validate with `validate_many`. |
| JSONB | n/a | JSONB is a Postgres column type, not a file format. Ship (1) a `.sql` script: `CREATE TABLE IF NOT EXISTS bob_dataset(id text primary key, task text, data jsonb not null);` + `INSERT ... $tag$...$tag$::jsonb` with a random dollar-quote tag, optional GIN index; and (2) optional direct "push to Postgres" via `psycopg` v3 `Jsonb()` or `COPY`. Label it "Postgres JSONB (.sql)". |
| CSV | `csv` | `newline=""`, `QUOTE_ALL`, `utf-8-sig` for Excel. Nested messages as a JSON string column plus flat prompt/response columns. Excel cell limit 32,767 chars. |
| HF Datasets | `datasets`, `huggingface_hub` | `Dataset.from_list(rows).train_test_split(0.1).push_to_hub(...)` + dataset card. Install before the event. |

Presets: OpenAI chat SFT, OpenAI DPO, Alpaca, ShareGPT, TRL (prompt/completion, prompt/chosen/rejected), ModelForge (see research 01).

## 3. Stack, layout, plan, demo, risks

### Stack
- Backend: Python FastAPI + uvicorn, pipeline as asyncio background tasks.
- State/realtime/files: Convex (`jobs`, `samples` tables; exports in storage).
- Frontend: Vite + React + Convex (Bolt or shadcn/Tailwind). Screens: Upload/URL + options; Live job (stepper, progress, cost ticker, sample feed with judge scores); Downloads (+ Push to HF).
- iMessage: Bun sidecar with `spectrum-ts` calling FastAPI.
- Cheap selection: markdown/semantic chunking, heuristic filters, MinHash dedup (`datasketch`), `model2vec` potion embeddings (about 30 MB, CPU) or `fastembed`, k-means/MMR diversity x info score, optional cheap teachability score.

### Pre-event (if allowed; else first 10 minutes)
Accounts and keys, Photon line, `npx convex dev`, `pip install` everything, download embedding model, pick demo URL. Write no product code beforehand.

### Hour-by-hour (A pipeline, B exporters, C web/Convex, D Photon/demo)
| Time | A | B | C | D |
|---|---|---|---|---|
| 5:00 to 5:20 | Everyone: repo + canonical row schema | | | |
| 5:20 to 6:20 | Ingest (Firecrawl + files), chunk, heuristic filter | JSONL/JSON/CSV/Parquet + OpenAI/Alpaca/ShareGPT presets | Convex schema + mutations, Vite skeleton | Spectrum echo bot on a real phone |
| 6:20 to 7:20 | Generation (SFT/QA), cost tracking | Avro, JSONB .sql, HF push, ModelForge preset | Live job view, upload to POST /jobs | Sidecar to FastAPI, reply with link |
| 7:20 to 8:00 | Integrate end to end | | | |
| 8:00 CUT LINE 1 (MVP) | URL to crawl to 100 SFT examples to JSONL + Parquet + CSV with live progress. If behind, drop Avro/JSONB/HF/DPO. | | | |
| 8:00 to 9:00 | DPO + judge filter, embedding selection | Zip bundle, storage links | Polish: stepper, cost ticker, score cards | iMessage attachment + preview; record backup video |
| 9:00 CUT LINE 2 (freeze) | Bug fixes only | | | |
| 9:00 to 9:30 | Stretch: hand Parquet to ModelForge, show one-line train command | | | |
| 9:30 to 9:50 | Rehearse demo 3x, preload cache, reset DB | | | |
| 9:50 to 10:00 | README + architecture diagram + sponsor list, commit | | | |

### 2-minute demo script
1. 0:00 Hook: "Fine-tuning data is the bottleneck. Bob turns any corpus into a training set for fractions of a cent per example."
2. 0:15 iMessage: text "https://docs.<judge-favorite>.com qa 100". Bob acks instantly.
3. 0:35 Web UI shows the same job live: 15 pages, 240 chunks, 60 high-signal kept (show rejected nav/boilerplate), cost ticker "$0.07 so far", sample cards with judge scores, one rejected as unfaithful.
4. 1:20 Formats: open Parquet and OpenAI JSONL, load JSONB .sql into Postgres in one line, ModelForge preset, Push to HF.
5. 1:40 Phone: "100 examples, $0.11, link + .jsonl attached."
6. 1:55 Close: "Any URL to training data in 60 seconds for about a dime."
Keep a pre-run job in a second tab.

### Risks
| Risk | Mitigation |
|---|---|
| Wifi | Cached corpus in `demo/`, "use cache" flag, phone hotspot, backup video at 9:00. |
| API rate limits | Semaphore 6 to 8, backoff, ≤150-example demo jobs, pooled keys, cached result for demo URL. |
| Firecrawl slow/credits | `limit≤15`, map then scrape, fallback `httpx` + `trafilatura`. |
| Model downloads | No torch on laptops; model2vec / fastembed; TF-IDF fallback. (GPU box changes this, see master plan.) |
| Photon delays | Sign up first, test on phone by 6:20, pin version, fall back to Spectrum terminal provider. |
| Convex limits | Files in storage; only last 50 samples in DB. |
| Bad LLM JSON | Structured output schema + Pydantic; count and drop failures. |
| Schema surprises | Explicit schemas; round-trip read test for every export. |
| Scope creep | Freeze at 9:00; DPO and HF push are toggles. |

## Sources
- Photon Spectrum: https://github.com/photon-hq/spectrum-ts, https://docs.photon.codes/spectrum-ts/getting-started, https://photon.codes/docs/spectrum-ts/content/attachments, https://photon.codes/weekly-update/may-14-2026
- Firecrawl: https://github.com/firecrawl/firecrawl/tree/main/apps/python-sdk, https://pypi.org/project/firecrawl/
- Convex: https://github.com/get-convex/convex-py, https://docs.convex.dev/functions/actions.md
- Anthropic: https://docs.claude.com/en/docs/about-claude/pricing
- Bolt: https://bolt.new/blog/bolt-cloud
- Event: https://luma.com/nighthack
- From general knowledge (verify): pyarrow, fastavro, psycopg 3 Jsonb, HF push_to_hub, OpenAI DPO JSONL shape.
