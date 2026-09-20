import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from .email_reader import read_email
from .document_reader import read_document
from .classifier import classify_email
from .extractor import extract_document
from .comparator import compare_with_ai
from .excel_report import append_run

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
EMAIL_SUFFIXES = {".json", ".eml", ".msg"}
UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{32}_", re.IGNORECASE)
SI_SUFFIX_RE = re.compile(r"(?:[_\-\s])SI$", re.IGNORECASE)
BL_SUFFIX_RE = re.compile(r"(?:[_\-\s])BL$", re.IGNORECASE)

ProgressCallback = Callable[[int, int, Optional[dict], str], None]


def clean_filename(value: str) -> str:
    return UUID_PREFIX_RE.sub("", Path(str(value)).name)


def attachment_name(value) -> str:
    if isinstance(value, str):
        return clean_filename(value)
    if isinstance(value, dict):
        for key in ("filename", "name", "file", "path"):
            if value.get(key):
                return clean_filename(str(value[key]))
    return clean_filename(str(value))


def standalone_group_name(filename: str) -> str:
    stem = Path(clean_filename(filename)).stem.strip()
    stem = re.sub(r"[_\-\s]+(SI|BL)$", "", stem, flags=re.IGNORECASE)
    return stem.lower()


def find_attachment(name: str, uploaded_files: dict[str, Path]) -> Optional[Path]:
    base = attachment_name(name)
    if base in uploaded_files:
        return uploaded_files[base]
    for physical_name, path in uploaded_files.items():
        if clean_filename(physical_name).lower() == base.lower():
            return path
    candidate = UPLOAD_DIR / base
    if candidate.exists():
        return candidate.resolve()
    challenge = BASE_DIR / "challenge_data" / "attachments" / base
    if challenge.exists():
        return challenge.resolve()
    if UPLOAD_DIR.exists():
        for item in UPLOAD_DIR.rglob("*"):
            if item.is_file() and clean_filename(item.name).lower() == base.lower():
                return item.resolve()
    return None


def dedupe_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    out = []
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def extract_one(path: Path) -> dict:
    try:
        text = read_document(path)
        if not text.strip():
            return {
                "filename": clean_filename(path.name),
                "status": "NEEDS_REVIEW",
                "review_reason": "unreadable",
                "result": {"document_type": "UNKNOWN", "language": "unknown", "fields": {}},
            }
        extracted = extract_document(text, clean_filename(path.name))
        return {"filename": clean_filename(path.name), "status": "EXTRACTED", "result": extracted}
    except Exception as exc:
        return {
            "filename": clean_filename(path.name),
            "status": "NEEDS_REVIEW",
            "review_reason": "read_or_extraction_failed",
            "details": str(exc),
            "result": {"document_type": "UNKNOWN", "language": "unknown", "fields": {}},
        }


def pair_si_bl(documents: list[dict]):
    """
    Pair a Shipping Instruction (SI) with a Bill of Lading (BL).

    Primary signal:
        AI document classification.

    Fallback signal:
        Attachment filename. This is important for Gmail because filenames
        such as `email_001_SI.pdf` and `email_001_BL.pdf` can identify the
        document role even when the AI document classifier is uncertain.

    The function returns the best SI/BL pair or (None, None) when a safe pair
    cannot be established.
    """

    normalized_documents = []

    for document in documents:
        item = dict(document)
        result = dict(item.get("result") or {})

        filename = clean_filename(
            str(item.get("filename") or "")
        )

        document_type = str(
            result.get("document_type") or ""
        ).strip().upper()

        # ------------------------------------------------------------
        # AI result is already a usable SI / BL type.
        # ------------------------------------------------------------
        if document_type not in {"SI", "BL"}:
            stem = Path(filename).stem.strip()

            # Remove the last extension-like separators only for matching;
            # preserve the actual filename in the result.
            if SI_SUFFIX_RE.search(stem):
                document_type = "SI"
                result["document_type_source"] = "filename_fallback"
            elif BL_SUFFIX_RE.search(stem):
                document_type = "BL"
                result["document_type_source"] = "filename_fallback"
            elif re.match(r"^SI(?:[_\-\s]|$)", stem, re.IGNORECASE):
                document_type = "SI"
                result["document_type_source"] = "filename_fallback"
            elif re.match(r"^BL(?:[_\-\s]|$)", stem, re.IGNORECASE):
                document_type = "BL"
                result["document_type_source"] = "filename_fallback"

        if document_type in {"SI", "BL"}:
            result["document_type"] = document_type

        item["filename"] = filename
        item["result"] = result
        normalized_documents.append(item)

    si = [
        d for d in normalized_documents
        if str((d.get("result") or {}).get("document_type") or "").upper() == "SI"
    ]

    bl = [
        d for d in normalized_documents
        if str((d.get("result") or {}).get("document_type") or "").upper() == "BL"
    ]

    print("[Analyzer] Document pairing:")
    for document in normalized_documents:
        result = document.get("result") or {}
        print(
            "  "
            f"{document.get('filename', '')} -> "
            f"{result.get('document_type', 'UNKNOWN')} "
            f"({result.get('document_type_source', 'AI')})"
        )

    print(f"[Analyzer] SI candidates: {len(si)}")
    print(f"[Analyzer] BL candidates: {len(bl)}")

    if not si or not bl:
        return None, None

    def score(left, right):
        a = left.get("result") or {}
        b = right.get("result") or {}
        score_value = 0

        # Shared shipment / booking references are strong pairing signals.
        for key in ("shipment_reference", "booking_reference"):
            x = a.get(key)
            y = b.get(key)
            if x and y:
                if str(x).strip().upper() == str(y).strip().upper():
                    score_value += 20

        af = a.get("fields") or {}
        bf = b.get("fields") or {}

        # Match the common shipping fields to choose the correct pair when
        # multiple SI / BL files are present in the same email.
        for key in (
            "shipper",
            "consignee",
            "notify_party",
            "port_of_loading",
            "port_of_discharge",
            "container_count",
            "gross_weight_kg",
        ):
            x = af.get(key)
            y = bf.get(key)

            if x is None or y is None:
                continue

            x_text = str(x).strip().upper()
            y_text = str(y).strip().upper()

            if not x_text or not y_text:
                continue

            if x_text == y_text:
                score_value += 3
            elif x_text in y_text or y_text in x_text:
                score_value += 1

        # Same logical base filename is another useful tiebreaker:
        #   email_001_SI.pdf
        #   email_001_BL.pdf
        left_group = standalone_group_name(left.get("filename", ""))
        right_group = standalone_group_name(right.get("filename", ""))
        if left_group and right_group and left_group == right_group:
            score_value += 10

        return score_value

    candidates = [
        (score(a, b), a, b)
        for a in si
        for b in bl
    ]

    best = max(
        candidates,
        key=lambda x: x[0]
    )

    print(
        "[Analyzer] Selected pair: "
        f"SI={best[1].get('filename', '')} "
        f"BL={best[2].get('filename', '')} "
        f"score={best[0]}"
    )

    return best[1], best[2]


