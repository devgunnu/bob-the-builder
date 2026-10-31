# UX rules for the frontend (keep it calm)

> Why: after the prompt, the first version showed every control and number at once. These rules keep each screen to one idea and one next step, with the same functionality behind progressive disclosure.

## Principles
1. **One primary action per screen.** Setup: Draft the plan. Plan: Start building. Build: (none until done) then See the report. Report: Download dataset. Everything else is a quiet text button.
2. **Summary first, details on demand** (progressive disclosure). Lead with one sentence or one number; put the rest behind a tab, a "Change" or a "Fine-tune" toggle.
3. **Fewer choices at once** (Hick's law). Group sources into tabs (Website / Files / Apps); hide filters until "Filter" is clicked.
4. **Smart defaults.** 1,000 rows, $10, 25 pages, openai-chat JSONL. Show them as one line the user can change.
5. **Silence when healthy.** Provider status is a green dot; it only becomes a chip when something fails. Errors and fallbacks always show.
6. **Never hide what matters:** errors, budget overruns, rejected-row reasons, cancel.

## Screen by screen
| Screen | Shows by default | Behind a click |
|---|---|---|
| Setup | Goal bar, source tabs, added-source chips, one options line, Draft the plan | Rows, budget, seeds ("Change"); page preview |
| Reading | Bob + one sentence + one progress bar + counts line | Cancel (text link) |
| Plan | One-sentence summary with rows and cost, Planner notes, the grid (click = on/off, double-click = rows), Start | Personas, difficulty, system prompt, grid filters ("Fine-tune") |
| Build | "X of Y rows kept", one status sentence, cost vs frontier-only, coverage map, Kept / Rejected tabs | Filters, cost breakdown (hover), reject reasons (Rejected tab), cancel |
| Row | Verdict, conversation, cited sources, "All N checks passed" | Passed checks list; failed checks always open |
| Report | Headline, one sentence of key numbers, Download dataset | Tabs: Coverage, Quality, Spot-check, Other formats |

Sources: progressive disclosure (Nielsen, via [The Decision Lab](https://thedecisionlab.com/es-ES/reference-guide/design/progressive-disclosure), [ezud](https://ezud.com/progressive-disclosure-showing-complexity/)); Hick's law ([Helio](https://helio.zurb.com/ux-research/laws-of-ux/hicks-law/), [Octet](https://octet.design/journal/hicks-law)).
