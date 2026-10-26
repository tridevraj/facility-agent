# Test Cases

All cases are automated in `tests/test_app.py` (run `python -m pytest`). The Claude path is tested with a scripted fake client, so no API key or network is needed.

| ID | Scenario | Expected result | FR |
|---|---|---|---|
| TC-01 | "AC not working in Block C, Room 204" | hvac, medium, Assigned, asset AC-C-204, five tool calls in order | FR-01 |
| TC-02 | Urgency and category wording | no water = high; scratches = low; fire/smoke = critical; unknown text = other | FR-02 |
| TC-03 | Location extraction | "Block C, Room 204"; falls back to the hint, then "Unspecified" | FR-03 |
| TC-04 | Request for Room 999 | AC in Room 204 is not linked | FR-03 |
| TC-05 | Sparking switchboard | critical, Pending Approval, tentative technician; approve moves it to Assigned | FR-07, FR-08 |
| TC-06 | Reject, then approve again | Rejected; second decision returns 400 | FR-08 |
| TC-07 | Cost 9000 vs 100 | Over the limit waits for approval; under the limit does not | FR-07 |
| TC-08 | Assign an electrician to a plumbing order | Refused | FR-05 |
| TC-09 | Same AC problem raised twice | Second order has `repeat_of` set to the first | FR-04 |
| TC-10 | Two electrical jobs | Different electricians chosen | FR-05 |
| TC-11 | All plumbers unavailable | Order created, unassigned, message explains | FR-06 |
| TC-12 | High-priority order checked at 4h, 9h, 9.5h, 13h | Nothing; level 1; nothing (no repeat alert); level 2 with priority raised; two notifications in total | FR-09, FR-10 |
| TC-13 | Completed order, 30 days later | Not escalated | FR-10 |
| TC-14 | `advance_hours` simulation | Medium order escalates after 30h | FR-10 |
| TC-15 | Status jumps | In Progress then Assigned is refused; Completed sets `resolved_at` | FR-11 |
| TC-16 | Audit trail | created, assigned and approve recorded with the right actors | FR-12 |
| TC-17 | Dashboard and daily summary | Counts, problem asset, repeat issue and summary text are correct | FR-13, FR-14 |
| TC-18 | Empty text, over-long text, unknown id | 400, 400, 404 | FR-01 |
| TC-19 | Claude agent with scripted tool calls | Order created, assigned, asset linked, requester kept | FR-02 |
| TC-20 | Invalid category from the model; model call fails | Tool rejects invalid values; rule-based fallback still creates the order | FR-02, FR-16 |

## Manual UAT checklist (run with a supervisor)
- [ ] Submit 10 real past requests; the supervisor marks category and priority correct or not. Record accuracy: **[X]%**
- [ ] Confirm the approval screen is clear to a non-technical user
- [ ] Click "Simulate +12 hours" and confirm notifications go to the right people
- [ ] Check dashboard numbers against a manual count
