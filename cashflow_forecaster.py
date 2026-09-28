"""
Program 4 — Cash-Flow Forecaster
Kaveri Infrasystems / Assignment Three

Forecasts monthly cash inflow for October, November and December 2026 and
writes the result into ClickUp where the finance head will see it.

Design decisions (see build_log.md for the full reasoning):
  - Imports bill_engine.py directly and reuses its compute_bill() function
    rather than re-implementing the GST/retention/advance-recovery formula
    here. This guarantees the forecast is always internally consistent
    with the actual RA-04 bill — a forecast that quietly used a slightly
    different formula from the real bill engine would be worse than
    useless, since the two numbers would silently disagree.
  - Three genuinely different kinds of inflow feed the forecast, not just
    "remaining quantity x rate":
      1. RA-03's payment is still OUTSTANDING (bill_register.csv shows it
         submitted but not yet paid) — a real near-term inflow that
         belongs in this forecast, not a historical figure to ignore.
      2. RA-04's own payment (just computed by bill_engine.py).
      3. §4.3's forecast rule: each BOQ item's remaining contract quantity
         is assumed certified in full, with no disputes/QC issues, in the
         month its linked WBS activity is scheduled to finish (read from
         WBS/Schedule's native Due Date — no Custom Field lock issue here,
         Due Date is a built-in property).
    Missing any of these three would understate the forecast.
  - §4.1: a bill for work month M is submitted on the 5th of M+1, and paid
    30 days after submission. This is applied literally (not "next month")
    to each of the three inflow sources above to place it in the correct
    forecast month — including the possibility a payment lands OUTSIDE
    the Oct-Dec window entirely (B07's commissioning milestone finishes in
    November, so its bill would only be paid in January 2027 — correctly
    excluded from this forecast, and reported as excluded, not silently
    dropped).
  - §4.2: retention is released 12 months after commissioning, outside
    this forecast window, so retention is never added back as an inflow
    here.
  - Written back to ClickUp via Name + Description on a task per forecast
    month, since Custom Fields remain locked on this workspace (see
    schedule_importer.py's header for the full finding).

Usage:
    python cashflow_forecaster.py

Environment (.env): all the List IDs already used by schedule_importer.py
and bill_engine.py, plus:
    CLICKUP_CASHFLOW_LIST_ID=...   (or reuse CLICKUP_RA_BILLS_LIST_ID)
"""

import os
import re
import sys
import calendar
import datetime
import requests
import importlib.util
from dotenv import load_dotenv

load_dotenv()

# Import bill_engine.py as a module so its compute_bill() (and constants)
# are reused rather than re-implemented — see header note above.
_be_spec = importlib.util.spec_from_file_location(
    "bill_engine", os.path.join(os.path.dirname(__file__), "bill_engine.py"))
bill_engine = importlib.util.module_from_spec(_be_spec)
_be_spec.loader.exec_module(bill_engine)

API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
WBS_LIST_ID = os.getenv("CLICKUP_WBS_LIST_ID")
BOQ_LIST_ID = os.getenv("CLICKUP_BOQ_LIST_ID")
MEASUREMENT_LIST_ID = os.getenv("CLICKUP_MEASUREMENT_LIST_ID")
PRODUCTION_ORDERS_LIST_ID = os.getenv("CLICKUP_PRODUCTION_ORDERS_LIST_ID")
CASHFLOW_LIST_ID = os.getenv("CLICKUP_CASHFLOW_LIST_ID") or os.getenv("CLICKUP_RA_BILLS_LIST_ID")
BASE_URL = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": API_TOKEN, "Content-Type": "application/json"}

FORECAST_MONTHS = ["2026-10", "2026-11", "2026-12"]

# BOQ item -> the WBS activity whose finish date governs when its
# remaining quantity is assumed certified, per §4.3. B04 links to two
# activities in the source schedule (A3000, A3010); A3010 governs since
# that's the activity still open (A3000 already complete).
BOQ_TO_GOVERNING_ACTIVITY = {
    "B02": "A2020", "B03": "A2030", "B04": "A3010", "B05": "A3020",
    "B06": "A3030", "B07": "A4010",
}


