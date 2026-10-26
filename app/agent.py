"""Intake agents. Both agents only act through ToolBox tools.

LLMAgent      - Claude with tool calling (needs ANTHROPIC_API_KEY).
RuleBasedAgent- deterministic keyword agent; the offline fallback and the test baseline.
"""
import json
import os
import re

from .utils import has_phrase, norm

LOCATION_RE = re.compile(
    r"(?:block\s+[a-z0-9]+|room\s*(?:no\.?\s*:?\s*)?\d+[a-z]?|floor\s*\d+|ground floor|hostel\s+[a-z0-9]+|"
    r"lab\s*\d*|library|cafeteria|server room|terrace)", re.I)


def extract_location(text, hint=None):
    seen, parts = set(), []
    for m in LOCATION_RE.findall(text or ""):
        label = re.sub(r"\s+", " ", m.strip()).title()
        label = re.sub(r"^Room\s*(?:No\.?\s*:?\s*)?(\d)", r"Room \1", label)
        if label.lower() not in seen:
            seen.add(label.lower())
            parts.append(label)
    return ", ".join(parts) or (hint or "Unspecified")


def classify(text, config):
    t = norm(text)
    best, best_score = "other", 0
    for cat, spec in config["categories"].items():
        score = sum(1 for kw in spec.get("keywords", []) if has_phrase(t, kw)) * spec.get("weight", 1)
        if score > best_score:
            best, best_score = cat, score
    return best


def prioritize(text, category, config):
    t = norm(text)
    kws = config.get("priority_keywords", {})
    for level in ("critical", "high", "low"):
        if any(has_phrase(t, k) for k in kws.get(level, [])):
            result = level
            break
    else:
        result = "medium"
    if category == "safety" and result in ("medium", "low"):
        result = "high"
    return result


class RuleBasedAgent:
    name = "rule-based"

    def __init__(self, toolbox, config):
        self.tb, self.cfg = toolbox, config

    def handle(self, text, requester="Unknown", location_hint=None):
        trace = []

        def call(tool, **args):
            out = self.tb.dispatch(tool, args)
            trace.append({"tool": tool, "input": args, "output": out})
            return out

        location = extract_location(text, location_hint)
        category = classify(text, self.cfg)
        priority = prioritize(text, category, self.cfg)

        assets = call("lookup_asset", location=location, category=category)["matches"]
        dups = call("check_duplicates", location=location, category=category)["open_duplicates"]
        reasoning = (f"Matched '{category}' keywords; priority '{priority}' from urgency wording"
                     + (f"; linked to asset {assets[0]['code']}" if assets else "")
                     + (f"; repeat of WO #{dups[0]['id']}" if dups else "") + ".")
        created = call("create_work_order", request_text=text, requester=requester, location=location,
                       category=category, priority=priority,
                       asset_code=assets[0]["code"] if assets else None,
                       repeat_of=dups[0]["id"] if dups else None, reasoning=reasoning)
        if not created["ok"]:
            return {"agent": self.name, "trace": trace, "work_order_id": None, "message": created["error"]}
        wo_id = created["work_order"]["id"]
        cands = call("find_technician", category=category).get("candidates", [])
        if cands:
            call("assign_technician", work_order_id=wo_id, technician_id=cands[0]["id"])
        return {"agent": self.name, "trace": trace, "work_order_id": wo_id,
                "message": reasoning + ("" if cands else " No technician available; left unassigned.")}


