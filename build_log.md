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
**what i did**
- Build the whole skeleton including the lists in workspace 
- add all the necessary custom fields for the list 

**blocked on**
- nothing blocking 

**tomorrow**
- Populate master data + BOQ + approval matrix

## Day 3 23.9.26
**what i did**
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