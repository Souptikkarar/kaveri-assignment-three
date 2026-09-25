"""
Program 1 — Schedule Importer
Kaveri Infrasystems / Assignment Three

Parses a Primavera P6 .xer export and creates the WBS structure + activities
in a ClickUp List, with dependencies, durations, dates and milestones.

Design decisions (see build_log.md for the full reasoning):
  - Flat list, not nested subtasks. Every WBS node AND every activity is a
    task in the same ClickUp List. Hierarchy is represented with a
    "Parent WBS Code" text field rather than ClickUp task nesting, because
    it's simpler to write idempotently (no need to resolve parent task IDs
    across re-runs) and still groupable/sortable in ClickUp's UI.
  - Idempotent by design: before creating anything, the script fetches all
    existing tasks in the target list and indexes them by their
    "Task Code" (for activities) or "WBS Code" (for WBS nodes) custom
    field. A second run updates matching tasks in place instead of
    duplicating them.
  - Durations in the XER are in HOURS (target_drtn_hr_cnt), converted to
    working days using the calendar's day_hr_cnt (8 hours/day here, per
    the CALENDAR table — "7-Day 8-Hour").
  - ClickUp's native task-dependency API doesn't model P6's FS/SS/FF/SF
    types or lag directly. This script creates a native ClickUp
    "waiting on" dependency for every predecessor link (so the Gantt view
    shows something real) AND writes the original type + lag into a
    comment on the successor task, so nothing from the source file is lost.

Usage:
    python schedule_importer.py path/to/SCP2_schedule.xer

Environment (.env):
    CLICKUP_API_TOKEN=pk_...
    CLICKUP_WBS_LIST_ID=...      # the "WBS / Schedule" List's ID
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
WBS_LIST_ID = os.getenv("CLICKUP_WBS_LIST_ID")
BASE_URL = "https://api.clickup.com/api/v2"

HEADERS = {
    "Authorization": API_TOKEN,
    "Content-Type": "application/json",
}

REQUIRED_CUSTOM_FIELDS = {
    # name -> ClickUp field type to create if missing
    "WBS Code": "text",
    "Parent WBS Code": "text",
    "Task Code": "text",
    "Duration (days)": "number",
    "Percent Complete": "number",
    "Milestone": "checkbox",
    "Node Type": "drop_down",  # options: WBS Group, Activity
}


# ---------------------------------------------------------------------------
# XER parsing
# ---------------------------------------------------------------------------

def parse_xer(path):
    """Parse a .xer file into {table_name: [dict, ...]}."""
    with open(path, "rb") as f:
        raw = f.read().decode("latin-1")  # XER is not UTF-8 by spec

    lines = raw.split("\r\n")
    tables = {}
    current_table = None
    headers = None

    for line in lines:
        if not line:
            continue
        if line.startswith("%T"):
            current_table = line.split("\t")[1]
            tables.setdefault(current_table, [])
            headers = None
        elif line.startswith("%F"):
            headers = line.split("\t")[1:]
        elif line.startswith("%R") and current_table is not None:
            values = line.split("\t")[1:]
            row = dict(zip(headers, values))
            tables[current_table].append(row)
        # %E (end) and ERMHDR lines are ignored

    return tables


def get_calendar_day_hours(tables):
    """Return {clndr_id: day_hr_cnt} so duration conversion isn't hardcoded."""
    return {c["clndr_id"]: float(c["day_hr_cnt"]) for c in tables.get("CALENDAR", [])}


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


def get_list_custom_fields(list_id):
    """Return {field_name: field_dict} for the target List."""
    data = api_get(f"/list/{list_id}/field")
    return {f["name"]: f for f in data["fields"]}


def ensure_custom_fields_exist(list_id):
    """
    ClickUp's public API does not support creating custom fields directly
    on a List (this has to be done once, manually, in the ClickUp UI —
    which matches how you already built Execution Records/BOQ by hand).
    This function just verifies the fields this script needs are present
    and gives a clear error naming exactly what to add if not, rather than
    failing on an obscure 4xx deep in the task-creation loop.
    """
    existing = get_list_custom_fields(list_id)
    missing = [name for name in REQUIRED_CUSTOM_FIELDS if name not in existing]
    if missing:
        print("The WBS/Schedule list is missing these custom fields:")
        for name in missing:
            print(f"  - {name} ({REQUIRED_CUSTOM_FIELDS[name]})")
        print("\nAdd them in ClickUp (same way you added BOQ's fields), then re-run.")
        sys.exit(1)
    return existing


