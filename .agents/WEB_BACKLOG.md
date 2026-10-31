# Web backlog (for Codex and anyone picking up web work)

> Branch: `claude/bob-web`. App: `frontend/` (Vite + React 18 + TypeScript + Tailwind v4 + `motion`). Read `frontend/README.md` first.
> What exists today (v4): landing (floating field, glowing composer, ghost text), blackout transition, composer morph into Setup, and all v4 screens wired to the real API (Setup, Plan, Build, Row inspector, Report, Jobs, OAuth callback). No mock engine.

## Ground rules
- `frontend/src/api/types.ts` mirrors CONTRACTS §2 exactly; never add fields that aren't in the contract.
- Real data only (CONTRACTS §0, §12): no sample rows or demo numbers in the repo.
- Every animation must respect `prefers-reduced-motion` (use `useReducedMotion` from `motion/react`).
- Run `npm run build` before pushing; it must pass with zero type errors.

---

## A. Art: Bob sprite sheets

### Spec (all sheets)
- Same style, line weight and palette as the existing sheets (yellow hard hat, white/blue body, mint eyes, blue data cube, grey wrench).
- PNG or WebP, **transparent background**, frames in **one horizontal row** with clear transparent gaps between them.
- Same character scale across frames, feet on the same baseline.
- 3 to 4 frames per pose loop.
- Slice with `python3 frontend/scripts/slice_sprites.py sheet.png name-1 name-2 name-3` (writes `frontend/src/assets/bob/*.webp`), then add the pose to `POSES` in `frontend/src/components/Bob.tsx`.

### Poses needed (priority order)
| # | Pose name | Frames | Where it's used |
|---|---|---|---|
| 1 | `dive` | 3 | Blackout transition: Bob jumps into the glowing bar before it morphs | Done |
| 2 | `read` | 3 | Plan screen while reading (fetch, triage, evidence): Bob with a document and magnifying glass | Done |
| 3 | `type` | 3 | Build screen during `generate`: Bob typing on a tiny laptop | Done |
| 4 | `stamp` | 3 | Build screen during `verify`: Bob stamping a cube "VERIFIED" | Done |
| 5 | `nope` | 3 | Rejected rows: Bob shaking head, tossing a cracked cube in a bin | Done |
| 6 | `point` | 2 | Plan screen: Bob pointing at the Start button | Done |
| 7 | `carry` | 3 | Export: Bob carrying a stack of cubes | Done |
| 8 | `blink` | 3 | Idle loop: subtle blink / breathing | Done |
| 9 | `sweat` | 2 | Error state: confused, sweat drop | Done |
| 10 | `sleep` | 2 | Long idle on the landing page: zzz | Done |

## B. Art: Bob memes for the carousel (Done)

- Drop images in `frontend/src/assets/memes/` (`.webp` preferred, under 150 KB each, about 600x600).
- Caption = filename (`bob-reads-the-terms-of-service.webp` -> "Bob reads the terms of service"), or override in `frontend/src/assets/memes/captions.json`: `{ "file.webp": "Caption" }`.
- They cycle automatically in the meme card that floats on the landing page (`MemeCarousel.tsx` inside `Landing.tsx`). No code changes needed. Memes stay on the landing page only (UX_NOTES rule 7).

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
2. **Stage-aware Bob (still frames only).** Swap the still AppShell / reading-screen pose by `lastStage` (`read` for fetch/triage/evidence, `type` for generate, `stamp` for verify, `carry` for export). No loops inside the app (UX_NOTES rule 7). *Done when:* Plan and Build pass the pose from the stream. **Done.**
3. **Whole-page drag and drop** on the landing page: dropping files shows a glowing drop zone and attaches them to the composer. *Done when:* files appear as chips in the composer.
4. **Cubes assemble on verify.** A small cube pile next to the Kept counter grows as kept rows arrive; rejected rows show a cracked cube falling away. *Done when:* smooth at 30 rows/s.
5. **Completion moment (subtle).** On `done`, a single soft fade-in of the report headline; no confetti inside the app (UX_NOTES rule 7).
6. **Source scan line.** When a row is selected, a scan line sweeps the source block before the highlight appears.
7. **Done:** real API client, SSE helper with replay de-duplication, all v4 screens.
8. **Row history.** Build feed keeps the last 200 events; add a "load more" that pages `GET /jobs/{id}/rows`. **Done.**
9. **Heatgrid cell click** on Build: open a drawer listing that cell's rows (`GET /rows?cell_id=`).
10. **Keyboard.** `j/k` moves through rows, `e` opens Export, `Esc` clears the selection.
11. **Accessibility pass.** Focus rings on all controls, `aria-live` for Bob's chat messages, colour-contrast check on dim text.
12. **Landing polish.** Idle `sleep` pose after 60 s without input; new poses and memes go here, where the personality lives.

## D. Known gaps
- Fonts load from Google Fonts; add local fallbacks if the venue wifi is bad.
