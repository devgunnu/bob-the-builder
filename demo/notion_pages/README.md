# Demo Notion pages (fictional internal support wiki)

These pages are seeded into the demo Notion workspace under a parent page called
**"Bob Demo – Support Wiki (fictional)"**, then fetched back through Composio like
any user's Notion pages (`connectors/composio.py`).

They play the role of a support team's internal wiki for the demo product
(Firecrawl). They were written by the Bob team for the demo. They are **not**
Firecrawl's real internal policies.

Rules they follow:
- Facts that also appear in the public docs (`demo/smoke/`) match the docs exactly:
  plan credits, rate limits, concurrency, webhook retries, billing rules.
- Facts that exist only here (escalation tiers, response targets, goodwill credits,
  known issues, hand-off rules) are internal-only. They give the dataset answers
  that the public docs do not have, and they leave gaps that become
  "not in docs" cases.

Seed with `demo/seed_notion.py` (needs a Notion connection that can create pages).
