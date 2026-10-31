# Human review rubric

## Select a sample

Record the run ID, revision, source set and total accepted and rejected counts. Randomly sample accepted rows using a recorded seed and list of eligible row IDs. For a small pilot, review up to 50 or all accepted rows if fewer exist. Also inspect a separate, explicitly non-random selection of rejected rows across available rejection reasons. If deliberately sampling rare case types, report those results separately from the random sample; do not combine them into an overall error estimate without accounting for the selection.

## Review each row

Read the question and answer, then the cited passages and relevant surrounding source material. Use pass, fail, or unable to judge for each dimension:

| Dimension | Pass when | Examples of failure |
|---|---|---|
| Realism | A plausible user might ask the question and it is understandable. | Contrived wording or a duplicate with trivial paraphrasing. |
| Behavior | The answer responds appropriately: answer, clarify, acknowledge a gap, request needed account information, or escalate. | Refuses an answerable question; invents a policy; fails to escalate. |
| Evidence | Every material factual claim follows from the source in context, including numbers and conditions. | Real citation that does not support the claim; correct number applied to the wrong thing. |
| Completeness and usefulness | The response addresses the question and important qualifications without misleading omissions. | Omits an exception or gives only a vague refusal. |
| Format and privacy | The row matches the intended export format and contains no inappropriate sensitive data. | Broken role order or exposed personal data. |

Mark **reject** if any dimension fails, **uncertain** if none fails but any cannot be judged, and **accept** only if all applicable dimensions pass. Multiple error labels are allowed: unsupported, contradicted, missing qualification, wrong behavior, unhelpful, unrealistic, duplicate, format, privacy, other. Mark severity as critical for material misinformation, privacy exposure, or unsafe handling; otherwise mark ordinary and explain. These are review conventions, not calibrated risk scores.

## Record and report

`run_id | row_id | case_type | selection (random/reject-focused) | realism | behavior | evidence | usefulness | format/privacy | decision | error labels | severity | source/claim notes | reviewer | date`

Report sampled and eligible counts, how the sample was selected, accepts/rejects/uncertain, counts by error label, and concrete examples. Separate human decisions from automated check outcomes and model-judge agreement. A small sample cannot establish a precise error rate or prove the dataset will improve a trained model. Escalate disagreements for a second review and preserve both decisions.
