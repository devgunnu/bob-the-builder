# Research 09: Bringing in the LLM ("LLM proposes, Bob proves")

> 2026-10-30. **Supersedes the strict zero-LLM rule (D13).** Reason: hand-written templates cannot cover every use case, and template-shaped data looks like templating. The team decided an LLM is needed to make Bob truly impressive.
> Design goal: get the LLM's generality and natural language **without** bringing back hallucinated answers.

## 1. The principle

**The LLM writes the generators. Code runs them at scale. Verifiers prove every row.**

| Role | Model | How often | Job |
|---|---|---|---|
| **Architect** | Strong model (Claude Opus 5.5 or Sonnet 5.5) | A few dozen calls **per corpus** | Reads a sample of the corpus plus the user's goal; designs the task taxonomy, the extraction schema, and **generator programs with their own verifier code and unit tests** |
| **Writer** | Cheap model (Claude Haiku 5.5, or a local model on the GPU box) | Once **per row** | Turns locked facts and computed answers into natural questions, conversations and responses, in many personas |
| **Verifiers** | Jev, ScaleDown CDMs, code | Every row | Prove the row: answer supported by source, computed value present, constraints pass, abstentions truly unanswerable |

The expensive model never touches individual rows, and the cheap model never decides what is true.

## 2. Why this solves the two problems

**"Templates won't scale."** No human writes templates any more. For a new corpus (cooking recipes, a legal handbook, a SaaS API), the Architect proposes what a fine-tuned model in that domain should be able to do, then writes the code that generates and checks those tasks. Bob runs the code in a sandbox, keeps only generators whose tests pass, and runs them thousands of times.

**"It looks like templating."** The Writer phrases every row freshly, in different personas, so no two rows read alike. The structure underneath stays verifiable.

## 3. Evidence

