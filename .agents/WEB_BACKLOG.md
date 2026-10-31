# Web backlog (for Codex and anyone picking up web work)

> Branch: `claude/bob-web`. App: `web/` (Vite + React 19 + TypeScript + Tailwind v4 + `motion`). Read `web/README.md` first.
> What exists today: landing (floating field, glowing composer, ghost text), blackout transition, composer morph into the workspace, workspace (chat with Bob, Architect plan approval, stage rail, stat tiles, live row stream, inspector with source highlight and checks, export with presets), meme carousel slot, all running on a clearly labelled simulated engine.

## Ground rules
- Don't change data shapes in `web/src/lib/types.ts` without updating `.agents/CONTRACTS.md` (they mirror each other).
- Keep the "Simulated" badge while `mockEngine.ts` is in use. Never present simulated numbers as real results.
- Every animation must respect `prefers-reduced-motion` (use `useReducedMotion` from `motion/react`).
- Run `npm run build` before pushing; it must pass with zero type errors.

---

## A. Art: Bob sprite sheets

### Spec (all sheets)
- Same style, line weight and palette as the existing sheets (yellow hard hat, white/blue body, mint eyes, blue data cube, grey wrench).
- PNG or WebP, **transparent background**, frames in **one horizontal row** with clear transparent gaps between them.
- Same character scale across frames, feet on the same baseline.
- 3 to 4 frames per pose loop.
- Slice with `python3 web/scripts/slice_sprites.py sheet.png name-1 name-2 name-3` (writes `web/src/assets/bob/*.webp`), then add the pose to `POSES` in `web/src/components/Bob.tsx`.

### Poses needed (priority order)
| # | Pose name | Frames | Where it's used |
|---|---|---|---|
| 1 | `dive` | 3 | Blackout transition: Bob jumps into the glowing bar before it morphs |
| 2 | `read` | 3 | Ingest / extract stages: Bob with a document and magnifying glass |
| 3 | `type` | 3 | Write stage: Bob typing on a tiny laptop |
| 4 | `stamp` | 3 | Verify stage: Bob stamping a cube "VERIFIED" |
| 5 | `nope` | 3 | Rejected rows: Bob shaking head, tossing a cracked cube in a bin |
| 6 | `point` | 2 | Waiting for plan approval: Bob pointing left at the Build button |
| 7 | `carry` | 3 | Export: Bob carrying a stack of cubes |
| 8 | `blink` | 3 | Idle loop: subtle blink / breathing |
| 9 | `sweat` | 2 | Error state: confused, sweat drop |
| 10 | `sleep` | 2 | Long idle on the landing page: zzz |

## B. Art: Bob memes for the carousel

- Drop images in `web/src/assets/memes/` (`.webp` preferred, under 150 KB each, about 600x600).
- Caption = filename (`bob-reads-the-terms-of-service.webp` -> "Bob reads the terms of service"), or override in `web/src/assets/memes/captions.json`: `{ "file.webp": "Caption" }`.
- They cycle automatically in the workspace while Bob is waiting (`MemeCarousel.tsx`). No code changes needed.

Ideas (data jokes, keep them kind):
1. Bob reading a 400-page PDF at 3am with coffee
2. Bob staring at a CSV where every column is called "Unnamed: 0"
3. Bob with a lie detector, interrogating an LLM answer
4. Bob sweeping duplicate rows under a rug (then getting caught by the dedup check)
5. Bob building a tower of data cubes; one cube labelled "hallucination" wobbling
6. Bob at a "Fact or Marketing?" game show
7. Bob filling a ".jsonl" box with cubes, one stuck halfway
8. Bob in a hard hat inspecting a "row 4,812" with a magnifier
9. Bob giving a cube a gold star "verified"
10. Bob arguing with a cloud labelled "the docs don't say"
11. Bob at a gym, lifting "10,000 rows"
12. Bob on vacation while the generators run

## C. Animation and UI tasks (code)

Each has an acceptance check.

1. **Bob dives into the bar** (needs `dive` pose). During `blackout`, Bob jumps from the landing header into the bar before the morph. *Done when:* visible in the 2.1 s blackout, no layout jump.
2. **Stage-aware Bob.** Map workspace pose to the active stage (`read` for ingest/extract, `type` for write, `stamp` for verify, `nope` flash on each rejection, `carry` on export). *Done when:* `Workspace.tsx` picks the pose from `job.stages`.
3. **Whole-page drag and drop** on the landing page: dropping files shows a glowing drop zone and attaches them to the composer. *Done when:* files appear as chips in the composer.
4. **Cubes assemble on verify.** A small cube pile in the stat tile grows as verified rows arrive; rejected rows show a cracked cube falling away. *Done when:* smooth at 30 rows/s, no dropped frames.
5. **Completion celebration.** Confetti made of mini data cubes and pixels on `done`, 1.5 s, reduced-motion aware.
6. **Source scan line.** When a row is selected, a scan line sweeps the source block before the highlight appears.
7. **Real API client.** Implement `JobClient` (`POST /jobs`, then server-sent events mapped to `JobEvent`), behind `VITE_API_URL`; fall back to the mock when unset and keep the badge. *Done when:* switching is one env var.
8. **Backend formats.** Wire Parquet, Avro and Postgres JSONB `.sql` downloads to the backend export endpoint (buttons exist, currently locked).
9. **Row list virtualisation** for 10k+ rows (only the last 120 render today).
10. **Keyboard.** `j/k` moves through rows, `e` opens Export, `Esc` clears the selection.
11. **Accessibility pass.** Focus rings on all controls, `aria-live` for Bob's chat messages, colour-contrast check on dim text.
12. **Landing polish.** Optional sound toggle (soft blip on Enter), idle `sleep` pose after 60 s without input.

## D. Known gaps
- The simulated engine always uses one sample corpus for row content; only the source list reflects the user's URL/files.
- Fonts load from Google Fonts; add local fallbacks if the venue wifi is bad.
