# Research 07: Generating Fine-Tuning Datasets Without an LLM

> 2026-10-30. **Supersedes research 06**, which wrongly centred on ModelForge. ModelForge is only one compatible trainer; Bob works on any user's corpus and any domain.
> Goal: Bob must **synthesize the rows of a fine-tuning dataset** (instructions, responses, conversations, preference pairs, reasoning), not just restructure what the corpus says. Strictly zero-LLM (D13).

## 1. The principle

An LLM can synthesize data because it has two things: **knowledge** and **language**. Bob replaces both without an LLM:

| What an LLM supplies | What Bob uses instead |
|---|---|
| Knowledge | The user's corpus, compiled into a fact graph (ScaleDown Extract + code) |
| Language | ScaleDown Summarize / Extract, grammars, deterministic text transforms, Jev to choose |
| Judgement | Jev decisions + programmatic verifiers |

Bob then creates **new rows** along three axes:
1. **New tasks:** one passage becomes 15+ different instruction types (skills, not only facts).
2. **New inputs:** corrupted, constrained, re-voiced, recombined, counterfactual versions that never existed.
3. **Constructed targets:** every response is built by a known procedure, so Bob also knows exactly why it is correct and can ship a verifier with it.

What this cannot do (say it plainly): invent knowledge that isn't in the corpus, or write with the open-ended voice of a frontier model. What it can do better than an LLM: produce **large, diverse, verifiable** data with **no hallucinated answers**, for cents.

## 2. The generator library

Each generator turns corpus material into finished dataset rows. Every row records its generator, source spans and verifier.

### G1. Task multiplier (one passage, many tasks)
From a single chunk:
- summarize (1 sentence / 3 bullets / 50 words) via ScaleDown Summarize
- write a title or headline (Summarize, short)
- extract to JSON with a schema Bob generates from the chunk's entity types (ScaleDown Extract)
- classify into labels Bob derives from the corpus taxonomy (Jev provides the gold)
- list the keywords / entities / numbers
- outline (from headings and sentence roles)
- convert prose to a table, a table to prose, bullets to prose, and back
- answer questions (fact-graph programs, G4)
- fill in the blank, true or false, which statement is correct (multiple choice built from the graph with sibling-value distractors)

**Why it matters:** fine-tuned models need *skills over the domain*, not only facts. Bonito-style task diversity is what makes instruction tuning generalize; Bob gets it from rules and CDMs instead of a model.

### G2. Corrupt and restore (denoising instructions)
Apply a known corruption to clean text, then ask the model to undo it. The gold answer is the original, and the diff is known exactly.

| Corruption | Instruction |
|---|---|
| shuffle procedure steps | "Put these steps in the right order." |
| delete a step | "Which step is missing from this procedure?" |
| swap a number or entity with a sibling value | "Find and fix the factual error." |
| insert an off-topic sentence | "Remove the sentence that doesn't belong." |
| inject typos, casing, broken formatting | "Clean up this text." |
| contradict one sentence | "Which two statements conflict?" |
| merge two sections | "Split this into its two topics, with titles." |

Unlimited volume, perfectly verifiable, and it teaches editing, checking and attention to detail.

### G3. Constraint compositor (verifiable instruction following)
Take any base task (from G1, G2 or G4) and attach randomly sampled constraints: answer as JSON / YAML / a table, exactly N bullets, under N words, include or avoid given keywords, start or end with a phrase, use given section headers, all lowercase, numbered steps, cite the source section. The response is produced by **deterministic renderers** applied to the base answer (formatters, bulletizer, Summarize with a length target, keyword weaving), and each constraint ships with a **verification function**.

Evidence: AI2's "Generalizing Verifiable Instruction Following" found most models overfit to IFEval's 25 constraint types; training on more and more varied verifiable constraints improved generalization (TÜLU-3-8B IFEval 82.4 -> 92.2 with their IFTrain constraints). Bob can generate this kind of data **over the user's own domain**, and export the verifiers for RLVR trainers.

### G4. Knowledge composer (from research 05)
Fact-graph programs: lookups, multi-hop joins, comparisons, arithmetic, aggregation, procedures, conditions, chain-of-thought traces from the graph path. These questions appear in no document; the answers are computed.

### G5. Symbolic variants
Turn any computed question into a template with typed variables and constraints (GSM-Symbolic style), then instantiate it with new values and recompute. Adds a difficulty dial (more steps, distractors, unit conversions) and therefore a curriculum.

### G6. Conversation simulator
A dialogue-act state machine (ask, clarify, answer, follow up, correct, confirm, thank) walks a neighbourhood of the fact graph:
- **Clarification turns:** Bob deliberately drops a required slot from the user turn, so the gold assistant turn asks for it.
- **Follow-ups** reuse context with pronouns ("and what about its timeout?").
- **User corrections** ("sorry, I meant the EU region") force the assistant to revise.
- Personas (G10) vary the user side.
Produces multi-turn chat SFT rows that no document contains.

