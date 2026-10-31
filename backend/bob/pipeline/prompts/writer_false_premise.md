## Case type: false_premise

The USER assumes a wrong fact. The passages state the right fact.

- Each slot gives one evidence item: its id, name, value and the exact source text. The USER message assumes a wrong value or a wrong behavior for that item, as a real customer could remember it wrongly (for example a wrong number of days, a wrong limit, a wrong default). The user states the wrong assumption naturally inside the question. They do not ask "is it true that".
- The wrong value must be clearly wrong, not a rounding of the right value.
- The ASSISTANT reply politely corrects the assumption with the right value from the passage ("It is actually 30 days, not 60"), then helps with what the user wants to do. It does not accept the wrong value anywhere.
- Set `premise_evidence_id` to the evidence id of the slot. Set `absent_topic` to null.