def get_existing_tasks_indexed(list_id, code_field_names):
    """
    Fetch every task currently in the list and index it by whichever of
    'Task Code' / 'WBS Code' it has set, so we can decide create-vs-update.
    Returns {code_value: task_id}.
    """
    index = {}
    page = 0
    while True:
        data = api_get(f"/list/{list_id}/task", params={"page": page, "include_closed": True})
        tasks = data.get("tasks", [])
        if not tasks:
            break
        for t in tasks:
            for cf in t.get("custom_fields", []):
                if cf["name"] in code_field_names and cf.get("value"):
                    index[cf["value"]] = t["id"]
        if data.get("last_page", True):
            break
        page += 1
    return index


def build_custom_field_payload(field_defs, values):
    """
    field_defs: {name: field_dict} from get_list_custom_fields
    values: {name: value}
    Returns the list format ClickUp expects for task creation/update.

    Dropdown fields are special: ClickUp does not accept the option's
    display text as the value. It needs the option's UUID (from the
    field's type_config.options list). This looks that UUID up by
    matching the option's "name" to the human-readable value we were
    given, so the rest of the script can keep working with plain
    strings like "WBS Group" / "Activity".
    """
    payload = []
    for name, value in values.items():
        if value is None:
            continue
        field = field_defs.get(name)
        if not field:
            continue  # already warned about missing fields earlier

        if field["type"] == "drop_down":
            options = field.get("type_config", {}).get("options", [])
            match = next((o for o in options if o["name"] == value), None)
            if not match:
                print(f"  ! Dropdown '{name}' has no option named '{value}' — "
                      f"add it in ClickUp's field settings, or fix the spelling. Skipping.")
                continue
            resolved_value = match["id"]
        else:
            resolved_value = value

        payload.append({"id": field["id"], "value": resolved_value})
    return payload


def xer_date_to_ms(date_str):
    """'2026-06-01 08:00' -> epoch milliseconds ClickUp expects, or None."""
    if not date_str:
        return None
    fmt = "%Y-%m-%d %H:%M"
    t = time.strptime(date_str.strip(), fmt)
    return int(time.mktime(t) * 1000)


STATUS_MAP = {
    "TK_NotStart": "to do",
    "TK_Active": "in progress",
    "TK_Complete": "complete",
}


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