| Claim | Evidence |
|---|---|
| LLM-written verifier code makes synthetic data trustworthy | **AutoIF** (Qwen, ICLR 2025): the LLM writes instructions, the verification code, and unit tests to cross-check that code; only code that compiles, passes the tests and back-translates to the instruction is kept. First to pass 90% loose instruction accuracy on IFEval, without hurting general, math or coding ability; works for SFT and DPO. ([arXiv 2406.13542](https://arxiv.org/html/2406.13542v3), [ICLR](https://www.iclr.cc/virtual/2025/poster/29049)) |
| Programs as gold-answer oracles, LLM writes the narrative | "The Imitation Game" uses programs as executable oracles that supply gold outputs and verifiable intermediate signals, moving the logic into natural-language narratives. ([arXiv 2609.16076](https://arxiv.org/pdf/2609.16076)) |
| More unique tasks beats more answers per task | SynthSmith: scaling unique tasks from 32k to 200k helped more than adding solutions per task. ([alphaxiv 2601.06953](https://alphaxiv.org/overview/2601.06953v1)) |
| Personas scale diversity | Persona Hub (Tencent): 1B personas; 1.09M persona-driven math problems fine-tuned a 7B Qwen2 with gains on MATH following a scaling-law trend. ([arXiv 2406.20094](https://arxiv.org/html/2406.20094v1)) |
| Verified generation at scale | ATLAS (verified Dafny programs, about 19K training examples improved verification performance) and Formal Disco. ([arXiv 2512.10173](https://arxiv.org/html/2512.10173v1), [arXiv 2607.04631](https://arxiv.org/pdf/2607.04631)) |
| Constraint diversity matters | AI2 IFTrain/IFBench (research 07). ([arXiv 2507.02833](https://arxiv.org/pdf/2507.02833)) |

## 4. The pipeline (v3)

```
1  INGEST + FILTER            free heuristics, dedup, embeddings
2  TRIAGE      (Jev)          useful / density / type / boilerplate / PII / injection
3  EXTRACT     (ScaleDown)    facts with verbatim spans -> fact graph
4  ARCHITECT   (strong LLM)   per corpus, once:
                                a. capability map: "a model for this corpus should be able to..."
                                b. persona set: who will ask, and how
                                c. generator specs: Python generator + verifier + unit tests per task family
                                d. a held-out eval plan (task families reserved for testing)
5  SANDBOX TEST               run each generator's tests; repair loop (max 2 retries); keep passing ones
6  GENERATE    (code)         run generators over the fact graph -> skeletons:
                                {task, facts, computed_answer, constraints, persona, defect?}
7  WRITE       (cheap LLM)    skeleton -> natural row; answer slots LOCKED (must contain computed value)
8  VERIFY                     generator verifier + Jev "supported?" + "answerable alone?" +
                              locked-slot check + dedup + decontam; failures dropped and counted
9  CERTIFY + EXPORT           pass rates per generator; formats + presets as before
```

### What survives from the zero-LLM work
Jev triage, ScaleDown Extract and the fact graph, computed answers, abstention and false-premise families, preference pairs from **programmatically injected** defects (the Writer only phrases them; code guarantees the defect exists), all verifiers, provenance, formats and presets.

### What the LLM adds
- Any domain, with no human-written templates.
- Natural, varied language and real conversations.
- Persona-driven inputs (beginners, experts, non-native speakers, the frustrated customer).
- Harder, realistic adversarial items: plausible fake-feature questions, near-miss false premises. The graph still verifies they are unanswerable.

## 5. Cost (1M-token corpus to about 10,000 rows)

| Step | Estimate |
|---|---|
| Jev triage + ScaleDown Extract | about $0.10 |
| Architect (about 30 Opus 5.5 calls with large context) | about $1 to $3 per corpus, one time |
| Writer (Haiku 5.5, about 600 in + 250 out tokens per row) | about $1.85 standard, about $0.93 batch |
| Jev verification | about $0.30 |
| **Total** | **about $3 to $5** |
| Same 10k rows written and judged by Opus 5.5 | about $140 |

Prices from research 03 (Anthropic official page). Verify at 5pm. The cost story is still strong, but **correctness is the headline**.

## 6. Fair evaluation (fixes the circularity problem)
1. **Human-written test set:** before training, a teammate who never sees the generators writes 30 questions, including 8 about features that don't exist.
2. **Three-way comparison:** base model vs model tuned on **naive LLM data** (same Writer model, same budget, a plain "write Q&A from this chunk" prompt, no verification) vs model tuned on **Bob data**.
3. Score: accuracy on real questions, **hallucination rate** on fake-feature questions, constraint-following rate.

The middle column is what makes the result convincing: it isolates Bob's contribution from "an LLM made some data".

## 7. Demo
1. Paste a docs URL the judges know.
2. Show the Architect's output live: "For this product, a fine-tuned model should be able to: ..." plus the generators it wrote, with tests going green.
3. Rows stream in, varied and natural. Click one: its facts light up in the source, and its checks pass. A counter shows rows dropped by verification ("312 rows rejected: unsupported claim").
4. The three-way chart: base vs naive LLM data vs Bob data, on human-written questions and fake-feature questions.
5. Live: a judge asks about a feature that doesn't exist. The naive-data model invents it; the Bob model says it isn't documented and cites the real section.

## 8. Risks
| Risk | Mitigation |
|---|---|
| Architect writes broken or trivial generators | Sandbox + unit tests + repair loop; require each generator to produce N distinct outputs; human can veto in the UI |
| Writer drifts from locked facts | Locked-slot check + Jev "supported?"; drop failures |
| Executing LLM-written code | Run in a subprocess sandbox with no network, a time limit and a restricted import allowlist |
| Rate limits | Semaphores, backoff, batch API for non-live runs, cached architect output for the demo corpus |
| Naive baseline beats Bob | Then report it honestly and show where Bob wins (hallucination rate is the most likely win) |
| Fine-tuning three models in 5 hours | Small base model (0.5B to 1.5B), LoRA, short runs on the GPU box; start by 8pm |
