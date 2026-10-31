# Research 11: The data factory (v4 ideation record)

> 2026-10-30. Record of the design conversation that produced v4. **Supersedes** the template parts of research 05 to 08 and sections 1 to 4 of research 09 (DECISIONS D18).
> Source of truth for the build: `PLAN.md` and `CONTRACTS.md`. This file explains why.

## 1. The problem

A team wants a small model for one narrow job. They have docs and internal notes, but no training data. Today they have two bad options:

- **Write the data by hand.** Slow and expensive. Nobody does more than a few hundred rows.
- **Ask a frontier LLM to write it.** Fast, but the rows can be wrong, and nobody can see which ones. The model skips whole topics, repeats itself, and almost never writes the hard cases: questions the docs do not answer, and questions with a wrong assumption.

The value is not in generation. Generation is cheap and common. The value is in **coverage** (every topic, persona and hard case) and **proof** (every row checked against the source). Research 10 came to the same conclusion.

## 2. Why templates were dropped

v2 and v3 tried to get correctness by construction:

| Version | Idea | Why it failed the bar |
|---|---|---|
| v2 (research 05, 07, 08) | Zero-LLM: Extract builds a fact graph, question programs compose rows, a grammar bank phrases them, Jev picks the best phrasing | Reads as templated. Hand-built schemas and grammars per domain. Strong on fact-dense tables, weak on narrative docs (ASSESSMENT, weak points 3 and 4) |
| v3 (research 09) | An Architect LLM writes generator code + verifier code + unit tests per corpus; a cheap Writer phrases rows with locked slots | Still templates, only written by an LLM. Needs a sandbox, a repair loop and code review. Too much machinery for 4 hours, and hard to show in a demo |

The user decided to drop templates completely (D18). The Writer LLM writes each row directly. The correctness guarantee moves from "built correct" to "checked correct": every row goes through a verification cascade, and only checked rows ship.

What carries over: the verification ideas (D16), the evidence index with verbatim spans (from the fact graph), and the focus on faithfulness and abstention (D17).

## 3. Mechanisms considered

| | Mechanism | Idea | Result | Why |
|---|---|---|---|---|
| A | Student in the loop | Train a small model on each round, find where it fails, generate more there | **Dropped** | Bob does not train models (D20). A training loop does not fit in 4 hours and makes Bob depend on a GPU |
| B | Quality-diversity map (MAP-Elites; Rainbow Teaming, Meta 2024) | Keep an archive over chosen axes; fill each cell with the best item | **Kept, as the coverage map** | Axes = topic x persona x case_type x difficulty. The map makes coverage visible, editable by the user, and measurable. It is also the demo visual (D19) |
| C | Anchor on real data (Humpback-style backtranslation) | Start from real text and real examples, not from the model's imagination | **Kept, in a lighter form** | Every candidate is written from retrieved chunks and must cite them. Optional seed examples set style, and the Planner reports which topics the seeds miss |
| D | Cost cascade | Cheap checks on every row, expensive checks only where the cheap ones are unsure | **Kept, as the 3-tier cascade** | Code, then Jev + Extract, then the Sonnet judge on about 5% + a 2% audit. About $1.70 vs about $20 frontier-only per 1,000 kept rows (D21) |
| E | Self-trained generator | Fine-tune the Writer on Bob's own verified rows so it improves over time | **Future** | Needs training (D20). The DPO pairs Bob exports are the input for this later |
| F | Simulated environments for agent data | Run a tool or product simulator to make verified agent trajectories | **Future** | Strong idea for tool-call data, but too large for tonight |

### Gap signals without training
With no student model, the gap controller uses signals Bob can measure itself:
1. **Coverage gaps:** cells under their target (measured with `jev.cell`, not assumed from the cell the Writer was asked for).
2. **Rejection rate:** a cell where many candidates fail is a hard cell. It gets more weight in the next round.
3. **Base-model probing (stretch):** ask a base model the kept questions. Cells where it fails get a boost.

## 4. The user-side flow

Example from the conversation: a support team at "Lumen", an invoicing SaaS, wants a small model that writes first replies to tickets. They have public help docs, an internal Notion FAQ and escalation policy, Jira tickets about known bugs, and 40 real past tickets as seeds.

| Step | User | Bob |
|---|---|---|
| 1. Goal | Types "first replies to support tickets; use only our docs; hand off when unsure". Adds the help-center URL, connects Notion and Jira, uploads 40 seed tickets. Sets 1,000 rows and a $10 budget | Firecrawl crawls the URL, Composio fetches the Notion pages and Jira issues, parsers read the uploads |
| 2. Plan | Sees the coverage map: 14 topics (Refunds, Recurring invoices, Tax, ...) x personas (Accountant, Small-business owner, Frustrated customer, ...) x 4 case types x 3 difficulty levels. Reads "Your seeds cover 4 of 14 topics". Turns off "Partner API", clicks Start | Reads the material (chunk, filter, Jev triage, topics, Extract evidence), proposes the map and a cost estimate |
| 3. Build | Watches the map fill. Opens a rejected row: "Mentions 'bulk PDF export', which is not in the docs" | Writer makes candidates per cell; the cascade checks each one; only verified rows are kept |
| 4. Fill gaps | Sees "Round 2: 9 thin cells, 3 hard cells" | The gap controller targets empty and high-rejection cells |
| 5. Result | Spot-checks 50 rows, downloads OpenAI-chat JSONL and the DPO file | Report: coverage, pass rate per check, reject reasons, judge agreement, Jev accuracy from the spot-check, cost |
| 6. Docs change (P1) | Clicks Re-sync after the refund policy changes | Re-fetches, diffs, re-checks stale rows, regenerates only the affected cells |

