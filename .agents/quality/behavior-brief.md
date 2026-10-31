# Behavior brief: product exploration

**Status: proposal for discussion.** This is not a change to the current plan, contracts, or work assigned to implementation agents.

Bob could help a user specify what the future assistant should do, then use that brief to plan and review training examples. Topics describe the subject; behaviors describe the intended response.

## Draft interaction

1. The user provides a goal and sources, optionally including real examples.
2. Bob proposes a brief and links each source-derived point to evidence. It labels suggestions and unresolved assumptions distinctly; it does not present invented policy as fact.
3. The user edits or approves the brief, including what to do when information is incomplete or sources conflict.
4. Bob proposes coverage across topics and behaviors. The user can adjust targets and mark combinations inapplicable.
5. Rows show evidence, checks and the brief version used. Review feedback can suggest a brief change or inform a later batch, subject to user review.

## Illustrative brief

Using the fictional Harbor Notes fixture, a proposed support assistant brief might say:

- **Role:** Help users understand documented product features and procedures.
- **Answer:** Give the documented answer and material conditions, with source evidence.
- **Clarify:** Ask what was deleted when notebook versus workspace deletion changes the answer.
- **Acknowledge limits:** Do not invent refund eligibility, account status, or a security response time.
- **Escalate:** Direct refund requests to billing and suspected account compromise to security, as the fixture says.
- **Conflict:** Surface both sync claims and ask for a resolution; do not silently choose.
- **Tone suggestion:** Direct and calm. This is a proposed style, not a source policy.

## Decisions to explore

- Who can approve or change a brief, and what happens to earlier rows after a change?
- Which feedback should change future generation, and when must a human approve that change?
- How should a user resolve conflicts or provide policy absent from source material, and how is that decision attributed?
- How should the UI distinguish target coverage, observed rows, and untested behavior?
- What evidence would show the brief improves review or dataset quality? Compare reviewer outcomes on comparable batches before claiming an improvement.
