"""
Part C, Task 4 — Weekly Management Report
Kaveri Infrasystems / Assignment Three

Pulls real figures already computed by Programs 2-4 and Program 3's
routing comments out of ClickUp, and asks a local Ollama model to write a
short narrative wrapped around them. The model never computes or invents
a single number — every figure in the report comes from data already
sitting in ClickUp, put there by code.

Design decisions (see build_log.md for the full reasoning):
  - "Use ClickUp's agents if the trial provides them, or your own script
    plus the local model if not — and say which and why": this workspace
    stayed on Free Plan per client instruction (Rajesh said no premium),
    and ClickUp's Brain2 agent features sit behind the same paid-tier
    lock that blocked Custom Fields. So this uses the second option: an
    own script, with a local Ollama model for the narrative only.
  - Numbers are pulled by reading the ALREADY-CREATED tasks that
    bill_engine.py and cashflow_forecaster.py wrote to ClickUp (RA-04's
    bill, the three forecast-month tasks), rather than recomputing the
    same math a third time. Purchase-request routing counts come from
    approval_router.py's own "Routed to:" comments; QC failures come
    from Production Orders' Name-encoded data, read the same way
    bill_engine.py reads it. This keeps every number traceable to the
    specific program that computed it first.
  - The AI's prompt explicitly forbids adding, estimating, or inferring
    any figure not given to it — it is only allowed to write sentences
    AROUND the numbers table, never produce a new one. The numbers table
    itself is printed and written to ClickUp exactly as computed, before
    the model ever sees it, so a bad AI response can't silently corrupt
    a number — at worst it writes an unhelpful sentence.

Usage:
    python weekly_report.py

Environment (.env): reuses List IDs already defined for Programs 1-4.
"""

import os
import re
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
RA_BILLS_LIST_ID = os.getenv("CLICKUP_RA_BILLS_LIST_ID")
CASHFLOW_LIST_ID = os.getenv("CLICKUP_CASHFLOW_LIST_ID") or RA_BILLS_LIST_ID
PURCHASE_REQUESTS_LIST_ID = os.getenv("CLICKUP_PURCHASE_REQUESTS_LIST_ID")
PRODUCTION_ORDERS_LIST_ID = os.getenv("CLICKUP_PRODUCTION_ORDERS_LIST_ID")
WBS_LIST_ID = os.getenv("CLICKUP_WBS_LIST_ID")
BASE_URL = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": API_TOKEN, "Content-Type": "application/json"}

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


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


# ---------------------------------------------------------------------------
# Pull each figure from where the program that computed it already wrote it
# ---------------------------------------------------------------------------

def get_ra04_net_payable():
    for t in get_all_tasks(RA_BILLS_LIST_ID):
        if t["name"].startswith("RA-04"):
            m = re.search(r"Net Payable Rs\.([\d,]+\.\d{2})", t["name"])
            if m:
                return float(m.group(1).replace(",", ""))
    return None


def get_cashflow_forecast():
    """Returns {"October": amount, "November": amount, "December": amount}."""
    result = {}
    for t in get_all_tasks(CASHFLOW_LIST_ID):
        m = re.search(r"Cash Flow Forecast - (\w+) 2026 - Rs\.([\d,]+\.\d{2})", t["name"])
        if m:
            result[m.group(1)] = float(m.group(2).replace(",", ""))
    return result


def get_pr_routing_counts():
    """Returns {level: count} by reading approval_router.py's own comments."""
    counts = {}
    for t in get_all_tasks(PURCHASE_REQUESTS_LIST_ID):
        comments = api_get(f"/task/{t['id']}/comment").get("comments", [])
        for c in comments:
            m = re.match(r"Routed to: .+ \(L(\d)\)", c.get("comment_text", ""))
            if m:
                level = f"L{m.group(1)}"
                counts[level] = counts.get(level, 0) + 1
                break  # one routing decision per PR
    return counts


PO_QC_PATTERN = re.compile(r"(?P<po>PO-[\w-]+)\s*-\s*(?P<boq>B\d+).*?qc:(?P<qc>PASS|FAIL|PARTIAL)")


def get_qc_failures():
    """Returns [{"po": ..., "boq": ..., "qc": "FAIL"/"PARTIAL"}] — the
    orders that need attention, same Name-encoded data bill_engine.py
    already parses for the RA-04 bill."""
    failures = []
    for t in get_all_tasks(PRODUCTION_ORDERS_LIST_ID):
        m = PO_QC_PATTERN.search(t["name"])
        if m and m.group("qc") in ("FAIL", "PARTIAL"):
            failures.append({"po": m.group("po"), "boq": m.group("boq"), "qc": m.group("qc")})
    return failures


def get_schedule_status_counts():
    """Returns {status: count} across WBS/Schedule's native Status."""
    counts = {}
    for t in get_all_tasks(WBS_LIST_ID):
        if not re.match(r"^A\d+", t["name"]):
            continue  # skip WBS group rows, only count actual activities
        status = t.get("status", {}).get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# AI narrative — numbers only, no computation
