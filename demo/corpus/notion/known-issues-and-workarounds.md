---
source_url: notion://40a41e04-143a-8123-becd-dadd993345c8
title: Known issues and workarounds
fetched_at: 2026-10-31T02:52:30+00:00
---

Keep this page short. Remove an entry when engineering ships the fix.
## Crawl status shows fewer pages than the dashboard
**Symptom:** the crawl status endpoint reports fewer completed pages than the usage dashboard for the same job.
**Cause:** the dashboard counts credits as pages finish billing, which can run ahead of or behind the status endpoint for a few minutes.
**Workaround:** wait for the crawl status to reach `completed` and compare again. If the numbers still differ by more than 5% after one hour, escalate to Tier 2 with the crawl id.
## JavaScript-heavy pages come back nearly empty
**Symptom:** a scrape returns a page with only the navigation or a loading message.
**Workaround:** ask the customer to set `waitFor` (for example 2,000 to 5,000 ms) so the page can render before capture. If the page loads content after a click, they need `actions`.
**Do not:** promise that every single-page app will work. Some sites block automated browsers.
## Webhook marked failed after customer deploys
**Symptom:** the customer's webhook was marked failed during their own deploy.
**Cause:** the endpoint did not answer with a 2xx within 10 seconds, and all 3 retries (after 1, 5 and 15 minutes) failed while the endpoint was down.
**Workaround:** there is no manual replay from support. The customer can read the results through the crawl status endpoint instead. Suggest they keep the old endpoint up during deploys.
## Signature check fails in frameworks that parse the body
**Symptom:** the customer's `X-Firecrawl-Signature` check always fails.
**Cause:** their framework parsed the JSON body before the check, so the HMAC is computed on re-serialized JSON instead of the raw body.
**Workaround:** compute the HMAC-SHA256 over the raw request body. Link the webhook security page.
## Search results count rounding
**Symptom:** a customer asks why 11 search results cost 4 credits.
**Cause:** search costs 2 credits per 10 results, rounded up per 10 results.
**Workaround:** none needed; explain the rounding.
