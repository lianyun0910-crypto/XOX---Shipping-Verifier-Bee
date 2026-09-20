from .ai_client import call_json

EMAIL_CATEGORIES = [
    "BL_COMPARISON",
    "SI_REQUEST",
    "INVOICE_QUERY",
    "GENERAL",
    "SPAM",
]


def _confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number /= 100
    return max(0.0, min(1.0, number))


def classify_email(email: dict) -> dict:
    system = """You classify business emails for an international shipping verification system.
The email may be in English, Chinese, Malay, Japanese, Korean, or another language.
Understand meaning and context rather than relying on fixed keywords.
Return JSON only. Do not provide hidden chain-of-thought. Give a concise user-facing explanation instead."""
    user = f"""Classify this email into exactly one category:
BL_COMPARISON = asks to compare/check/reconcile a Shipping Instruction and Bill of Lading or draft BL.
SI_REQUEST = primarily submits/requests/discusses a Shipping Instruction without an SI-vs-BL comparison.
INVOICE_QUERY = primarily about invoices, charges, billing or payment.
GENERAL = legitimate business email outside the categories above.
SPAM = unsolicited promotional, scam-like, irrelevant or obvious spam.

Return JSON:
{{
  "category": "BL_COMPARISON",
  "confidence": 0.0,
  "reason": "one-sentence result",
  "explanation": "2-3 concise sentences explaining the classification using observable email evidence",
  "evidence": ["observable clue 1", "observable clue 2"],
  "language": "English",
  "next_action": "what the operator should do next"
}}

Do not invent attachments or facts.

FROM:
{email.get("from", "")}

SUBJECT:
{email.get("subject", "")}

BODY:
{email.get("body", "")}

ATTACHMENTS:
{email.get("attachments", [])}
"""
    result = call_json(system, user)
    category = result.get("category")
    if category not in EMAIL_CATEGORIES:
        raise ValueError(f"Invalid email category: {result}")
    return {
        "category": category,
        "confidence": _confidence(result.get("confidence")),
        "reason": str(result.get("reason") or "").strip(),
        "explanation": str(result.get("explanation") or result.get("reason") or "").strip(),
        "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
        "language": str(result.get("language") or "unknown"),
        "next_action": str(result.get("next_action") or "").strip(),
    }
