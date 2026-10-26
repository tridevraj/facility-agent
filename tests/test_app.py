from types import SimpleNamespace

from app.agent import LLMAgent, classify, extract_location, prioritize
from app.models import WorkOrder
from app.services import ToolBox
from app.sla import run_sla_check
from app.utils import utcnow
from datetime import timedelta
from conftest import submit


# ---- TC-01..04: intake, classification, priority, asset link ------------------------------
def test_tc01_ac_request_is_classified_assigned_and_linked(client):
    code, r = submit(client, "AC not working in Block C, Room 204")
    wo = r["work_order"]
    assert code == 201
    assert (wo["category"], wo["priority"], wo["status"]) == ("hvac", "medium", "Assigned")
    assert wo["asset_code"] == "AC-C-204" and wo["technician"] in ("Anand", "Divya")
    assert [t["tool"] for t in r["trace"]] == ["lookup_asset", "check_duplicates", "create_work_order",
                                                "find_technician", "assign_technician"]


def test_tc02_urgency_words_raise_priority(app):
    cfg = app.fm_config
    assert prioritize("no water in hostel A", "plumbing", cfg) == "high"
    assert prioritize("scratches on the desk", "civil", cfg) == "low"
    assert prioritize("fire smoke in lab", "safety", cfg) == "critical"
    assert classify("projector and wifi down in lab 2", cfg) == "it_network"
    assert classify("something strange happened", cfg) == "other"


def test_tc03_location_extraction():
    assert extract_location("AC off in Block C, Room 204") == "Block C, Room 204"
    assert extract_location("tap leaking", hint="Hostel B") == "Hostel B"
    assert extract_location("tap leaking") == "Unspecified"
    assert extract_location("AC not working in Block C (Room no:206)") == "Block C, Room 206"
    assert extract_location("Water leaking in block a(room no:105)") == "Block A, Room 105"


def test_tc04_asset_in_a_different_room_is_not_linked(client):
    _, r = submit(client, "AC not working in Block C, Room 999")
    assert r["work_order"]["asset_code"] is None
    _, r = submit(client, "AC not working in Block C")          # too vague to pick one specific unit
    assert r["work_order"]["asset_code"] is None
    _, r = submit(client, "Wifi is down in the Library")        # asset whose whole location is named
    assert r["work_order"]["asset_code"] == "IT-LIB-AP1"


# ---- TC-05..08: approval workflow ---------------------------------------------------------
def test_tc05_critical_work_is_held_then_approved(client):
    _, r = submit(client, "Sparking from the switch board in Block B ground floor")
    wo = r["work_order"]
    assert wo["priority"] == "critical" and wo["status"] == "Pending Approval"
    assert wo["technician"] == "Arun" and wo["approval_status"] == "pending"
    res = client.post(f"/api/work-orders/{wo['id']}/decision", json={"approver": "Sup", "decision": "approve"})
    assert res.get_json()["work_order"]["status"] == "Assigned"


def test_tc06_rejection_closes_the_order(client):
    _, r = submit(client, "Smoke smell in Block A")
    wid = r["work_order"]["id"]
    res = client.post(f"/api/work-orders/{wid}/decision", json={"decision": "reject"}).get_json()
    assert res["work_order"]["status"] == "Rejected"
    again = client.post(f"/api/work-orders/{wid}/decision", json={"decision": "approve"})
    assert again.status_code == 400


def test_tc07_cost_over_threshold_needs_approval(app):
    with app.session_factory() as s:
        tb = ToolBox(s, app.fm_config)
        out = tb.create_work_order("Replace chiller", "Block A", "hvac", "medium", estimated_cost=9000)
        assert out["work_order"]["status"] == "Pending Approval"
        out2 = tb.create_work_order("Replace bulb", "Block A", "electrical", "low", estimated_cost=100)
        assert out2["work_order"]["status"] == "New"


