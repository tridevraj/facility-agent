from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

OPEN_STATUSES = ("New", "Pending Approval", "Assigned", "In Progress")
ALL_STATUSES = OPEN_STATUSES + ("Completed", "Rejected")


def iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    category = Column(String(32), nullable=False)
    location = Column(String(120), nullable=False)
    status = Column(String(20), default="Operational")

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name,
                "category": self.category, "location": self.location, "status": self.status}


class Technician(Base):
    __tablename__ = "technicians"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    skill = Column(String(40), nullable=False)
    available = Column(Boolean, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "skill": self.skill, "available": bool(self.available)}


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id = Column(Integer, primary_key=True)
    request_text = Column(Text, nullable=False)
    requester = Column(String(80), default="Unknown")
    location = Column(String(120), default="Unspecified")
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    category = Column(String(32), nullable=False)
    priority = Column(String(16), nullable=False)
    status = Column(String(20), nullable=False, default="New")
    technician_id = Column(Integer, ForeignKey("technicians.id"), nullable=True)
    estimated_cost = Column(Float, default=0)
    requires_approval = Column(Boolean, default=False)
    approval_status = Column(String(16), nullable=True)  # pending / approved / rejected
    approved_by = Column(String(80), nullable=True)
    repeat_of = Column(Integer, nullable=True)
    agent_reasoning = Column(Text, nullable=True)
    escalation_level = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False)
    due_at = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    asset = relationship("Asset")
    technician = relationship("Technician")

    def to_dict(self, now=None):
        overdue = bool(now and self.status in OPEN_STATUSES and self.due_at < now)
        return {
            "id": self.id, "request_text": self.request_text, "requester": self.requester,
            "location": self.location,
            "asset_code": self.asset.code if self.asset else None,
            "asset_name": self.asset.name if self.asset else None,
            "category": self.category, "priority": self.priority, "status": self.status,
            "technician_id": self.technician_id,
            "technician": self.technician.name if self.technician else None,
            "estimated_cost": self.estimated_cost, "requires_approval": bool(self.requires_approval),
            "approval_status": self.approval_status, "approved_by": self.approved_by,
            "repeat_of": self.repeat_of, "agent_reasoning": self.agent_reasoning,
            "escalation_level": self.escalation_level, "overdue": overdue,
            "created_at": iso(self.created_at), "due_at": iso(self.due_at),
            "started_at": iso(self.started_at), "resolved_at": iso(self.resolved_at),
        }


class Event(Base):
    """Audit trail: every action by the agent, a human or the SLA monitor."""
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)
    actor = Column(String(80), nullable=False)
    action = Column(String(40), nullable=False)
    detail = Column(Text, default="")
    created_at = Column(DateTime, nullable=False)

    def to_dict(self):
        return {"id": self.id, "work_order_id": self.work_order_id, "actor": self.actor,
                "action": self.action, "detail": self.detail, "created_at": iso(self.created_at)}


class Notification(Base):
    """Simulated outbound messages (email/SMS/Slack would plug in here)."""
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)
    recipient = Column(String(120), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)

    def to_dict(self):
        return {"id": self.id, "work_order_id": self.work_order_id, "recipient": self.recipient,
                "message": self.message, "created_at": iso(self.created_at)}
