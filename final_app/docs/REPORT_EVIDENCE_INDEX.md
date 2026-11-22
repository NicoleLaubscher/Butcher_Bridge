# Report and demonstration evidence index

| Evidence ID | Material | Supports | Evidence scope |
|---|---|---|---|
| E01 | [Schema](../sql/schema.sql) · [Seed](../sql/seed.sql) · [ERD and index notes](diagrams/README.md) | B1, Part C architecture | Nine InnoDB tables on disposable MySQL. Seed is fictional. |
| E02 | [System architecture](diagrams/architecture.svg) · [Decision workflow](diagrams/decision_workflow.svg) | B1, B3, Part C concept and journey | Diagrams of current implementation, with editable sources. |
| E03 | [API documentation](API_DOCUMENTATION.md) · [API regression tests](../tests/test_api_contracts.py) | B2, B7, Part C technology | Eleven explicit API methods and routes. Negative cases and pagination checked with mocked SQL. |
| E04 | [Three verified workflows](END_TO_END_WORKFLOWS.md) · [Reproducer](../scripts/verify_mysql_workflows.py) | B3, Part C user journey | Real browser, Flask and disposable MySQL. Re-run with `--screenshots` for simulated captures. |
| E05 | [Deployment, backup and restore procedures](DEPLOYMENT_GUIDE.md) · [Environment template](../.env.example) | B4, Part C implementation and risk | Fresh environment and disposable setup verified. Managed deployment and its recovery drill require operator evidence. |
| E06 | [Impact table and chart](IMPACT_AND_KPIS.md) · [Offline demo](../demo_comparison.py) | B5, Part C sustainability | Same-input simulated comparison and measured test KPI recalculation. Client gains require primary evidence. |
| E07 | [Primary data collection protocol](PRIMARY_DATA_COLLECTION.md) | B5, evidence method | Collection plan and consent requirements. Complete with actual consented data if available. |
| E08 | [Team and Git audit](TEAM_CONTRIBUTIONS_AUDIT.md) | B6, Part C reflections | Historical changes and linked GitHub author metadata. Confirm final responsibilities and reflections. |
| E09 | [Rubric evidence matrix](RUBRIC_COMPLIANCE_MATRIX.md) · [Test commands](DEPLOYMENT_GUIDE.md#5-verify-after-installation) | B1–B7 | Traceable implementation, checks and residual rubric gaps. No grade prediction. |
| E10 | [Part C page plan](PART_C_REPORT_BLUEPRINT.md) · [Demo walkthrough](DEMO_WALKTHROUGH.md) | Report assembly and demonstration | Draft evidence map. Team assembles final PDF, records the walkthrough and confirms current instructions. |

Attach the actual approved proposal, field evidence, hosting evidence, PDF and similarity report only when available. If any is missing, state the resulting scope limit at the relevant claim. Capture dates, versions, Git SHAs and simulated/test labels with the material used in the submission.
