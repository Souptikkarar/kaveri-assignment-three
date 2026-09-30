## Day 1 — 21.9.26

**What I did:**
- Read contract_and_policy_terms.md, mapped each section to the program/BOQ item it governs
- Went through every file in the data pack against those rules
- Set up repo scaffolding (.gitignore, .env, requirements.txt), created ClickUp workspace
- [add anything else you actually did]

**Data-pack issues found:**
1. EX-908 logs 4200m in one day, 5.25× over the 800m/day crew cap (§5.4)
2. EX-917 references WBS code A3050, which doesn't exist in the schedule (§5.5)
3. B04 execution log mixes m and km units — need conversion before summing (§5.2)
4. B05: cumulative billed + this period's certified qty (3300 + 950 = 4250) exceeds the 4000m contract cap by 250m — excess goes to a variation claim, not the bill (§2.3)
5. PO-T-09 dispatched 300m but FAILED QC — 0 billable despite being dispatched (§2.1)
6. PO-P-05: 2 of 12 poles failed QC — only 10 billable (§2.1)
7. PO-T-09 steel issued is 11.8% over standard — flagged (§7.2)
8. PR-103 at ₹50,001 is over L1's limit by ₹1 — routes to L2, not L1 (§6.1)
9. PR-104 falls during L2's leave (22–26 Sep) — routes to L3 (§6.2)
10. PR-105 and PR-106 share requester/vendor/date — aggregate ₹90,000 routes both to L3 (§6.3)
11. PR-108's date is the last day of L2's leave (inclusive) — also routes to L3 despite being under L2's limit (§6.2)

**Blocked on / questions:**
- nothing blocked 

**Tomorrow:**
workspace skeleton creation (Spaces/Folders/Lists, empty), custom fields define

## Day 2 22.9.26
**What i did**
- Build the whole skeleton including the lists in workspace 
- add all the necessary custom fields for the list 

**blocked on**
- nothing blocking 

**tomorrow**
- Populate master data + BOQ + approval matrix

## Day 3 23.9.26
**What i did**
- populated the master data,boq,approval etc

**blocked on**
- found out you need 2-4 code for full boq 
- found out you cannot link 2 relationship

**tommorrow**
- dashboard creation with automation

## day 4 24.9.26
**What i did**
- created the dashboard and worked on some automation 

**Blocked on**
- ClickUp's free plan does not include Chart or Calculation dashboard widgets (Unlimited plan+ required). Substituted Table view widgets showing the same underlying figures.

**Tommorrow**
- building the Schedule importer code 

## day 5 25.9.26


**What I did:**
- Built and tested Program 1 (schedule_importer.py) — parsed SCP2_schedule.xer,
  created 22 tasks (10 WBS groups + 12 activities) in ClickUp, verified every
  duration/date/percent-complete value against the source XER by hand
- Confirmed dependencies render correctly on the Gantt view, including P6 lag
  preserved via task comments (ClickUp has no native FS/SS/lag field)
- Discovered ClickUp's Free Plan hard-blocks Custom Fields entirely on this
  workspace — not just the 60-use quota (which was hit first), but a full
  plan-tier lock ("Custom Fields isn't available on your current plan")
- Confirmed with Rajesh: staying on Free Plan, no upgrade
- Redesigned the data model around this: everywhere a field was still needed
  after the lock, moved it to a native ClickUp property (Status, Assignee,
  Due Date, Description) or, where no native equivalent existed and the API
  still needs structured data, encoded it into the task Name using a fixed
  convention (e.g. "EX-901 - A3010 - B04 - 420m") parsed by code instead of
  read via a custom field
- Built and tested Program 2 (bill_engine.py) — computes RA-04 per §2/§3 of
  the terms, verified the full arithmetic by hand against the data pack
  before running it against ClickUp

**Data/logic issues found today:**
1. ClickUp Free Plan: Custom Fields blocked entirely, not just quota-limited
   — required redesigning the field strategy for every list populated after
   this point (§ referenced in README.md and schedule_importer.py header)
2. Advance recovery cap: RA-04's flat 10%-of-gross recovery (₹3,88,350) would
   exceed the outstanding advance balance (₹3,24,650) — recovery must be
   capped at the balance, per §3.1. This wasn't in my original list of data
   issues; found it while hand-verifying the bill arithmetic before coding it.
