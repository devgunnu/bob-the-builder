# End-to-end acceptance checklist

All checks start **not run**. Record revision, environment, timestamp, operator, job ID, expected and observed result, and a safe link or path to evidence. Never place keys, tokens, private source text, or customer data in this file. Use a real approved demo corpus for the product demo; the fictional fixture is for controlled testing only.

## Local first

- [ ] Start backend and frontend using documented local settings; health and configuration reflect the actual environment.
- [ ] Upload approved Markdown sources, create a small job with a budget, and verify the source count and content are correctly associated with the job.
- [ ] Observe a proposed plan; change a target or cell and approve it. Verify the running job uses the approved plan.
- [ ] Observe real generation and checks. Inspect an accepted row and a rejected row: source evidence, relevant check outcomes and rejection reasons are visible and correspond to the row.
- [ ] Verify progress and counts reconcile with stored rows and final report. Coverage represents configured targets and actual counts, not a claim of complete domain coverage.
- [ ] Export a supported format. Open the downloaded file, parse every row, compare its content and count with the selected export, and inspect available provenance. Record unsupported formats as not tested.
- [ ] Run the controlled cases where the product exposes a suitable path, and independently review a sample using the rubric.

## Failure and recovery

- [ ] Provider failure: use a controlled invalid configuration or interrupt access in a safe test environment; observe an actionable error or documented real fallback. Restore settings afterwards.
- [ ] Cancel an active job; confirm terminal state, no further generation after cancellation completes, and a clear UI outcome. Record latency and any in-flight calls.
- [ ] Disconnect and reconnect the live stream; confirm replay uses the last event ID, no missing events, and duplicate events do not inflate displayed counts.
- [ ] Submit a known unsupported or contradicted candidate to the verifier if an accessible test path exists; record its verdict and evidence. If unavailable, mark blocked rather than infer success.
- [ ] Try invalid inputs and a job exceeding available capacity; observe appropriate errors without exposing secrets.
- [ ] Exercise the budget guard and record incurred and in-flight spend; do not call it a strict cap unless verified.

## Cloud and user isolation

- [ ] Sign in as the test user, connect and verify the intended AWS role and models; start and complete a real cloud job, observe its events and download its export.
- [ ] Verify a second test user cannot view, control, stream, or download the first user's job or uploads; check ownership at each relevant endpoint.
- [ ] Test SSE reconnect through the deployed domain and record worker startup time. Test worker failure and confirm the job reaches a visible terminal error.
- [ ] Confirm deployment-specific routes and static assets work; record actual configuration and any unavailable dependencies. Do not infer a cloud pass from local results.

## Execution record

| Date / revision | Environment / job | Check | Result (pass/fail/blocked) | Evidence / issue |
|---|---|---|---|---|
| — | — | — | Not run | — |
