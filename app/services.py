"""Business logic. The agent's tools and the human endpoints all go through here,
so the LLM never touches the database directly and every rule lives in one place."""
import re
from datetime import timedelta

from sqlalchemy import func

from .models import OPEN_STATUSES, Asset, Event, Notification, Technician, WorkOrder
from .utils import norm, utcnow

LOC_TOKEN = re.compile(
    r"(?:block|room|floor|hostel|lab)\s+[a-z0-9]+|library|cafeteria|server room|terrace|ground floor")

# Allowed manual status transitions.
TRANSITIONS = {
    "Assigned": ("In Progress", "Completed"),
    "In Progress": ("Completed",),
}


class ToolBox:
    def __init__(self, session, config, now_fn=utcnow):
        self.s = session
        self.cfg = config
        self.now = now_fn

    # ------------------------------------------------------------------ helpers
    def _log(self, wo_id, actor, action, detail=""):
        self.s.add(Event(work_order_id=wo_id, actor=actor, action=action,
                         detail=detail, created_at=self.now()))

    def approval_needed(self, priority, category, cost):
        rule = self.cfg["approval"]
        reasons = []
        if priority in rule.get("priorities", []):
            reasons.append(f"priority is {priority}")
        if category in rule.get("categories", []):
            reasons.append(f"category is {category}")
        limit = rule.get("cost_above")
        if limit is not None and (cost or 0) > limit:
            reasons.append(f"estimated cost {cost:.0f} is above {limit}")
        return bool(reasons), reasons

    def _open_orders_for(self, tech_id):
        return (self.s.query(func.count(WorkOrder.id))
                .filter(WorkOrder.technician_id == tech_id, WorkOrder.status.in_(OPEN_STATUSES))
                .scalar())

    # --------------------------------------------------------------- agent tools
    def lookup_asset(self, location, category=None):
        """Find assets whose full location is named in the request.

        'Block C, Room 204' matches an asset at 'Block C - Room 204', but a request that only
        says 'Block C' matches nothing: guessing a specific asset would be wrong more often than not."""
        want = set(LOC_TOKEN.findall(norm(location)))
        q = self.s.query(Asset)
        if category:
            q = q.filter(Asset.category == category)
        scored = []
        for a in q.all():
            have = set(LOC_TOKEN.findall(norm(a.location)))
            if have and have <= want:
                scored.append((len(have), a))
        scored.sort(key=lambda x: (-x[0], x[1].code))
        return {"ok": True, "matches": [dict(a.to_dict(), match_score=sc) for sc, a in scored[:5]]}

    def check_duplicates(self, location, category):
        """Open work orders already raised for the same category and place."""
        loc = norm(location)
        found = []
        for wo in self.s.query(WorkOrder).filter(WorkOrder.category == category,
                                                 WorkOrder.status.in_(OPEN_STATUSES)).all():
            w = norm(wo.location)
            if loc and w and (loc == w or loc in w or w in loc):
                found.append({"id": wo.id, "location": wo.location, "status": wo.status,
                              "priority": wo.priority, "request_text": wo.request_text})
        return {"ok": True, "open_duplicates": found}

    def find_technician(self, category):
        """Available technicians with the right skill, least-loaded first."""
        spec = self.cfg["categories"].get(category)
        if not spec:
            return {"ok": False, "error": f"unknown category '{category}'"}
        techs = (self.s.query(Technician)
                 .filter(Technician.skill == spec["skill"], Technician.available.is_(True)).all())
        ranked = sorted(((self._open_orders_for(t.id), t) for t in techs), key=lambda x: (x[0], x[1].id))
        return {"ok": True, "required_skill": spec["skill"],
                "candidates": [dict(t.to_dict(), open_orders=n) for n, t in ranked[:3]]}

    def create_work_order(self, request_text, location, category, priority, requester="Unknown",
                          estimated_cost=None, asset_code=None, repeat_of=None, reasoning=""):
        if category not in self.cfg["categories"]:
            return {"ok": False, "error": f"category must be one of {list(self.cfg['categories'])}"}
        if priority not in self.cfg["priorities"]:
            return {"ok": False, "error": f"priority must be one of {list(self.cfg['priorities'])}"}
        asset = None
        if asset_code:
            asset = self.s.query(Asset).filter(Asset.code == asset_code).first()
            if not asset:
                return {"ok": False, "error": f"unknown asset_code '{asset_code}'"}
        if estimated_cost is None:
            estimated_cost = self.cfg["categories"][category].get("default_cost", 0)
        needs, reasons = self.approval_needed(priority, category, float(estimated_cost))
        now = self.now()
        wo = WorkOrder(
            request_text=request_text, requester=requester or "Unknown", location=location or "Unspecified",
            asset=asset, category=category, priority=priority, estimated_cost=float(estimated_cost),
            status="Pending Approval" if needs else "New",
            requires_approval=needs, approval_status="pending" if needs else None,
            repeat_of=repeat_of, agent_reasoning=reasoning, created_at=now,
            due_at=now + timedelta(hours=self.cfg["priorities"][priority]["sla_hours"]),
        )
        self.s.add(wo)
        self.s.flush()
        self._log(wo.id, "agent", "created", f"{category}/{priority}; approval: {'; '.join(reasons) or 'not required'}")
        self.s.commit()
        return {"ok": True, "work_order": wo.to_dict(self.now())}

    def assign_technician(self, work_order_id, technician_id):
        wo = self.s.get(WorkOrder, work_order_id)
        tech = self.s.get(Technician, technician_id)
        if not wo or not tech:
            return {"ok": False, "error": "work order or technician not found"}
        if wo.status not in ("New", "Pending Approval"):
            return {"ok": False, "error": f"cannot assign while status is {wo.status}"}
        required = self.cfg["categories"][wo.category]["skill"]
        if tech.skill != required:
            return {"ok": False, "error": f"technician skill {tech.skill} does not match required {required}"}
        wo.technician_id = tech.id
        if wo.requires_approval and wo.approval_status == "pending":
            note = "tentative, waiting for supervisor approval"   # stays Pending Approval
        else:
            wo.status = "Assigned"
            note = "dispatched"
        self._log(wo.id, "agent", "assigned", f"{tech.name} ({note})")
        self.s.commit()
        return {"ok": True, "work_order": wo.to_dict(self.now())}

    def dispatch(self, name, args):
        fn = {"lookup_asset": self.lookup_asset, "check_duplicates": self.check_duplicates,
              "find_technician": self.find_technician, "create_work_order": self.create_work_order,
              "assign_technician": self.assign_technician}.get(name)
        if not fn:
            return {"ok": False, "error": f"unknown tool '{name}'"}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {"ok": False, "error": f"bad arguments: {e}"}

    # ------------------------------------------------------- human-driven actions
    def decide(self, work_order_id, approver, decision, note=""):
        wo = self.s.get(WorkOrder, work_order_id)
        if not wo:
            return {"ok": False, "error": "work order not found"}
        if wo.status != "Pending Approval":
            return {"ok": False, "error": f"work order is {wo.status}, not Pending Approval"}
        if decision == "approve":
            wo.approval_status, wo.approved_by = "approved", approver
            wo.status = "Assigned" if wo.technician_id else "New"
        elif decision == "reject":
            wo.approval_status, wo.approved_by, wo.status = "rejected", approver, "Rejected"
        else:
            return {"ok": False, "error": "decision must be 'approve' or 'reject'"}
        self._log(wo.id, approver, decision, note)
        self.s.commit()
        return {"ok": True, "work_order": wo.to_dict(self.now())}

    def update_status(self, work_order_id, new_status, actor="technician"):
        wo = self.s.get(WorkOrder, work_order_id)
        if not wo:
            return {"ok": False, "error": "work order not found"}
        if new_status not in TRANSITIONS.get(wo.status, ()):
            return {"ok": False, "error": f"cannot move from {wo.status} to {new_status}"}
        wo.status = new_status
        if new_status == "In Progress":
            wo.started_at = self.now()
        if new_status == "Completed":
            wo.resolved_at = self.now()
        self._log(wo.id, actor, "status", new_status)
        self.s.commit()
        return {"ok": True, "work_order": wo.to_dict(self.now())}
