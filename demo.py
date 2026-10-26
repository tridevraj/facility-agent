"""Run the whole story without starting a server (good for a screen recording):
    python demo.py
Uses an in-memory-style temp database so it never touches facility.db."""
import json
import os
import tempfile

os.environ.setdefault("FACILITY_AGENT", "rule")  # set ANTHROPIC_API_KEY and FACILITY_AGENT=llm to use Claude
from app import create_app  # noqa: E402

REQUESTS = [
    ("AC not working in Block C, Room 204", "Priya (Faculty)"),
    ("Water leaking from the ceiling in Block A room 101", "Imran (Student)"),
    ("Sparking from the switch board in Block B ground floor, burning smell", "Security desk"),
    ("Wifi is down in the Library, exams tomorrow", "Librarian"),
    ("AC is not cooling in Block C Room 204 again", "Priya (Faculty)"),
    ("Corridor floor in Block A is dusty", "Warden"),
]

path = os.path.join(tempfile.mkdtemp(), "demo.db")
app = create_app({"DATABASE_URL": f"sqlite:///{path}"})
c = app.test_client()

for text, who in REQUESTS:
    r = c.post("/api/requests", json={"text": text, "requester": who}).get_json()
    wo = r["work_order"]
    print(f"\n> {text}")
    print(f"  tools: {' -> '.join(t['tool'] for t in r['trace'])}")
    print(f"  WO #{wo['id']} | {wo['category']} | {wo['priority']} | {wo['status']} | tech: {wo['technician']} | asset: {wo['asset_code']} | repeat_of: {wo['repeat_of']}")

pending = [w for w in c.get("/api/work-orders?status=Pending Approval").get_json()]
for w in pending:
    c.post(f"/api/work-orders/{w['id']}/decision", json={"approver": "Supervisor", "decision": "approve"})
    print(f"\nSupervisor approved WO #{w['id']}")

print("\nAdvancing the clock 3 hours and running the SLA monitor...")
print(json.dumps(c.post("/api/sla/run", json={"advance_hours": 3}).get_json()["escalations"], indent=2))
print("\n" + c.get("/api/summary/daily").get_json()["text"])
