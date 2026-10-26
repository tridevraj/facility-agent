from collections import Counter

from .models import OPEN_STATUSES, WorkOrder
from .utils import utcnow


def build_dashboard(session, now=None):
    now = now or utcnow()
    orders = session.query(WorkOrder).all()
    open_orders = [w for w in orders if w.status in OPEN_STATUSES]
    done = [w for w in orders if w.status == "Completed" and w.resolved_at]
    on_time = [w for w in done if w.resolved_at <= w.due_at]
    hours = [(w.resolved_at - w.created_at).total_seconds() / 3600 for w in done]
    asset_counts = Counter((w.asset.code, w.asset.name) for w in orders if w.asset)
    place_counts = Counter((w.category, w.location) for w in orders)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "totals": {
            "all": len(orders), "open": len(open_orders),
            "overdue": sum(1 for w in open_orders if w.due_at < now),
            "pending_approval": sum(1 for w in orders if w.status == "Pending Approval"),
            "escalated": sum(1 for w in open_orders if (w.escalation_level or 0) > 0),
            "completed": len(done),
        },
        "sla_compliance_pct": round(100 * len(on_time) / len(done), 1) if done else None,
        "avg_resolution_hours": round(sum(hours) / len(hours), 1) if hours else None,
        "by_status": dict(Counter(w.status for w in orders)),
        "by_category": dict(Counter(w.category for w in orders)),
        "by_priority": dict(Counter(w.priority for w in orders)),
        "top_problem_assets": [{"code": c, "name": n, "work_orders": k} for (c, n), k in asset_counts.most_common(5)],
        "repeat_issues": [{"category": c, "location": l, "count": k} for (c, l), k in place_counts.most_common() if k > 1][:5],
    }


def daily_summary(session, now=None):
    now = now or utcnow()
    d = build_dashboard(session, now)
    from datetime import timedelta
    last_day = [w for w in session.query(WorkOrder).all() if w.created_at >= now - timedelta(hours=24)]
    t = d["totals"]
    lines = [f"Daily summary for {now:%d %b %Y}: {len(last_day)} new request(s) in the last 24h; "
             f"{t['open']} open, {t['overdue']} overdue, {t['pending_approval']} awaiting approval, {t['escalated']} escalated."]
    if d["by_category"]:
        cat, n = max(d["by_category"].items(), key=lambda kv: kv[1])
        lines.append(f"Most common category: {cat} ({n}).")
    if d["top_problem_assets"]:
        a = d["top_problem_assets"][0]
        lines.append(f"Most problematic asset: {a['code']} {a['name']} ({a['work_orders']} work orders).")
    if d["repeat_issues"]:
        r = d["repeat_issues"][0]
        lines.append(f"Repeat issue: {r['category']} at {r['location']} ({r['count']} times).")
    if d["sla_compliance_pct"] is not None:
        lines.append(f"SLA compliance on completed work: {d['sla_compliance_pct']}%.")
    return {"text": " ".join(lines), "dashboard": d}
