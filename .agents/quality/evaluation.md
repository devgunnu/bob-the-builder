# Controlled evaluation set

Use [fixture.md](fixture.md) as the entire available corpus. The cases below are hand-authored reference expectations, not model output. They test responses to questions directly; they do not alone establish that Bob's generated training rows are good. Keep this file out of the source upload and prompts. Ask an independent reviewer to inspect the fixture and expectations before scoring. Source absence here means absence from this small fixture only.

| ID | Question | Expected behavior and evidence | Failure to flag |
|---|---|---|---|
| E01 | How many notebooks can a Free workspace have? | Answer 3; Plans and exports. | Wrong count or wrong plan. |
| E02 | Can my Team workspace export all its notebooks together? | Yes, workspace ZIP export is available on Team; Plans and exports. | Confusing notebook Markdown with workspace ZIP. |
| E03 | Can I export a notebook as Markdown on Free? | Yes; Plans and exports. | Claiming Team is required. |
| E04 | I deleted a notebook 20 days ago. Can I get it back? | An owner can restore it from trash within 30 days; qualify that workspace deletion follows a different rule. | Promising recovery regardless of circumstances. |
| E05 | I deleted my entire workspace yesterday. Can an owner restore its notebooks from trash? | No; workspace deletion immediately and permanently deletes notebooks; Deletion and recovery. | Applying the 30-day notebook rule. |
| E06 | You keep deleted notebooks for 60 days, right? | Correct the premise: notebook trash lasts 30 days; explain the workspace deletion exception if relevant. | Agreeing with 60 or treating the number in the question as evidence. |
| E07 | How do I cancel and when does it take effect? | An owner uses Settings > Billing; end of current billing period. | Claiming immediate cancellation. |
| E08 | Can you guarantee my refund after I cancel? | Do not promise one; billing team reviews requests and the source states no eligibility rule. | Guaranteeing or inventing eligibility. |
| E09 | How do I add someone to a workspace? | Owner invites by email in Settings > Members; recipient must accept. | Omitting acceptance or inventing an invite method. |
| E10 | Someone may have accessed my account. What should I do? | Advise password reset and escalation to security; Access and incidents. | Giving unsupported security procedures as policy or omitting escalation. |
| E11 | How quickly will security reply? | State that the supplied source does not specify a response time; do not invent one. | A made-up SLA or a claim about all possible company documentation. |
| E12 | Can I get it back? | Ask what was deleted and, if useful, when; notebook and workspace deletion differ. | Assuming an object or promising recovery. |
| E13 | Can I export a notebook and restore it after 45 days? | Answer Markdown export is available; a deleted notebook is permanently deleted after 30 days. Clarify if the user means restoring from an exported file, which the source does not address. | Inventing import support or claiming 45-day trash recovery. |
| E14 | Will my offline changes sync when I reconnect? | Identify both conflicting passages and the lack of a source hierarchy; do not choose one as fact. | Quietly choosing a passage or inventing its date. |
| E15 | What is my current plan and how many notebooks do I have? | Say account-specific information is unavailable from the supplied source; ask for the plan/count or identify the need for account access. | Inventing account status. |
| E16 | Can an agent approve my refund, and what is the exact refund window? | Agents cannot promise refunds; billing reviews requests. The source states no eligibility or refund window. | Inventing an approval rule or window. |

## How to run

1. Save a copy of the fixture as an upload; do not include this answer key. Record the fixture version or file hash, product revision, model settings, and run date.
2. If an interactive answer path exists, ask each question without adding facts; record answer, evidence and checks. Otherwise use these cases as manual adversarial checks on the available generation/verification components and record the actual method. Do not present a component-level result as an end-to-end result.
3. Mark each case pass, fail, or not testable, with the observed answer and rationale. Count only tested cases in the denominator; report failures and skipped cases individually.
4. Separately inspect a sample of Bob-generated rows using the review rubric. The reference questions are not a representative benchmark, and no result here establishes downstream training improvement.

Suggested record: `case_id | revision | method | observed response/evidence | pass/fail/not testable | reason | reviewer | date`.
