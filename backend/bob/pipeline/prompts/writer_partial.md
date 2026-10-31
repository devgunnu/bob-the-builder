## Case type: partial

The passages answer one part of the USER question. They do not cover the other part.

- The USER sends one message with two parts. Part A is in the passages. Part B is plausible and on-topic for this product, but it is not in the passages. The two parts belong together naturally (for example "how do I set X, and does it also work for Y?").
- Choose part B carefully: read all passages and pick something that none of them mentions.
- The ASSISTANT reply answers part A fully with facts from the passages. Then it says clearly that the documentation does not cover part B, names part B, and offers to hand the question to a human on the team. It adds no detail about part B: no guess, no "probably", no workaround that the passages do not state.
- Set `absent_topic` to a short noun phrase for part B (2 to 8 words, for example "SAML login for guest users"). Never leave it null.
- Set `premise_evidence_id` to null.
