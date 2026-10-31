# Workstream readiness

Snapshot based on the ownership and timeline in [PLAN.md](../PLAN.md). These are assignments, not confirmation that anyone has started or finished. Check with each owner and record actual revision and evidence before relying on status. Do not edit another owner's files; use the existing change-request process when a dependency needs a change.

| Owner | Planned responsibility | Immediate dependency or handoff | Status to verify |
|---|---|---|---|
| A1 | Core, local backends, orchestration, LLM layer | Shared models and protocol signatures for A2–A5 and G1 | User reports A1 underway; interface readiness unverified. |
| A2 | Source reading, provider clients, evidence and retrieval | Shared models; real provider access and request shapes | User reports A2 underway; integration readiness unverified. |
| A3 | Planner, writer and gap controller | A1 LLM/models; A2 evidence; G2 smoke corpus | User reports A3 underway; integration readiness unverified. |
| A4 | Verification, reports and exports | Shared models, writer candidates, evidence and provider clients | User reports A4 underway; integration readiness unverified. |
| A5 | AWS backends, worker and deployment | A1 protocols; AWS account/bootstrap, Docker, deployment configuration | Assigned in plan; activity and cloud prerequisites unverified. |
| G1 | API, auth, uploads and parsers | A1 orchestrator and models; upload and job routes unblock thin path | **Verified 2026-10-31 on `gunbir/integration`:** every CONTRACTS §6 route exists (incl. `/health`, `/uploads/presign`), runs on A1's real local core; resync 501 until G2 `sync.py`. 50 G1 tests pass (`test_api*.py`, `test_sse.py`, `test_parsers.py`); fresh-install container boot answers `/api/ping`. Details: [WORKLOG_GUNBIR.md](../WORKLOG_GUNBIR.md). |
| G2 | Source connectors and real demo corpus | Provider accounts; a real smoke corpus for A3 and integration | **Verified 2026-10-31 on `gunbir/integration`:** Firecrawl crawl/scrape and Composio Notion (read-only, per user) with real calls; `demo/smoke/` (5 pages + 10 seeds), `demo/corpus/` (25 docs pages) and `demo/corpus/notion/` (6 fictional wiki pages). 18 G2 tests pass. Not yet: `sync.py`, Jira / Confluence / Drive (P1). |
| G3 | Account, setup and plan UI | API contracts, auth configuration and G1 routes | Assigned in plan; activity and UI readiness unverified. |
| G4 | Build, inspector and report UI | Shared types, SSE, row and report routes | Assigned in plan; activity and UI readiness unverified. |

## Integration handoffs to confirm

- [ ] A1 publishes the models and local interfaces; A2–A5 and G1 confirm their imports and signatures.
- [ ] G2 provides an approved real smoke corpus; G1 can upload it; A3 can use it for a real writer call.
- [ ] G1 and A1 expose a local job path; G3/G4 connect to real routes and events as they become available.
- [ ] A4 and G4 agree on row checks, evidence, rejection reasons and export shapes.
- [ ] A5 confirms AWS prerequisites, backend handoffs and deployed health; test the full job separately.
- [ ] Owners record blockers and requests in the project's existing coordination channel. This tracker has not contacted anyone or verified external account state.
