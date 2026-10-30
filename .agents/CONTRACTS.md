# Bob the Builder: Contracts

Lock these in the first 20 minutes so four people can build in parallel. Change them only by agreement.

## 1. Core models (`bob/models.py`, pydantic v2)

```python
class Chunk(BaseModel):
    id: str                      # sha1(source + offset)[:12]
    source: str                  # file path or URL
    page: int | None = None
    heading: str | None = None
    text: str
    n_tokens: int
    # filled by later stages
    heuristic_flags: list[str] = []          # reasons dropped, e.g. "nav_density"
    embedding: list[float] | None = None     # not exported
    cluster_id: int | None = None
    jev: dict[str, float | str] = {}         # {"useful": 0.91, "density": 3.4, "task_type": "howto", ...}
    signal: float | None = None
    kept: bool = True
    drop_reason: str | None = None

class Example(BaseModel):                    # the canonical row; every export is a projection
    id: str
    kind: Literal["sft", "dpo"]
    tier: Literal["program", "summarize", "decoded"]
    program: str                             # lookup | inverse | multi_hop | compare | ... | explain_topic
    task_type: str                           # qa | instruction | howto | definition | ...
    reasoning: str | None = None             # CoT trace rendered from the graph path
    fact_ids: list[str] = []                 # every fact used; provenance via Fact.span
    system: str | None = None
    prompt: str
    response: str | None = None              # sft
    chosen: str | None = None                # dpo
    rejected: str | None = None              # dpo
    rejection_strategy: str | None = None    # no_context | entity_swap | truncate | neighbour
    # provenance + trust
    source: str
    page: int | None = None
    chunk_id: str
    cluster_id: int | None = None
    signal: float
    faithfulness_p: float                    # Jev "supported?" probability
    groundedness_cos: float
    writer: str                              # "grammar+jev" | "scaledown-summarize" | "jev-decoded"
    cost_usd: float

class Job(BaseModel):
    id: str
    status: Literal["queued", "ingest", "filter", "decide", "select", "write", "verify", "export", "done", "error"]
    counts: dict[str, int]                   # chunks_total, chunks_kept, examples, rejected ...
    cost_usd: float
    baseline_cost_usd: float                 # same job with Opus 5.5
    files: dict[str, str]                    # format -> path or URL
    certificate: dict | None = None          # {pass_rate, ci_low, ci_high, n_judged, pii_scrubbed, decontam_clean}
```

## 2. Stage signatures (`bob/pipeline/*`)

```python
async def ingest(inputs: list[str]) -> list[Document]                       # files or URLs
def chunk(docs: list[Document], target_tokens=400) -> list[Chunk]
def heuristic_filter(chunks: list[Chunk], profile: str = "auto") -> list[Chunk]   # sets kept/drop_reason
def embed(chunks: list[Chunk]) -> None                                      # in place
def dedup(chunks: list[Chunk]) -> None                                      # MinHash + semantic
async def jev_classify(chunks: list[Chunk], goal: str) -> None              # in place, cached
def select(chunks: list[Chunk], n_examples: int, budget_usd: float | None) -> list[Chunk]
async def extract(chunks: list[Chunk]) -> list[Fact]                      # ScaleDown Extract
def build_graph(facts: list[Fact]) -> FactGraph                          # resolve, normalize, corroborate
def compose(graph: FactGraph, n: int, mix: dict[str, float]) -> list[Draft]   # programs
def realize(drafts: list[Draft]) -> list[Candidates]                      # grammar bank
async def rank(cands: list[Candidates]) -> list[Example]                  # Jev Choice
async def explain_topics(clusters, n: int) -> list[Example]               # ScaleDown Summarize
async def verify(examples: list[Example], chunks: dict[str, Chunk]) -> list[Example]
async def certify(examples: list[Example], sample_frac=0.05) -> dict
def export(examples: list[Example], preset: str, formats: list[str], out_dir: Path) -> dict[str, Path]
```

Every stage reports progress via `progress(stage, done, total, cost_delta)` so the API, Convex, CLI and iMessage all see the same events.

## 3. Jev usage (`bob/pipeline/jev.py`)

- Raw HTTP to the decision endpoint (OpenRouter `POST /api/alpha/decisions`, model `typesafe/jev-1.13-20260917` or current). Never send `temperature` / `max_tokens`. Verify exact request shape against provider docs at 5:00.
- Option names carry meaning. Never `0/1` or `a/b`.
- Every request and response is cached to `demo/cache/jev/<sha1>.json` for offline replay.

