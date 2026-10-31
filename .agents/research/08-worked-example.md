# Research 08: Worked Example (how one passage becomes ~570 rows)

> 2026-10-30. A grounded walkthrough of the research 07 generators on **one real passage**. Every fact and every computed answer below can be checked against the source. ModelForge's guide is used only because it is a real document we can cite line by line; the steps are identical for any product's docs.

## 1. The input: one real passage

Source: `ForgeOpus/ModelForgeRedesign`, `DEVELOPER_GUIDE.md` lines 255-262 (verbatim):

```
### PEFT Tier Logic

| Tier | Memory per Param | Triggered When |
|---|---|---|
| `full_finetune` | 18 bytes | Very high VRAM (for small models) |
| `lora_bf16` | ~2 bytes (frozen) | 16+ GB adjusted VRAM |
| `qlora_8bit` | ~1 byte (frozen) | 8–16 GB adjusted VRAM |
| `qlora_4bit` | ~0.5 bytes (frozen) | Below 8 GB adjusted VRAM |
```

About 60 words. Formatting it would give **1 row** ("Explain the PEFT tiers" -> the table).

## 2. Step 1: read it into facts (ScaleDown Extract)

| id | subject | predicate | value | span |
|---|---|---|---|---|
| f1 | full_finetune | memory per param | 18 bytes | row 1 |
| f2 | lora_bf16 | memory per param | ~2 bytes (frozen) | row 2 |
| f3 | qlora_8bit | memory per param | ~1 byte (frozen) | row 3 |
| f4 | qlora_4bit | memory per param | ~0.5 bytes (frozen) | row 4 |
| f5 | full_finetune | triggered when | very high VRAM, small models (**no number**) | row 1 |
| f6 | lora_bf16 | triggered when | adjusted VRAM ≥ 16 GB | row 2 |
| f7 | qlora_8bit | triggered when | adjusted VRAM 8 to 16 GB | row 3 |
| f8 | qlora_4bit | triggered when | adjusted VRAM < 8 GB | row 4 |

Bob also records two things it **must not** invent:
- **Ambiguity:** 16 GB appears in both "16+" and "8–16". Bob does not generate questions at exactly 8 or 16 GB.
- **Gap:** full_finetune has no numeric trigger. Questions needing one become abstention rows.

## 3. Step 2: generate (row counts are exact for this passage)

### G4 Knowledge composer: 21 rows
Lookups (8), inverse lookups (4), pairwise comparisons C(4,2) = 6, superlatives (2), ordering (1).
> **Q:** How many times more memory per parameter does lora_bf16 use than qlora_4bit?
> **A:** About 4 times (about 2 bytes vs about 0.5 bytes per frozen parameter). *[f2, f4; computed 2 / 0.5]*

### G5 Symbolic variants: 161 rows (the quantity engine)
Templates with typed variables, answers recomputed from the facts each time.
- **A. VRAM to tier:** 11 values strictly inside the documented bands: {2, 4, 6} -> qlora_4bit; {10, 12, 14} -> qlora_8bit; {20, 24, 32, 48, 80} -> lora_bf16. **11 rows.**
- **B. Weight memory:** 10 common model sizes {0.5, 1, 1.5, 3, 7, 8, 13, 14, 32, 70}B x 4 tiers. **40 rows.**
- **C. Combined:** 11 VRAM values x 10 sizes. **110 rows.**

> **Q:** I have 12 GB of adjusted VRAM and want to fine-tune a 7B model. Which tier does the guide indicate, and how much memory do the frozen weights take?
> **A:** qlora_8bit, since 12 GB falls in the 8 to 16 GB band. At about 1 byte per frozen parameter, a 7B model's weights take about 7 GB. The guide's table does not cover activation memory, so check that separately. *[f7, f3; computed 7e9 x 1 byte]*

> **Q:** How much memory do the frozen weights of a 13B model need under lora_bf16?
> **A:** About 26 GB (13B x about 2 bytes). *[f2]*

Every one of the 161 answers is different, computed, and traceable to two facts.

### G1 Task multiplier: 15 rows
One-sentence summary, three-bullet summary, title, table-to-prose, table-to-JSON (Extract), list of tiers (6), plus fill-in-the-blank on each of the 8 cells (8). The summaries come from ScaleDown Summarize; everything else is code.

### G2 Corrupt and restore: 24 rows
Swap a number with another tier's value (4 cells x 3 wrong values = 12), shuffle the row order (5), delete a row (4), insert a row from another section (3).
> **Q:** One value in this table is wrong. Find and fix it. *(table with qlora_4bit at "~2 bytes")*
> **A:** qlora_4bit should be about 0.5 bytes per parameter, not about 2; 2 bytes belongs to lora_bf16. *[f4, f2]*

### G7 Abstention and false premise: 17 rows
- Undocumented attributes (speed, accuracy loss, CPU support) x 4 tiers = 12.
- "Exactly how much VRAM triggers full_finetune?" = 1 (the guide gives no number).
- False premises (one wrong value per tier) = 4.
> **Q:** Why does qlora_4bit use 2 bytes per parameter?
> **A:** It doesn't. The guide lists qlora_4bit at about 0.5 bytes per frozen parameter; about 2 bytes is lora_bf16. *[f4, f2]*