### G7. Abstention and false-premise data (anti-hallucination)
- **Unanswerable:** sample entity x attribute pairs that are *plausible but absent* from the graph ("What is the refund window for the Pro plan?" when none is documented). Gold: a grounded "not covered in the documentation", plus the closest related fact.
- **False premise:** perturb a fact inside the question ("Why does X support Y?" when it doesn't). Gold: correct the premise, citing the source.
This is the data that stops fine-tuned models from making things up, and LLM generators rarely produce it well because they tend to invent an answer.

### G8. Preference pairs (DPO) by controlled degradation
Chosen = the constructed correct response. Rejected = the same response with one **known defect**: a fact removed, a fact swapped, a constraint violated, padding added, wrong format, an invented extra detail, or (for G7) a fabricated answer instead of abstaining. Every pair is labelled with its defect, so users can build targeted preference sets ("teach it not to pad", "teach it to abstain").

### G9. Few-shot expander (the user's own format)
The user uploads 10 to 50 examples of the exact task they want (support replies, product Q&A, extraction records). Bob:
1. aligns the examples and finds the varying spans (anti-unification / template induction),
2. types each slot (Extract + Jev),
3. builds a probabilistic grammar from the fixed parts,
4. fills slots from the corpus lexicon, the fact graph and Faker,
5. derives outputs where the mapping is rule-based, or composes them from the graph.
Result: thousands of new rows in the user's exact house style. Prior art: PCFG + slot-filling generation trained a production NER system with no manual labels; grammar induction for slot filling.

### G10. Voice and diversity layer
A persona x expertise x tone x length x noise grammar rewrites user turns (expert and terse, beginner and vague, multi-intent, typos, wrong terminology). Jev ranks naturalness; Jev-decoded paraphrase (research 05) adds wording variety. Noisy and clean versions of the same request map to the same answer, which teaches robustness.

### G11. Structured data synthesis (when the corpus has tables)
Fit an SDV Gaussian copula on the corpus tables, sample new realistic rows, then produce table QA, aggregation and text-to-SQL rows (PCFG-sampled SQL, executed for the gold answer, realized from grammar).

## 3. Recipes (what the user picks)
A recipe is a weighted mix of generators, with a target row count and preset.

| Recipe | Mix |
|---|---|
| Domain assistant | G4 30%, G1 20%, G6 20%, G7 10%, G3 10%, G2 10% |
| Support agent | G6 35%, G7 15%, G9 20% (from sample tickets), G4 20%, G10 on all |
| Extraction model | G1 extract 50%, G3 JSON constraints 30%, G2 15%, G7 5% |
| Reasoning model | G4 CoT 40%, G5 30%, G2 20%, G3 10% |
| Preference tuning | G8 over any of the above |

## 4. Cost
Most generators are pure code. Paid calls: Jev (triage, labels, ranking) and ScaleDown (Extract once per chunk, Summarize for summary-type tasks). A 1M-token corpus to about 10,000 rows comes to roughly **$0.50 to $1.00** at list prices, and about $0 on ScaleDown's 50M starter tokens. LLM tokens: 0.

## 5. Recommended for tonight

| Priority | Generators | Why |
|---|---|---|
| Core | G1, G2, G3, G4 | Biggest variety for the least code; all verifiable |
| Core | G7 + G8 | The anti-hallucination story is the strongest demo |
| Next | G6 (single clarification + follow-up), G10 | Makes the data feel human |
| Stretch | G9, G5, G11 | High wow, more build time |

## 6. Demo
1. Upload a real product's public docs (any product the judges know).
2. Pick the "Domain assistant" recipe and drag the mix sliders. Bob shows **"40 pages -> 10,000 rows across 14 task types, $0.00, LLM tokens: 0"**.
3. Click through one row from each generator, each with its source span and verifier.
4. Fine-tune a small model on it (ModelForge or any trainer).
5. Side by side, base vs tuned: (a) a held-out question about the product, (b) a constrained request ("3 bullets, JSON"), (c) a question about a feature that **doesn't exist**. The base model makes something up; the tuned model says it isn't documented.

## 7. Risks
| Risk | Mitigation |
|---|---|
| Rows feel templated | Wide grammars, G10 voice layer, Jev ranking, hold out templates in eval |
| Task mix overfits to Bob's style | Many generators at moderate weights; dedup across generators |
| Extraction errors propagate | Confidence and span checks (research 05); G2/G3 don't depend on extraction |
| Abstention overdone (model refuses too often) | Keep G7 at 5 to 15% of the mix; pair every unanswerable with an answerable sibling |

## Sources
- Verifiable instruction following and constraint diversity (IFBench, IFTrain, RLVR): https://arxiv.org/pdf/2507.02833, https://arxiv.org/html/2507.02833v3
- Lexical instruction-following eval: https://arxiv.org/html/2511.17561v1
- Tasks from unlabeled text: https://arxiv.org/pdf/2210.09175; Bonito: https://arxiv.org/html/2402.18334v2; self-supervised task distributions: https://preview.aclanthology.org/moar-dois/2020.emnlp-main.38
- PCFG + slot filling for NER training data: https://appliedmldays.org/events/amld-epfl-2022/talks/synthetic-data-generation-for-natural-language-understanding-with-probabilistic-context-free-grammars
- Grammar induction for slot filling: https://paperswithcode.com/paper/a-weakly-supervised-sequence-tagging-and; anti-unification templates: https://arxiv.org/pdf/2607.18357; grammar induction survey: https://jmlr.org/papers/v4/cicchello03a.html
- Procedural generators: https://arxiv.org/html/2505.24760v2, https://arxiv.org/pdf/2603.02208
- SDV: https://docs.sdv.dev/SDV/single-table-data/modeling/synthesizers/copulagansynthesizer; SQLsynth: https://github.com/magic-YuanTian/SQLsynth
- From model knowledge (verify): SQuAD 2.0 unanswerable questions, GSM-Symbolic, EDA augmentation.