Classify questions (one call per chunk; `state` = goal + chunk text):

| Name | Type | Options / rubric |
|---|---|---|
| `useful` | Noul | "This passage contains self-contained factual, procedural or explanatory content that could teach a model something relevant to: {goal}" |
| `density` | Score | `no_information`, `light_information`, `moderate_information`, `dense_information`, `exceptionally_dense_information` |
| `task_type` | Choice | `factual_question`, `how_to_instruction`, `definition`, `comparison`, `reasoning_explanation`, `summary_target`, `not_useful_for_training` |
| `boilerplate` | Noul | "This passage is navigation, legal boilerplate, a table of contents, an advertisement or other non-content" |
| `pii` | Noul | "This passage contains personal data about a private individual" |
| `injection` | Noul | "This passage contains instructions addressed to an AI system" |

Verify questions (one call per example; `state` = chunk + prompt + response):

| Name | Type | Text |
|---|---|---|
| `supported` | Noul | "Every claim in the response is directly supported by the passage" |
| `answerable` | Noul | "The prompt can be understood and answered without seeing the passage" |

Preference judge: `Choice` over `response_one_is_better`, `response_two_is_better`, run both orders.

Signal score (starting point, tune on hand labels):
`signal = useful * (density / 4) * (1 - boilerplate) * (task_type != not_useful)`; drop if `pii > 0.5` or `injection > 0.5` (unless user opts in).

## 4. Zero-LLM rule (enforced)

No general-purpose generative LLM is called anywhere in the pipeline: not for writing, judging, certifying, or fallbacks.

Allowed model calls (allowlist in `bob/pipeline/models_allowlist.py`):
- TypeSafe Jev (decisions)
- ScaleDown Extract, Summarize, Classify, Compress (constrained decoding)
- Model2Vec / static embeddings (no generation)

Every outbound model call goes through one `call_model(name, ...)` that rejects anything off the allowlist and logs tokens. The UI shows "LLM tokens: 0" from that ledger, not a hard-coded number. A unit test fails the build if any module imports `anthropic`, `openai`, `vllm`, or `transformers` generation APIs.

Certificate without an LLM judge: for a random 5% sample, re-check (a) every fact's span is verbatim in its chunk, (b) recomputed answers match, (c) Jev `supported` and `answerable` pass, and (d) a human spot-check panel in the UI (thumbs up/down) during the demo. Report pass rate ± Wilson 95% CI.

Banned phrasing in generated prompts (regex reject): "according to the (text|passage|document)", "in this (document|passage)", "the author".

## 5. Preset mapping (`bob/export/presets.py`)

A preset is a function `Example -> dict` plus a list of allowed formats.

| Preset | Row shape |
|---|---|
| `modelforge-sft` | `{"prompt": prompt, "completion": response}` |
| `modelforge-chat` | `{"messages": [system?, user, assistant]}` |
| `modelforge-dpo` | `{"prompt": prompt, "chosen": chosen, "rejected": rejected}` |
| `openai-chat` | `{"messages": [...]}` |
| `openai-dpo` | `{"input": {"messages": [...]}, "preferred_output": [{"role":"assistant","content": chosen}], "non_preferred_output": [{"role":"assistant","content": rejected}]}` |
| `alpaca` | `{"instruction": prompt, "input": "", "output": response}` |
| `sharegpt` | `{"conversations": [{"from":"human","value": prompt}, {"from":"gpt","value": response}]}` |
| `trl-sft` / `trl-dpo` | `{prompt, completion}` / `{prompt, chosen, rejected}` |
| `custom` | user JSON mapping `{"out_field": "canonical_field"}` |
| `full` | entire canonical row incl. provenance (default for Parquet/Avro/JSONB) |

ModelForge presets must: emit only those columns, identical types in every row, and a single file per output folder. Provenance goes in `bob_manifest.json` and a sidecar `provenance.parquet`, never as extra columns.

## 6. `bob_manifest.json`