The four case types are the core of the data. For Lumen:
- **answerable:** "How do I set up a recurring invoice?" -> steps from the docs.
- **partial:** "Can I do recurring invoices in two currencies?" -> answers the documented part, says which part the docs do not cover, offers a handoff.
- **unanswerable:** "Do you integrate with my bank's API?" -> the docs do not cover this; hand off, invent nothing.
- **false_premise:** "Why did my 60-day refund window close early?" -> politely corrects it: the docs say 30 days.

The tonight demo uses the same flow on Firecrawl's public docs plus internal-style Notion pages (PLAN section 9).

## 5. Where Jev and the CDMs work

| Stage | Jev (decision model) | ScaleDown CDMs | Code |
|---|---|---|---|
| Read | Triage each chunk: useful, boilerplate, PII, injection (one call, 4 questions) | **Extract** builds the evidence index (features, settings, limits, numbers, URLs) with verbatim spans; **Summarize** writes topic briefs | Heading-aware chunking, heuristic filter, embedding dedup, k-means topics |
| Generate | | **Compress** shrinks context; briefs replace full pages in Writer prompts | Cell allocation, batching |
| Verify | One call per candidate, questions by case type (`jev.supported`, `jev.answers`, `jev.flags_gap`, `jev.abstains`, `jev.corrects`, ...); calibrated probability routes the row | **Extract** pulls every name from the reply; each must match the evidence index (invented-feature detector) | Format, banned phrases, dedup, every number must appear in the sources |
| "Not in docs" rows | Confirms the top-5 retrieved chunks do not answer the question | | Retriever picks the top 5 |
| Gap fill | Labels each kept row with its real topic (`jev.cell`) | | Deficit and rejection-rate weights |
| Report | Spot-check measures Jev's real accuracy on this job | Spans power the row inspector | Pass rates, judge agreement, cost ledger |

### Known weaknesses and guards
| Weakness | Guard |
|---|---|
| Jev is about 11.5% wrong at >= 90% confidence | Kept answerable rows need both `jev.supported` and `extract.names`; the 2% tier-3 audit measures the real error rate |
| Jev follows option names more than the rubric | Descriptive option names only, never `0/1` |
| Jev is weak at arithmetic and dates | The tier-1 `numbers` check does this in code |
| Extract field accuracy is about 89.5% | Keep only fields whose `span_text` is a verbatim substring of the input |
| A provider fails | Real fallbacks: Jev -> ScaleDown Classify -> Haiku JSON; Extract -> Haiku extraction + the same span check. The UI shows a badge |

## 6. The cascade

```
 candidate (Writer, Haiku 5.5)
     |
     v
 TIER 1  code (free)            format, banned_phrases, dedup, numbers
     |  fail -> REJECTED (reason shown)
     v
 TIER 2  decision models        extract.names: every feature / setting / URL in the reply is in the evidence index
         (about $0.0001/row)    Jev: 5 questions by case type -> calibrated probabilities
     |  hard fail or confidence < 0.3 -> REJECTED
     |  all pass and confidence >= 0.9 -> KEPT ----+--- 2% random audit ---+
     |  otherwise (about 5%)                       |                        |
     v                                             v                        v
 TIER 3  Sonnet 5.5 judge  <-----------------------------------------------+
         verdict is final; tier-2 vs tier-3 agreement goes into the report
     |
     v
 KEPT rows -> coverage map, export      REJECTED + KEPT replies to the same question -> DPO pairs
```

Pitch line: *"The LLM writes, and small decision models check every row. The frontier model only looks at the rows where the checks disagree."*

## 7. Decisions from this conversation

| ID | Decision |
|---|---|
| D18 | Retire templates: question programs, grammar bank, generator library and Architect-written generator code. Keep the verification ideas and the faithfulness / abstention focus |
| D19 | Closed-loop factory: map -> generate -> verify -> fill gaps |
| D20 | Bob makes data only. No training. Gap signals: coverage, rejection rate, probing (stretch) |
| D21 | 3-tier verification cascade; Jev and CDM roles; guards and real fallbacks |
| D22 | Models on AWS Bedrock: Haiku 5.5 Writer, Sonnet 5.5 Judge and Planner |
| D23 | Real-only development: no mocks, no fake data; a cache of real responses is allowed |
| D24 | FastAPI + React + SSE; Firecrawl and Composio; Convex and Photon dropped; demo on Firecrawl docs + Notion; Aaditya (AI + backend, A1 to A4) and Gunbir (frontend + integrations, G1 to G4) |

Details and "what would change it" for each: `DECISIONS.md`.

## 8. Sources
- Rainbow Teaming (Meta, 2024), quality-diversity search over a feature grid: https://arxiv.org/abs/2402.16822
- MAP-Elites (Mouret and Clune, 2015): https://arxiv.org/abs/1504.04909
- Humpback, instruction backtranslation (Meta, 2023): https://arxiv.org/abs/2308.06259
- Jev and ScaleDown facts and failure modes: research 02 (Jev sections) and 05 (CDM facts).
