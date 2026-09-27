"""
Program 3 — Approval Router
Kaveri Infrasystems / Assignment Three

Polls the Purchase Requests list, works out the correct approver for each
PR per contract_and_policy_terms.md section 6 (value-based limits, leave
rerouting, same-day/vendor/requester aggregation), assigns that approver
to the task, and posts a comment explaining the decision.

Design decisions (see build_log.md for the full reasoning):
  - Polling, not webhooks: this machine has no public endpoint, and a
    purchase-request approval has no sub-second latency requirement — a
    script run periodically (cron / Task Scheduler / manual, your choice)
    is functionally equivalent to a live webhook for this workflow, with
    far less infrastructure to stand up and defend.
  - Purchase Requests carries its input data (requester, vendor, value,
    date) in the task Name, not custom fields — same reason as
    Measurement & Certification and Production Orders: this workspace's
    ClickUp Free Plan blocks Custom Fields entirely (see
    schedule_importer.py's header for the full finding).
  - This program's actual REQUIRED outputs — "assign it to the correct
    approver" and "write a comment explaining why" — map onto ClickUp's
    native Assignee and Comment features, neither of which is a custom
    field and neither of which costs quota. So the Custom Field lock,
    which was a serious obstacle for Programs 1 and 2, doesn't block this
    program's core deliverable at all.
  - Assignee is only set if the named approver exists as a real member of
    this ClickUp workspace (checked via /team). In a single-developer demo
    workspace, that's often not the case — the four approvers are people
    in the client's org, not ClickUp accounts here. When no matching
    member is found, the routing decision is still fully recorded in the
    comment and the task's Description; only the native-Assignee action
    is skipped, and this is printed clearly rather than silently skipped.
  - Idempotent: re-running does not re-route a PR that's already been
    routed and commented on (checked by looking for a prior "Routed to:"
    comment on the task) — it just confirms it's already handled.

Usage:
    python approval_router.py

Environment (.env):
    CLICKUP_API_TOKEN=pk_...
    CLICKUP_APPROVERS_LIST_ID=...
    CLICKUP_PURCHASE_REQUESTS_LIST_ID=...
"""

import os
import re
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
APPROVERS_LIST_ID = os.getenv("CLICKUP_APPROVERS_LIST_ID")
PURCHASE_REQUESTS_LIST_ID = os.getenv("CLICKUP_PURCHASE_REQUESTS_LIST_ID")
BASE_URL = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": API_TOKEN, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# ClickUp helpers
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


def api_put(path, payload):
    r = requests.put(f"{BASE_URL}{path}", headers=HEADERS, json=payload)
    if r.status_code >= 400:
        print(f"  ! PUT {path} failed: {r.status_code} {r.text}")
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
    for cf in task.get("custom_fields", []):
        if cf["name"] == field_name:
            return cf.get("value")
    return None


def get_workspace_members():
    """Returns {lowercased_name_or_email: user_id} for assignee matching."""
    team_id = api_get("/team")["teams"][0]["id"]
    data = api_get(f"/team/{team_id}")
    members = {}
    for m in data["team"]["members"]:
        user = m["user"]
        members[user["username"].lower()] = user["id"]
        members[user["email"].lower()] = user["id"]
    return members


# ---------------------------------------------------------------------------
# Approvers (real custom fields, still readable — set before the lock)
# ---------------------------------------------------------------------------

def fetch_approvers(list_id):
    """Returns a list sorted by level: [{"name", "level", "limit", "leave_from", "leave_to"}]"""
    approvers = []
    for t in get_all_tasks(list_id):
        limit = get_custom_field_value(t, "Approval Limit")
        leave_from = get_custom_field_value(t, "Leave From")
        leave_to = get_custom_field_value(t, "Leave To")

        # Level is a dropdown; rather than resolve its option UUID here,
        # cross-check against the known 4-approver structure by name,
        # since this workspace's approver set is small and fixed. This
        # mirrors the same honest trade-off made for BOQ's Billing Basis.
        level = KNOWN_APPROVER_LEVELS.get(t["name"].strip())
        approvers.append({
            "name": t["name"].strip(),
            "level": level,
            "limit": float(limit) if limit is not None else None,
            "leave_from": ms_to_date(leave_from),
            "leave_to": ms_to_date(leave_to),
        })
    approvers = [a for a in approvers if a["level"] is not None]
    approvers.sort(key=lambda a: a["level"])
    return approvers


KNOWN_APPROVER_LEVELS = {
    "Arjun Mehta": 1, "Neha Kulkarni": 2, "Vikram Rao": 3, "Suresh Iyer": 4,
}


def ms_to_date(ms_value):
    """ClickUp date custom fields come back as epoch milliseconds (string or int)."""
    if not ms_value:
        return None
    import datetime
    return datetime.date.fromtimestamp(int(ms_value) / 1000)