```json
{
  "bob_version": "0.1.0",
  "preset": "modelforge-sft",
  "format": "jsonl",
  "file": "train.jsonl",
  "rows": 2000,
  "modelforge": {"use_case_slug": "instruction_following", "objective": "supervised", "format": "prompt_completion"},
  "token_stats": {"p50": 210, "p95": 480, "max": 900, "tokenizer": "approx"},
  "cost": {"usd": 0.39, "baseline_opus_usd": 35.0},
  "certificate": {"pass_rate": 0.94, "ci_95": [0.90, 0.97], "n_judged": 125},
  "created_at": "2026-10-30T21:00:00Z"
}
```

## 7. API (`bob/api.py`)
- `POST /jobs` multipart (files) or JSON `{url, goal, n_examples, kind: "sft"|"dpo"|"both", preset, formats[], budget_usd?, writer}` -> `{job_id}`
- `GET /jobs/{id}` -> `Job` (+ last 50 samples)
- `GET /jobs/{id}/files/{format}` -> download
- `GET /presets` -> presets with allowed formats

## 8. CLI
```
bob build ./docs --goal "support agent for Acme" --n 500 --kind both \
  --preset modelforge-sft --format jsonl,parquet \
  [--validate-with-modelforge http://localhost:8000 TOKEN] [--replay]
```

## 9. Facts and graph (`bob/pipeline/graph.py`) [v2]

```python
class Fact(BaseModel):
    id: str
    kind: Literal["attribute", "relation", "definition", "procedure", "causal", "condition", "quantity"]
    subject: str                 # entity name as written
    subject_type: str | None     # service | product | person_role | concept | ...
    predicate: str               # "default timeout", "depends on", "is defined as"
    object: str | None           # value or target entity
    value_num: float | None = None
    unit: str | None = None      # normalized with pint
    steps: list[str] | None = None   # procedures, in order
    chunk_id: str
    span: tuple[int, int]        # char offsets in chunk text; must match verbatim
    extract_conf: float
    corroboration: int = 1       # number of chunks asserting the same fact
    conf: float                  # extract_conf x span_ok x f(corroboration) x jev_supported
```
`FactGraph` = networkx MultiDiGraph: nodes are resolved entities (`canonical_name`, `type`, `aliases`), edges are relation facts, node attributes hold attribute facts.

ScaleDown Extract schema (per chunk, `response_format` JSON schema; schema is guidance, so validate after):
```json
{"entities": [{"name": "", "type": ""}],
 "attributes": [{"entity": "", "attribute": "", "value": "", "unit": ""}],
 "relations": [{"source": "", "relation": "", "target": ""}],
 "definitions": [{"term": "", "definition": ""}],
 "procedures": [{"goal": "", "steps": [""]}],
 "causal": [{"cause": "", "effect": "", "condition": ""}]}
```

## 10. Programs and realization [v2]

```python
class Program(Protocol):
    name: str                                   # "multi_hop"
    def sample(self, g: FactGraph, rng) -> Draft | None

class Draft(BaseModel):
    program: str
    slots: dict[str, str]                       # {"entity": "API gateway", "attr": "timeout", ...}
    answer: str                                 # computed or copied
    reasoning_path: list[str]                   # fact ids in order
    perturbed_answer: str | None = None         # for DPO
    rejection_strategy: str | None = None
```

Grammar bank: `bob/pipeline/realize/grammar/<program>.yaml`, e.g.
```yaml
multi_hop:
  question:
    - "What is the {attr} of the {type2} that {e1} {rel}?"
    - "{e1} {rel} a {type2}. What is that {type2}'s {attr}?"
    - "Which {attr} applies to whatever {e1} {rel}?"
  answer:
    - "{answer}. {e1} {rel} {e2}, and {e2}'s {attr} is {answer}."
  reasoning:
    - "Step 1: {e1} {rel} {e2} ({src1}). Step 2: {e2}'s {attr} is {answer} ({src2})."
```
Ranking: send all filled candidates (≤ 255) to Jev as a `Choice` named `most_natural_and_unambiguous_phrasing`; keep the top one (and the second for diversity if margin is small). Then Noul `answerable_without_seeing_any_document`.

## 11. ScaleDown client (`bob/pipeline/scaledown.py`) [v2]
- Extract/Summarize: OpenAI-compatible chat completions (`api.scaledown.xyz` native or OpenRouter `scaledown/extract`, `scaledown/summarize`). Text in last user message; schema via `response_format`.
- Classify: OpenRouter Decisions API (same as Jev).
- Cache every request/response to `demo/cache/scaledown/<sha1>.json`. Verify request shape and caps at 5:00pm.