3. [carry forward the 12 data-pack issues from Day 1, if not already logged
   separately — EX-908 crew-cap overshoot, EX-917's nonexistent A3050 code,
   B05's 250m contract-cap breach, PO-T-09's failed QC, PO-P-05's partial QC,
   PO-T-09's 11.8% steel variance, PR-103/104/105/106/108 routing, unit
   mixing on B04's log entries]

**RA-04 computed result:**
Gross ₹38,83,500 | GST ₹6,99,030 | Retention ₹1,94,175 | Advance recovery
₹3,24,650 (capped) | Net payable ₹40,63,705

**Blocked on / questions:**
- nothing

**Tomorrow:**
- [Day 6 plan — populate remaining ClickUp data, run bill_engine.py live,
  generate the RA-04 PDF]

## Day 6 — 26.9.26

**What I did:**
- Populated Measurement & Certification (3 rows: B04, B05, B06) and Production
  Orders (5 rows: PO-T-07/08/09, PO-P-04/05) using the Name-encoding
  convention, since Custom Fields remain locked on this workspace
- Built and tested Program 2 (bill_engine.py) — reads BOQ via still-readable
  custom fields, reads Measurement & Certification and Production Orders via
  regex-parsed task Names, computes RA-04 per §2/§3
- Ran it live against ClickUp: caught a real data-entry bug of my own
  (B07's Rate custom field showed Rs.14,500 instead of the correct
  Rs.4,50,000 — likely a Day 3 copy-paste slip from B06)
- Since Custom Fields can't be edited to fix it, built a transparent
  override mechanism: a CORRECTED_RATE tag in the task's Description
  (a native, freely-editable field), parsed and applied by the script with
  a printed warning — never a silent fix
- Re-ran after the correction; verified every output value against my own
  hand-calculated arithmetic from before any code was written

**Result — RA-04 (work month September 2026):**
- Gross value: Rs.38,83,500
- GST (18%): Rs.6,99,030
- Retention (5%): Rs.1,94,175
- Advance recovery: Rs.3,24,650 (capped — 10% of gross would have been
  Rs.3,88,350, which exceeds the outstanding advance balance; §3.1 caps
  recovery at whatever remains)
- **Net payable: Rs.40,63,705**
- Exclusions applied and logged by the code (not by me manually removing
  anything): PO-T-09's 300m QC-failed and excluded entirely from B02;
  PO-P-05's 2 QC-failed poles excluded from B03; B04's 0.3km disputed
  quantity carried forward, not billed; B05's certified 950m capped at
  700m billable because the remaining 250m would exceed the 4000m
  contract quantity — excess flagged as a variation claim
- RA-04 task created in ClickUp's RA Bills list (Name + Description, no
  custom fields needed for output)

**Issues found today:**
1. B07 Rate custom field entered incorrectly during Day 3 master-data
   population (Rs.14,500 instead of Rs.4,50,000) — caught only because
   the bill engine's contract-value calculation for advance recovery
   depends on every BOQ item's rate being correct, even items not billed
   this period
2. Confirms the CustomField lock is permanent for this workspace, not a
   temporary quota that resets — worked around via Description-based
   override tags rather than waiting for it to change

**Blocked on / questions:**
- nothing

**Tomorrow:**
- Program 3 (approval router) — logic already dry-run tested against all
  9 purchase requests and confirmed correct before touching the live API
  
## Day 7 — 27.9.26

**What I did:**
- Populated Purchase Requests (9 rows) using Name-encoding, since Custom
  Fields remain locked on this workspace — no workaround needed here since
  the program's actual required outputs (assign approver, write comment)
  map onto ClickUp's native Assignee and Comment features, neither of
  which is a custom field
- Built and dry-run tested Program 3 (approval_router.py) against all 9
  PRs before touching the live API — confirmed §6.1-6.3 logic correct by
  hand (value-based routing, leave rerouting, same-day/vendor/requester
  aggregation) before running anything against ClickUp
- Chose polling over webhooks — no public endpoint on this machine, and PR
  approval routing has no sub-second latency requirement
