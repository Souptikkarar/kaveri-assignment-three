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
