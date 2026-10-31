You make negative examples for preference training of a customer support assistant. For each item you receive the documentation passages, the case type, a USER message and the correct ASSISTANT reply. You write one FLAWED reply to the same USER message.

The flawed reply must look like a confident, fluent and helpful support reply, with the same tone and a similar length as the correct reply. It must contain exactly the flaw that the case type asks for, so that a careful checker can catch it. Do not mark the flaw, do not hedge and do not explain it.

## The flaw by case type

- `answerable`: keep the correct facts, and add one plausible detail that the passages do not state: an extra setting, menu path, option, limit or step that sounds real but is not in the passages.
- `partial`: answer the covered part correctly, then also answer the uncovered part with invented details, as if the documentation covered it. Do not say that the docs do not cover it. Do not offer a handoff.
- `unanswerable`: answer the question confidently with invented steps or facts, as if the documentation covered it. Do not abstain. Do not offer a handoff.
- `false_premise`: accept the wrong assumption of the USER as true and build the answer on it. Do not correct it.

## Other rules

- Do not say "according to the document", "according to the passage", "according to the text", "in the provided context" or "as an AI".
- Each reply is between 10 and 400 words.

## Output

Return one JSON object and nothing else:

{"replies": [{"item": 1, "assistant": "..."}]}

Write exactly one reply for each item number.
