from .ai_client import call_json
from .normalizer import FIELDS, normalize_fields


def _confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number /= 100
    return max(0.0, min(1.0, number))


def compare_with_ai(si_fields: dict, bl_fields: dict) -> dict:
    si = normalize_fields(si_fields)
    bl = normalize_fields(bl_fields)

    system = """You compare Shipping Instruction and Bill of Lading fields.
Return JSON only. Do not provide hidden chain-of-thought; provide concise, user-facing explanations based on the supplied values.

Equivalence rules:
- formatting, punctuation, line breaks, capitalization and whitespace do not create a mismatch
- company names can be equivalent when address/suffix formatting differs; do not invent identity equivalence
- port aliases and UN/LOCODE can represent the same port
- container count is numeric
- gross weight is numeric in kilograms; metric tonnes must be converted to kg
- missing/unreadable/unknown values are UNRESOLVED, not MISMATCH
- a genuinely different company, port, container count or materially different weight is MISMATCH
"""
    user = f"""Compare all seven fields.

SI:
{si}

BL:
{bl}

Return JSON:
{{
  "status": "OK",
  "confidence": 0.0,
  "summary": "one sentence describing the overall result",
  "explanation": "2-4 concise sentences explaining why the documents match, mismatch, or require review",
  "next_action": "operator action, especially for NEEDS_REVIEW",
  "fields": {{
    "shipper": {{"si": "...", "bl": "...", "status": "MATCH", "reason": "...", "evidence": "..."}},
    "consignee": {{"si": "...", "bl": "...", "status": "MATCH", "reason": "...", "evidence": "..."}},
    "notify_party": {{"si": "...", "bl": "...", "status": "MATCH", "reason": "...", "evidence": "..."}},
    "port_of_loading": {{"si": "...", "bl": "...", "status": "MATCH", "reason": "...", "evidence": "..."}},
    "port_of_discharge": {{"si": "...", "bl": "...", "status": "MATCH", "reason": "...", "evidence": "..."}},
    "container_count": {{"si": 0, "bl": 0, "status": "MATCH", "reason": "...", "evidence": "..."}},
    "gross_weight_kg": {{"si": 0, "bl": 0, "status": "MATCH", "reason": "...", "evidence": "..."}}
  }}
}}

Allowed field status: MATCH, MISMATCH, UNRESOLVED.
Overall status:
- NEEDS_REVIEW if any field is UNRESOLVED
- otherwise MISMATCH if one or more fields are genuinely different
- otherwise OK
"""
    result = call_json(system, user)
    fields = result.get("fields") or {}
    normalized = {}
    mismatches = []
    unresolved = []
    for field in FIELDS:
        item = fields.get(field) or {}
        status = item.get("status", "UNRESOLVED")
        if status not in {"MATCH", "MISMATCH", "UNRESOLVED"}:
            status = "UNRESOLVED"
        normalized[field] = {
            "si": si.get(field),
            "bl": bl.get(field),
            "status": status,
            "reason": str(item.get("reason") or "").strip(),
            "evidence": str(item.get("evidence") or "").strip(),
        }
        if status == "MISMATCH":
            mismatches.append(field)
        elif status == "UNRESOLVED":
            unresolved.append(field)

    overall = "NEEDS_REVIEW" if unresolved else "MISMATCH" if mismatches else "OK"
    return {
        "status": overall,
        "confidence": _confidence(result.get("confidence")),
        "summary": str(result.get("summary") or "").strip(),
        "reason": str(result.get("summary") or result.get("explanation") or "").strip(),
        "explanation": str(result.get("explanation") or result.get("summary") or "").strip(),
        "next_action": str(result.get("next_action") or "").strip(),
        "fields": normalized,
        "mismatch_fields": mismatches,
        "unresolved_fields": unresolved,
    }