def test_tc08_only_matching_skill_can_be_assigned(app):
    with app.session_factory() as s:
        tb = ToolBox(s, app.fm_config)
        wid = tb.create_work_order("Leak", "Block A", "plumbing", "high")["work_order"]["id"]
        electrician = tb.find_technician("electrical")["candidates"][0]["id"]
        assert tb.assign_technician(wid, electrician)["ok"] is False


# ---- TC-09..11: duplicates, workload, no technician ---------------------------------------
def test_tc09_repeat_request_is_linked(client):
    _, a = submit(client, "AC not cooling in Block C Room 204")
    _, b = submit(client, "AC still not cooling in Block C Room 204")
    assert b["work_order"]["repeat_of"] == a["work_order"]["id"]


def test_tc10_load_is_spread_across_technicians(client):
    names = {submit(client, f"Light not working in Block A room {n}")[1]["work_order"]["technician"] for n in (1, 2)}
    assert names == {"Ravi", "Karthik"}


def test_tc11_no_available_technician_leaves_order_unassigned(app, client):
    with app.session_factory() as s:
        from app.models import Technician
        for t in s.query(Technician).filter(Technician.skill == "plumber"):
            t.available = False
        s.commit()
    _, r = submit(client, "Tap leaking in Block A")
    assert r["work_order"]["technician"] is None and r["work_order"]["status"] == "New"
    assert "No technician available" in r["message"]


# ---- TC-12..14: SLA escalation ------------------------------------------------------------
def test_tc12_sla_escalates_in_two_levels_and_only_once(app, client):
    _, r = submit(client, "Wifi is down in the Library, exams tomorrow")   # high -> 8h SLA
    wid = r["work_order"]["id"]
    with app.session_factory() as s:
        created = s.get(WorkOrder, wid).created_at
        assert run_sla_check(s, app.fm_config, created + timedelta(hours=4)) == []
        l1 = run_sla_check(s, app.fm_config, created + timedelta(hours=9))
        assert l1[0]["level"] == 1 and l1[0]["notified"] == app.fm_config["escalation"]["level1_notify"]
        assert run_sla_check(s, app.fm_config, created + timedelta(hours=9.5)) == []     # no duplicate alert
        l2 = run_sla_check(s, app.fm_config, created + timedelta(hours=13))
        assert l2[0]["level"] == 2
        assert s.get(WorkOrder, wid).priority == "critical"                              # bumped high -> critical
    assert len(client.get("/api/notifications").get_json()) == 2


def test_tc13_completed_orders_are_not_escalated(app, client):
    _, r = submit(client, "Light not working in Block A")
    wid = r["work_order"]["id"]
    client.post(f"/api/work-orders/{wid}/status", json={"status": "Completed"})
    with app.session_factory() as s:
        assert run_sla_check(s, app.fm_config, utcnow() + timedelta(days=30)) == []


def test_tc14_sla_endpoint_can_simulate_time(client):
    submit(client, "Light not working in Block A")            # medium, 24h
    res = client.post("/api/sla/run", json={"advance_hours": 30}).get_json()
    assert res["escalations"] and res["escalations"][0]["level"] == 1


# ---- TC-15..16: status transitions --------------------------------------------------------
def test_tc15_status_flow_and_invalid_jumps(client):
    _, r = submit(client, "Light not working in Block A")
    wid = r["work_order"]["id"]
    assert client.post(f"/api/work-orders/{wid}/status", json={"status": "In Progress"}).status_code == 200
    assert client.post(f"/api/work-orders/{wid}/status", json={"status": "Assigned"}).status_code == 400
    done = client.post(f"/api/work-orders/{wid}/status", json={"status": "Completed"}).get_json()
    assert done["work_order"]["resolved_at"]