- First live run gave 2 wrong results out of 9 (PR-104, PR-108 — both
  stayed at L2 instead of rerouting to L3 for Neha Kulkarni's leave). No
  error was thrown; the script ran clean and still gave wrong answers,
  which only surfaced by comparing live output against the hand-verified
  expected table, not from any crash
- Root cause: custom field name lookup was case-sensitive
  ("Leave To" in code vs. "Leave to" as actually typed in ClickUp) — a
  silent mismatch that returned None instead of erroring, so the leave
  check always evaluated false
- Fixed with a case-insensitive field-name match; applied the same
  defensive fix to bill_engine.py proactively, since it used the same
  fragile exact-match pattern (it happened to work there by luck, not by
  correctness)
- Deleted the 9 stale "Routed to:" comments from the buggy run, re-ran —
  all 9 PRs now match the hand-verified routing exactly, including both
  leave-reroute cases

**Issues found today:**
1. Custom field name matching is case-sensitive by default in the ClickUp
   API — a mismatch fails silently (returns None) rather than erroring,
   which is a dangerous failure mode since nothing visibly breaks
2. A brief DNS/connectivity failure (getaddrinfo error) interrupted one
   run — unrelated to the code, resolved by confirming network access and
   retrying
3. Native Assignee can only be set for approvers who exist as real
   ClickUp workspace members — this single-developer demo workspace only
   has one real member, so all 9 PRs were "commented only," not assigned.
   A production deployment would need all 4 approvers invited as members.

**Confirmed correct routing (all 9):**
PR-101, 102 -> L1 | PR-103, 109 -> L2 | PR-104 (leave reroute), 105, 106
(aggregation), 108 (leave reroute) -> L3 | PR-107 -> L4

**Blocked on / questions:**
- nothing
**Tomorrow:**
- Program 4 (cash-flow forecaster)

## Day 8 — 28.9.26

**What I did:**
- Built and ran Program 4 (cashflow_forecaster.py) against live ClickUp data
- Refactored bill_engine.py to expose a shared compute_bill() function, so
  the forecaster reuses the exact RA-04 formula instead of a second copy
  that could drift out of sync
- Read schedule finish dates from WBS/Schedule's native Due Date, which
  needs no custom field and so wasn't affected by the plan lock
- Applied the §4.1 timing literally: submitted on the 5th of the next
  month, paid 30 days after submission
- Wrote one forecast task per month back into ClickUp [in the RA Bills
  list / in a new Cash Flow Forecast list - say which]

**Findings:**
1. RA-03 is submitted but not yet paid (bill_register.csv has a blank
   paid_on), so its payment is still due around 5 Oct 2026. October's
   forecast is entirely that payment. A forecaster that treated RA-01 to
   RA-03 as settled would have shown Rs.0 for October.
2. The advance is fully recovered exactly at RA-04 (outstanding balance
   after RA-04 = 0), so the December forecast carries no advance deduction.
3. B05's contract quantity is exhausted after RA-04, so it contributes
   nothing further.
4. B07's commissioning milestone finishes in November, so its payment
   lands in January 2027, outside the Oct-Dec window. It is excluded and
   reported as excluded, not silently dropped.
5. Retention is not counted as an inflow, since §4.2 releases it 12
   months after commissioning.

**Result (INR):**
October 24,57,065 | November 40,63,705 | December 17,18,730
Total Oct-Dec: 82,39,500

**Problem hit:** the first run failed with "module bill_engine has no
attribute compute_bill". My local bill_engine.py was the old version,
from before the refactor. I replaced it and re-ran. The live output
matched my offline dry run to the rupee.

**Blocked on / questions:**
- nothing

**Tomorrow:**
- Part C: local Ollama extraction against my hand labels

## Day 9 — 29.9.26

**What I did:**
- Hand-labeled all 26 execution-log remarks myself (category + delay hours),
  before writing any extraction code, so the AI's accuracy would be measured
  against an independent human judgment — deliberately holding to "not
  stated" rather than converting vague phrases like "pura din"/"aadha din"
  into invented hour counts, per the assignment's explicit instruction
- Built ollama_extraction.py — reads each Execution Record's Description via
  the ClickUp API, runs it through a local Ollama model, compares output to
  hand_labels.csv field-by-field, and writes the result back onto each
  record as a native comment (no custom field needed — locked on this plan)
- Ran the extraction with qwen2.5:3b: 76.9% category accuracy (20/26),
  65.4% delay-hours accuracy (17/26)
- Ran it again with llama3.1:8b: 80.8% category (21/26), 57.7% hours
  (15/26) — bigger model, better categories, worse hours; not the result
  I expected
- Re-ran llama3.1:8b a second time with identical input and got different
  hour outputs on 5 of 26 records (EX-926, EX-905, EX-906, EX-922, EX-920),
  despite matching totals — the model was sampling non-deterministically,
  so the first reported percentage wasn't reproducible
- Fixed by setting temperature=0 and a fixed seed in the Ollama request,
  and added a REPLACE_EXISTING option so a re-run can safely delete and
  replace this script's own prior comments (matched by an exact model-name
  prefix) without touching a different model's comments or a human's

