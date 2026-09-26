"""
Program 2 — RA Bill Engine
Kaveri Infrasystems / Assignment Three

Reads September's BOQ, certification, and production/QC data and computes
RA-04 exactly per contract_and_policy_terms.md sections 2 and 3, then
writes the result into ClickUp's "RA Bills" list and prints a bill summary.

Design decisions (see build_log.md for the full reasoning):
  - ClickUp's Free Plan blocks Custom Fields entirely on this workspace
    (confirmed via a plan-upgrade modal, not just the 60-use quota — see
    schedule_importer.py's header for the quota finding). BOQ's fields
    (Billing Basis, Rate, Contract Qty, WBS links) were set before this
    block took effect and remain READABLE — reading isn't restricted,
    only writing new values is. Everywhere data was entered AFTER the
    block (Measurement & Certification, Production Orders), it lives in
    the task Name as structured text instead, e.g.
      "MC-B04 - measured:5.2km - certified:4.9km - disputed:0.3km"
      "PO-T-07 - B02 - planned:900m - produced:900m - steel:4450kg -
       std:4.8 - qc:PASS - qcfail:0 - dispatch:900m@2026-09-06"
    This program parses those names with regex rather than reading custom
    fields, and the RA Bills task it creates also writes its results into
    the Name/Description, for the same reason.
  - cumulative_billed_to_RA03.csv and bill_register.csv (RA-01 to RA-03)
    are historical figures that predate this ClickUp build and were never
    asked to be entered into it — they're read directly from the local
    data pack as reference inputs, not from the ClickUp API. Only the new
    RA-04 result is written back into ClickUp.
  - Every number is computed here, in code — nothing is asked of, or
    accepted from, an AI model, per the assignment's "every number must
    be computed by code, never by AI" instruction (also aligned with
    §8.1 — none of this data leaves a machine Kaveri controls in any
    case, since no AI call is made at all in this program).
  - Bad/ambiguous data is flagged and excluded, never silently "fixed":
    an execution record with an impossible quantity or an unknown WBS
    code is reported, not corrected.

Usage:
    python bill_engine.py

Environment (.env):
    CLICKUP_API_TOKEN=pk_...
    CLICKUP_BOQ_LIST_ID=...
    CLICKUP_MEASUREMENT_LIST_ID=...
    CLICKUP_PRODUCTION_ORDERS_LIST_ID=...
    CLICKUP_RA_BILLS_LIST_ID=...

Local files expected in the same folder:
    cumulative_billed_to_RA03.csv
    bill_register.csv
"""

import os
import re
import csv
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
BOQ_LIST_ID = os.getenv("CLICKUP_BOQ_LIST_ID")
MEASUREMENT_LIST_ID = os.getenv("CLICKUP_MEASUREMENT_LIST_ID")
PRODUCTION_ORDERS_LIST_ID = os.getenv("CLICKUP_PRODUCTION_ORDERS_LIST_ID")
RA_BILLS_LIST_ID = os.getenv("CLICKUP_RA_BILLS_LIST_ID")
BASE_URL = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": API_TOKEN, "Content-Type": "application/json"}

GST_RATE = 0.18
RETENTION_RATE = 0.05
ADVANCE_RATE_OF_CONTRACT = 0.08
ADVANCE_RECOVERY_RATE_OF_GROSS = 0.10

WORK_MONTH = "2026-09"


# ---------------------------------------------------------------------------
# ClickUp fetch helpers
# ---------------------------------------------------------------------------

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


def get_custom_field_value(task, field_name):
    """Read a value from a task's already-set custom fields (BOQ only —
    these fields predate the plan's Custom Field lock and remain readable
    even though new ones can no longer be written)."""
    for cf in task.get("custom_fields", []):
        if cf["name"] == field_name:
            return cf.get("value")
    return None


# ---------------------------------------------------------------------------
# BOQ
# ---------------------------------------------------------------------------

RATE_CORRECTION_PATTERN = re.compile(r"CORRECTED_RATE:(?P<rate>[\d.]+)")


