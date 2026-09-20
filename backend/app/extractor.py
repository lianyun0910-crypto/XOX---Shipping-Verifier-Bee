from .ai_client import call_json

FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

DOCUMENT_TYPES = [
    "SI",
    "BL",
    "COMMERCIAL_INVOICE",
    "PACKING_LIST",
    "CERTIFICATE_OF_ORIGIN",
    "OTHER",
    "UNKNOWN",
]


def _confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number /= 100
    return max(0.0, min(1.0, number))


def extract_document(text: str, filename: str) -> dict:
    system = """You are a multilingual shipping document understanding engine.
Identify document type and fields by semantic meaning, not filenames or exact labels.
Never guess. If a value cannot be reliably determined, use null.
Return JSON only. Do not provide hidden chain-of-thought; provide concise evidence instead."""
    user = f"""Analyze this document.

Determine document_type and language, then extract the seven verification fields.
Document types: {DOCUMENT_TYPES}
Semantic equivalents include shipper/exporter/consignor; consignee/importer/receiver/buyer; notify/notify party; POL/loading port; POD/discharge port/destination; container quantity; gross weight/gross mass/gross wt.

Rules:
- company identity can remain equivalent despite address formatting or legal suffix differences
- container count must be an integer
- convert metric tonnes / MT / tons to kilograms
- do not confuse package count with container count
- do not confuse net weight with gross weight
- use null when absent or unreadable

Return JSON:
{{
  "document_type": "SI",
  "language": "English",
  "confidence": 0.0,
  "explanation": "short explanation of how the document was identified",
  "evidence": ["observable clue 1", "observable clue 2"],
  "shipment_reference": null,
  "booking_reference": null,
  "fields": {{
    "shipper": null,
    "consignee": null,
    "notify_party": null,
    "port_of_loading": null,
    "port_of_discharge": null,
    "container_count": null,
    "gross_weight_kg": null
  }}
}}

FILENAME:
{filename}

DOCUMENT TEXT:
{text}
"""
    result = call_json(system, user)
    dtype = result.get("document_type", "UNKNOWN")
    if dtype not in DOCUMENT_TYPES:
        dtype = "UNKNOWN"
    fields = result.get("fields") or {}
    return {
        "document_type": dtype,
        "language": result.get("language", "unknown"),
        "confidence": _confidence(result.get("confidence")),
        "explanation": str(result.get("explanation") or "").strip(),
        "evidence": result.get("evidence") if isinstance(result.get("evidence"), list) else [],
        "shipment_reference": result.get("shipment_reference"),
        "booking_reference": result.get("booking_reference"),
        "fields": {field: fields.get(field) for field in FIELDS},
    }
