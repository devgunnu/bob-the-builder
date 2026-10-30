# Research 06: True Synthetic Generation (beyond formatting the corpus)

> 2026-10-30. The founder's bar: Bob must **generate** data, not just restructure what the corpus already says. Strictly zero-LLM still applies (D13).

## 1. The core idea in one line

**New data = new inputs x a trustworthy oracle.**

The corpus is not the dataset. It is the *world model*. Bob uses it to learn what the product is, which inputs exist, and what rules govern it. Then Bob **imagines new situations that never appear in the docs** and gets the correct answer for each from an oracle that is not an LLM:

| Oracle | Where the truth comes from | Example |
|---|---|---|
| **The real product** (execution) | Run the actual software on the new input | Invent 3,000 hardware setups, run ModelForge's real recommendation engine on each |
| **A simulator** compiled from the docs | Extracted rules and conditions, executed | "If VRAM < 12 GB then max_length = 512" becomes code; simulate new cases and counterfactuals |
| **A solver / planner** | Logic, planning, arithmetic, SQL execution | Plan a new procedure for a goal the docs never covered |
| **The fact graph** (research 05) | Computed joins and arithmetic | Multi-hop questions |

The LLM approach (everyone else) *imagines the answers too*, which is why it hallucinates. Bob imagines only the **questions and situations**, and never the answers.

## 2. Ideas, ranked

### Idea 1 (flagship): Product-as-Oracle, execution-grounded synthesis
Bob reads the product's input schemas (CLI flags, API/OpenAPI specs, config models, pydantic classes, function signatures), **samples brand-new valid and invalid inputs**, runs the real product, and records what actually happens.

What it produces:
- **Advice data:** synthetic user situation -> the product's real answer. *"I have two RTX 3060s (12 GB each), 32 GB RAM, and want to fine-tune for summarization. What should I use?"* -> ModelForge's real strategy, PEFT tier, max length, LoRA rank, warnings.
- **Tool-use / function-calling data:** request -> the exact correct CLI command or API JSON -> the real result. Verified by execution, not by a judge.
- **Error-diagnosis data:** mutate valid inputs into broken ones (missing column, wrong extension, mixed types, DPO file in the wizard), run the product, capture the **real error**, pair it with the fix (the mutation reversed). *"Why does my dataset fail validation?"*
- **Boundary data:** sample densely near decision thresholds (e.g. 11.9 GB vs 12.1 GB VRAM) so the model learns exactly where behaviour changes.

How samples are generated (no LLM): typed schema walkers (Hypothesis-style strategies per field: ranges, enums, realistic distributions such as real GPU catalogues), boundary search around thresholds found in code/docs, mutation operators for invalid inputs, and coverage-guided sampling (keep inputs that produce a new output or code path).

Why it is the most impressive: every answer is **true by execution**, the model learns the product's *behaviour* (not just its docs), and the accuracy is **measurable**: hold out unseen configurations and score the tuned model against the real product.

ModelForge fit (verified in repo): `RecommendationEngine.recommend(use_case_slug, training_objective, hardware, n)` (`utilities/recommendation_engine.py:45`) takes a `HardwareSpecs` object (`utilities/hardware_detector.py:19`: cores, disk, RAM, GPU list with VRAM), so hardware can be **synthesized and injected** instead of detected. Steps 1 to 4 (VRAM math, strategy, PEFT tier) are deterministic. Step 5 queries the HF Hub (network), so cache it or score only the deterministic fields. `POST /api/datasets/validate` and `DatasetFactory` give the error-diagnosis oracle.

