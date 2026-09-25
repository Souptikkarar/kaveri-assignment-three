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

## Day 5 — [today's date]

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
- [anything you're still unsure about — e.g. whether the Custom Field lock
  is quota-based-and-permanent or plan-based-and-would-lift on any trial]

**Tomorrow:**
- [Day 6 plan — populate remaining ClickUp data, run bill_engine.py live,
  generate the RA-04 PDF]