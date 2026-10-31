# Prompt for Codex (frontend)

Paste everything below the line into Codex, opened on the `bob-the-builder` folder, branch `claude/bob-web`.

---

You are working on the frontend of **Bob the Builder**, a synthetic data factory: a user gives a goal and their company's docs, Bob plans a coverage map, writes candidate fine-tuning rows with a cheap LLM, checks every row with small decision models, and ships the dataset with proof for each row.

## Read these first, in order
1. `.agents/UX_NOTES.md`: the UI rules. They are not optional.
2. `.agents/WEB_BACKLOG.md`: your task list (sections A, B, C).
3. `frontend/README.md`: setup, flow and folder structure.
4. `.agents/CONTRACTS.md` sections 2 (data models), 6 (HTTP API), 8 (SSE events) and 14 (accounts, AWS, models). `frontend/src/api/types.ts` mirrors section 2 exactly.
5. `.agents/AGENT_BRIEFS.md`, the G3 and G4 briefs (frontend ownership and pitfalls).

## Setup
```bash
git checkout claude/bob-web && git pull
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api to localhost:8000
```

## Hard rules
- **Work only in `frontend/` and `.agents/WEB_BACKLOG.md`.** Never touch `backend/`, `infra/`, or the other `.agents/` files. If you need a backend change, add a row to `.agents/CHANGES_REQUESTED.md`.
- **Real data only.** No mock clients, sample rows, fake numbers or placeholder JSON in the repo. Screens show an empty or loading state until the API answers. (For visual checks you may intercept `/api` in a throwaway Playwright script outside the repo; never commit it.)
- **Never change `src/api/types.ts`** except to match `.agents/CONTRACTS.md` section 2 exactly.
- **Keep the UI calm** (UX_NOTES):
  - one primary action per screen;
  - summary first, details behind a click;
  - plain language, no jargon;
  - no hidden gestures (no double-click or long-press only);
  - visible keyboard focus;
  - respect `prefers-reduced-motion`.
- **Personality lives on the landing page only** (`/`, `src/components/Landing.tsx`). Inside the app, Bob is a still image (`<Bob still float={false} />`) and motion is limited to short fades, progress bars and the row-arrival flash. No looping animations, confetti or memes inside the app.
- **Auth and network:**
  - Every API call goes through `src/api/client.ts` (bearer token, relative `/api`).
  - Live updates use `subscribeJob`.
  - Downloads use `api.download` (the signed `/url` route), never a plain `<a href>` to the API.
- **No em dashes** in any UI text, docs or commit messages.
- Keep files small and readable; match the existing style (Tailwind classes, `motion/react`, `lucide-react` icons, the colour tokens in `src/index.css`).

## Your tasks (in this order)
1. **Sprites (WEB_BACKLOG A).** For each new sprite sheet in `frontend/art/` (create the folder if needed):
   - slice it with `python3 frontend/scripts/slice_sprites.py <sheet> <name-1> <name-2> ...`;
   - register the pose in `src/components/Bob.tsx`.
   If no sheets exist yet, skip this step; don't draw placeholder art.
2. **Memes (WEB_BACKLOG B).** Meme images go in `src/assets/memes/` (WebP, under 150 KB). Captions come from filenames or `captions.json`. They only rotate in the landing page meme card.
3. **Stage-aware still Bob (WEB_BACKLOG C2).** On the Plan reading view and the Build headline, pick a still pose from `useJobStream().lastStage`:
   - `read` for fetch, triage and evidence;
   - `type` for generate;
   - `stamp` for verify;
   - `carry` for export.
   Fall back to existing poses when a pose doesn't exist yet.
4. **Row history (C8).** The Build row feed keeps the last 200 events. Add a quiet "Load older rows" button that pages `GET /jobs/{id}/rows` (`api.rows`).
5. **Cell drawer (C9).** Clicking a Build heatgrid cell opens a side drawer listing that cell's rows (`api.rows(id, { cell_id })`), each linking to the row screen. Esc closes it.
6. **Accessibility (C11).**
   - `aria-live="polite"` on the Build status sentence.
   - Visible focus on every control.
   - Check contrast of `text-dim` on panels (WCAG AA 4.5:1 for small text) and fix any failures.
7. **Performance.**
   - Lazy-load the Amplify sign-in (`src/auth/AuthGate.tsx`) and the screens with `React.lazy`, so the first bundle shrinks (the build currently warns about chunk size).
   - Make the Build row feed stay smooth with 1,000+ row events.
8. **Landing polish (C1, C12).** Only if the art exists:
   - Bob dives into the glowing bar during the blackout (`src/screens/Home.tsx`);
   - Bob sleeps after 60 s idle on the landing page.
   Nothing in the app screens.

After each task, tick it off in `.agents/WEB_BACKLOG.md`.

## Done means, for every task
- `cd frontend && npx tsc -b && npm run build` passes with no errors.
- No new hard-coded data, hosts or Cognito ids.
- The screen still follows UX_NOTES. Check it at 1440x900 and 390x844.
- Commit small, one task per commit, with a clear message, on `claude/bob-web`, then `git push origin claude/bob-web`.

When unsure, choose the simpler, calmer option and leave a note in `.agents/WEB_BACKLOG.md` instead of guessing.
