# Facility Maintenance Operations Agent
## Screenshots

![Tests passing](screenshots/01-tests-passing.png)
![Dashboard](screenshots/02-dashboard.png)
![Approval](screenshots/03-approval.png)
![Escalation](screenshots/04-escalation.png)

An AI agent that turns free-text maintenance requests ("AC not working in Block C, Room 204") into dispatched work orders, then keeps them on track.

- **Intake agent** (Claude with tool calling, or a rule-based fallback) classifies the request, finds the asset, checks for repeats, creates the work order and assigns the right technician.
- **Approval gate:** critical, safety-related or high-cost work is held for a supervisor. The agent cannot approve anything.
- **SLA monitor** (deterministic, no AI) escalates overdue work in two levels and logs every notification.
- **Dashboard:** open, overdue, escalated and pending work, problem assets, repeat issues and a daily summary.
- **Audit trail:** every action records who did what and when.

Built with Python, Flask, SQLAlchemy (SQLite by default, MySQL supported) and the Anthropic API.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest              # 20 tests, no API key needed
python demo.py                # full story in the terminal
python run.py                 # dashboard at http://localhost:5000
```

## Using Claude as the agent
```bash
export ANTHROPIC_API_KEY=sk-ant-...          # Windows PowerShell: $env:ANTHROPIC_API_KEY="..."
export ANTHROPIC_MODEL=claude-sonnet-5-5     # optional, this is the default
python run.py
```
- With a key set, Claude runs the five tools in a loop (`app/agent.py`, `LLMAgent`).
- Without a key, or if the API call fails, the rule-based agent takes over, so a request is never lost.
- Force a mode with `FACILITY_AGENT=rule` or `FACILITY_AGENT=llm`.

The Claude path is covered by tests using a scripted fake client. It has not been run against the live API in this repo, so run `python demo.py` with your key and check the traces before demoing it.

## Switching to MySQL
```bash
pip install PyMySQL
export DATABASE_URL="mysql+pymysql://user:password@localhost/facility"
python run.py
```
Tables are created on first start.

## How it works
```
request text --> Agent --> lookup_asset -> check_duplicates -> create_work_order -> find_technician -> assign_technician
                                          (all tools go through services.py, which enforces the rules)
                           |
            approval rule? --> Pending Approval --> supervisor approve/reject --> Assigned
                           |
SLA monitor (every N minutes or on demand) --> level 1 supervisor, level 2 manager + priority raised
```
Design choice: the model decides *what* the request is; plain code decides *what is allowed*. Every tool validates its inputs, the agent has no tool to approve or close work, and the SLA logic never depends on the model.

## Configure without code (`config.json`)
Categories and keywords, required technician skills, SLA hours per priority, approval rules (priorities, categories, cost limit) and escalation contacts. A different site type (hospital, mall, data centre) is mainly a config, assets and technicians change.

## API
| Method and path | Purpose |
|---|---|
| `POST /api/requests` | `{text, requester?, location?}` returns the work order and the agent's tool trace |
| `GET /api/work-orders?status=&category=&priority=` | List |
| `GET /api/work-orders/{id}` | Detail with audit events |
| `POST /api/work-orders/{id}/decision` | `{approver, decision: approve or reject, note}` |
| `POST /api/work-orders/{id}/status` | `{status: In Progress or Completed}` |
| `POST /api/sla/run` | Run escalation now; `{advance_hours: 3}` simulates time passing |
| `GET /api/dashboard`, `/api/summary/daily` | Reporting |
| `GET /api/notifications`, `/api/assets`, `/api/technicians`, `/api/config` | Reference data |

Set `SLA_CHECK_MINUTES=5` to run the SLA monitor automatically in the background.

## Project layout
```
app/agent.py      Claude agent, rule-based agent, tool schemas
app/services.py   Tools and business rules (approval, assignment, status)
app/sla.py        SLA escalation
app/reports.py    Dashboard numbers and daily summary
app/routes.py     REST API and dashboard page
config.json      All business rules
tests/           20 automated tests (see docs/test_cases.md)
docs/            BRD, FRD with workflow diagram, test cases, interview guide
```

## Known limitations
- Rule-based asset linking is location-only, so it can pick a nearby asset that is not the faulty one (for example a fire extinguisher for a sparking switchboard). Claude sees the candidates and reasons about them.
- Notifications are saved, not sent. Email, SMS or Slack would plug in at `app/sla.py`.
- No login or roles: anyone using the dashboard can approve. Add authentication before real use.
- SLA clocks run 24x7 (no shifts or holidays).
- Cost estimates are category defaults unless the model supplies one.

## Ideas for next steps
Technician mobile view, IoT or sensor-triggered work orders, shift-aware SLAs, spare-parts tracking, a feedback score after completion, and an evaluation set of real requests to measure classification accuracy.