Standalone rule (D9) still holds: oracles are **adapters** configured per product (`exec` = command template, `http` = OpenAPI endpoint, `python` = function called in the product's own environment through a subprocess). Bob core never imports the product.

### Idea 2: Docs-to-Simulator (executable world model)
ScaleDown Extract pulls **rules** from the docs (conditions, thresholds, if/then, defaults, limits, causes and effects) into a small rule language. Bob compiles them into an executable forward-chaining simulator, then:
- samples **new scenarios** and derives outcomes,
- asks **counterfactuals** ("what if I had 24 GB instead?"), giving contrastive pairs where a minimal change flips the answer,
- runs **fault injection** over the causal graph: pick a root cause, propagate symptoms, then turn the path into a **troubleshooting dialogue** (symptom -> diagnostic question -> observation -> root cause -> fix). This is the flowchart-to-dialogue idea from PlanDA, with the flowchart compiled from docs instead of written by hand.

Bonus: when both the simulator and the real product exist, disagreements between them are **documentation bugs**. Bob can report "your docs say X, your product does Y" (research 01 already found several in ModelForge). That alone makes a great demo moment.

### Idea 3: Symbolic variants (GSM-Symbolic style)
Every numeric fact or computed question becomes a **template with typed variables and constraints**. Bob instantiates unlimited new versions with new values and recomputes the answer. *"A 7B model in 4-bit needs about X GB; will it fit on a 10 GB card with batch size 4?"* with fresh numbers each time. A difficulty dial (more steps, distractors, unit conversions) yields a curriculum.

### Idea 4: Planner-generated procedures and agent trajectories
Turn extracted procedures into planning operators (preconditions, effects), then use a classical planner (e.g. pyperplan, PDDL) to generate **new plans for new start states and goals** the docs never described. Executing each step against the product oracle gives **agent trajectories with real observations** (ReAct-style: thought from template, action, real observation), and inserting a wrong step followed by the oracle's correction gives **self-correction data**.

### Idea 5: Synthetic users (input diversity engine)
A persona x intent x expertise x tone x noise grammar renders the same scenario the way different people actually type it: expert terse, beginner vague, multi-intent, typos and abbreviations, wrong terminology. Jev ranks naturalness. Pairs such as noisy request -> same correct answer teach robustness. This turns 1 scenario into 10 realistic conversations without an LLM.

### Idea 6: Synthetic structured worlds (tables, SQL, analytics)
For products with data: fit an SDV Gaussian copula (or CTGAN) on sample tables, or on a schema from the docs, and **sample whole new databases**. PCFG-sample SQL over the schema, execute it, and realize the question from SQL with templates (the grammar-based first stages of SQLsynth). The result is text-to-SQL and table-QA data with execution-verified answers. Faker fills realistic entity values.

### Idea 7: Procedural reasoning gyms, skinned with the domain
Plug in existing LLM-free generators and verifiers (Reasoning Gym: 100+ generators; Reasoning Core: planning, first-order logic, causal Bayes nets, equation systems), with variables renamed to the product's entities. Useful as a general reasoning mix, and every row is solver-verified.

### Idea 8: Jev-decoded paraphrase (from research 05)
Phrase-by-phrase constrained generation by Jev decisions, for wording diversity on top of everything above.

## 3. Recommended for tonight

| Priority | Build | Why |
|---|---|---|
| 1 | **Product-as-Oracle** with a ModelForge adapter: synthetic hardware -> real recommendations; mutated datasets -> real validation errors; CLI command synthesis | Flagship, dogfooding, measurable, true by execution |
| 2 | **Synthetic users** grammar on top of every scenario | Makes the data look and feel human, cheap to build in parallel |
| 3 | **Symbolic variants + counterfactual pairs** | Cheap once the oracle exists; gives DPO and contrastive data |
| 4 | Docs-to-Simulator with doc-vs-product disagreement report | Stretch; the "docs bug" moment |
| 5 | Fact-graph programs (research 05) | Already planned; covers the documentation side |

## 4. The demo becomes a benchmark
1. Bob reads ModelForge's docs and code schemas.
2. Bob **invents 3,000 users with hardware nobody wrote down**, runs ModelForge's real engine on each, and builds the dataset (zero LLM tokens).
3. ModelForge fine-tunes a small model on that dataset.
4. On **500 held-out invented configurations**, score base vs tuned against ModelForge's real output. Show one chart, e.g. "base 18% -> tuned 90%" (illustrative; measure it tonight).
5. A judge describes **their own laptop**; the tuned model answers like ModelForge would, and Bob runs ModelForge live to confirm.

## 5. Risks
| Risk | Mitigation |
|---|---|
| HF Hub calls in `recommend` are slow or rate-limited | Cache per (task, max_params); score deterministic fields (strategy, PEFT tier, max length, LoRA rank, warnings) |
| Running ModelForge requires its heavy env (Python 3.13, torch) | Run the oracle on the GPU box in ModelForge's own venv; Bob calls it through the `python` adapter (subprocess, JSON in/out). Bob core stays light |
| Synthetic inputs unrealistic | Sample from real catalogues (GPU names/VRAM, common RAM sizes); persona grammar; Jev "plausible setup?" check |
| Overfitting to templates | Wide grammar, held-out templates in eval, synthetic-user noise |
| Scope | Oracle + users first; simulator and planner are stretch |

## Sources
- Reasoning Gym (100+ procedural generators and verifiers): https://arxiv.org/html/2505.24760v2, https://www.sourcepulse.org/projects/1855901
- Reasoning Core (planning, FOL, causal Bayes nets, equations; solver-verified): https://arxiv.org/pdf/2603.02208
- SQLsynth (PCFG SQL sampling, execution filtering, grammar-based SQL-to-text): https://github.com/magic-YuanTian/SQLsynth; PCFG + SQL-to-text: https://arxiv.org/pdf/2104.05827v1; template/IR synthesis: https://arxiv.org/pdf/2212.08785
- Execution-verified tool-use synthesis (LLM-based prior art, for contrast): InfTool https://www.emergentmind.com/topics/inftool, GEM https://arxiv.org/pdf/2601.10355v1
- Causal fault injection for RCA: https://arxiv.org/pdf/2408.13729; industrial rule-based fault injection: https://arxiv.org/pdf/2607.29092; GraphTracer: https://arxiv.org/pdf/2510.10581; AgentFault: https://ieee-dataport.org/documents/agentfault
- SDV / CTGAN / Gaussian copula: https://docs.sdv.dev/SDV/single-table-data/modeling/synthesizers/copulagansynthesizer, https://arxiv.org/pdf/2506.17847, https://github.com/diegonov1/ctgan
- From model knowledge (verify): GSM-Symbolic (Apple, arXiv 2410.05229), PlanDA flowchart-to-dialogue, Hypothesis property-based testing, pyperplan / PDDL, Faker.
- ModelForge code: `utilities/recommendation_engine.py:45`, `utilities/hardware_detector.py:19`, `cli/main.py:94`, `workflow/service.py:121`.
