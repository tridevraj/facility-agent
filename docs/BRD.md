# Business Requirements Document: Facility Maintenance Operations Agent

| | |
|---|---|
| Version | 1.0 (draft) |
| Author | [Your name] |
| Status | Draft. Items marked **[FILL FROM INTERVIEWS]** must come from your real stakeholder conversations |

## 1. Background and problem
Maintenance requests in large buildings and campuses arrive through many informal channels (calls, messaging apps, email, walk-ins). Staff read each one, decide the category and urgency, find a suitable technician and chase progress by hand. This causes slow triage, inconsistent prioritisation, missed SLAs, invisible repeat failures and no audit trail.

## 2. Objectives
| ID | Objective | Measure of success |
|---|---|---|
| O1 | Cut the time from request to dispatched work order | Median triage time under 1 minute (baseline: **[FILL FROM INTERVIEWS]**) |
| O2 | Apply priority and SLA rules consistently | 100% of requests carry a category, priority and SLA due time |
| O3 | Keep humans in control of risky or costly work | 100% of critical, safety and high-cost orders held for approval |
| O4 | Make SLA breaches visible before they escalate further | Every breach produces a timed, recorded notification |
| O5 | Expose recurring failures | Repeat issues and problem assets are reported automatically |

## 3. Scope
**In scope:** free-text request intake; classification and prioritisation; asset lookup; duplicate and repeat detection; technician matching and load balancing; approval for risky work; SLA tracking and two-level escalation; audit trail; operations dashboard; daily summary.

**Out of scope (v1):** real email/SMS delivery (notifications are simulated), mobile technician app, spare-parts inventory, vendor management, sensor/IoT triggers, user login and roles.

## 4. Stakeholders
| Stakeholder | Interest | Input gathered |
|---|---|---|
| Requester (staff, student, tenant) | Fast acknowledgement, no re-explaining | **[FILL FROM INTERVIEWS]** |
| Facility supervisor | Fewer calls, control over risky work | **[FILL FROM INTERVIEWS]** |
| Technician | Clear, correctly routed jobs | **[FILL FROM INTERVIEWS]** |
| Facility manager | SLA performance, recurring issues, cost | **[FILL FROM INTERVIEWS]** |

See `docs/interview_guide.md` for questions to ask each group.

## 5. Business requirements
| ID | Requirement | Priority |
|---|---|---|
| BR-01 | Staff can raise a request in plain language without choosing categories or forms | Must |
| BR-02 | Each request becomes a work order with category, priority, location and SLA due time | Must |
| BR-03 | Requests are linked to a known asset where possible | Should |
| BR-04 | Repeat requests for the same place and category are linked and reported | Should |
| BR-05 | A technician with the right skill and the lowest workload is assigned | Must |
| BR-06 | Critical, safety-related or high-cost work waits for supervisor approval before dispatch | Must |
| BR-07 | Orders nearing or past SLA trigger notifications to the right person, once per level | Must |
| BR-08 | Every action (agent, human, system) is recorded with who, what and when | Must |
| BR-09 | Managers see open, overdue, escalated and pending work, plus problem assets and repeat issues | Must |
| BR-10 | Categories, priorities, SLAs, approval rules and escalation contacts are configurable without code changes | Must |
| BR-11 | If the AI service is unavailable, requests are still processed | Must |

## 6. Assumptions and constraints
- An asset register and technician roster exist and are maintained.
- Working hours and shifts are not modelled in v1: SLA clocks run continuously.
- The AI agent can only act through defined tools and cannot approve work.
- Costs are rough estimates used only to trigger approval.

## 7. Risks
| Risk | Mitigation |
|---|---|
| AI misclassifies a request | Reasoning stored on each order; tools validate every value; rule-based fallback; supervisor can see and correct |
| Safety issue treated as routine | Safety category and critical keywords always route to approval and a safety officer |
| Notification fatigue | One notification per escalation level per order |
| Poor asset data | Asset link is optional; unlinked orders still work |

## 8. Success criteria for go-live
All Must requirements pass the test cases in `docs/test_cases.md`, and a pilot at **[pilot site]** processes **[X]** real requests with triage accuracy of **[X]%**, reviewed by a supervisor.