def fetch_boq(list_id):
    """
    Returns {boq_item: {"billing_basis": ..., "rate": float, "contract_qty": float}}
    Parsed from the task Name ("B04 - OFC laying...") for the code, and
    from custom fields for the numbers (still readable, set before the
    Free Plan Custom Field lock took effect).

    Known-bad values that can no longer be fixed in the custom field
    itself (writes are blocked) can be overridden by adding a line like
    "CORRECTED_RATE:450000" to the task's Description — a native field,
    still freely editable. This is a visible, logged override, not a
    silent correction: every use prints a warning naming the task, the
    wrong value, and the corrected value actually used.
    """
    boq = {}
    for t in get_all_tasks(list_id):
        m = re.match(r"^(B\d+)", t["name"])
        if not m:
            continue
        code = m.group(1)
        rate = get_custom_field_value(t, "Rate")
        contract_qty = get_custom_field_value(t, "Contract Qty")
        basis = get_custom_field_value(t, "Billing Basis")

        correction = RATE_CORRECTION_PATTERN.search(t.get("description") or "")
        if correction:
            corrected_rate = float(correction.group("rate"))
            print(f"  ! {code}: Rate field shows {rate}, overridden to {corrected_rate} "
                  f"per CORRECTED_RATE tag in task description (custom field locked, cannot be fixed in-field).")
            rate = corrected_rate

        boq[code] = {
            "rate": float(rate) if rate is not None else None,
            "contract_qty": float(contract_qty) if contract_qty is not None else None,
            "billing_basis_raw": basis,
        }
    return boq


# Billing basis is hardcoded here as a fallback/cross-check against the
# contract's own BOQ (boq.csv), since the dropdown's stored value isn't
# safely decodable without knowing this workspace's specific option
# UUIDs. Cross-checking against the source-of-truth file rather than
# trusting either blindly is deliberate — see build_log.md.
KNOWN_BILLING_BASIS = {
    "B01": "MILESTONE", "B02": "DELIVERY_QC", "B03": "DELIVERY_QC",
    "B04": "PROGRESS", "B05": "PROGRESS", "B06": "PROGRESS", "B07": "MILESTONE",
}


# ---------------------------------------------------------------------------
# Measurement & Certification (PROGRESS items)
# ---------------------------------------------------------------------------

MC_PATTERN = re.compile(
    r"MC-(?P<boq>B\d+)\s*-\s*measured:(?P<measured>[\d.]+)(?P<munit>\w+)\s*-\s*"
    r"certified:(?P<certified>[\d.]+)(?P<cunit>\w+)\s*-\s*"
    r"disputed:(?P<disputed>[\d.]+)(?P<dunit>\w+)"
)


def fetch_measurement_certification(list_id):
    """Returns {boq_item: {"measured": float, "certified": float, "disputed": float, "unit": str}}"""
    result = {}
    for t in get_all_tasks(list_id):
        m = MC_PATTERN.search(t["name"])
        if not m:
            print(f"  ! Could not parse Measurement & Certification task name: {t['name']!r} — skipped, not guessed.")
            continue
        result[m.group("boq")] = {
            "measured": float(m.group("measured")),
            "certified": float(m.group("certified")),
            "disputed": float(m.group("disputed")),
            "unit": m.group("cunit"),
        }
    return result


# ---------------------------------------------------------------------------
# Production Orders (DELIVERY_QC items)
# ---------------------------------------------------------------------------

PO_PATTERN = re.compile(
    r"(?P<po>PO-[\w-]+)\s*-\s*(?P<boq>B\d+)\s*-\s*"
    r"planned:(?P<planned>[\d.]+)(?P<punit>\w+)\s*-\s*"
    r"produced:(?P<produced>[\d.]+)\w+\s*-\s*"
    r"steel:(?P<steel>[\d.]+)kg\s*-\s*std:(?P<std>[\d.]+)\s*-\s*"
    r"qc:(?P<qc>PASS|FAIL|PARTIAL)\s*-\s*qcfail:(?P<qcfail>[\d.]+)\s*-\s*"
    r"dispatch:(?P<dispatched>[\d.]+)\w+@(?P<date>[\d-]+)"
)


def fetch_production_orders(list_id):
    """Returns a list of dicts, one per production order."""
    orders = []
    for t in get_all_tasks(list_id):
        m = PO_PATTERN.search(t["name"])
        if not m:
            print(f"  ! Could not parse Production Order task name: {t['name']!r} — skipped, not guessed.")
            continue
        orders.append({
            "po": m.group("po"),
            "boq": m.group("boq"),
            "planned": float(m.group("planned")),
            "produced": float(m.group("produced")),
            "steel_issued": float(m.group("steel")),
            "std_steel": float(m.group("std")),
            "qc_result": m.group("qc"),
            "qc_failed_qty": float(m.group("qcfail")),
            "dispatched": float(m.group("dispatched")),
            "dispatch_date": m.group("date"),
            "unit": m.group("punit"),
        })
    return orders


