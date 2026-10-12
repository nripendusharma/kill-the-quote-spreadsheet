"""RFx co-pilot: the buyer talks, the model keeps a structured RFx draft current and asks what is missing.
Also drafts clarification emails to vendors from the review queue."""
from . import llm

LINE = {"type": "object", "additionalProperties": False,
        "required": ["id", "description", "kind", "ply", "flute", "size", "annual_qty", "notes"],
        "properties": {"id": {"type": "string"}, "description": {"type": "string"}, "kind": {"type": "string"},
                       "ply": {"type": ["integer", "null"]}, "flute": {"type": ["string", "null"]}, "size": {"type": "string"},
                       "annual_qty": {"type": ["integer", "null"]}, "notes": {"type": ["string", "null"]}}}

DRAFT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["reply", "draft", "open_questions"],
    "properties": {
        "reply": {"type": "string", "description": "what you say to the buyer this turn: short, specific"},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "draft": {"type": "object", "additionalProperties": False,
                  "required": ["title", "scope", "lines", "questionnaire", "terms", "vendors_to_invite"],
                  "properties": {
                      "title": {"type": "string"}, "scope": {"type": "string"},
                      "lines": {"type": "array", "items": LINE},
                      "questionnaire": {"type": "array", "items": {
                          "type": "object", "additionalProperties": False, "required": ["id", "text", "must_pass", "rule"],
                          "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "must_pass": {"type": "boolean"},
                                         "rule": {"type": ["string", "null"]}}}},
                      "terms": {"type": "object", "additionalProperties": False,
                                "required": ["currency", "price_basis", "delivery", "payment_days", "validity", "response_due", "other"],
                                "properties": {"currency": {"type": "string"}, "price_basis": {"type": "string"},
                                               "delivery": {"type": "string"}, "payment_days": {"type": ["integer", "null"]},
                                               "validity": {"type": "string"}, "response_due": {"type": "string"},
                                               "other": {"type": "string"}}},
                      "vendors_to_invite": {"type": "array", "items": {"type": "string"}}}},
    },
}

SYSTEM = """You are an RFx co-pilot for a category buyer in an Indian FMCG company. Turn what the buyer says into a complete, sendable RFx.
- Keep the full draft current every turn (return the whole draft, not a diff). Preserve what the buyer already agreed.
- A good corrugated RFx pins: dimensions (internal, mm), ply, flute, paper GSM per layer and BF, print, annual quantity, delivery point, price basis (INR per piece ex-GST, freight included), payment terms, validity, price-revision mechanism for kraft paper.
- Ask for the few things that genuinely block sending (max 3 questions per turn). Propose sensible defaults instead of asking about everything.
- The questionnaire should separate must-pass (with a checkable rule) from informational questions.
- Ask vendors to use the template, but never assume they will. Tell the buyer that's fine, the system reads whatever comes back."""


def turn(history, draft, user_text):
    msgs = []
    for role, text in history:
        msgs.append({"role": role, "content": text})
    ctx = f"Current draft (JSON):\n{draft}\n\nBuyer says: {user_text}" if draft else f"Buyer says: {user_text}"
    msgs.append({"role": "user", "content": ctx})
    out, _ = llm.structured(msgs, DRAFT_SCHEMA, system=SYSTEM, effort="medium", max_tokens=32000)
    return out


CLARIFY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["subject", "body"],
                  "properties": {"subject": {"type": "string"}, "body": {"type": "string"}}}


def clarification_email(rfx, vendor_name, issues):
    prompt = (f"Write a short, polite clarification email from {rfx['buyer']['person']} at {rfx['buyer']['company']} to {vendor_name} "
              f"about their reply to {rfx['id']}. Ask every question below in one email, numbered, specific enough that the vendor "
              f"can answer in one reply. Plain text, no em-dashes, under 200 words.\n\nOpen issues:\n" + "\n".join(f"- {i}" for i in issues))
    out, _ = llm.structured([{"role": "user", "content": prompt}], CLARIFY_SCHEMA, effort="low", max_tokens=4000)
    return out
