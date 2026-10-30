# Research 01: ModelForge Integration

> Source: research agent reading `ForgeOpus/ModelForgeRedesign` (package `modelforge-finetuning` v4.0.0), 2026-10-30. Read only; nothing modified. README is empty, so `DEVELOPER_GUIDE.md` and the code are the only documentation. Paths below are relative to that repo.

## 1. Accepted formats and schemas

### File types (`dataset_manager/dataset_factory.py`)
- Extensions: `.parquet`, `.arrow`, `.jsonl`, `.json`, `.csv`, `.txt` (L10, L134). `.jsonl` uses the `json` loader; `.txt` uses the `text` loader (L11, L141-143).
- Directory: loads only the most preferred extension, parquet > arrow > jsonl > json > csv > txt (L10, L16-31), concatenating all files of that type sorted by name.
- JSON (`handle_json`, L34-79): tries JSONL, then a top-level array, then an object (regex-scans the first 64 KB for `"key": [`). Directory shards are assumed flat JSONL (L91-93).
- HF Hub IDs load with `remote=True` (L110-117, L127-128).
- Not supported: `.gz`, uppercase extensions, no extension (case-sensitive `endswith` at L134 falls through to a confusing Hub lookup).

### What the validators actually check
- SFT (`finetuning_strategies/strategies/sft.py:96-111`): one of `messages`, `text`, or `prompt` + `completion`. Case-sensitive.
- DPO (`finetuning_strategies/strategies/dpo.py:82-97`): `chosen` + `rejected` required; `prompt` optional (warning if missing). Lowercased comparison.

### Use case to strategy to required record
Use cases: `recommendation_engine/language_use_cases/*.py`. Objective map (`utilities/recommendation_engine.py:30-34`): supervised = `sft`, preference = `dpo`, reinforcement = `grpo` (not implemented).

| Use case slug | Objective | Task | Bob must emit |
|---|---|---|---|
| `text_generation` | supervised | causal_language_modeling | `prompt`, `completion` |
| `instruction_following` | supervised | causal_language_modeling | `prompt`, `completion` (or `messages`) |
| `instruction_following` | preference | causal_language_modeling | `prompt`, `chosen`, `rejected` |
| `summarization` | supervised | seq2seq_modeling | `prompt`, `completion` (see quirk 1) |
| `extractive_qa` | supervised | token_classification | cannot train (see quirk 2) |

### Example records (JSONL)
SFT prompt-completion (text_generation, instruction_following, summarization):
```json
{"prompt": "Summarise this ticket: user cannot log in after reset.", "completion": "Customer is locked out after a password reset."}
```
SFT conversational:
```json
{"messages": [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "Explain LoRA."}, {"role": "assistant", "content": "LoRA trains low-rank adapters..."}]}
```
SFT conversational prompt-completion:
```json
{"prompt": [{"role": "user", "content": "Explain LoRA."}], "completion": [{"role": "assistant", "content": "LoRA trains..."}]}
```
SFT language modeling (`.txt` also becomes `text`):
```json
{"text": "Once upon a time there was a compiler..."}
```
DPO standard:
```json
{"prompt": "Explain LoRA.", "chosen": "LoRA freezes base weights and trains low-rank matrices...", "rejected": "It is a thing."}
```
DPO conversational:
```json
{"prompt": [{"role": "user", "content": "Explain LoRA."}], "chosen": [{"role": "assistant", "content": "LoRA freezes..."}], "rejected": [{"role": "assistant", "content": "It is a thing."}]}
```
Extractive QA (documented, currently fails):
```json
{"context": "ModelForge was released in 1999.", "question": "When?", "answers": {"text": ["1999"], "answer_start": [27]}}
```
UI docs table: `web/frontend/src/screens/Docs.tsx:42-67` (advertises `document, summary` for summarization, which conflicts with the validator).

