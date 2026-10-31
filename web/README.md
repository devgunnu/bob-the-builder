# Bob web

The landing page and workspace for Bob the Builder.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

## Flow
1. **Landing**: floating field (parallax), glowing composer with ghost-text suggestions (Tab accepts).
2. **Enter**: everything scatters, the room goes black, only the glowing bar stays.
3. **Workspace**: the bar flies into the chat panel (shared `layoutId="composer"`), panels rise in.

## Structure
```
src/
  App.tsx                     phase machine: landing -> blackout -> workspace
  components/
    Bob.tsx                   sprite animator (poses: hero, idle, wave, think, idea, cheer)
    Composer.tsx              glowing input, ghost typing, file attach
    Landing.tsx               backdrop, floaters, header
    MemeCarousel.tsx          cycles images in src/assets/memes/
    workspace/                ChatPanel, Pipeline (stages + stats), RowStream, Inspector (+ export)
  lib/
    types.ts                  mirrors .agents/CONTRACTS.md
    mockEngine.ts             SIMULATED engine (shows "Simulated" badge)
    useJob.ts                 subscribes to a JobSession
    exporters.ts              presets + JSONL/JSON/CSV in the browser
  assets/bob/                 sliced sprite frames (640x640, shared baseline)
  assets/memes/               drop meme images here
scripts/slice_sprites.py      slice new sprite sheets into frames
```

## Connecting the real backend
Implement `JobClient` from `src/lib/types.ts` (for example `POST /jobs` then an event stream emitting `JobEvent`s), swap it in `App.tsx`, and set `SIMULATED = false`.

## Adding art
- Sprites: `python3 scripts/slice_sprites.py sheet.png pose-1 pose-2 pose-3`, then register the pose in `Bob.tsx`.
- Memes: drop `.webp/.png/.jpg/.gif` files in `src/assets/memes/`. Captions come from filenames, or `captions.json`.

See `.agents/WEB_BACKLOG.md` for the open art and animation tasks.
