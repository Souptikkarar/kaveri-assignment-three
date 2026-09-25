# Kaveri Infrasystems — Assignment Three

Four Python programs implementing what ClickUp cannot do natively, against the SCP2 contract data pack.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your own ClickUp token + workspace ID
```

## Programs

| Program | File | What it does |
|---|---|---|
| 1. Schedule importer | `schedule_importer.py` | Parses SCP2_schedule.xer into ClickUp WBS/activities |
| 2. RA bill engine | `bill_engine.py` | Computes and creates the RA-04 bill from ClickUp data |
| 3. Approval router | `approval_router.py` | Routes purchase requests per section 6 of the terms |
| 4. Cash-flow forecaster | `cashflow_forecaster.py` | Forecasts Oct–Dec 2026 inflow |

Each is runnable standalone: `python schedule_importer.py`

## Notes

See `build_log.md` for the daily log of decisions and issues found in the data pack.

## ClickUp Free Plan constraint — custom field quota

ClickUp's Free plan hard-caps **custom field value-setting at 60 uses, total, for the whole
workspace, for the lifetime of the workspace** — clearing an existing value does not free up
quota (confirmed via ClickUp's own help docs). This workspace stays on the Free plan per client
instruction, so the system is designed around this limit rather than assuming it will be lifted:

- **Relationship fields never count against the quota**, so the full WBS → Execution Record →
  BOQ traceability chain (§5.1 of the terms) is unaffected regardless of plan.
- **Native ClickUp properties don't count either** — Status (with custom per-list status stages),
  Assignee, Due Date, Description, and native file Attachments are all free. Everywhere the data
  doesn't strictly need a true custom field (a real Number ClickUp can sum/filter on, for
  instance), this build uses a native property instead.
- Real custom fields are reserved for WBS/Schedule (Task Code, Duration, % Complete, Milestone,
  Node Type — no native equivalent exists) and for numeric BOQ/billing fields the bill engine
  needs to read and sum precisely (Rate, Contract Qty).
- This is documented as a CONFIGURATION-level feasibility finding relevant to Part D (F8, F13 in
  particular) — a production deployment at Kaveri's actual scale would need at minimum the
  Unlimited plan.
