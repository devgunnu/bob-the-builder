# Support FAQ (internal)

Quick answers for the support queue. Link the public doc page in the reply when one exists.

## Billing and credits

**Customer says they were charged for pages that returned 404.**
That is expected. If Firecrawl returned a document, the page costs 1 credit, even when the target site answered 403 or 404. Point them to `metadata.statusCode` so they can stop retrying dead URLs. A scrape that returned no document at all costs 0 credits.

**Customer's crawl credits keep going up after the crawl "finished".**
Crawl and batch scrape credits are billed as each page completes, not when the job is submitted. Late pages can keep appearing for minutes, sometimes hours, at busy times. Do not issue a refund for this; explain the delay.

**Customer on the free plan gets HTTP 402.**
They used their 1,000 monthly credits. The free plan has no pay-as-you-go, so requests return 402 until the monthly reset. Options: upgrade, or wait for the reset.

**Customer asks if unused credits roll over.**
Plan credits do not roll over by default. Annual Scale plans roll unused credits over 1 month and annual Enterprise plans roll them over 2 months. Credits they bought manually stay until used, unless they cancel.

## Rate limits

**Free plan user hitting 429 on /crawl.**
The free plan allows 2 crawl requests per minute. Limits are per team, so every key on the team shares the counter. Hobby raises /crawl to 20 per minute.

**Customer asks for a temporary rate-limit increase for a one-off backfill.**
We do not raise limits for single jobs. Suggest batch scrape (it shares the crawl limit but packs many URLs per request) or a plan upgrade. Custom limits are an Enterprise hand-off (see "Enterprise and plan-change hand-offs").

## Accounts

**Customer wants to move credits from one team to another.**
Credits cannot be transferred between teams. Escalate to Tier 2 only if the customer bought the credits by mistake on the wrong team within the last 14 days.

**Customer lost access to the account owner's email.**
Do not change the owner from the support queue. Escalate to Tier 2 with the team id; Tier 2 runs the ownership-verification checklist.

## Things we do not answer in support

- Legal questions (data processing terms, subpoenas): forward to legal@ with the ticket link.
- Security disclosures: forward to the security inbox and do not discuss details in the ticket.
- Questions about other customers' usage or accounts.
