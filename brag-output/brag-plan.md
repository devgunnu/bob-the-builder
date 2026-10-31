# Bob the Builder: 60-second demo video plan

Made with the /brag skill (latent-spaces/brag). On Opus 5.5 /brag hands off to /brag-slim, so the video is built by hand: the real app is captured frame by frame, then composited and rendered in a headless browser.

Length: 59.5 s. That's longer than brag's usual 15 to 25 s because the hackathon form asks for a demo of up to 60 s.

## Answers to the planning questions

- **What is it?** A synthetic data factory: goal + company docs in, a verified fine-tuning dataset out. Every row ships with its proof.
- **Who is it for?** Teams fine-tuning a support or docs model who have docs but no training data.
- **What sets it apart?** A cheap LLM writes. Small decision models (Jev, ScaleDown) check every row against the source, and the strong judge model only sees rows where the checks disagree. It also covers the cases synthetic data usually skips: "not in the docs" and "wrong assumption".
- **Most impressive claim:** every kept row links to its source passage and to every check it passed.
- **Visual hook:** a row that sounds confident but invents a feature, stamped as rejected.
- **Real UI to show:** Landing (Bob, ghost-typed goal) > blackout dive > Sources > Plan grid > live Build heatgrid + feed > Row inspector with highlighted source > Report + export presets.
- **Tone:** `default`, punchy and playful, matching Bob's character and palette. The product is serious; the mascot carries the fun.
- **Share caption:** see share-copy.txt.

## Identity (taken from the code)

- Palette: Bob yellow #ffc82e, blue #1f5bff, sky #4d8bff, mint #63f0cf, navy #0b1533, cream #f6f3ec, void #030409.
- Type: Bricolage Grotesque (display), Inter (UI), JetBrains Mono (data).
- Art: Bob's sprite poses from `frontend/src/assets/bob/` (wave, dive, type, stamp, cheer, hero, nope).

## Music

"Happy Beats / Business Moves Vol. 10" by Sascha Ende (ende.app), CC BY 4.0, bundled with brag. It's 60.0 s at ~110 BPM and ends on its own at 59.5 s. Beat 1 is at 0.267 s; one bar = 2.183 s. Natural break at 43.9 to 45.5 s, used for the punchline. Every cut below is on a bar line.

## Storyboard

| # | Time (s) | Scene | On screen | Caption |
|---|---|---|---|---|
| 1 | 0.00 to 2.45 | Hook | Cream, big type punches in | "Fine-tuning needs thousands of examples." |
| 2 | 2.45 to 4.63 | Hook | A confident synthetic row, stamped REJECTED: invented feature | "Synthetic data makes things up." |
| 3 | 4.63 to 11.18 | Reveal | Real landing: Bob waves, goal ghost-types, Enter, the room goes black, Bob dives | "Meet Bob." |
| 4 | 11.18 to 15.55 | Sources | Real Setup: docs.firecrawl.dev typed, Notion support wiki picked | "Point him at your docs and your Notion." |
| 5 | 15.55 to 22.10 | Plan | Reading progress, then the plan grid (topics x 4 kinds of question); cursor clicks Start building | "He maps what the data must cover." / "Even what the docs don't answer." |
| 6 | 22.10 to 33.02 | Build | Live heatgrid fills, rows stream in, rejects appear, gap round, Bob cheers | "A cheap model writes every row." / "Small decision models check every one." / "The judge only sees rows where checks disagree." |
| 7 | 33.02 to 39.57 | Proof | Row inspector: a wrong-assumption row, source passage highlighted, checks expand | "Every row ships with its proof." |
| 8 | 39.57 to 43.93 | Ship | Report headline, Other formats tab: openai-chat, sharegpt, alpaca, modelforge, dpo, full | "Export to any format." |
| 9 | 43.93 to 45.56 | Punchline (music break) | Bob stamps, near silence | "No made-up rows." |
| 10 | 45.56 to 52.67 | Under the hood | Pipeline: Firecrawl + Composio > Jev + ScaleDown > AWS Bedrock > dataset | "Built from scratch in 5 hours." |
| 11 | 52.67 to 59.50 | Outro | Bob hero, wordmark, one-liner, team, repo | "building datasets you never could" |

## Data shown in the app

No full job had run end to end when this was made, so the app screens are driven by a scripted stand-in for the API (Playwright request interception plus an in-page event stream). Everything visible is real product UI. The questions, answers and source passages come from the team's real demo corpus (`demo/corpus/`: Firecrawl docs + the fictional Notion support wiki). Row counts and costs are illustrative; costs follow the plan's own estimate (about $1.85 per 1,000 kept rows vs about $20 frontier-only). Captions make no numeric claims. Swap in a capture of a real run when one exists.

No secrets, keys, emails or real customer data appear. The user shown is local mode (no sign-in).