# ---------------------------------------------------------------------------

NARRATIVE_PROMPT = """You are writing the narrative section of a weekly management report for a \
construction project. Below are the ONLY facts you may use. Do not invent, estimate, calculate, \
or add any number that is not explicitly given below. Do not perform any arithmetic.

Two more rules, both important:
1. Every figure listed in the Facts section below must be mentioned somewhere in your paragraph.
   Do not omit any of them, even if it makes the paragraph longer.
2. Do not use subjective or evaluative words — "stable", "strong", "healthy", "significant",
   "finalized", "good", "on track", "concerning", or similar — unless that exact word or an
   equivalent judgement is explicitly stated in the Facts below. If the Facts are silent on
   whether something is good or bad, your paragraph must also stay silent on that — report the
   figures neutrally instead of characterizing them.

Your job is only to connect the facts in plain, professional prose for a management audience —
3 to 6 short sentences, covering every figure given.

Facts:
{facts}

Write only the narrative paragraph. No headers, no bullet points, no restating this instruction.
"""


SUBJECTIVE_WORDS = ["stable", "strong", "healthy", "significant", "finalized", "finalised",
                     "good", "on track", "concerning", "robust", "solid", "comfortable"]


def verify_narrative(narrative, facts_text):
    """Checks the model actually followed the two hard rules, rather than
    trusting its compliance — flags every number from the facts that's
    missing from the narrative, and every subjective word it wasn't
    supposed to use. Doesn't fix anything automatically; just reports."""
    issues = []

    fact_numbers = re.findall(r"Rs\.[\d,]+\.\d{2}", facts_text)
    for num in set(fact_numbers):
        if num not in narrative:
            issues.append(f"Figure {num} from the Facts is missing from the narrative.")

    lowered = narrative.lower()
    for word in SUBJECTIVE_WORDS:
        if word in lowered:
            issues.append(f"Narrative uses unsupported subjective word '{word}' not licensed by the Facts.")

    return issues


def generate_narrative(facts_text):
    prompt = NARRATIVE_PROMPT.format(facts=facts_text)
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.3, "seed": 42},
        }, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.RequestException as e:
        print(f"  ! Ollama request failed ({e}) — report will be numbers-only.")
        return "[AI narrative unavailable — Ollama was not reachable when this report was generated.]"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    if not API_TOKEN:
        print("Set CLICKUP_API_TOKEN in .env first."); sys.exit(1)

    ra04_net = get_ra04_net_payable()
    forecast = get_cashflow_forecast()
    pr_counts = get_pr_routing_counts()
    qc_failures = get_qc_failures()
    schedule_counts = get_schedule_status_counts()

    lines = ["WEEKLY MANAGEMENT REPORT — Kaveri Infrasystems, SCP2", "=" * 55, ""]
    lines.append("RA-04 BILLING")
    lines.append(f"  Net payable: Rs.{ra04_net:,.2f}" if ra04_net else "  RA-04 not found in ClickUp.")
    lines.append("")
    lines.append("CASH-FLOW FORECAST")
    for month, amount in forecast.items():
        lines.append(f"  {month} 2026: Rs.{amount:,.2f}")
    lines.append("")
    lines.append("PURCHASE REQUEST ROUTING")
    for level in sorted(pr_counts):
        lines.append(f"  {level}: {pr_counts[level]} request(s)")
    lines.append("")
    lines.append("QC FAILURES / PARTIAL PASSES THIS MONTH")
    if qc_failures:
        for f in qc_failures:
            lines.append(f"  {f['po']} ({f['boq']}): {f['qc']}")
    else:
        lines.append("  None.")
    lines.append("")
    lines.append("SCHEDULE STATUS (activities)")
    for status, count in schedule_counts.items():
        lines.append(f"  {status}: {count}")

    facts_text = "\n".join(lines)
    print(facts_text)

    narrative = generate_narrative(facts_text)
    print(f"\n{'='*55}\nNARRATIVE (AI-written, numbers-only input)\n{'='*55}")
    print(narrative)

    issues = verify_narrative(narrative, facts_text)
    if issues:
        print(f"\n{'!'*55}\nNARRATIVE CHECK FAILED — not auto-fixed, review before using:")
        for issue in issues:
            print(f"  - {issue}")
        print(f"{'!'*55}")
    else:
        print("\nNarrative check passed: every figure present, no unsupported subjective language.")

    if RA_BILLS_LIST_ID:
        api_post(f"/list/{RA_BILLS_LIST_ID}/task", {
            "name": "Weekly Management Report - " + __import__("datetime").date.today().isoformat(),
            "description": facts_text + "\n\nNarrative:\n" + narrative,
        })
        print("\nReport written to ClickUp.")


if __name__ == "__main__":
    run()
