---
source_url: notion://40a41e04-143a-810a-bd05-cfc5a94e92eb
title: Reply style guide and canned replies
fetched_at: 2026-10-31T02:52:28+00:00
---

## Style
- Answer the question in the first sentence. Explain after.
- Use the customer's words for their problem; use our words for the product (credits, concurrent browsers, crawl, batch scrape).
- Give exact numbers from the docs. Never estimate a limit or a price.
- If the docs and this wiki do not cover the question, say so plainly and offer a hand-off. Do not guess.
- No "according to the documentation". Link the page instead.
- Sign off with your first name only.
## Canned replies
**Rate limit (429) on a paid plan**
> Thanks for the details. Your team hit its requests-per-minute limit for this endpoint. Limits are shared by every API key on the team. Spreading requests out, or retrying with backoff, will clear it. If you need a higher limit, I can connect you with our sales team.
**HTTP 402 on the free plan**
> Your team has used its 1,000 free credits for this month, so requests that use credits return 402 until the monthly reset. You can upgrade from billing settings to keep going today.
**Charged for 404 pages**
> Pages that came back with a 404 still return a document, so they use 1 credit each. You can check `metadata.statusCode` in each response and stop retrying URLs that keep failing.
**Question we cannot answer**
> Good question. Our docs don't cover this, and I don't want to guess. I've passed it to our engineering team and will update you here.