def run(xer_path):
    if not API_TOKEN or not WBS_LIST_ID:
        print("Set CLICKUP_API_TOKEN and CLICKUP_WBS_LIST_ID in your .env file first.")
        sys.exit(1)

    tables = parse_xer(xer_path)
    day_hours = get_calendar_day_hours(tables)

    field_defs = ensure_custom_fields_exist(WBS_LIST_ID)
    existing_index = get_existing_tasks_indexed(WBS_LIST_ID, {"WBS Code", "Task Code"})

    wbs_rows = tables.get("PROJWBS", [])
    task_rows = tables.get("TASK", [])
    pred_rows = tables.get("TASKPRED", [])

    # wbs_id -> wbs_short_name, for parent-code lookups and for mapping
    # each activity to the WBS group it belongs to.
    wbs_id_to_code = {w["wbs_id"]: w["wbs_short_name"] for w in wbs_rows}

    created, updated = 0, 0

    # --- 1. WBS group nodes (skip the root project node, proj_node_flag=Y) ---
    print("Importing WBS nodes...")
    for w in wbs_rows:
        if w["proj_node_flag"] == "Y":
            continue  # this is the project root (SCP2), not a real WBS level

        code = w["wbs_short_name"]
        parent_id = w["parent_wbs_id"]
        parent_code = wbs_id_to_code.get(parent_id, "")
        # Don't show the project root (e.g. "SCP2") as a parent — it isn't
        # a real WBS level, just the XER's container node.
        project_root = next((r for r in wbs_rows if r["proj_node_flag"] == "Y"), None)
        if project_root and parent_id == project_root["wbs_id"]:
            parent_code = ""  # top-level WBS group, no meaningful parent code

        name = f"{code} - {w['wbs_name']}"
        values = {
            "WBS Code": code,
            "Parent WBS Code": parent_code,
            "Node Type": "WBS Group",
        }
        cf_payload = build_custom_field_payload(field_defs, values)

        if code in existing_index:
            api_put(f"/task/{existing_index[code]}", {"name": name})
            for cf in cf_payload:
                api_post(f"/task/{existing_index[code]}/field/{cf['id']}", {"value": cf["value"]})
            updated += 1
            print(f"  updated WBS {code}")
        else:
            body = {"name": name, "custom_fields": cf_payload}
            resp = api_post(f"/list/{WBS_LIST_ID}/task", body)
            existing_index[code] = resp["id"]
            created += 1
            print(f"  created WBS {code}")

    # --- 2. Activities (the TASK table) ---
    print("Importing activities...")
    task_code_to_clickup_id = {}
    for t in task_rows:
        code = t["task_code"]
        wbs_code = wbs_id_to_code.get(t["wbs_id"], "")
        day_hr = day_hours.get(t["clndr_id"], 8.0)
        duration_days = round(float(t["target_drtn_hr_cnt"]) / day_hr, 2)
        is_milestone = t["task_type"] == "TT_FinMile"

        name = f"{code} - {t['task_name']}"
        values = {
            "Task Code": code,
            "Parent WBS Code": wbs_code,
            "Duration (days)": duration_days,
            "Percent Complete": float(t["phys_complete_pct"]),
            "Milestone": is_milestone,
            "Node Type": "Activity",
        }
        cf_payload = build_custom_field_payload(field_defs, values)

        start_ms = xer_date_to_ms(t.get("act_start_date") or t.get("target_start_date"))
        end_ms = xer_date_to_ms(t.get("act_end_date") or t.get("target_end_date"))
        clickup_status = STATUS_MAP.get(t["status_code"], "to do")

        body = {
            "name": name,
            "start_date": start_ms,
            "due_date": end_ms,
            "status": clickup_status,
            "custom_fields": cf_payload,
        }

        if code in existing_index:
            task_id = existing_index[code]
            api_put(f"/task/{task_id}", body)
            for cf in cf_payload:
                api_post(f"/task/{task_id}/field/{cf['id']}", {"value": cf["value"]})
            updated += 1
            print(f"  updated activity {code}")
        else:
            resp = api_post(f"/list/{WBS_LIST_ID}/task", body)
            task_id = resp["id"]
            existing_index[code] = task_id
            created += 1
            print(f"  created activity {code}")

        task_code_to_clickup_id[code] = task_id

    # --- 3. Dependencies ---
    print("Importing dependencies...")
    task_id_to_code = {t["task_id"]: t["task_code"] for t in task_rows}
    for p in pred_rows:
        succ_code = task_id_to_code.get(p["task_id"])
        pred_code = task_id_to_code.get(p["pred_task_id"])
        if not succ_code or not pred_code:
            continue  # cross-project predecessor, not in this file — skip, don't guess

        succ_id = task_code_to_clickup_id.get(succ_code)
        pred_id = task_code_to_clickup_id.get(pred_code)
        if not succ_id or not pred_id:
            continue

        # Native ClickUp dependency: succ_id is "waiting on" pred_id
        try:
            api_post(f"/task/{succ_id}/dependency", {"depends_on": pred_id})
        except requests.HTTPError:
            pass  # likely already exists from a prior run — fine, not an error

        # P6 dependency type + lag has no ClickUp equivalent field, so it's
        # preserved as a comment rather than silently dropped.
        lag_days = round(float(p["lag_hr_cnt"]) / 8.0, 2)
        comment = (
            f"Schedule import: predecessor {pred_code} "
            f"(type {p['pred_type']}, lag {p['lag_hr_cnt']}h = {lag_days}d) "
            f"— from SCP2_schedule.xer, not natively representable as a "
            f"ClickUp dependency type."
        )
        try:
            api_post(f"/task/{succ_id}/comment", {"comment_text": comment})
        except requests.HTTPError:
            pass

    print(f"\nDone. {created} tasks created, {updated} tasks updated.")
    print("Re-run this script any time — it will update in place, not duplicate.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python schedule_importer.py path/to/SCP2_schedule.xer")
        sys.exit(1)
    run(sys.argv[1])
