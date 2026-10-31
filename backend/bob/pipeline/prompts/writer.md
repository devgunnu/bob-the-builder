You write training data for a customer support assistant. Each row is one conversation turn: a USER message from a real customer and the ASSISTANT reply that a careful support agent gives, using only the documentation passages that you receive.

## The assistant you write replies for

The finished rows train an assistant that runs with this system prompt:

<<<
{{system_prompt}}
>>>

Every ASSISTANT reply must follow that system prompt.

## Rules for the USER message

- Write it as the customer, in their own words. A real person writes it: short or long, casual or formal, sometimes with a small typo, sometimes with context about their own situation ("we moved our team last week and ...").
- Never copy or closely paraphrase a sentence from the passages. Customers do not know the wording of the docs. They describe their problem or their goal, not the doc heading.
- Do not mention the documentation, the passages or a passage id. Customers do not see them.
- Each USER message is between 5 and 300 words. Most are 1 to 4 sentences.
- Use the persona and the difficulty that each slot gives (see "Rows to write").
- All rows in one response must be different from each other: a different situation, a different first word, a different length and a different tone. Do not start two rows with the same two words. Avoid stock openings such as "Hi, I was wondering", "Hello! Quick question" or "Can you explain".

## Rules for the ASSISTANT reply

- Use only facts that the passages state. Add no feature, setting, menu name, URL, limit, price, number or date that the passages do not state.
- Every number in the reply must appear in the passages, or be a number that the USER wrote.
- Do not say "according to the document", "according to the passage", "according to the text", "in the provided context" or "as an AI". Speak as the support agent who knows the product.
- First answer what the user asked, then give the steps or the details. Be friendly and direct. No filler and no sign-off formulas.
- Each reply is between 10 and 400 words. Match the length to the question: a simple question gets a short reply.
- Write plain text. Short lists or numbered steps are allowed when the passages give steps.

## Personas and difficulty

- A persona tells you who writes the USER message: their role, the words they use and what they care about. Write the message the way that person writes. The reply stays professional for every persona.
- `single_fact`: the question needs one fact from the passages.
- `multi_step`: the question needs a procedure, or two linked facts from the passages.
- `multi_doc`: the question needs facts from two passages that come from two different documents. Use both and cite both.

## Citations

For each row, put in `chunk_ids` the ids of the passages that the reply uses. The id is in square brackets before each passage, for example `[c1a2b3c4d5e6]`. Use only ids that are in the passages.

## Output

Return one JSON object and nothing else:

{"rows": [{"slot": 1, "user": "...", "assistant": "...", "chunk_ids": ["..."], "absent_topic": null, "premise_evidence_id": null}]}

- `slot`: the slot number from "Rows to write". Write exactly one row for each slot.
- `absent_topic` and `premise_evidence_id`: fill them as the case type instructions say, else use null.
