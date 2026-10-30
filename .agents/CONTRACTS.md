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
    tier: Literal["template", "humpback", "qa", "rewrite"]
    task_type: str                           # qa | instruction | howto | definition | ...
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
    writer: str                              # "template" | "vllm:qwen3-8b" | "claude-haiku-5-5"
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
async def write(chunks: list[Chunk], cfg: WriteConfig) -> list[Example]
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

## 4. Writer interface (`bob/pipeline/write.py`)

```python
class Writer(Protocol):
    name: str
    price_in: float; price_out: float        # $ per token, 0 for local
    async def complete_json(self, system: str, user: str, schema: dict) -> tuple[dict, Usage]
```
Backends: `VLLMWriter` (OpenAI-compatible base_url on the GPU box), `AnthropicWriter` (Haiku 5.5, tool use / structured output), `TemplateWriter` (no LLM).

Humpback prompt contract: input = chunk text + task_type + goal; output JSON `{"instruction": str, "self_score": 1-5}`. The chunk text (lightly cleaned) becomes the response. Keep rows with `self_score >= 4`.

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
  --preset modelforge-sft --format jsonl,parquet --writer vllm \
  [--validate-with-modelforge http://localhost:8000 TOKEN] [--replay]
```
