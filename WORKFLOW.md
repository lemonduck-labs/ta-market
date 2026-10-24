# Workflow

| Stage | Owner | What happens | Gate |
|---|---|---|---|
| 1. Pull | housing-data-engineer | MHCLG detailed local authority tables and revenue outturn | Release noted; hashes logged; parsers pass on the real files |
| 2. Picture | market-analyst | Cost per household, accommodation mix, trends, outliers | Unit tests pass; every figure names its release |
| 3. Plan (phase 2) | move-forward-planner | Move-forward plans on synthetic records into the approval queue | Synthetic data only; assumptions shown |
| 4. Decide | A housing officer | Approve or reject each step, with a reason | Only a person can decide (enforced in fdcore.decisions) |
| 5. Review | fact-checker, guardrails-reviewer | Independent checks on anything to be shared | Both pass |
| 6. Ship | The person | Push, link, demo | /ship checklist passes |

## Phases

| Phase | What |
|---|---|
| 0 | Data spike: households by type and spend by council, joined on the council code |
| 1 | Market picture: cost per household, mix, trends, peer comparison, savings model with user-set inputs |
| 2 | Move forward planner on synthetic records, approval screen, memory core |
| 3 | Evals, guardrails, decision records |
| 4 | Design, wayfinding and walkthrough films |