def analyze_email(email: dict, uploaded_files: dict[str, Path]) -> dict:
    classification = classify_email(email)
    result = {
        "filename": clean_filename(email.get("_filename", email.get("email_id", ""))),
        "email_id": email.get("email_id", ""),
        "from": email.get("from", ""),
        "subject": email.get("subject", ""),
        "language": classification.get("language", ""),
        "email_category": classification["category"],
        "category": classification["category"],
        "reason": classification.get("reason", ""),
        "explanation": classification.get("explanation", ""),
        "evidence": classification.get("evidence", []),
        "classification_confidence": classification.get("confidence", 0.0),
        "next_action": classification.get("next_action", ""),
        "status": "CLASSIFIED",
        "documents": [],
    }

    attachments = email.get("attachments") or []
    paths = []
    for attachment in attachments:
        path = find_attachment(attachment_name(attachment), uploaded_files)
        if path:
            paths.append(path)
    paths = dedupe_paths(paths)

    if classification["category"] in {"SPAM", "GENERAL", "INVOICE_QUERY"}:
        result["status"] = "OK"
        result["decision_confidence"] = float(classification.get("confidence") or 0.0)
        result["confidence"] = result["decision_confidence"]
        return result

    if not paths:
        result.update(
            status="NEEDS_REVIEW",
            decision_confidence=min(float(classification.get("confidence") or 0.0), 0.25),
            confidence=min(float(classification.get("confidence") or 0.0), 0.25),
            review_reason="missing_attachment",
            explanation="The email requires document verification, but no usable attachment was available to inspect.",
            next_action="Attach or open the required shipping document and verify it manually.",
        )
        return result

    with ThreadPoolExecutor(max_workers=1) as executor:
        documents = list(executor.map(extract_one, paths))

    result["documents"] = documents
    si, bl = pair_si_bl(documents)
    if not si or not bl:
        result.update(
            status="NEEDS_REVIEW",
            decision_confidence=min(float(classification.get("confidence") or 0.0), 0.40),
            confidence=min(float(classification.get("confidence") or 0.0), 0.40),
            review_reason="missing_si_or_bl",
            explanation="The required Shipping Instruction and Bill of Lading pair could not be established safely.",
            next_action="Check that both SI and BL/draft BL are present and readable.",
        )
        return result

    result.update(si_filename=si["filename"], bl_filename=bl["filename"], si=si, bl=bl)
    comparison = compare_with_ai(
        (si.get("result") or {}).get("fields") or {},
        (bl.get("result") or {}).get("fields") or {},
    )
    result["comparison"] = comparison
    result["status"] = comparison["status"]
    result["comparison_confidence"] = comparison.get("confidence", 0.0)
    result["decision_confidence"] = min(
        [
            float(result.get("classification_confidence") or 0.0),
            float(comparison.get("confidence") or 0.0),
            *[float((doc.get("result") or {}).get("confidence") or 0.0) for doc in documents],
        ]
    )
    result["confidence"] = result["decision_confidence"]
    result["explanation"] = comparison.get("explanation") or result.get("explanation", "")
    result["next_action"] = comparison.get("next_action") or result.get("next_action", "")
    if comparison.get("unresolved_fields"):
        result["review_reason"] = "missing_value"
    return result