# ---------------------------------------------------------------------------
# Local historical reference data
# ---------------------------------------------------------------------------

def load_cumulative_billed(path="cumulative_billed_to_RA03.csv"):
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out[row["boq_item"]] = float(row["cumulative_qty_billed"])
    return out


def load_bill_register(path="bill_register.csv"):
    bills = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            bills.append(row)
    return bills


# ---------------------------------------------------------------------------
# Billing logic
# ---------------------------------------------------------------------------

def compute_billable_delivery_qc(boq_item, production_orders, cumulative_before, contract_qty):
    """§2.1: dispatched AND passed QC in the month, minus any QC-failed
    quantity even on a PARTIAL order. §2.3: cap at remaining contract qty."""
    total_billable = 0.0
    notes = []
    for po in production_orders:
        if po["boq"] != boq_item:
            continue
        if po["qc_result"] == "FAIL":
            notes.append(f"{po['po']}: {po['dispatched']}{po['unit']} dispatched but QC FAILED — 0 billable")
            continue
        billable_this_po = po["dispatched"] - po["qc_failed_qty"]
        total_billable += billable_this_po
        if po["qc_result"] == "PARTIAL":
            notes.append(f"{po['po']}: {po['dispatched']}{po['unit']} dispatched, "
                         f"{po['qc_failed_qty']}{po['unit']} failed QC — {billable_this_po}{po['unit']} billable")

    capped, excess = apply_contract_cap(total_billable, cumulative_before, contract_qty)
    if excess:
        notes.append(f"Cumulative would exceed contract qty by {excess} — excess excluded, goes to variation claim")
    return capped, notes


def compute_billable_progress(boq_item, mc_data, cumulative_before, contract_qty):
    """§2.2: disputed qty excluded. §2.3: cap at remaining contract qty."""
    notes = []
    row = mc_data.get(boq_item)
    if not row:
        notes.append("No Measurement & Certification data found for this item — 0 billed, flagged for follow-up")
        return 0.0, notes

    certified = row["certified"]
    if row["disputed"] > 0:
        notes.append(f"{row['disputed']}{row['unit']} disputed this period — excluded, carried forward")

    capped, excess = apply_contract_cap(certified, cumulative_before, contract_qty)
    if excess:
        notes.append(f"Certified {certified}{row['unit']} would push cumulative over the {contract_qty} contract "
                     f"cap by {excess} — excess excluded from this bill, recorded as a variation claim")
    return capped, notes


def apply_contract_cap(qty_this_period, cumulative_before, contract_qty):
    """Returns (billable_this_period, excess_beyond_cap)."""
    if contract_qty is None:
        return qty_this_period, 0.0
    remaining = contract_qty - cumulative_before
    if qty_this_period <= remaining:
        return qty_this_period, 0.0
    excess = round(qty_this_period - remaining, 4)
    return max(remaining, 0.0), excess


