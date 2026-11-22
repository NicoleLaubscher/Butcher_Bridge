# Part C consulting handover blueprint

**Project**  ButcherBridge, BFB321 Group 06

**Working release**  `feature/mysql-integration` based on `3a63b97fdc4373d4f0ac0f9273ae360b578ccda8`

**Status**  Technical evidence is available for drafting. The group still needs to assemble, paginate and approve the report, confirm individual reflections and obtain any required primary evidence.

Use a numbered cover and contents page as required by the course and keep the main report at ten pages or fewer. Cover, contents and appendices are excluded from the reproduced ten-page rule. Confirm font, margins, export format, file name, deadlines and source requirements against the current official instructions. This blueprint uses the rubric reproduced in the task and the repo's existing handover notes. The approved initial proposal and official rubric PDFs were not available for comparison in the working repository.

## Ten-page main report

| Section | Page budget | Content to write | Evidence |
|---|---:|---|---|
| 1. Executive Summary | 1 (p. 1) | State the compatible group-buying problem, who uses the application, the cost and feasibility decision it supports, the two simulated gains and the difference between verification and observed client outcomes. Recommend a controlled evidence pilot subject to approval. | [Impact and KPIs](IMPACT_AND_KPIS.md) · [Workflow results](END_TO_END_WORKFLOWS.md) |
| 2. Final Concept and Architecture | 1 (p. 2) | Explain the final workflow and evolution from the earlier demo. Include the compact architecture diagram and refer to the full ERD in the appendix. Add an approved proposal comparison once the team can supply it. | [Architecture](diagrams/architecture.svg) · [ERD](diagrams/database_erd.svg) · [Commit evidence](TEAM_CONTRIBUTIONS_AUDIT.md) |
| 3. Technology Integration | 1 (p. 3) | Trace one Jinja/JavaScript request through Flask, PyMySQL and InnoDB. Show order/tier/hold relationships, REST validation, transactional reservation and the consistent read snapshot. Explain the in-memory split between evaluation and bounded planners. | [API contract](API_DOCUMENTATION.md) · [Model and indexes](diagrams/README.md) |
| 4. User Journey/Workflow | 2 (pp. 4–5) | One labelled UI capture per workflow and a short request/response and SQL evidence caption. Show why a draft is excluded, how capacity prevents two individually eligible windows from booking the same offer, and how fulfilment reaches the KPI tiles. Distinguish a proposal from a recorded reservation. | [Three workflows and capture command](END_TO_END_WORKFLOWS.md) · [Decision workflow](diagrams/decision_workflow.svg) |
| 5. Implementation Guide | 1 (p. 6) | Identify the approved revision, Python and MySQL versions, secrets and install prerequisites. Outline start, sign-in, smoke test, backup/restore and app rollback. Separate verified disposable setup from the target hosting plan and outstanding owner decisions. | [Deployment and recovery](DEPLOYMENT_GUIDE.md) |
| 6. Risks and Mitigations | 1 (p. 7) | Use the risk table below. Include unverified supplier pricing, double-booking risk at confirmation, limited personal authorisation, bad input evidence, connectivity, logistics verification and backup recovery. Identify which safeguards are presently tested. | [Rubric matrix](RUBRIC_COMPLIANCE_MATRIX.md) · [API edge cases](API_DOCUMENTATION.md#authentication-and-errors) |
| 7. Sustainability and Scalability | 2 (pp. 8–9) | Page 8 uses the simulated before/after figure, costs and actual KPI test example. Page 9 explains solver limits, capacity shared across windows and a scoped plan to measure logistics or client impact with consent. Include fairness trade-offs. | [Cost table and figure](IMPACT_AND_KPIS.md) · [Solver bounds](../README.md#retailer-group-optimisation) |
| 8. Team Reflections and Key Learnings | 1 (p. 10) | Each member writes a short, personally verified reflection on a technical choice, difficulty, test or handover lesson and points to real evidence. Identify assistant use and human review as required by the institution. Include contributions with agreed role and GitHub handle. | [Team contribution audit](TEAM_CONTRIBUTIONS_AUDIT.md) |
| 9. Appendices | Excluded | Full ERD and decision flow, expanded API examples, three workflow screenshots, verification logs, input instruments and actual primary results if authorised. Add the contribution evidence and actual similarity report only if obtained. Label all simulated figures. | [Evidence index](REPORT_EVIDENCE_INDEX.md) |

## Evidence-based narrative for the main text

The earlier classroom app demonstrated compatibility, delivered cost and post-order metrics with fictional inputs and form previews. The final application persists orders, offers, capacity holds and recorded outcomes in MySQL. It adds transactional REST writes, read-only recommendations, exact retailer shares and optional group formation with safe limits. The latest verified comparison provides comparable totals from one database snapshot. This is the evolution visible in source history. The team should add a short table of approved proposal commitments and documented changes once it has the original proposal.

For a prospective coordinator, the system helps decide whether orders can share a supplier purchase after capacity, service and cost checks. On a disposable MySQL test, draft-to-commit, supplier/tier creation and fulfilment were demonstrated in Chromium with persisted evidence. This establishes application behavior for the test environment. Hosted service availability, operating capacity and retailer acceptance require separate confirmation.

## Risk table starter

| Risk to the client | Current safeguard | Handover action and owner to confirm |
|---|---|---|
| A proposal is treated as a booking | Advisory decision reads, separate POST with offer lock and unique offer/window key | Coordinator verifies terms and available capacity before booking. Agree cancellation and released-key process. |
| Incorrect or outdated commercial inputs | Validation, dated decisions, evidence labels and exact cost reconciliation | Supplier and retailer contacts confirm quotes, baseline methods and consent. Keep omissions and assumptions visible. |
| Unequal benefits across retailers | Proposed charges capped at individual baselines | Explain fixed-versus-optimised trade-offs and obtain voluntary participation. |
| Search or infrastructure limits | Bounded fallbacks, error logging, database read/write boundaries | Operating owner measures latency, fallback rates and DB resource limits. Test recovery on the intended environment. |
| Sensitive party, price or sign-in data exposed | Local secret file, TLS configuration option, demo session controls | Establish per-user access, CSRF, audit and least privilege before wider use. Redact report and video evidence. |
| Claimed transport or cold-chain gains without measurement | Distance/trips are descriptive, eligibility and KPIs are explicitly scoped | Validate a lane with documented load, route, timing, fuel and refrigeration observations before claiming reductions. |

## Information the team must provide

- Approved initial proposal and any official instructions that settle the detailed marks, report format or required recording duration.
- Each member's confirmed role, contribution or review, and personal reflection. The repository supports some attributions, with additional evidence needed for final-app team allocation.
- Authorised primary input and any independently observed baseline/outcome measurements if a client benefit claim is required. Otherwise keep financial claims simulated and reported.
- Intended host, HTTPS/MySQL access arrangement, backup owner and approved recovery evidence if deployment is a graded deliverable.
- Actual similarity report or explicit confirmation of its absence. Use the real result, settings and date if reporting it.

Keep the full sources, logs, client permissions and appendix figures separate from the main-page budget. Replace draft placeholders before export and verify the final PDF page count directly.