def collect_email_attachment_names(email_paths: list[Path]) -> set[str]:
    names = set()
    for path in email_paths:
        try:
            email = read_email(path)
            for attachment in email.get("attachments") or []:
                name = attachment_name(attachment)
                if name:
                    names.add(name.lower())
        except Exception:
            continue
    return names


def group_standalone_documents(paths: list[Path]) -> dict[str, list[Path]]:
    groups = {}
    for path in paths:
        groups.setdefault(standalone_group_name(path.name), []).append(path)
    return groups


def analyze_standalone_group(group_name: str, paths: list[Path]) -> dict:
    with ThreadPoolExecutor(max_workers=1) as executor:
        documents = list(executor.map(extract_one, dedupe_paths(paths)))
    si, bl = pair_si_bl(documents)
    result = {
        "filename": group_name,
        "status": "CLASSIFIED",
        "category": "DOCUMENT_UPLOAD",
        "documents": documents,
    }
    if not si or not bl:
        result.update(
            status="NEEDS_REVIEW",
            review_reason="missing_si_or_bl",
            explanation="The required Shipping Instruction and Bill of Lading pair could not be established safely.",
            next_action="Check that both SI and BL/draft BL are present and readable.",
        )
        return result
    result.update(si_filename=si["filename"], bl_filename=bl["filename"], si=si, bl=bl)
    comparison = compare_with_ai(
        (si.get("result") or {}).get("fields") or {},
        (bl.get("result") or {}).get("fields") or {},
    )
    result["comparison"] = comparison
    result["status"] = comparison["status"]
    result["comparison_confidence"] = comparison.get("confidence", 0.0)
    result["decision_confidence"] = min(
        [
            float(comparison.get("confidence") or 0.0),
            *[float((doc.get("result") or {}).get("confidence") or 0.0) for doc in documents],
        ]
    )
    result["confidence"] = result["decision_confidence"]
    result["explanation"] = comparison.get("explanation") or result.get("explanation", "")
    result["next_action"] = comparison.get("next_action") or result.get("next_action", "")
    if comparison.get("unresolved_fields"):
        result["review_reason"] = "missing_value"
    return result


def build_analysis_cases(paths: list[Path]):
    uploaded_files = {path.name: path for path in paths}
    email_paths = [p for p in paths if p.suffix.lower() in EMAIL_SUFFIXES]
    document_paths = [p for p in paths if p.suffix.lower() not in EMAIL_SUFFIXES]
    attached_names = collect_email_attachment_names(email_paths)
    cases = [{"type": "email", "email_path": p} for p in email_paths]
    standalone = [p for p in document_paths if clean_filename(p.name).lower() not in attached_names]
    for group_name, group_paths in group_standalone_documents(dedupe_paths(standalone)).items():
        cases.append({"type": "standalone", "group_name": group_name, "paths": group_paths})
    return cases, uploaded_files


def analyze_case(case: dict, uploaded_files: dict[str, Path]) -> dict:
    if case["type"] == "email":
        path = case["email_path"]
        email = read_email(path)
        email["_filename"] = path.name
        email["_source_path"] = str(path)
        return analyze_email(email, uploaded_files)
    return analyze_standalone_group(case["group_name"], case["paths"])


def analyze_document_batch(paths: list[Path], progress_callback: Optional[ProgressCallback] = None) -> list[dict]:
    cases, uploaded_files = build_analysis_cases(paths)
    total = len(cases)
    if progress_callback:
        progress_callback(0, total, None, "processing")
    results = []
    for index, case in enumerate(cases, start=1):
        try:
            result = analyze_case(case, uploaded_files)
        except Exception as exc:
            label = case["email_path"].name if case["type"] == "email" else case["group_name"]
            result = {
                "filename": clean_filename(label),
                "status": "NEEDS_REVIEW",
                "category": "UNKNOWN" if case["type"] == "email" else "DOCUMENT_UPLOAD",
                "review_reason": "case_processing_failed",
                "details": str(exc),
                "documents": [],
            }
        results.append(result)
        if progress_callback:
            progress_callback(index, total, result, "processing")
    return results


def analyze_uploaded_batch(paths: list[Path], progress_callback: Optional[ProgressCallback] = None) -> dict:
    run_id = uuid.uuid4().hex
    results = analyze_document_batch(paths, progress_callback)
    if progress_callback:
        progress_callback(len(results), len(results), None, "generating_report")
    excel = append_run(run_id, "upload", results)
    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "summary": {
            "total": len(results),
            "ok": sum(r.get("status") == "OK" for r in results),
            "mismatch": sum(r.get("status") == "MISMATCH" for r in results),
            "needs_review": sum(r.get("status") == "NEEDS_REVIEW" for r in results),
        },
        "results": results,
        "excel": excel,
    }
