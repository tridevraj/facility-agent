from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, render_template, request

from .agent import build_agent
from .models import Asset, Event, Notification, Technician, WorkOrder
from .reports import build_dashboard, daily_summary
from .services import ToolBox
from .sla import run_sla_check
from .utils import utcnow

bp = Blueprint("main", __name__)


def _session():
    if "session" not in g:
        g.session = current_app.session_factory()
    return g.session


@bp.teardown_app_request
def _close(_exc):
    s = g.pop("session", None)
    if s is not None:
        s.close()


def _toolbox():
    return ToolBox(_session(), current_app.fm_config)


def _err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


@bp.get("/")
def home():
    return render_template("dashboard.html")


@bp.get("/api/config")
def get_config():
    cfg = current_app.fm_config
    return jsonify({"categories": list(cfg["categories"]), "priorities": cfg["priorities"],
                    "approval": cfg["approval"], "escalation": cfg["escalation"]})


@bp.post("/api/requests")
def submit_request():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return _err("'text' is required")
    if len(text) > 1000:
        return _err("'text' must be 1000 characters or fewer")
    tb = _toolbox()
    factory = current_app.config.get("AGENT_FACTORY") or build_agent
    result = factory(tb, current_app.fm_config).handle(
        text, requester=(data.get("requester") or "Unknown").strip()[:80],
        location_hint=(data.get("location") or None))
    wo = _session().get(WorkOrder, result["work_order_id"]) if result.get("work_order_id") else None
    return jsonify({"ok": wo is not None, "agent": result["agent"], "message": result["message"],
                    "trace": result["trace"], "work_order": wo.to_dict(utcnow()) if wo else None}), (201 if wo else 422)


@bp.get("/api/work-orders")
def list_work_orders():
    q = _session().query(WorkOrder)
    for field in ("status", "category", "priority"):
        if request.args.get(field):
            q = q.filter(getattr(WorkOrder, field) == request.args[field])
    now = utcnow()
    return jsonify([w.to_dict(now) for w in q.order_by(WorkOrder.id.desc()).all()])


@bp.get("/api/work-orders/<int:wo_id>")
def get_work_order(wo_id):
    s = _session()
    wo = s.get(WorkOrder, wo_id)
    if not wo:
        return _err("not found", 404)
    events = s.query(Event).filter(Event.work_order_id == wo_id).order_by(Event.id).all()
    return jsonify(dict(wo.to_dict(utcnow()), events=[e.to_dict() for e in events]))


@bp.post("/api/work-orders/<int:wo_id>/decision")
def decision(wo_id):
    d = request.get_json(silent=True) or {}
    res = _toolbox().decide(wo_id, (d.get("approver") or "supervisor").strip()[:80],
                            d.get("decision"), d.get("note", ""))
    return jsonify(res), (200 if res["ok"] else 400)


@bp.post("/api/work-orders/<int:wo_id>/status")
def set_status(wo_id):
    d = request.get_json(silent=True) or {}
    res = _toolbox().update_status(wo_id, d.get("status"), (d.get("actor") or "technician")[:80])
    return jsonify(res), (200 if res["ok"] else 400)


@bp.post("/api/sla/run")
def sla_run():
    """advance_hours lets you simulate time passing for demos and tests."""
    d = request.get_json(silent=True) or {}
    now = utcnow() + timedelta(hours=float(d.get("advance_hours", 0)))
    return jsonify({"checked_at": now.isoformat(timespec="seconds"),
                    "escalations": run_sla_check(_session(), current_app.fm_config, now)})


@bp.get("/api/dashboard")
def dashboard():
    return jsonify(build_dashboard(_session()))


@bp.get("/api/summary/daily")
def summary():
    return jsonify(daily_summary(_session()))


@bp.get("/api/notifications")
def notifications():
    rows = _session().query(Notification).order_by(Notification.id.desc()).limit(50).all()
    return jsonify([n.to_dict() for n in rows])


@bp.get("/api/technicians")
def technicians():
    return jsonify([t.to_dict() for t in _session().query(Technician).all()])


@bp.get("/api/assets")
def assets():
    return jsonify([a.to_dict() for a in _session().query(Asset).all()])