## 2. Loading, validation, size, splitting
- `DatasetFactory.load(path, type_=None, streaming=False, remote=False)` (`dataset_factory.py:120-147`); streaming never enabled.
- Pre-flight: `WorkflowService.validate_dataset` (`workflow/service.py:121-156`) checks path, loads, takes the first split, runs `validate_data_format`, returns `{valid, path, remote, columns, format_description, error, row_count}`. Exposed as `POST /api/datasets/validate` (`web/app.py:115-117`), body `DatasetValidationRequest` (`workflow/models.py:32-36`): `{path, remote, use_case_slug, objective}`.
- Training (`workflow/jobs.py:272-274`) keeps only the first split; validation runs again in `SFT.finetune` (`sft.py:367`) and `DPO.finetune` (`dpo.py:319`).
- No train/test split and no `eval_dataset` (`workflow/training.py:83-96`). Bob's eval/test files are ignored.
- No row or size caps. Effective limit is `max_length` by VRAM: 512 (<12 GB), 1024 (<32 GB), 2048 otherwise (`sft.py:262-271`). Packing on (`bfd`); long samples truncated.
- `DataFormatSpec.column_aliases` (`use_case.py:5-9`) is declared but never applied. Bob must emit canonical names.

## 3. Strategies
- Registered: `sft`, `dpo` only (`workflow/registries.py:9-14`).
- SFT: causal LM + seq2seq. DPO: causal LM only, 2x memory.
- PEFT tiers (`sft.py:273-297`): `full_finetune`, `lora_bf16`, `qlora_8bit`, `qlora_4bit`, auto-picked by hardware. Same data shape for all.
- LoRA rank by model size: r = 8/16/32/64 (`sft.py:331-349`).
- Not implemented: GRPO, token classification. `unsloth` provider listed but not registered.

## 4. Stack and integration points
- Python >= 3.13; transformers >= 5.8, trl >= 1.4, peft, accelerate, bitsandbytes, datasets; FastAPI + uvicorn + websockets; pydantic v2; SQLite run state.
- Frontend: React 19, Vite, TS, Tailwind v4, Radix, recharts, react-router 7.
- CLI (`pyproject.toml`): `modelforge` with `run` (web UI on :8000 with token), `cli` (wizard), `recommend`, `history`, `list-tasks`, `tensorboard`; `modelforge-nb`. No non-interactive "train this file" command.

Integration options, best first:
1. **File drop (default).** Bob writes `<out>/train.jsonl` with canonical columns; user pastes the path in ModelForge. Zero coupling, so Bob stands alone.
2. **REST.** Token via `Authorization: Bearer`, `X-ModelForge-Token`, or `?token=` (`web/auth.py:23-32`); fix it with `modelforge run --token X`. Endpoints: `POST /api/datasets/validate`, `POST /api/runs` (`TrainingRunRequest`, `workflow/models.py:39-58`: `{use_case_slug, objective, model_id, dataset_path, output_dir, gpu_indices?, tensorboard?, recommendation?}`), `GET /api/use-cases` (live `data_formats`). Server-local paths only, no upload endpoint.
3. **In-process Python.** Pulls in torch. Not recommended.
4. **`bob_manifest.json` sidecar.** `{use_case_slug, objective, format: "prompt_completion"|"messages"|"dpo", row_count, est_max_tokens}`, mapping directly onto the validate/run requests.

**Recommendation:** 1 + 4, plus optional `--validate-with-modelforge URL TOKEN` hitting `/api/datasets/validate`.

## 5. Quirks Bob must handle
1. Summarization: emit `prompt`/`completion`, not `document`/`summary`.
2. Extractive QA: skip, or fall back to SFT `instruction_following` with context + question in `prompt` and answer in `completion`.
3. Terminal wizard always validates with SFT (`cli/wizard.py:191`), so DPO files fail in `modelforge cli`. Web UI and notebook CLI are fine.
4. Directory loading merges every file of the dominant type, and a `.parquet` hides `.jsonl` files. Write one file, or splits in separate folders.
5. Only the first split is used; no eval.
6. Wrapped JSON objects may load the wrong array key. Emit plain JSONL.
7. CSV cannot hold nested `messages` / `answers`. Use JSONL or Parquet for conversational or QA data.
8. Keep every record's keys and types identical; avoid extra columns (a stray `text` column can change TRL formatting).
9. `messages` needs a tokenizer chat template; plain prompt/completion strings are safest for small base models.
10. Report token-length stats and offer a max-length cap (512 truncation under 12 GB).
11. Docs drift: `modelforge run` starts the web UI; DPO exists; GRPO does not.
12. Do not offer the `reinforcement` objective.
13. Hub datasets load by ID; only the first split is used.
