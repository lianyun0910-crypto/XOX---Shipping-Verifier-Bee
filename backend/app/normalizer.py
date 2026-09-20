import re
from typing import Any

FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

MISSING = {"", "???", "TBA", "TBC", "N/A", "NA", "NONE", "NULL", "UNKNOWN", "UNAVAILABLE", "-", "____", "______"}

def text(v: Any):
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v).replace("\u00a0", " ")).strip()
    if not s or s.upper() in MISSING:
        return None
    return s.upper()

def party(v):
    s = text(v)
    if not s:
        return None
    s = re.sub(r"[.,;]+$", "", s)
    s = re.sub(r"\s*&\s*", " AND ", s)
    return s

def port(v):
    s = text(v)
    if not s:
        return None
    return re.sub(r"\s+", " ", s.replace(" PORT", "")).strip()

def count(v):
    if v is None:
        return None
    m = re.search(r"\d[\d,]*", str(v))
    return int(m.group(0).replace(",", "")) if m else None

def weight(v):
    if v is None:
        return None
    s = str(v).upper().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(KG|KGS|MT|TON|TONNE|TONNES)?", s)
    if not m:
        return None
    n = float(m.group(1))
    if m.group(2) in {"MT", "TON", "TONNE", "TONNES"}:
        n *= 1000
    return n

def normalize_fields(fields: dict) -> dict:
    return {
        "shipper": party(fields.get("shipper")),
        "consignee": party(fields.get("consignee")),
        "notify_party": party(fields.get("notify_party")),
        "port_of_loading": port(fields.get("port_of_loading")),
        "port_of_discharge": port(fields.get("port_of_discharge")),
        "container_count": count(fields.get("container_count")),
        "gross_weight_kg": weight(fields.get("gross_weight_kg")),
    }