> **Q:** How much slower is qlora_4bit than lora_bf16?
> **A:** The PEFT tier table doesn't give speed figures, only memory per parameter and when each tier is used. *[abstain; Bob checks the whole fact graph before abstaining]*

### G6 Conversations: 30 rows
Multi-turn chats sampled from template C combinations: the user states VRAM, the assistant gives a tier, the user asks whether a model size fits, then the user corrects their VRAM and the assistant revises.

### G3 Constraint compositor: 120 rows
40 base rows x 3 sampled constraint sets ("answer in JSON with keys tier and weight_gb", "exactly 2 bullets", "under 25 words", "start with 'Short answer:'"). Each constraint has a verifier function.

### G8 Preference pairs: 182 pairs
One known defect for each computed row (21 + 161): wrong tier, wrong arithmetic, dropped caveat, or padding, labelled by defect type.

## 4. The count

| Generator | Rows |
|---|---|
| G4 Knowledge | 21 |
| G5 Symbolic variants | 161 |
| G1 Task multiplier | 15 |
| G2 Corrupt and restore | 24 |
| G7 Abstention | 17 |
| G6 Conversations | 30 |
| G3 Constraints | 120 |
| **SFT total** | **388** |
| G8 DPO pairs | 182 |
| **All rows** | **570** |

**1 formatted row -> about 570 generated rows from a 60-word table, with zero LLM tokens.** The optional voice layer (G10) can multiply user turns by about 4x more.

### Read this honestly
- **Facts learned stay at 8.** What multiplies is how the model *uses* them: computing, comparing, applying to new situations, catching errors, following formats, refusing to guess. That is the point of fine-tuning data, but it is not new knowledge.
- **Rows are not equally valuable.** The 110 combined variants teach one mapping many ways. Bob caps any single template at a share of the final mix (for example 20%) and deduplicates.
- **The multiplier depends on the passage.** Number-dense tables like this one multiply a lot. Narrative prose multiplies less (mostly G1, G2, G7). These are estimates; measure on the demo corpus.
- **The source is what Bob trusts.** This guide's bands are simplified compared with ModelForge's actual tier code (`utilities/recommendation_engine.py:344-411`, which uses parameter-count inequalities). Bob generates what the corpus says and, if the corpus contains both, flags the conflict instead of picking one.

## 5. Evidence that each technique works

| Generator | Evidence | Strength |
|---|---|---|
| G1 Task multiplier | Bonito turns unannotated text into instruction tasks and significantly improves pretrained and instruction-tuned models over the self-supervised baseline ([arXiv 2402.18334](https://arxiv.org/html/2402.18334v2)). Pseudo-tasks from unlabeled text help zero-shot cross-task generalization ([arXiv 2210.09175](https://arxiv.org/pdf/2210.09175)). | Strong (Bonito uses a model to write tasks; Bob uses rules + CDMs, so effect size must be measured) |
| G5 Symbolic variants | Reasoning Gym: 100+ procedural generators giving effectively unlimited data with adjustable difficulty ([arXiv 2505.24760](https://arxiv.org/html/2505.24760v2)). Reasoning Core: solver-verified procedural data improved downstream reasoning ([arXiv 2603.02208](https://arxiv.org/pdf/2603.02208)). GSM-Symbolic templates (from model knowledge, verify). | Strong |
| G3 Constraints | AI2: more and more varied verifiable constraints improve instruction-following generalization; TÜLU-3-8B IFEval 82.4 -> 92.2; models overfit when constraint types are few ([arXiv 2507.02833](https://arxiv.org/pdf/2507.02833)). | Strong |
| G8 Preference pairs | Same paper: preference data from verifiable outcomes works, though GRPO beat DPO on it ([arXiv 2507.02833](https://arxiv.org/pdf/2507.02833)). | Medium |
| G9/G10 Grammar generation | PCFG + slot filling trained a production NER system with no manual labels ([AMLD 2022 talk](https://appliedmldays.org/events/amld-epfl-2022/talks/synthetic-data-generation-for-natural-language-understanding-with-probabilistic-context-free-grammars)). | Medium (talk, not peer reviewed) |
| G7 Abstention | Unanswerable-question training (SQuAD 2.0 style) is well established (from model knowledge, verify). | Medium, needs a citation check |
| G2 Corrupt and restore | Denoising is the T5/BART pretraining objective (from model knowledge). No paper found that tests it as instruction data. | Weak: plausible, measure it |
| G6 Conversations | Flowchart-to-dialogue synthesis (PlanDA, found in research 06 search) is related; no direct zero-LLM study found. | Weak: measure it |

## 6. How we prove it tonight
Hold out 20% of templates and generators, fine-tune a small model on the rest, and score base vs tuned on the held-out rows with each row's own verifier (computed answer match, constraint checks, abstention detection). That turns "more data" into a measured result instead of a claim.
