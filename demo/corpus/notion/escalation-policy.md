---
source_url: notion://40a41e04-143a-816c-8dd5-d2776cbf4d0b
title: Escalation policy
fetched_at: 2026-10-31T02:52:30+00:00
---

## Tiers
- **Tier 1 (support queue):** answers from the docs and this wiki, account questions, billing explanations. Can issue goodwill credits up to 500 credits per ticket.
- **Tier 2 (support engineers):** reproduces bugs, reads job logs, runs the ownership-verification checklist, issues goodwill credits up to 5,000 credits per ticket.
- **Tier 3 (on-call engineering):** platform incidents, data loss, security issues. Reached only through the on-call page, never by direct message.
## First-response targets by plan

| Plan | First response | Channel |
| --- | --- | --- |
| Free | best effort, community forum | community |
| Hobby | 2 business days | email |
| Standard | 1 business day | email |
| Growth | 8 business hours | email + shared channel |
| Scale | 4 business hours | email + shared channel |
| Enterprise | per contract SLA, usually 1 hour for severity 1 | dedicated channel |

Business hours are 09:00 to 18:00 US Eastern, Monday to Friday.
## Severity
- **Sev 1:** the API is down or returns errors for most requests from many customers, or a customer reports data exposure. Page on-call immediately.
- **Sev 2:** one major feature is broken for many customers (for example webhooks not delivering), or one Enterprise customer is fully blocked. Page on-call during business hours; outside business hours, page only for Enterprise.
- **Sev 3:** a bug with a workaround, or one non-Enterprise customer blocked. Create a Tier 2 ticket.
- **Sev 4:** questions, feature requests, docs fixes. Stay in Tier 1.
## When to escalate from Tier 1
Escalate to Tier 2 when any of these is true:
- You cannot reproduce the customer's answer from the docs or this wiki.
- The customer reports the same failure on more than 3 jobs after following the documented fix.
- The request needs a goodwill credit above 500 credits.
- The customer asks for an account ownership change.
## What to include in an escalation
1. Team id and plan.
2. Job ids (crawl, batch scrape or agent) and timestamps in UTC.
3. What the customer expected and what happened, in one sentence each.
4. What you already tried.
Do not paste API keys into tickets. If a customer pastes a key, tell them to rotate it from the API Keys page and redact it from the ticket.