**Findings:**
1. Initial non-deterministic runs showed both models occasionally inventing 
24 hours for vague "pura din"/"aadha din" phrases despite explicit instructions
 not to. After fixing sampling to be deterministic (temperature=0, seed=42)
  and re-running, llama3.1:8b correctly returned "not stated" on every such 
  case (100% hours accuracy), showing the earlier failures were an artifact
   of random sampling, not the model's judgment. This changes the finding: 
   reproducibility matters as much as raw accuracy when evaluating an AI 
   component for a system of record — a model that behaves correctly only 
   sometimes needs deterministic settings to be trustworthy at all.
   
2. Model output was non-deterministic by default — the same model, same
   input, same prompt gave different answers on different runs. Any
   reported accuracy figure needed temperature=0 to be a fixed, reportable
   number rather than one sample among several possible outcomes
3. [carry forward once confirmed: whether the fixed-seed re-run still
   shows the EX-921/905 "pura din -> 24h" failure, which would upgrade it
   from "happened in one run" to "the model reliably does this"]

**Blocked on / questions:**
- nothing

**Tomorrow:**
- ClickUp Brain2 comparison (Task 2), 6 verification questions (Task 3),
  weekly report (Task 4)

## Day 10 — 30.9.26

**What I did:**
- Tested ClickUp Brain2 availability — unlike Custom Fields, it works on
  the Free plan (uses a "Max" model, not locked behind the same paywall)
- Ran the head-to-head classification: fed Brain2 the same 26 execution-log
  remarks used for the local-model comparison, scored against
  hand_labels.csv — 100% on both category and delay-hours (26/26), correctly
  handling both "pura din" and "aadha din" cases without guessing
- Ran the 6 verification questions (Task 3): 5/6 correct. The one wrong
  answer (B04's total logged quantity) revealed a real gap — my Execution
  Records task Names don't include the BOQ code, so Brain2 had no reliable
  way to attribute records to B04 and silently summed the wrong BOQ item's
  five records instead (950m from B05, not B04's actual 8,980m)
- Wrote the §8.1 data-rule verdict: Brain2 scored higher than either local
  model, but sends workspace data to ClickUp's own infrastructure with no
  way to verify processing/retention — ruled out for real contract data
  regardless of accuracy; only local Ollama models are usable under §8.1
- Built and tested weekly_report.py (Task 4) — pulls every figure from
  tasks Programs 2-4 already wrote to ClickUp (RA-04 net payable, Oct/Nov/
  Dec forecast, PR routing counts from Program 3's own comments, QC
  failures from Production Orders, schedule status counts), and has a
  local model write only the connecting narrative
- First run: numbers were all correct, but the AI narrative added
  unsupported characterizations ("stable," "significant amount of funds")
  the data didn't support, and silently dropped October's figure while
  reporting the other two
- Fixed by tightening the prompt (explicit ban on unsupported subjective
  words unless licensed by the facts; every given figure must appear) and
  adding an automated post-generation check that verifies both rules
  itself rather than trusting the model's compliance
- Re-ran: narrative check passed — every figure present, no unsupported
  language

**Findings:**
1. Brain2 is available on Free Plan (unlike Custom Fields) but its 100%
   accuracy isn't directly comparable to the local models' scores, since
   it likely runs on a materially larger model ("Max") — the win reflects
   scale as much as platform
2. Brain2's one wrong answer (B04 quantity) traced to a real gap in my own
   data design (BOQ code missing from Execution Record task Names), not a
   Brain2 limitation — worth fixing the naming convention if time allows
3. An AI can follow a numeric-accuracy constraint perfectly while still
   producing a misleading report through tone and omission — constraining
   "don't invent numbers" isn't sufficient on its own; the output still
   needed an automated compliance check, not just a better prompt

**Part C — final status: complete.**
Task 1 (local extraction): done, deterministic, two models compared
Task 2 (Brain2 comparison): done, 100% accuracy, data-rule verdict written
Task 3 (6 questions): done, 5/6 correct
Task 4 (weekly report): done, one real AI failure found, fixed, verified

**Blocked on / questions:**
- nothing 

**Tomorrow:**
- Part D — the 13 feasibility verdicts (F1-F13)