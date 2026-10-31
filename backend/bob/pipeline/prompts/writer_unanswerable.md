## Case type: unanswerable

The passages do not answer the USER question, but the question is on-topic and plausible for this product.

- Ask about something that a real customer of this product could ask about this topic, but that none of the passages mentions. Read all passages first and make sure that the answer is not in them, not even in part.
- Do not ask about a different product or an absurd feature. The question must sound like something that the docs could cover.
- The ASSISTANT reply says that the documentation does not cover this, names what the user asked about, and offers to hand the question to a human on the team. It invents nothing: no steps, no settings, no "you could try", no guess. It can point to a related thing that the passages cover only if that thing is a real fact from the passages.
- Set `absent_topic` to a short noun phrase for what is missing (2 to 8 words, for example "bulk PDF export"). Never leave it null.
- Set `premise_evidence_id` to null.

- Set `chunk_ids` to the supplied focus passage IDs you reviewed. These show the context searched, not proof that the answer is absent from the entire corpus.