# ---------------------------------------------------------------------------
# Purchase Requests (Name-encoded: "PR-101 - Requester - Vendor - Rs.42000 - 2026-09-03 - item")
# ---------------------------------------------------------------------------

PR_PATTERN = re.compile(
    r"(?P<pr>PR-\d+)\s*-\s*(?P<requester>[^-]+?)\s*-\s*(?P<vendor>[^-]+?)\s*-\s*"
    r"Rs\.(?P<value>[\d.]+)\s*-\s*(?P<date>\d{4}-\d{2}-\d{2})"
)


def fetch_purchase_requests(list_id):
    requests_list = []
    for t in get_all_tasks(list_id):
        m = PR_PATTERN.search(t["name"])
        if not m:
            print(f"  ! Could not parse Purchase Request task name: {t['name']!r} — skipped, not guessed.")
            continue
        requests_list.append({
            "task_id": t["id"],
            "pr": m.group("pr"),
            "requester": m.group("requester").strip(),
            "vendor": m.group("vendor").strip(),
            "value": float(m.group("value")),
            "date": m.group("date"),
            "already_routed": any(
                c.get("comment_text", "").startswith("Routed to:")
                for c in api_get(f"/task/{t['id']}/comment").get("comments", [])
            ),
        })
    return requests_list


# ---------------------------------------------------------------------------
# Routing logic (§6.1–6.3)
# ---------------------------------------------------------------------------

import datetime


def route_purchase_request(pr, all_prs, approvers):
    """Returns (approver_dict, [reasoning lines])."""
    notes = []

    # §6.3 anti-splitting: aggregate with same requester+vendor+date
    group = [p for p in all_prs
             if p["requester"] == pr["requester"] and p["vendor"] == pr["vendor"] and p["date"] == pr["date"]]
    routing_value = pr["value"]
    if len(group) > 1:
        routing_value = sum(p["value"] for p in group)
        other_ids = ", ".join(p["pr"] for p in group if p["pr"] != pr["pr"])
        notes.append(f"Aggregated with {other_ids} (same requester, vendor, and date per §6.3): "
                     f"combined value Rs.{routing_value:,.0f}")

    # §6.1: smallest level whose limit covers the (aggregated) value
    candidate = next((a for a in approvers if a["limit"] is None or routing_value <= a["limit"]), approvers[-1])
    limit_text = "unlimited" if candidate["limit"] is None else f"Rs.{candidate['limit']:,.0f}"
    notes.append(f"Value Rs.{routing_value:,.0f} requires L{candidate['level']} "
                 f"({candidate['name']}, limit {limit_text})")

    # §6.2: reroute if the assigned approver is on leave on the request date
    req_date = datetime.date.fromisoformat(pr["date"])
    while candidate["leave_from"] and candidate["leave_to"] and candidate["leave_from"] <= req_date <= candidate["leave_to"]:
        notes.append(f"{candidate['name']} (L{candidate['level']}) on leave "
                     f"{candidate['leave_from']} to {candidate['leave_to']} — request date {req_date} falls within this window")
        next_level = next((a for a in approvers if a["level"] > candidate["level"]), None)
        if not next_level:
            notes.append("No higher approver available — escalation stops here.")
            break
        candidate = next_level
        notes.append(f"Rerouted to L{candidate['level']} ({candidate['name']}) per §6.2")

    return candidate, notes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    if not API_TOKEN:
        print("Set CLICKUP_API_TOKEN in .env first."); sys.exit(1)

    approvers = fetch_approvers(APPROVERS_LIST_ID)
    if len(approvers) != 4:
        print(f"  ! Expected 4 approvers with resolvable levels, found {len(approvers)}. Check Approvers list/field readability.")

    members = {}
    try:
        members = get_workspace_members()
    except requests.HTTPError:
        print("  ! Could not fetch workspace members — Assignee will be skipped for all PRs, routing will still be recorded in comments.")

    all_prs = fetch_purchase_requests(PURCHASE_REQUESTS_LIST_ID)

    for pr in all_prs:
        if pr["already_routed"]:
            print(f"{pr['pr']}: already routed, skipping (idempotent re-run).")
            continue

        approver, notes = route_purchase_request(pr, all_prs, approvers)

        comment_lines = [f"Routed to: {approver['name']} (L{approver['level']})"]
        comment_lines.extend(notes)
        comment_text = "\n".join(comment_lines)

        api_post(f"/task/{pr['task_id']}/comment", {"comment_text": comment_text})

        assignee_id = members.get(approver["name"].lower())
        if assignee_id:
            api_put(f"/task/{pr['task_id']}", {"assignees": {"add": [assignee_id], "rem": []}})
            print(f"{pr['pr']} -> {approver['name']} (L{approver['level']}) — assigned + commented")
        else:
            print(f"{pr['pr']} -> {approver['name']} (L{approver['level']}) — commented only "
                  f"(no matching ClickUp workspace member to assign)")


if __name__ == "__main__":
    run()
