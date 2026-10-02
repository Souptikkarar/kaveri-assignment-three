# Kaveri Infrasystems — Assignment Three

A ClickUp implementation and seven Python programs for Kaveri Infrasystems' project-to-cash workflow: schedule import, RA billing, purchase approval routing, cash-flow forecasting, and an AI-assisted delay extraction and weekly report — all built and tested against the real SCP2 contract data pack.

See `build_log.md` for the full day-by-day record of decisions, bugs found and fixed, and data-pack issues caught. See `part-d-feasibility-verdicts.md` for the F1–F13 feasibility verdicts.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env              # then fill in every value below
```

You'll also need [Ollama](https://ollama.com) running locally with at least one model pulled, for the two AI-section scripts:

```bash
ollama pull llama3.1:8b
```

### `.env` reference

```
CLICKUP_API_TOKEN=pk_...
CLICKUP_WORKSPACE_ID=...

CLICKUP_WBS_LIST_ID=...
CLICKUP_BOQ_LIST_ID=...
CLICKUP_MEASUREMENT_LIST_ID=...
CLICKUP_PRODUCTION_ORDERS_LIST_ID=...
CLICKUP_EXECUTION_RECORDS_LIST_ID=...
CLICKUP_APPROVERS_LIST_ID=...
CLICKUP_PURCHASE_REQUESTS_LIST_ID=...
CLICKUP_RA_BILLS_LIST_ID=...
CLICKUP_CASHFLOW_LIST_ID=...       # optional — falls back to RA_BILLS_LIST_ID if unset

OLLAMA_MODEL=llama3.1:8b           # optional — this is the default
WRITE_BACK=true                    # ollama_extraction.py: set false to score without writing to ClickUp
REPLACE_EXISTING=false             # ollama_extraction.py: set true to overwrite this script's own prior comments
```

Get a List ID from ClickUp by opening the list → "..." menu → Copy link → the number after `/li/` (or `/l/` in some URL formats) in the copied link.

## Programs

| # | File | What it does |
|---|---|---|
| 1 | `schedule_importer.py` | Parses `SCP2_schedule.xer` (Primavera P6 export) and creates the WBS + activities in ClickUp, idempotently, with dependencies and lag preserved. |
| 2 | `bill_engine.py` | Computes and creates the RA-04 bill from live ClickUp data per §2/§3 of the contract terms. Also runs an F7 certification-compliance audit on every call (report-only — see script header). |
| 3 | `approval_router.py` | Routes purchase requests to the correct approver per §6 (value limits, leave rerouting, same-day/vendor/requester aggregation), assigning and commenting on each. |
| 4 | `cashflow_forecaster.py` | Forecasts Oct–Dec 2026 cash inflow — outstanding prior-bill payments, the current bill, and remaining BOQ quantity priced per §4.3. Imports `bill_engine.py` directly so the two never disagree. |
| 5 | `ollama_extraction.py` | Runs each Execution Record's remark through a local Ollama model to extract a delay category and hours, scores it against `hand_labels.csv`, and writes the result back as a ClickUp comment. |
| 6 | `weekly_report.py` | Pulls every figure already written to ClickUp by Programs 2–4 and has a local Ollama model write only the narrative — with an automated check that the narrative didn't drop a figure or add unsupported claims. |
| 7 | `generate_bill_pdf.py` | Produces the client-facing `RA-04_Bill.pdf`, by calling `bill_engine.py`'s `compute_bill()` directly rather than recomputing the numbers separately. |

Each is runnable standalone, e.g.:

```bash
python schedule_importer.py SCP2_schedule.xer
python bill_engine.py
python approval_router.py
python cashflow_forecaster.py
python ollama_extraction.py
python weekly_report.py
python generate_bill_pdf.py
```

Programs 1 and 3 are idempotent (safe to re-run; they update existing tasks rather than duplicating them). Programs 2, 4, 6, and 7 currently create a new task on every run rather than checking for an existing one first — a known limitation, noted in `build_log.md`, not fixed in this submission.

## ClickUp Free Plan constraint — Custom Fields

This workspace stays on ClickUp's **Free plan** throughout, per explicit client instruction (no premium). Two things were discovered about what that means in practice, in this order:

1. **A 60-use lifetime quota** on setting Custom Field values, workspace-wide, non-recoverable even after clearing a value (confirmed via ClickUp's own help docs). Hit during Program 1's first live run.
2. **A full plan-tier lock** on Custom Fields, confirmed via an in-app upgrade modal ("Custom Fields isn't available on your current plan") — not just the quota running out, but the feature itself gated behind the paid Core plan.

Everything built **before** the lock took effect (BOQ's Rate/Contract Qty/Billing Basis, Approvers' Level/Limit/Leave dates, WBS/Schedule's Task Code/Duration/etc.) uses real Custom Fields, and remains **readable** by the API even though no new fields can be set. Everything built **after** the lock avoids Custom Fields entirely:

- **Relationship fields never counted against the quota and were never plan-locked either** — but once Custom Fields were blocked wholesale, Relationships (a Custom Field type internally) went with them.
- **Native ClickUp properties are unaffected** — Name, Status (including custom per-list status stages), Assignee, Due Date, Description, and native file Attachments all remained fully usable.
- Where structured, parseable data was still needed and no native field fit, it's encoded directly into the task **Name** using a fixed convention and parsed with regex by whichever script reads it — e.g. `EX-901 - A3010 - B04 - 420m` (log ID, WBS activity, BOQ item, quantity+unit), or `PO-T-07 - B02 - planned:900m - produced:900m - steel:4450kg - std:4.8 - qc:PASS - qcfail:0 - dispatch:900m@2026-09-06`.
- A known-bad Custom Field value that can no longer be corrected in-field (BOQ's B07 Rate, entered incorrectly on Day 3) is overridden via a `CORRECTED_RATE:450000` tag in the task's Description — a native, freely-editable field — read and applied by `bill_engine.py` with a printed warning on every run. Never a silent fix.

This is documented as a feasibility finding across several of Part D's verdicts (notably F1, F2, F8, F13) — several things that would be a clean **NATIVE** answer on a Custom-Field-enabled plan became **CUSTOM BUILD** specifically because of this constraint, as tested.

## Known gaps (see `build_log.md` and Part D for full detail)

- **F4** (automatic finance notification on billable work/milestone completion) was designed around ClickUp's native Automate feature but never built or tested.
- **F7** (certification block) is implemented as a report-only audit in `bill_engine.py`, not a hard gate — see that file's header for why.
- MS Project schedule import (the other half of F9) was never attempted; no sample file was available to test against.
- Programs 2, 4, 6, and 7 are not idempotent (see above).
