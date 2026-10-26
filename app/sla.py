"""SLA monitor: deterministic (no LLM) so escalations are predictable and auditable."""
from .models import OPEN_STATUSES, Event, Notification, WorkOrder
from .utils import utcnow

PRIORITY_LADDER = ["low", "medium", "high", "critical"]


def run_sla_check(session, config, now=None):
    now = now or utcnow()
    esc = config["escalation"]
    escalated = []
    for wo in session.query(WorkOrder).filter(WorkOrder.status.in_(OPEN_STATUSES)).all():
        total = (wo.due_at - wo.created_at).total_seconds() or 1
        pct = (now - wo.created_at).total_seconds() / total * 100
        level = 2 if pct >= esc["level2_after_sla_pct"] else 1 if pct >= esc["level1_after_sla_pct"] else 0
        if level <= (wo.escalation_level or 0):
            continue
        wo.escalation_level = level
        recipient = esc["level2_notify"] if level == 2 else esc["level1_notify"]
        msg = (f"WO #{wo.id} ({wo.category}, {wo.priority}) at {wo.location} is at {pct:.0f}% of its SLA "
               f"and is still {wo.status}. Escalation level {level}.")
        detail = f"level {level} at {pct:.0f}% of SLA"
        if level == 2 and wo.priority != "critical":
            new_p = PRIORITY_LADDER[PRIORITY_LADDER.index(wo.priority) + 1]
            detail += f"; priority raised {wo.priority} -> {new_p}"
            wo.priority = new_p
        session.add(Notification(work_order_id=wo.id, recipient=recipient, message=msg, created_at=now))
        session.add(Event(work_order_id=wo.id, actor="sla-monitor", action="escalated",
                          detail=detail, created_at=now))
        escalated.append({"work_order_id": wo.id, "level": level, "sla_pct": round(pct), "notified": recipient})
    session.commit()
    return escalated
