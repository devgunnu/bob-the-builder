# Honest Assessment: Is Bob impressive enough for Night Hack?

> 2026-10-30, written before the build. Judged against the event format: 120+ projects, 5 hours, live demos, exhibition judging (a few minutes per table), finalists demo on stage.

## Verdict
**The idea is strong. The plan as scoped is not a winner yet.** As written, it lands in the solid middle: technically interesting, hard to *see* in two minutes, and too big to finish. Narrow it and change what the demo shows, and it becomes a real finalist contender.

## What is strong
1. **A real insight:** LLM-generated data hallucinates and needs an LLM judge. Bob's answers are computed or copied from the source, so every row is verifiable. That is a defensible point, not a gimmick.
2. **Anti-hallucination data** (abstention and false-premise rows) is the most valuable and least common thing Bob makes.
3. **Grounded quantity:** one 60-word table to about 570 checkable rows (research 08).
4. **Clear workflow:** docs in, training-ready file out, in any format.

## What is weak (no sugar-coating)
1. **Datasets are invisible.** A judge walking past sees a table of rows. Nobody gets excited by JSONL. The proof (a better model) is the exciting part, and the current plan puts it last.
2. **"Cheap" is not a differentiator.** Claude Haiku 5.5 already generates 1,000 grounded examples for about $0.09 to $0.21 (research 03). Leading with "costs cents" invites "so does an LLM". Correctness is the real edge.
3. **It can look like a template engine.** 110 rows of "I have N GB and a P-B model..." read as 2010s-style templating to a sharp judge. The worked example used the best case (a table full of numbers); narrative docs multiply far less.
4. **Generalizing across domains in 5 hours is hard.** Extraction schemas, entity resolution and grammars per program type are a lot of hand-built machinery. The risk is that it works great on one corpus and poorly on a judge's random URL.
5. **Circular evaluation.** Scoring a model on held-out rows from Bob's own generators proves it learned Bob's templates, not the product. Judges who know ML will notice.
6. **Scope is about 3x too big:** 11 generators, 7 formats, Convex, Photon, a UI and a live fine-tune, in 5 hours.
7. **Vendor risk:** Jev is 6 weeks old, ScaleDown CDMs 17 days old, and neither's docs could be checked from here. If access fails at 5pm, the core breaks.
8. **Sponsor fit is thin:** strict zero-LLM means Anthropic has no role in the product, and "text a URL, get a dataset" is a weak fit for Photon's "agent you can text" prize.

## What would make it a contender
1. **Lead with model behaviour, not data.** Open on the side-by-side: the base model confidently invents a feature that doesn't exist; the Bob-tuned model says "that isn't documented" and cites the real section. Then show how Bob made the data.
2. **Pitch correctness, not cost:** "A compiler for training data. Every row is computed from your docs and ships with its own checker. Nothing is made up."
3. **Pick a corpus the judges care about:** a sponsor's public docs (Convex or Firecrawl), ingested with Firecrawl. "We built a Convex expert in 5 hours that won't invent APIs" lands with the people judging.
4. **Cut to 4 generators, done well:** symbolic variants, rules-to-follow constraints, abstention/false premise, preference pairs. Two formats (JSONL + Parquet) plus the ModelForge preset.
5. **Evaluate fairly:** a teammate who never saw the templates writes 20 real questions (including 5 about fake features) before training. Score base vs tuned on those. Report both numbers honestly.
6. **Make data visible:** click any row to see its source span light up and its checker pass. Show the row counter climbing while the generator runs.
7. **De-risk first:** confirm Jev and ScaleDown calls before 5:00pm; if either fails, switch to the fallbacks immediately.
8. **Drop Photon** unless someone is free after 8pm.

## Bottom line
The core idea is good enough to impress technical founders. The current plan isn't, mainly because it shows data instead of behaviour and tries to do too much. The fixes are scope and storytelling, not a new idea.

## Update after v3 and research 10: "Would a judge make it win?"

**Not as it stands; finals if the live comparison works with real numbers.** Winning needs one moment that makes the room react.

| Criterion | Score | Why |
|---|---|---|
| Usefulness | High | Trustworthy training data for small models is a real problem |
| Technical depth | High | Architect writes generators + checker code, cheap Writer phrases rows, every row verified against source with decoys |
| Novelty | Medium | Parts have prior art (AutoIF, RAFT, Persona Hub, synthetic-data-kit, distilabel); the combination is new |
| Demo appeal | Low to medium | Datasets are invisible; charts land only with big numbers |
| Works live in 5 hours | Risky | Generate, verify, fine-tune 3 to 4 models, score; one failure leaves only slides |

What would make it win:
1. A judge invents a fake feature live; the naive-data model describes it, the Bob-data model says it isn't in the docs and shows what they do say.
2. A big honest number on questions the team didn't write (for example fabrication 70% -> 10%; 70% -> 55% won't carry it).
3. Instantly showing a rejected row and why it failed.
4. One sentence: "Bob turns your docs into training data that teaches small models not to make things up."

What would sink it: showing the dataset before the behaviour, scoring on Bob's own questions, leading with cost, or a chart that looks pre-made.

Recommendation: build the live hallucination test first; everything else after 8pm.
