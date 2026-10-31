# Bob frontend

React 18 + TypeScript + Vite + Tailwind v4 + `motion`, with `@microsoft/fetch-event-source` for the live stream.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000 (BOB_API_PROXY overrides)
npm run build      # tsc + vite build
```
The client always calls the relative `/api` (same origin through CloudFront in production). The application does not require sign-in.

## Flow
0. Bob uses Bedrock in its hosting account and checks the configured models when a job starts. Model settings can be changed at `/account`.
1. `/` landing: floating field, glowing composer, ghost-text suggestions (Tab accepts).
2. Enter: everything scatters, the room goes black, only the bar stays lit.
3. The bar morphs (shared `layoutId="composer"`) into the Setup screen's goal field. Sources: website (Firecrawl), files (`/uploads`), connected apps (Composio OAuth popup + page picker), seeds, rows, budget.
4. `/jobs/:id/plan`: live reading progress (SSE `stage.progress`), then the editable coverage map. Start sends `PUT /jobs/{id}/plan`.
5. `/jobs/:id/build`: heatgrid (kept / target), counters, cost meter vs frontier-only, round banner, fallback badge, row feed.
6. `/jobs/:id/rows/:rowId`: conversation, cited spans, checks by tier.
7. `/jobs/:id/report`: coverage, pass rates, reject reasons, judge agreement, rounds, spot-check, export.

## Real data only
No mock engine, no sample rows (CONTRACTS §0, §12). Every screen renders an empty or loading state until the API answers. `src/api/types.ts` mirrors CONTRACTS §2 exactly; `src/api/client.ts` has one function per §6 route; `useJobStream` applies §8 events and de-duplicates replays.

## Structure
```
src/api/           types.ts, client.ts, useJobStream.ts           (G3)
src/screens/       Home, Setup, Plan, Account, JobList, OAuthCallback   (G3)
                   Build, RowInspector, Report                    (G4)
src/components/    Bob (sprites), Composer, Landing, AppShell, ui, ModelsEditor, MemeCarousel
src/components/viz Heatgrid, Bars                                 (G4)
src/assets/bob/    sprite frames (640x640, shared baseline)
src/assets/memes/  drop meme images here; they rotate automatically
scripts/slice_sprites.py
```