def build_tool_schemas(config):
    cats, pris = list(config["categories"]), list(config["priorities"])
    s = lambda d: {"type": "string", "description": d}
    return [
        {"name": "lookup_asset", "description": "Find registered assets matching a location, optionally filtered by category.",
         "input_schema": {"type": "object", "properties": {"location": s("Free-text location, e.g. 'Block C, Room 204'"),
                                                           "category": {"type": "string", "enum": cats}}, "required": ["location"]}},
        {"name": "check_duplicates", "description": "Check whether an open work order already exists for the same place and category.",
         "input_schema": {"type": "object", "properties": {"location": s("Location"), "category": {"type": "string", "enum": cats}},
                          "required": ["location", "category"]}},
        {"name": "create_work_order", "description": "Create the work order. Must be called exactly once per request.",
         "input_schema": {"type": "object", "properties": {
             "request_text": s("The original request"), "requester": s("Who raised it"), "location": s("Normalised location"),
             "category": {"type": "string", "enum": cats}, "priority": {"type": "string", "enum": pris},
             "estimated_cost": {"type": "number", "description": "Rough cost in INR; omit to use the category default"},
             "asset_code": s("Asset code from lookup_asset, if one clearly matches"),
             "repeat_of": {"type": "integer", "description": "Id of an open duplicate work order, if any"},
             "reasoning": s("One or two sentences explaining category and priority")},
          "required": ["request_text", "location", "category", "priority", "reasoning"]}},
        {"name": "find_technician", "description": "List available technicians with the right skill, least busy first.",
         "input_schema": {"type": "object", "properties": {"category": {"type": "string", "enum": cats}}, "required": ["category"]}},
        {"name": "assign_technician", "description": "Assign a technician returned by find_technician to the work order.",
         "input_schema": {"type": "object", "properties": {"work_order_id": {"type": "integer"}, "technician_id": {"type": "integer"}},
                          "required": ["work_order_id", "technician_id"]}},
    ]


def system_prompt(config):
    cats = "\n".join(f"- {c}" for c in config["categories"])
    pris = "\n".join(f"- {p}: {v['meaning']} (SLA {v['sla_hours']}h)" for p, v in config["priorities"].items())
    return f"""You are the intake agent for a facility maintenance team. You turn one free-text request into a dispatched work order using the tools provided.

Categories:
{cats}

Priorities:
{pris}

Procedure: (1) lookup_asset, (2) check_duplicates, (3) create_work_order, (4) find_technician, (5) assign_technician.
Rules:
- Anything involving fire, smoke, gas, sparking or electric shock, or a trapped person, is critical.
- Never invent technician ids, asset codes or work order ids; use only values returned by tools.
- You cannot approve work. Critical or costly work is held for a human supervisor automatically; still assign a technician.
- If no technician is available, stop after creating the work order and say so.
- Finish with one short sentence summarising what you did."""


class LLMAgent:
    name = "claude"

    def __init__(self, toolbox, config, client=None, model=None, max_steps=8):
        self.tb, self.cfg = toolbox, config
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        self.max_steps = max_steps
        self.tools = build_tool_schemas(config)
        self.system = system_prompt(config)

    def handle(self, text, requester="Unknown", location_hint=None):
        trace, wo_id = [], None
        user = f"Requester: {requester}\nLocation hint: {location_hint or 'none'}\nRequest: {text}"
        messages = [{"role": "user", "content": user}]
        final = ""
        for _ in range(self.max_steps):
            resp = self.client.messages.create(model=self.model, max_tokens=1024, system=self.system,
                                               tools=self.tools, messages=messages)
            texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            if texts:
                final = " ".join(texts)
            if resp.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", "") != "tool_use":
                    continue
                args = dict(block.input or {})
                if block.name == "create_work_order":
                    args.setdefault("requester", requester)
                    args.setdefault("request_text", text)
                out = self.tb.dispatch(block.name, args)
                trace.append({"tool": block.name, "input": args, "output": out})
                if block.name == "create_work_order" and out.get("ok"):
                    wo_id = out["work_order"]["id"]
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)})
            messages.append({"role": "user", "content": results})
        if wo_id is None:
            raise RuntimeError("LLM agent finished without creating a work order")
        return {"agent": self.name, "trace": trace, "work_order_id": wo_id, "message": final}


def build_agent(toolbox, config):
    """Claude if a key is configured, otherwise (or on any failure) the rule-based agent."""
    mode = os.environ.get("FACILITY_AGENT", "auto").lower()
    use_llm = mode == "llm" or (mode == "auto" and os.environ.get("ANTHROPIC_API_KEY"))
    rule = RuleBasedAgent(toolbox, config)
    if not use_llm:
        return rule
    try:
        llm = LLMAgent(toolbox, config)
    except Exception:
        return rule

    class Safe:
        name = llm.name

        def handle(self, text, requester="Unknown", location_hint=None):
            try:
                return llm.handle(text, requester, location_hint)
            except Exception as e:  # network, auth, bad output: never lose a maintenance request
                out = rule.handle(text, requester, location_hint)
                out["message"] = f"(LLM unavailable: {type(e).__name__}; used rule-based fallback) " + out["message"]
                return out
    return Safe()
