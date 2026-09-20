import json
import threading
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
RECORD_DIR = BASE_DIR / "data" / "records"
REVIEW_PATH = RECORD_DIR / "review_queue.json"
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    if not REVIEW_PATH.exists():
        return {"cases": {}}
    try:
        value = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {"cases": {}}
        value.setdefault("cases", {})
        return value
    except Exception:
        return {"cases": {}}


def _save(value: dict) -> None:
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REVIEW_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(REVIEW_PATH)


def enqueue_reviews(run_id: str, source: str, results: list[dict]) -> list[dict]:
    created: list[dict] = []
    with _LOCK:
        db = _load()
        cases = db.setdefault("cases", {})
        for index, result in enumerate(results, start=1):
            if result.get("status") != "NEEDS_REVIEW":
                continue
            case_id = f"{run_id}-{index:04d}"
            existing = cases.get(case_id)
            if existing:
                continue
            case = {
                "case_id": case_id,
                "run_id": run_id,
                "source": source,
                "created_at": _now(),
                "status": "OPEN",
                "ai_status": result.get("status", "NEEDS_REVIEW"),
                "ai_confidence": result.get("decision_confidence", result.get("confidence")),
                "review_reason": result.get("review_reason", "ai_uncertain"),
                "subject": result.get("subject", ""),
                "filename": result.get("filename", ""),
                "result": result,
                "reviewer": "",
                "human_decision": None,
                "review_note": "",
                "reviewed_at": None,
            }
            cases[case_id] = case
            created.append(case)
        _save(db)
    return created


def list_reviews(status: str | None = "OPEN", limit: int = 100) -> list[dict]:
    with _LOCK:
        values = list(_load().get("cases", {}).values())
    if status and status.upper() != "ALL":
        values = [item for item in values if item.get("status") == status.upper()]
    values.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return values[: max(1, min(limit, 500))]


def get_review(case_id: str) -> dict | None:
    with _LOCK:
        return _load().get("cases", {}).get(case_id)


def resolve_review(case_id: str, decision: str, reviewer: str, note: str = "") -> dict:
    decision = decision.strip().upper()
    allowed = {"APPROVED", "MISMATCH_CONFIRMED", "REVIEW_REQUIRED"}
    if decision not in allowed:
        raise ValueError(f"Invalid review decision: {decision}")

    with _LOCK:
        db = _load()
        case = db.setdefault("cases", {}).get(case_id)
        if not case:
            raise KeyError(case_id)
        case["status"] = "RESOLVED" if decision != "REVIEW_REQUIRED" else "OPEN"
        case["human_decision"] = decision
        case["reviewer"] = reviewer.strip()[:200]
        case["review_note"] = note.strip()[:1000]
        case["reviewed_at"] = _now()
        if decision == "APPROVED":
            case["final_status"] = "APPROVED"
        elif decision == "MISMATCH_CONFIRMED":
            case["final_status"] = "MISMATCH"
        else:
            case["final_status"] = "NEEDS_REVIEW"
        _save(db)

    # Keep the shared Verification History synchronized with the human decision.
    try:
        from .storage import update_history_case
        update_history_case(
            case_id=case_id,
            final_status=case["final_status"],
            reviewer=case["reviewer"],
            review_note=case["review_note"],
            human_decision=case["human_decision"],
            reviewed_at=case["reviewed_at"],
        )
    except Exception:
        # Review data itself is already saved; history synchronization is best effort.
        pass

    return case