def test_tc16_event_log_records_who_did_what(client):
    _, r = submit(client, "Smoke in Block B")
    wid = r["work_order"]["id"]
    client.post(f"/api/work-orders/{wid}/decision", json={"approver": "Sup", "decision": "approve"})
    actions = [(e["actor"], e["action"]) for e in client.get(f"/api/work-orders/{wid}").get_json()["events"]]
    assert actions == [("agent", "created"), ("agent", "assigned"), ("Sup", "approve")]


# ---- TC-17..18: reporting -----------------------------------------------------------------
def test_tc17_dashboard_and_summary(client):
    submit(client, "AC not cooling in Block C Room 204")
    submit(client, "AC not cooling again in Block C Room 204")
    d = client.get("/api/dashboard").get_json()
    assert d["totals"]["open"] == 2 and d["by_category"] == {"hvac": 2}
    assert d["top_problem_assets"][0]["code"] == "AC-C-204"
    assert d["repeat_issues"][0]["count"] == 2
    assert "2 new request(s)" in client.get("/api/summary/daily").get_json()["text"]


def test_tc18_input_validation(client):
    assert client.post("/api/requests", json={"text": "  "}).status_code == 400
    assert client.post("/api/requests", json={"text": "x" * 1001}).status_code == 400
    assert client.get("/api/work-orders/9999").status_code == 404


# ---- TC-19..20: Claude agent (mocked client) ----------------------------------------------
class FakeClient:
    """Replays a scripted tool-calling conversation so the LLM path is tested without network."""
    def __init__(self, script):
        self.script, self.calls = list(script), 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls += 1
        return self.script.pop(0)


def _tool(id_, name, **inp):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


def _resp(stop, *blocks):
    return SimpleNamespace(stop_reason=stop, content=list(blocks))


def test_tc19_llm_agent_drives_the_tools(app):
    script = [
        _resp("tool_use", _tool("1", "lookup_asset", location="Block C, Room 204", category="hvac")),
        _resp("tool_use", _tool("2", "create_work_order", location="Block C, Room 204", category="hvac",
                                priority="medium", asset_code="AC-C-204", reasoning="AC fault")),
        _resp("tool_use", _tool("3", "find_technician", category="hvac")),
        _resp("tool_use", _tool("4", "assign_technician", work_order_id=1, technician_id=5)),
        _resp("end_turn", SimpleNamespace(type="text", text="Created and assigned.")),
    ]
    with app.session_factory() as s:
        agent = LLMAgent(ToolBox(s, app.fm_config), app.fm_config, client=FakeClient(script))
        out = agent.handle("AC not working in Block C, Room 204", "Priya")
        wo = s.get(WorkOrder, out["work_order_id"])
        assert out["agent"] == "claude" and out["message"] == "Created and assigned."
        assert wo.status == "Assigned" and wo.asset.code == "AC-C-204" and wo.requester == "Priya"


def test_tc20_bad_llm_output_is_rejected_by_tools_and_falls_back(app, client):
    with app.session_factory() as s:
        tb = ToolBox(s, app.fm_config)
        bad = tb.dispatch("create_work_order", {"request_text": "x", "location": "A", "category": "magic", "priority": "high"})
        assert bad["ok"] is False and "category" in bad["error"]
        assert tb.dispatch("delete_everything", {})["ok"] is False
    from app.agent import build_agent
    import os
    os.environ["FACILITY_AGENT"] = "llm"
    try:
        class Boom:
            messages = SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("network down")))
        import app.agent as agent_mod
        orig = agent_mod.LLMAgent.__init__
        agent_mod.LLMAgent.__init__ = lambda self, tb, cfg, **kw: orig(self, tb, cfg, client=Boom())
        with app.session_factory() as s:
            out = build_agent(ToolBox(s, app.fm_config), app.fm_config).handle("Tap leaking in Block A")
            assert out["work_order_id"] and "rule-based fallback" in out["message"]
    finally:
        agent_mod.LLMAgent.__init__ = orig
        os.environ["FACILITY_AGENT"] = "rule"