def api_get(path, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()


def api_post(path, payload):
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=payload)
    if r.status_code >= 400:
        print(f"  ! POST {path} failed: {r.status_code} {r.text}")
    r.raise_for_status()
    return r.json()


def get_all_tasks(list_id):
    tasks = []
    page = 0
    while True:
        data = api_get(f"/list/{list_id}/task", params={"page": page, "include_closed": True})
        batch = data.get("tasks", [])
        if not batch:
            break
        tasks.extend(batch)
        if data.get("last_page", True):
            break
        page += 1
    return tasks


def fetch_wbs_finish_dates(list_id):
    """Returns {task_code: date} from WBS/Schedule's native Due Date —
    no custom field needed, Due Date is a built-in ClickUp property."""
    finish_dates = {}
    for t in get_all_tasks(list_id):
        m = re.match(r"^(A\d+)", t["name"])
        if not m or not t.get("due_date"):
            continue
        finish_dates[m.group(1)] = datetime.date.fromtimestamp(int(t["due_date"]) / 1000)
    return finish_dates


def payment_month(work_month_date):
    """§4.1: submitted 5th of month+1, paid 30 days after submission.
    Returns the (year, month) the payment actually lands in."""
    year, month = work_month_date.year, work_month_date.month
    submit_month = month + 1
    submit_year = year
    if submit_month > 12:
        submit_month = 1
        submit_year += 1
    submission_date = datetime.date(submit_year, submit_month, 5)
    payment_date = submission_date + datetime.timedelta(days=30)
    return payment_date.year, payment_date.month


def month_key(year, month):
    return f"{year:04d}-{month:02d}"