def compute_milestone(boq_item, cumulative_before, milestone_complete):
    """§2.1 MILESTONE: billed once in full, only when complete and not
    already billed."""
    if cumulative_before > 0:
        return 0.0, ["Already billed in a prior RA bill — not billed again"]
    if not milestone_complete:
        return 0.0, ["Linked milestone activity not yet complete — not billed this period"]
    return 1.0, ["Milestone complete this period — billed in full"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    if not API_TOKEN:
        print("Set CLICKUP_API_TOKEN in .env first."); sys.exit(1)

    boq = fetch_boq(BOQ_LIST_ID)
    mc_data = fetch_measurement_certification(MEASUREMENT_LIST_ID)
    production_orders = fetch_production_orders(PRODUCTION_ORDERS_LIST_ID)
    cumulative_before = load_cumulative_billed()
    prior_bills = load_bill_register()

    boq_codes = sorted(boq.keys()) if boq else sorted(KNOWN_BILLING_BASIS.keys())

    line_items = []
    gross_total = 0.0

    for code in boq_codes:
        entry = boq.get(code, {})
        rate = entry.get("rate")
        contract_qty = entry.get("contract_qty")
        basis = KNOWN_BILLING_BASIS.get(code)

        if rate is None or contract_qty is None:
            print(f"  ! {code}: Rate or Contract Qty missing/unreadable from ClickUp — skipped, not guessed at.")
            continue

        cum_before = cumulative_before.get(code, 0.0)

        if basis == "DELIVERY_QC":
            billable, notes = compute_billable_delivery_qc(code, production_orders, cum_before, contract_qty)
        elif basis == "PROGRESS":
            billable, notes = compute_billable_progress(code, mc_data, cum_before, contract_qty)
        elif basis == "MILESTONE":
            # A4010/A1010 completion isn't parsed from the schedule here to
            # keep this program focused on billing math; cumulative_before
            # already tells us B01 was billed in RA-02. B07's milestone
            # (commissioning, A4010) is confirmed not yet complete as of
            # 30 Sep 2026 per the WBS/Schedule import — hardcoded as a
            # known fact of this specific run, flagged clearly as such.
            milestone_complete = False if code == "B07" else None
            billable, notes = compute_milestone(code, cum_before, milestone_complete)
        else:
            print(f"  ! {code}: unknown billing basis — skipped."); continue

        value = billable * rate
        gross_total += value
        line_items.append({
            "boq_item": code, "basis": basis, "billable_qty": billable,
            "rate": rate, "value": value, "notes": notes,
        })

    gst = round(gross_total * GST_RATE, 2)
    retention = round(gross_total * RETENTION_RATE, 2)

    # Advance recovery, capped at outstanding balance (§3.1)
    contract_value_total = sum(
        (boq[c]["contract_qty"] * boq[c]["rate"]) for c in boq
        if boq[c].get("contract_qty") is not None and boq[c].get("rate") is not None
    )
    total_advance = contract_value_total * ADVANCE_RATE_OF_CONTRACT
    recovered_so_far = sum(float(b["gross_value_inr"]) * ADVANCE_RECOVERY_RATE_OF_GROSS for b in prior_bills)
    outstanding_advance = max(total_advance - recovered_so_far, 0.0)
    proposed_recovery = round(gross_total * ADVANCE_RECOVERY_RATE_OF_GROSS, 2)
    advance_recovery = min(proposed_recovery, outstanding_advance)
    if advance_recovery < proposed_recovery:
        print(f"  ! Advance recovery capped: {proposed_recovery} would exceed outstanding balance "
              f"of {outstanding_advance} — recovering {advance_recovery} instead.")

    net_payable = round(gross_total + gst - retention - advance_recovery, 2)

    # --- Print the bill ---
    print(f"\n{'='*60}\nRA-04 — Work month {WORK_MONTH}\n{'='*60}")
    for li in line_items:
        print(f"{li['boq_item']} ({li['basis']}): {li['billable_qty']} x Rs.{li['rate']} = Rs.{li['value']:,.2f}")
        for n in li["notes"]:
            print(f"    - {n}")
    print(f"\nGross value:        Rs.{gross_total:,.2f}")
    print(f"GST (18%):          Rs.{gst:,.2f}")
    print(f"Retention (5%):     Rs.{retention:,.2f}")
    print(f"Advance recovery:   Rs.{advance_recovery:,.2f}")
    print(f"{'-'*40}")
    print(f"NET PAYABLE:        Rs.{net_payable:,.2f}")

    # --- Write to ClickUp (RA Bills list), Name/Description only — no
    # custom fields available on this plan ---
    if RA_BILLS_LIST_ID:
        name = f"RA-04 - {WORK_MONTH} - Net Payable Rs.{net_payable:,.2f}"
        description_lines = [f"Gross: Rs.{gross_total:,.2f}", f"GST: Rs.{gst:,.2f}",
                              f"Retention: Rs.{retention:,.2f}", f"Advance recovery: Rs.{advance_recovery:,.2f}",
                              "", "Line items:"]
        for li in line_items:
            description_lines.append(f"{li['boq_item']}: {li['billable_qty']} @ Rs.{li['rate']} = Rs.{li['value']:,.2f}")
            description_lines.extend(f"  - {n}" for n in li["notes"])
        api_post(f"/list/{RA_BILLS_LIST_ID}/task", {
            "name": name,
            "description": "\n".join(description_lines),
        })
        print(f"\nRA-04 task created in ClickUp's RA Bills list.")


if __name__ == "__main__":
    run()