def run():
    if not API_TOKEN:
        print("Set CLICKUP_API_TOKEN in .env first."); sys.exit(1)

    forecast = {m: {"total": 0.0, "items": []} for m in FORECAST_MONTHS}

    def add_inflow(work_month_date, amount, description):
        year, month = payment_month(work_month_date)
        key = month_key(year, month)
        if key not in forecast:
            print(f"  ! {description}: payment falls in {key}, outside the Oct-Dec 2026 forecast "
                  f"window — correctly excluded, not counted.")
            return
        forecast[key]["total"] += amount
        forecast[key]["items"].append(f"{description}: Rs.{amount:,.2f}")

    # --- Source 1: RA-03's still-outstanding payment ---
    prior_bills = bill_engine.load_bill_register()
    pending_prior_bill = None
    for b in prior_bills:
        if b["status"] == "SUBMITTED" and not b.get("paid_on"):
            bills_before_this_one = prior_bills[:prior_bills.index(b)]
            gross = float(b["gross_value_inr"])
            gst = round(gross * bill_engine.GST_RATE, 2)
            retention = round(gross * bill_engine.RETENTION_RATE, 2)
            work_month_date = datetime.date.fromisoformat(b["work_month"] + "-01")
            pending_prior_bill = {"bill_no": b["bill_no"], "gross": gross, "gst": gst,
                                   "retention": retention, "bills_before": bills_before_this_one,
                                   "work_month_date": work_month_date}

    # --- Live ClickUp data, shared with bill_engine's own logic ---
    boq = bill_engine.fetch_boq(BOQ_LIST_ID)
    mc_data = bill_engine.fetch_measurement_certification(MEASUREMENT_LIST_ID)
    production_orders = bill_engine.fetch_production_orders(PRODUCTION_ORDERS_LIST_ID)
    cumulative_before_ra04 = bill_engine.load_cumulative_billed()

    # Now resolve RA-03's net payable properly (needs contract_value_total)
    contract_value_total = sum(
        (boq[c]["contract_qty"] * boq[c]["rate"]) for c in boq
        if boq[c].get("contract_qty") is not None and boq[c].get("rate") is not None
    )
    total_advance = contract_value_total * bill_engine.ADVANCE_RATE_OF_CONTRACT
    if pending_prior_bill:
        fe = pending_prior_bill
        recovered_before = sum(float(pb["gross_value_inr"]) * bill_engine.ADVANCE_RECOVERY_RATE_OF_GROSS
                                for pb in fe["bills_before"])
        outstanding_before = max(total_advance - recovered_before, 0.0)
        proposed = round(fe["gross"] * bill_engine.ADVANCE_RECOVERY_RATE_OF_GROSS, 2)
        recovery = min(proposed, outstanding_before)
        net = round(fe["gross"] + fe["gst"] - fe["retention"] - recovery, 2)
        add_inflow(fe["work_month_date"], net, f"{fe['bill_no']} outstanding payment (submitted, not yet paid)")

    # --- Source 2: RA-04's own payment ---
    ra04_result = bill_engine.compute_bill(boq, mc_data, production_orders, cumulative_before_ra04, prior_bills)
    ra04_work_month_date = datetime.date.fromisoformat(bill_engine.WORK_MONTH + "-01")
    add_inflow(ra04_work_month_date, ra04_result["net_payable"], "RA-04 payment")

    # --- Source 3: remaining BOQ quantity, per §4.3, priced at the
    #     activity's finish month, with GST/retention applied and
    #     advance recovery correctly at 0 since RA-04 fully recovers it ---
    finish_dates = fetch_wbs_finish_dates(WBS_LIST_ID)
    cumulative_after_ra04 = dict(cumulative_before_ra04)
    for li in ra04_result["line_items"]:
        cumulative_after_ra04[li["boq_item"]] = cumulative_after_ra04.get(li["boq_item"], 0.0) + li["billable_qty"]

    for code, activity in BOQ_TO_GOVERNING_ACTIVITY.items():
        entry = boq.get(code)
        finish_date = finish_dates.get(activity)
        if not entry or not finish_date:
            print(f"  ! {code}: missing BOQ data or {activity} finish date — skipped, not guessed.")
            continue
        contract_qty = entry["contract_qty"]
        remaining = contract_qty - cumulative_after_ra04.get(code, 0.0)
        if remaining <= 0:
            continue  # contract fully billed already — e.g. B05, capped exactly at RA-04
        remaining_value = remaining * entry["rate"]
        gst = remaining_value * bill_engine.GST_RATE
        retention = remaining_value * bill_engine.RETENTION_RATE
        # Advance is fully recovered by RA-04 (outstanding_advance_after ==
        # 0, confirmed by bill_engine.compute_bill) so no further advance
        # deduction applies to this forecast money.
        net = round(remaining_value + gst - retention, 2)
        add_inflow(finish_date, net, f"{code} remaining qty ({remaining} units, certified per §4.3 forecast rule)")

    # --- Print + write to ClickUp ---
    print(f"\n{'='*60}\nCash-Flow Forecast — Oct/Nov/Dec 2026\n{'='*60}")
    grand_total = 0.0
    for m in FORECAST_MONTHS:
        month_name = calendar.month_name[int(m.split('-')[1])]
        print(f"\n{month_name} 2026: Rs.{forecast[m]['total']:,.2f}")
        for item in forecast[m]["items"]:
            print(f"    - {item}")
        grand_total += forecast[m]["total"]
    print(f"\nTotal Oct-Dec 2026 inflow: Rs.{grand_total:,.2f}")

    if CASHFLOW_LIST_ID:
        for m in FORECAST_MONTHS:
            month_name = calendar.month_name[int(m.split('-')[1])]
            name = f"Cash Flow Forecast - {month_name} 2026 - Rs.{forecast[m]['total']:,.2f}"
            description = "\n".join(forecast[m]["items"]) or "No inflow forecast for this month."
            api_post(f"/list/{CASHFLOW_LIST_ID}/task", {"name": name, "description": description})
        print("\nForecast tasks created in ClickUp.")


if __name__ == "__main__":
    run()
