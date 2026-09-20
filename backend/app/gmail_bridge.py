import base64
import html
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from .analyzer import analyze_email
from .classifier import classify_email
from .excel_report import append_run
from .gmail_oauth import (
    account_status,
    disconnect,
    finish_authorization,
    get_gmail_service,
    oauth_configured,
    start_authorization,
)
from .review_store import enqueue_reviews
from .storage import archive_run_to_cloud


router = APIRouter(
    prefix="/api/gmail",
    tags=["gmail"],
)


GMAIL_JOBS: dict[str, dict[str, Any]] = {}
GMAIL_LOCK = threading.Lock()

BASE_DIR = Path(__file__).resolve().parents[2]

GMAIL_RUN_DIR = (
    BASE_DIR
    / "data"
    / "records"
    / "gmail"
    / "runs"
)


DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
}

DOCUMENT_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
}


# ============================================================
# GENERAL HELPERS
# ============================================================


def _history_writer(
    run_id: str,
    source: str,
    results: list[dict],
    summary: dict,
) -> dict:

    from .storage import append_history

    return append_history(
        run_id,
        source,
        results,
        summary,
    )



def _update(
    job_id: str,
    **updates,
) -> None:

    with GMAIL_LOCK:

        if job_id in GMAIL_JOBS:

            GMAIL_JOBS[job_id].update(
                updates
            )



def _decode_base64url(
    value: str | None,
) -> bytes:

    if not value:
        return b""

    try:

        padding = "=" * (
            -len(value) % 4
        )

        return base64.urlsafe_b64decode(
            value + padding
        )

    except Exception:

        return b""



def _safe_filename(
    name: str,
) -> str:

    name = Path(
        str(name or "")
    ).name

    name = re.sub(
        r"[^A-Za-z0-9._()\- ]+",
        "_",
        name,
    ).strip()

    return name or "attachment.bin"



def _strip_html(
    value: str,
) -> str:

    value = re.sub(
        r"<br\s*/?>",
        "\n",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"</p\s*>",
        "\n",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    return html.unescape(
        value
    )



def _normalise_subject(
    value: str,
) -> str:

    value = str(
        value or ""
    ).strip().lower()

    value = re.sub(
        r"^(?:(?:re|fw|fwd)\s*:\s*)+",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value



def _header(
    headers: list[dict],
    name: str,
) -> str:

    wanted = name.lower()

    for item in headers or []:

        if (
            str(
                item.get(
                    "name",
                    "",
                )
            ).lower()
            == wanted
        ):

            return str(
                item.get(
                    "value",
                    "",
                )
            )

    return ""



def _payload_headers(
    message: dict,
) -> list[dict]:

    return (
        message.get(
            "payload"
        )
        or {}
    ).get(
        "headers"
    ) or []



def _message_subject(
    message: dict,
) -> str:

    return _header(
        _payload_headers(message),
        "Subject",
    )



def _message_attachments(
    message: dict,
) -> list[dict]:

    found: list[dict] = []

    def walk(
        part: dict,
    ) -> None:

        if not isinstance(
            part,
            dict,
        ):

            return

        filename = str(
            part.get(
                "filename"
            )
            or ""
        ).strip()

        body = (
            part.get(
                "body"
            )
            or {}
        )

        mime = str(
            part.get(
                "mimeType"
            )
            or "application/octet-stream"
        )

        if filename:

            found.append({
                "filename": filename,
                "mime_type": mime,
                "attachment_id": body.get(
                    "attachmentId"
                ),
                "data": body.get(
                    "data"
                ),
                "size": body.get(
                    "size",
                    0,
                ),
            })

        for child in (
            part.get(
                "parts"
            )
            or []
        ):

            walk(child)

    walk(
        message.get(
            "payload"
        )
        or {}
    )

    return found



def _extract_message_text(
    message: dict,
) -> str:

    text_parts: list[str] = []

    def walk(
        part: dict,
    ) -> None:

        if not isinstance(
            part,
            dict,
        ):

            return

        filename = str(
            part.get(
                "filename"
            )
            or ""
        ).strip()

        if filename:

            return

        mime = str(
            part.get(
                "mimeType"
            )
            or ""
        ).lower()

        body = (
            part.get(
                "body"
            )
            or {}
        )

        data = body.get(
            "data"
        )

        if (
            data
            and mime in {
                "text/plain",
                "text/html",
            }
        ):

            decoded = _decode_base64url(
                data
            ).decode(
                "utf-8",
                errors="replace",
            )

            if mime == "text/html":
                decoded = _strip_html(
                    decoded
                )

            if decoded.strip():
                text_parts.append(
                    decoded
                )

        for child in (
            part.get(
                "parts"
            )
            or []
        ):

            walk(child)

    walk(
        message.get(
            "payload"
        )
        or {}
    )

    return "\n\n".join(
        text_parts
    ).strip()



def _is_document_attachment(
    attachment: dict,
) -> bool:

    filename = str(
        attachment.get(
            "filename"
        )
        or ""
    ).lower()

    mime = str(
        attachment.get(
            "mime_type"
        )
        or ""
    ).lower()

    return (
        Path(filename).suffix.lower()
        in DOCUMENT_EXTENSIONS
        or
        mime in DOCUMENT_MIMES
    )


# ============================================================
# THREAD MESSAGE SELECTION
# ============================================================


def _message_score(
    message: dict,
    requested_subject: str,
    requested_body: str,
) -> int:

    score = 0

    subject = _message_subject(
        message
    )

    wanted = _normalise_subject(
        requested_subject
    )

    actual = _normalise_subject(
        subject
    )

    # --------------------------------------------------------
    # Subject similarity
    # --------------------------------------------------------

    if wanted and actual:

        if actual == wanted:
            score += 120

        elif (
            wanted in actual
            or actual in wanted
        ):

            score += 70

    # --------------------------------------------------------
    # Attachments are very strong evidence
    # --------------------------------------------------------

    attachments = _message_attachments(
        message
    )

    if attachments:
        score += 100

    document_count = sum(
        _is_document_attachment(item)
        for item in attachments
    )

    score += document_count * 40

    # --------------------------------------------------------
    # SI / BL filename hints
    # --------------------------------------------------------

    si_found = False
    bl_found = False

    for item in attachments:

        filename = str(
            item.get(
                "filename"
            )
            or ""
        ).lower()

        if re.search(
            r"(^|[_\-\s])si([_\-\s.]|$)",
            filename,
        ):
            si_found = True

        if re.search(
            r"(^|[_\-\s])bl([_\-\s.]|$)",
            filename,
        ):
            bl_found = True

    if si_found:
        score += 50

    if bl_found:
        score += 50

    if si_found and bl_found:
        score += 100

    # --------------------------------------------------------
    # Body hint
    # --------------------------------------------------------

    requested = re.sub(
        r"\s+",
        " ",
        str(
            requested_body
            or ""
        ).strip().lower(),
    )

    if requested:

        requested = requested[:150]

        message_text = _extract_message_text(
            message
        ).lower()

        if requested[:70] in message_text:
            score += 30

    # --------------------------------------------------------
    # Newer message as small tiebreaker
    # --------------------------------------------------------

    try:

        timestamp = int(
            message.get(
                "internalDate",
                "0",
            )
            or 0
        )

        score += min(
            timestamp // 10_000_000_000,
            20,
        )

    except Exception:
        pass

    return score



def _select_message_from_thread(
    thread: dict,
    requested_subject: str,
    requested_body: str,
) -> dict:

    messages = (
        thread.get(
            "messages"
        )
        or []
    )

    if not messages:
        raise RuntimeError(
            "Gmail thread contains no messages."
        )

    scored: list[tuple[int, dict]] = []

    for message in messages:

        score = _message_score(
            message,
            requested_subject,
            requested_body,
        )

        attachments = _message_attachments(
            message
        )

        print(
            "[Gmail] Thread candidate:"
        )
        print(
            f"  id={message.get('id', '')}"
        )
        print(
            f"  subject={_message_subject(message)}"
        )
        print(
            f"  attachments={len(attachments)}"
        )

        if attachments:

            print(
                "  files="
                + ", ".join(
                    str(
                        item.get(
                            "filename",
                            "",
                        )
                    )
                    for item in attachments
                )
            )

        print(
            f"  score={score}"
        )

        scored.append(
            (
                score,
                message,
            )
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return scored[0][1]


# ============================================================
# DOWNLOAD REAL GMAIL ATTACHMENTS
# ============================================================


def _download_gmail_attachment(
    service,
    message_id: str,
    attachment: dict,
) -> bytes:

    inline = attachment.get(
        "data"
    )

    if inline:

        data = _decode_base64url(
            inline
        )

        if data:
            return data

    attachment_id = attachment.get(
        "attachment_id"
    )

    if not attachment_id:
        return b""

    result = (
        service
        .users()
        .messages()
        .attachments()
        .get(
            userId="me",
            messageId=message_id,
            id=attachment_id,
        )
        .execute()
    )

    return _decode_base64url(
        result.get(
            "data"
        )
    )


# ============================================================
# GMAIL API SEARCH FALLBACK
# ============================================================


def _extract_email_address(value: str) -> str:

    match = re.search(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        str(value or ""),
        flags=re.IGNORECASE,
    )

    return match.group(0) if match else ""


def _search_gmail_by_subject_and_sender(
    service,
    requested_subject: str,
    requested_from: str,
    requested_body: str,
) -> dict | None:

    subject = _normalise_subject(requested_subject)
    sender = _extract_email_address(requested_from)

    queries: list[str] = []

    if subject:
        safe_subject = subject.replace('"', "'").strip()
        if sender:
            queries.append(
                f'subject:"{safe_subject}" from:"{sender}"'
            )
        queries.append(
            f'subject:"{safe_subject}"'
        )

    if sender:
        queries.append(
            f'from:"{sender}"'
        )

    # Keep the fallback bounded and deterministic.
    seen_queries: set[str] = set()
    candidates: list[tuple[int, dict]] = []

    for query in queries:

        if query in seen_queries:
            continue

        seen_queries.add(query)

        print(
            "[Gmail] API search fallback:"
        )
        print(
            f"  q={query}"
        )

        try:

            response = (
                service
                .users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=20,
                )
                .execute()
            )

        except Exception as exc:

            print(
                "[Gmail] API search failed: "
                f"{exc}"
            )
            continue

        for item in response.get("messages") or []:

            candidate_id = str(
                item.get("id") or ""
            ).strip()

            if not candidate_id:
                continue

            try:

                candidate = (
                    service
                    .users()
                    .messages()
                    .get(
                        userId="me",
                        id=candidate_id,
                        format="full",
                    )
                    .execute()
                )

            except Exception as exc:

                print(
                    "[Gmail] Candidate fetch failed: "
                    f"{exc}"
                )
                continue

            score = _message_score(
                candidate,
                requested_subject,
                requested_body,
            )

            actual_from = _header(
                _payload_headers(candidate),
                "From",
            )

            if sender and sender.lower() in actual_from.lower():
                score += 50

            attachments = _message_attachments(
                candidate
            )

            if attachments:
                score += 150

            print(
                "[Gmail] Search candidate:"
            )
            print(
                f"  id={candidate.get('id', '')}"
            )
            print(
                f"  subject={_message_subject(candidate)}"
            )
            print(
                f"  from={actual_from}"
            )
            print(
                f"  attachments={len(attachments)}"
            )
            print(
                f"  score={score}"
            )

            candidates.append(
                (score, candidate)
            )

        # If a query found strong shipping candidates, stop expanding
        # to broader queries.  This avoids selecting an unrelated message.
        if candidates:
            best_score = max(item[0] for item in candidates)
            if best_score >= 250:
                break

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


# ============================================================
# REAL GMAIL FETCH
# ============================================================


def fetch_gmail_message(
    input_email: dict,
    run_id: str,
    index: int,
) -> tuple[dict, list[Path]]:

    service = get_gmail_service()

    requested_message_id = str(
        input_email.get(
            "gmail_message_id"
        )
        or input_email.get(
            "message_id"
        )
        or ""
    ).strip()

    requested_thread_id = str(
        input_email.get(
            "gmail_thread_id"
        )
        or input_email.get(
            "thread_id"
        )
        or ""
    ).strip()

    # Chrome/Gmail DOM often supplies a synthetic email_id such as
    # "gmail-<timestamp>-<random>".  That is useful as an app-level
    # identifier but it is NOT a valid Gmail API message/thread ID.
    # Never send that synthetic value to the Gmail API.
    if requested_message_id.startswith("gmail-"):
        requested_message_id = ""

    if requested_thread_id.startswith("gmail-"):
        requested_thread_id = ""

    requested_subject = str(
        input_email.get(
            "subject"
        )
        or ""
    )

    requested_body = str(
        input_email.get(
            "body"
        )
        or ""
    )

    message: dict | None = None
    message_id = ""
    thread_id = ""

    # ========================================================
    # EXACT MESSAGE ID
    # ========================================================

    if requested_message_id:

        print(
            "[Gmail] Fetching exact Gmail message:"
        )
        print(
            f"  message_id={requested_message_id}"
        )

        try:

            message = (
                service
                .users()
                .messages()
                .get(
                    userId="me",
                    id=requested_message_id,
                    format="full",
                )
                .execute()
            )

        except Exception as exc:

            print(
                "[Gmail] Exact message lookup failed: "
                f"{exc}"
            )

            message = None

        if message:

            message_id = str(
                message.get(
                    "id",
                    requested_message_id,
                )
            )

            thread_id = str(
                message.get(
                    "threadId",
                    "",
                )
            )

    # ========================================================
    # THREAD ID
    # ========================================================

    if message is None and requested_thread_id:

        print(
            "[Gmail] Fetching Gmail thread:"
        )
        print(
            f"  thread_id={requested_thread_id}"
        )

        try:

            thread = (
                service
                .users()
                .threads()
                .get(
                    userId="me",
                    id=requested_thread_id,
                    format="full",
                )
                .execute()
            )

        except Exception as exc:

            print(
                "[Gmail] Thread lookup failed: "
                f"{exc}"
            )

            thread = None

        if thread:

            messages = (
                thread.get(
                    "messages"
                )
                or []
            )

            print(
                f"[Gmail] Thread contains "
                f"{len(messages)} message(s)."
            )

            message = _select_message_from_thread(
                thread,
                requested_subject,
                requested_body,
            )

            message_id = str(
                message.get(
                    "id",
                    "",
                )
            )

            thread_id = str(
                thread.get(
                    "id",
                    requested_thread_id,
                )
            )

    # ========================================================
    # SEARCH FALLBACK FOR SYNTHETIC / MISSING IDs
    # ========================================================

    if message is None:

        print(
            "[Gmail] No valid Gmail API ID was supplied. "
            "Searching Gmail by subject/sender instead."
        )

        message = _search_gmail_by_subject_and_sender(
            service,
            requested_subject,
            input_email.get("from", ""),
            requested_body,
        )

        if message:

            message_id = str(
                message.get(
                    "id",
                    "",
                )
            )

            thread_id = str(
                message.get(
                    "threadId",
                    "",
                )
            )

            print(
                "[Gmail] Search fallback selected message:"
            )
            print(
                f"  message_id={message_id}"
            )
            print(
                f"  thread_id={thread_id}"
            )

    if message is None:

        raise RuntimeError(
            "Unable to fetch the Gmail message. "
            "The supplied Gmail ID is not a valid message or thread ID."
        )

    # ========================================================
    # READ MESSAGE
    # ========================================================

    headers = _payload_headers(
        message
    )

    subject = (
        _header(
            headers,
            "Subject",
        )
        or requested_subject
        or "Gmail email"
    )

    sender = _header(
        headers,
        "From",
    ) or str(
        input_email.get(
            "from"
        )
        or ""
    )

    recipient = _header(
        headers,
        "To",
    ) or str(
        input_email.get(
            "to"
        )
        or ""
    )

    body = (
        _extract_message_text(
            message
        )
        or requested_body
    )

    attachments = _message_attachments(
        message
    )

    print(
        "[Gmail] Selected message:"
    )
    print(
        f"  message_id={message_id}"
    )
    print(
        f"  thread_id={thread_id}"
    )
    print(
        f"  subject={subject}"
    )
    print(
        f"  attachment_count={len(attachments)}"
    )

    for item in attachments:

        print(
            "  attachment="
            + str(
                item.get(
                    "filename",
                    "",
                )
            )
        )

    # ========================================================
    # SAVE ATTACHMENTS
    # ========================================================

    case_dir = (
        GMAIL_RUN_DIR
        / run_id
        / f"case_{index:04d}"
    )

    case_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    saved_paths: list[Path] = []
    attachment_details: list[dict] = []

    for attachment_index, item in enumerate(
        attachments,
        start=1,
    ):

        original_filename = str(
            item.get(
                "filename",
                f"attachment_{attachment_index}",
            )
        )

        filename = _safe_filename(
            original_filename
        )

        target = (
            case_dir
            / filename
        )

        if target.exists():

            stem = target.stem
            suffix = target.suffix

            target = (
                case_dir
                / f"{stem}_{attachment_index}{suffix}"
            )

        print(
            "[Gmail] Downloading attachment:"
        )
        print(
            f"  {filename}"
        )

        try:

            content = _download_gmail_attachment(
                service,
                message_id,
                item,
            )

        except Exception as exc:

            print(
                "[Gmail] Attachment download failed:"
            )
            print(
                f"  file={filename}"
            )
            print(
                f"  error={exc}"
            )

            attachment_details.append({
                "filename": filename,
                "mime_type": item.get(
                    "mime_type",
                    "",
                ),
                "downloaded": False,
                "error": str(exc),
            })

            continue

        if not content:

            print(
                "[Gmail] Attachment returned empty data:"
            )
            print(
                f"  file={filename}"
            )

            attachment_details.append({
                "filename": filename,
                "mime_type": item.get(
                    "mime_type",
                    "",
                ),
                "downloaded": False,
                "error": "Empty attachment data.",
            })

            continue

        if len(content) > 30 * 1024 * 1024:

            attachment_details.append({
                "filename": filename,
                "mime_type": item.get(
                    "mime_type",
                    "",
                ),
                "downloaded": False,
                "error": "Attachment exceeds 30 MB demo limit.",
            })

            print(
                "[Gmail] Attachment exceeds 30 MB limit:"
            )
            print(
                f"  file={filename}"
            )

            continue

        target.write_bytes(
            content
        )

        saved_paths.append(
            target
        )

        attachment_details.append({
            "filename": target.name,
            "mime_type": item.get(
                "mime_type",
                "",
            ),
            "downloaded": True,
            "local_path": str(target),
            "size": len(content),
        })

        print(
            "[Gmail] Attachment saved:"
        )
        print(
            f"  {target}"
        )
        print(
            f"  size={len(content)} bytes"
        )

    # ========================================================
    # NORMALIZED EMAIL FOR ANALYZER
    # ========================================================

    normalized_email = {
        "email_id": message_id or thread_id,
        "gmail_message_id": message_id,
        "gmail_thread_id": thread_id,
        "message_id": message_id,
        "thread_id": thread_id,
        "from": sender,
        "to": recipient,
        "subject": subject,
        "body": body[:30000],
        "attachments": [
            item["filename"]
            for item in attachment_details
            if item.get(
                "downloaded"
            )
        ],
        "attachment_details": attachment_details,
        "source": "gmail_oauth",
        "gmail_url": (
            f"https://mail.google.com/mail/u/0/#all/{message_id}"
            if message_id
            else str(
                input_email.get(
                    "gmail_url"
                )
                or ""
            )
        ),
    }

    print(
        "[Gmail] Download summary:"
    )
    print(
        f"  downloaded={len(saved_paths)}"
    )

    return (
        normalized_email,
        saved_paths,
    )


# ============================================================
# RESULT DECORATION
# ============================================================


def _decorate_result(
    result: dict,
    email: dict,
    case_id: str,
    run_id: str,
    attachment_paths: list[Path],
) -> dict:

    result = dict(
        result
    )

    result["source"] = "gmail"
    result["run_id"] = run_id
    result["case_id"] = case_id

    result["gmail_message_id"] = email.get(
        "gmail_message_id",
        "",
    )

    result["gmail_thread_id"] = email.get(
        "gmail_thread_id",
        "",
    )

    result["message_id"] = email.get(
        "message_id",
        "",
    )

    result["thread_id"] = email.get(
        "thread_id",
        "",
    )

    result["gmail_url"] = email.get(
        "gmail_url",
        "",
    )

    result["attachment_details"] = email.get(
        "attachment_details",
        [],
    )

    result["attachment_count"] = len(
        attachment_paths
    )

    classification_confidence = result.get(
        "classification_confidence"
    )

    comparison_confidence = (
        result.get(
            "comparison"
        )
        or {}
    ).get(
        "confidence"
    )

    document_confidences = []

    for doc in result.get(
        "documents"
    ) or []:

        value = (
            doc.get(
                "result"
            )
            or {}
        ).get(
            "confidence"
        )

        if value is not None:

            try:
                document_confidences.append(
                    float(value)
                )
            except Exception:
                pass

    candidates = []

    for value in [
        classification_confidence,
        comparison_confidence,
        *document_confidences,
    ]:

        if value is None:
            continue

        try:
            candidates.append(
                float(value)
            )
        except Exception:
            continue

    if candidates:

        result["decision_confidence"] = max(
            0.0,
            min(candidates),
        )

        result["confidence"] = result[
            "decision_confidence"
        ]

    return result


# ============================================================
# SINGLE CASE PROCESSING
# ============================================================


def _process_one(
    input_email: dict,
    run_id: str,
    index: int,
) -> tuple[dict, list[Path]]:

    case_id = (
        f"{run_id}-{index:04d}"
    )

    print(
        "=" * 70
    )
    print(
        f"[Gmail] Processing case {case_id}"
    )
    print(
        f"[Gmail] Subject: "
        f"{input_email.get('subject', '')}"
    )
    print(
        f"[Gmail] email_id: "
        f"{input_email.get('email_id', '')}"
    )
    print(
        "=" * 70
    )

    try:

        email, attachment_paths = fetch_gmail_message(
            input_email,
            run_id,
            index,
        )

        print(
            "[Gmail] Real attachments available:"
        )

        for path in attachment_paths:
            print(
                f"  -> {path}"
            )

        # ----------------------------------------------------
        # Analyzer receives actual local files.
        # ----------------------------------------------------

        uploaded_files = {
            path.name: path
            for path in attachment_paths
        }

        result = analyze_email(
            email,
            uploaded_files,
        )

        result = _decorate_result(
            result,
            email,
            case_id,
            run_id,
            attachment_paths,
        )

        print(
            "[Gmail] Final verification status: "
            f"{result.get('status', 'UNKNOWN')}"
        )

        if result.get(
            "si_filename"
        ):

            print(
                "[Gmail] SI: "
                f"{result.get('si_filename')}"
            )

        if result.get(
            "bl_filename"
        ):

            print(
                "[Gmail] BL: "
                f"{result.get('bl_filename')}"
            )

        if result.get(
            "comparison"
        ):

            print(
                "[Gmail] Comparison status: "
                f"{result['comparison'].get('status', '')}"
            )

        return result, attachment_paths

    except Exception as exc:

        print(
            "[Gmail] CASE FAILED:"
        )
        print(
            f"  error={exc}"
        )

        result = {
            "case_id": case_id,
            "run_id": run_id,
            "filename": input_email.get(
                "subject"
            ) or f"Gmail email {index}",
            "email_id": input_email.get(
                "email_id",
                f"gmail-{index}",
            ),
            "gmail_message_id": input_email.get(
                "gmail_message_id",
                "",
            ),
            "gmail_thread_id": input_email.get(
                "gmail_thread_id"
            ) or input_email.get(
                "thread_id",
                "",
            ),
            "message_id": input_email.get(
                "message_id",
                "",
            ),
            "thread_id": input_email.get(
                "thread_id",
                "",
            ),
            "from": input_email.get(
                "from",
                "",
            ),
            "subject": input_email.get(
                "subject",
                "",
            ),
            "category": "UNKNOWN",
            "email_category": "UNKNOWN",
            "language": "",
            "status": "NEEDS_REVIEW",
            "confidence": 0.0,
            "decision_confidence": 0.0,
            "review_reason": "gmail_fetch_or_verification_failed",
            "reason": "The Gmail message or its attachments could not be fully verified.",
            "explanation": "The system could not safely fetch or process the Gmail message and its shipping documents, so a human review is required.",
            "next_action": "Open the Gmail message and verify the SI and BL documents manually.",
            "details": str(exc),
            "source": "gmail",
        }

        return result, []


# ============================================================
# PROCESS BATCH
# ============================================================


def _process_batch_sync(
    emails: list[dict],
) -> dict:

    run_id = (
        f"gmail-{uuid.uuid4().hex}"
    )

    results: list[dict] = []
    source_paths: list[Path] = []

    total = len(
        emails
    )

    print(
        "[Gmail] =================================================="
    )
    print(
        f"[Gmail] START BATCH run_id={run_id} total={total}"
    )
    print(
        "[Gmail] =================================================="
    )

    for index, input_email in enumerate(
        emails,
        start=1,
    ):

        result, attachment_paths = _process_one(
            input_email,
            run_id,
            index,
        )

        source_paths.extend(
            attachment_paths
        )

        results.append(
            result
        )

    summary = {
        "total": len(results),
        "ok": sum(
            r.get("status") == "OK"
            for r in results
        ),
        "mismatch": sum(
            r.get("status") == "MISMATCH"
            for r in results
        ),
        "needs_review": sum(
            r.get("status") == "NEEDS_REVIEW"
            for r in results
        ),
        "documents_processed": sum(
            len(
                r.get(
                    "documents"
                )
                or []
            )
            for r in results
        ),
        "fields_compared": sum(
            len(
                (
                    r.get(
                        "comparison"
                    )
                    or {}
                ).get(
                    "fields"
                )
                or {}
            )
            for r in results
        ),
        "attachments_downloaded": len(
            source_paths
        ),
    }

    print(
        "[Gmail] Batch summary:"
    )
    print(
        f"  total={summary['total']}"
    )
    print(
        f"  OK={summary['ok']}"
    )
    print(
        f"  MISMATCH={summary['mismatch']}"
    )
    print(
        f"  NEEDS_REVIEW={summary['needs_review']}"
    )
    print(
        f"  attachments={summary['attachments_downloaded']}"
    )

    history = _history_writer(
        run_id,
        "gmail",
        results,
        summary,
    )

    print(
        "[Gmail History] SUCCESS"
    )

    review_cases = enqueue_reviews(
        run_id,
        "gmail",
        results,
    )

    excel = append_run(
        run_id,
        "gmail",
        results,
    )

    try:

        cloud = archive_run_to_cloud(
            run_id,
            results,
            summary,
            source_paths,
            source="gmail",
        )

    except Exception as exc:

        cloud = {
            "enabled": True,
            "uploaded": False,
            "error": str(exc),
        }

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "summary": summary,
        "results": results,
        "history": history,
        "review_cases": review_cases,
        "excel": excel,
        "cloud_archive": cloud,
    }


# ============================================================
# BACKGROUND JOB
# ============================================================


def _run_batch(
    job_id: str,
    emails: list[dict],
) -> None:

    _update(
        job_id,
        status="PROCESSING",
        phase="processing",
    )

    try:

        final = _process_batch_sync(
            emails
        )

        _update(
            job_id,
            status="COMPLETED",
            phase="completed",
            progress=100,
            processed=len(emails),
            total=len(emails),
            results=final[
                "results"
            ],
            summary=final[
                "summary"
            ],
            run_id=final[
                "run_id"
            ],
            history=final[
                "history"
            ],
            review_cases=final[
                "review_cases"
            ],
            excel=final[
                "excel"
            ],
            cloud=final[
                "cloud_archive"
            ],
            completed_at=time.time(),
            current_subject="",
        )

    except Exception as exc:

        _update(
            job_id,
            status="ERROR",
            phase="error",
            error=str(exc),
        )


# ============================================================
# OAUTH ROUTES
# ============================================================


@router.get(
    "/oauth/start"
)
def gmail_oauth_start():

    if not oauth_configured():

        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth is not configured. "
                "Add GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET to backend/.env."
            ),
        )

    try:

        return RedirectResponse(
            start_authorization()
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@router.get(
    "/oauth/callback"
)
def gmail_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):

    frontend = (
        __import__(
            "os"
        ).getenv(
            "FRONTEND_URL",
            "http://localhost:5173",
        ).strip()
        or "http://localhost:5173"
    )

    if error:

        return RedirectResponse(
            f"{frontend}/?gmail=error&reason={error}"
        )

    if not code or not state:

        return RedirectResponse(
            f"{frontend}/?gmail=error&reason=missing_code_or_state"
        )

    try:

        result = finish_authorization(
            code,
            state,
        )

        return RedirectResponse(
            f"{frontend}/?gmail=connected&email={result.get('email', '')}"
        )

    except Exception as exc:

        return RedirectResponse(
            f"{frontend}/?gmail=error&reason={str(exc)[:180]}"
        )


@router.get(
    "/account"
)
def gmail_account():
    return account_status()


@router.get(
    "/status"
)
def gmail_account_status():
    return account_status()


@router.post(
    "/disconnect"
)
def gmail_disconnect():

    disconnect()

    return {
        "connected": False
    }


# ============================================================
# GMAIL MESSAGE LIST / READ
# ============================================================


@router.get(
    "/messages"
)
def list_gmail_messages(
    max_results: int = 20,
    query: str = "",
):

    if not account_status().get(
        "connected"
    ):

        raise HTTPException(
            status_code=401,
            detail="Gmail is not connected.",
        )

    max_results = max(
        1,
        min(
            max_results,
            50,
        ),
    )

    try:

        service = get_gmail_service()

        response = (
            service
            .users()
            .messages()
            .list(
                userId="me",
                q=query or None,
                maxResults=max_results,
            )
            .execute()
        )

        messages = []

        for item in (
            response.get(
                "messages"
            )
            or []
        ):

            message = (
                service
                .users()
                .messages()
                .get(
                    userId="me",
                    id=item["id"],
                    format="metadata",
                    metadataHeaders=[
                        "Subject",
                        "From",
                        "To",
                        "Date",
                    ],
                )
                .execute()
            )

            headers = _payload_headers(
                message
            )

            messages.append({
                "id": message.get(
                    "id",
                    "",
                ),
                "threadId": message.get(
                    "threadId",
                    "",
                ),
                "subject": _header(
                    headers,
                    "Subject",
                ),
                "from": _header(
                    headers,
                    "From",
                ),
                "to": _header(
                    headers,
                    "To",
                ),
                "date": _header(
                    headers,
                    "Date",
                ),
            })

        return {
            "messages": messages,
            "next_page_token": response.get(
                "nextPageToken"
            ),
        }

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@router.get(
    "/messages/{message_id}"
)
def get_gmail_message_route(
    message_id: str,
):

    if not account_status().get(
        "connected"
    ):

        raise HTTPException(
            status_code=401,
            detail="Gmail is not connected.",
        )

    try:

        service = get_gmail_service()

        message = (
            service
            .users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

        headers = _payload_headers(
            message
        )

        attachments = _message_attachments(
            message
        )

        return {
            "id": message.get(
                "id",
                "",
            ),
            "thread_id": message.get(
                "threadId",
                "",
            ),
            "subject": _header(
                headers,
                "Subject",
            ),
            "from": _header(
                headers,
                "From",
            ),
            "to": _header(
                headers,
                "To",
            ),
            "date": _header(
                headers,
                "Date",
            ),
            "body": _extract_message_text(
                message
            ),
            "attachments": [
                {
                    "filename": item.get(
                        "filename",
                        "",
                    ),
                    "mime_type": item.get(
                        "mime_type",
                        "",
                    ),
                    "size": item.get(
                        "size",
                        0,
                    ),
                }
                for item in attachments
            ],
        }

    except Exception as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )


# ============================================================
# MAIN GMAIL VERIFICATION
# ============================================================


@router.post(
    "/classify-batch"
)
def classify_gmail_batch(
    payload: dict,
):

    emails = payload.get(
        "emails"
    )

    if not isinstance(
        emails,
        list,
    ) or not emails:

        raise HTTPException(
            status_code=400,
            detail="emails must be a non-empty list",
        )

    if len(emails) > 50:

        raise HTTPException(
            status_code=400,
            detail="A Gmail batch can contain at most 50 emails.",
        )

    if not account_status().get(
        "connected"
    ):

        raise HTTPException(
            status_code=401,
            detail="Gmail is not connected. Click Connect Gmail first.",
        )

    try:

        # IMPORTANT:
        # The browser extension sends mainly Gmail thread IDs.
        # This function now fetches the REAL Gmail message and
        # downloads its actual attachments before analysis.
        return _process_batch_sync(
            emails
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Gmail verification failed: {exc}",
        )


@router.post(
    "/analyze-message"
)
def analyze_gmail_message(
    payload: dict,
):

    if not isinstance(
        payload,
        dict,
    ):

        raise HTTPException(
            status_code=400,
            detail="Email payload must be an object.",
        )

    if not account_status().get(
        "connected"
    ):

        raise HTTPException(
            status_code=401,
            detail="Gmail is not connected.",
        )

    try:

        result = _process_batch_sync(
            [payload]
        )

        return result

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Gmail message analysis failed: {exc}",
        )


# ============================================================
# LONG-RUNNING GMAIL BATCH
# ============================================================


@router.post(
    "/analyze-batch"
)
def analyze_gmail_batch(
    payload: dict,
):

    emails = payload.get(
        "emails"
    )

    if not isinstance(
        emails,
        list,
    ) or not emails:

        raise HTTPException(
            status_code=400,
            detail="emails must be a non-empty list",
        )

    if len(emails) > 50:

        raise HTTPException(
            status_code=400,
            detail="A Gmail batch can contain at most 50 emails.",
        )

    if not account_status().get(
        "connected"
    ):

        raise HTTPException(
            status_code=401,
            detail="Gmail is not connected.",
        )

    job_id = uuid.uuid4().hex

    with GMAIL_LOCK:

        GMAIL_JOBS[
            job_id
        ] = {
            "job_id": job_id,
            "status": "QUEUED",
            "phase": "queued",
            "progress": 0,
            "processed": 0,
            "total": len(emails),
            "results": [],
            "summary": None,
            "error": "",
        }

    threading.Thread(
        target=_run_batch,
        args=(
            job_id,
            emails,
        ),
        daemon=True,
    ).start()

    return {
        "job_id": job_id,
        "status": "QUEUED",
        "total": len(emails),
    }


@router.get(
    "/job-status/{job_id}"
)
def gmail_job_status_alias(
    job_id: str,
):

    with GMAIL_LOCK:

        job = GMAIL_JOBS.get(
            job_id
        )

        if not job:

            raise HTTPException(
                status_code=404,
                detail="Gmail job not found.",
            )

        return dict(
            job
        )


@router.get(
    "/status/{job_id}"
)
def gmail_status(
    job_id: str,
):

    with GMAIL_LOCK:

        job = GMAIL_JOBS.get(
            job_id
        )

        if not job:

            raise HTTPException(
                status_code=404,
                detail="Gmail job not found.",
            )

        return dict(
            job
        )


# ============================================================
# BACKWARD-COMPATIBLE CLASSIFICATION ENDPOINT
# ============================================================


@router.post(
    "/classify"
)
def classify_gmail_email(
    payload: dict,
):

    if not isinstance(
        payload,
        dict,
    ):

        raise HTTPException(
            status_code=400,
            detail="Email payload must be an object.",
        )

    email = {
        "email_id": payload.get(
            "email_id",
            "gmail-prototype",
        ),
        "gmail_thread_id": payload.get(
            "gmail_thread_id"
        ) or payload.get(
            "thread_id"
        ) or payload.get(
            "email_id",
            "",
        ),
        "gmail_message_id": payload.get(
            "gmail_message_id"
        ) or payload.get(
            "message_id",
            "",
        ),
        "from": payload.get(
            "from",
            "",
        ),
        "to": payload.get(
            "to",
            "",
        ),
        "subject": payload.get(
            "subject",
            "",
        ),
        "body": payload.get(
            "body",
            "",
        ),
        "attachments": payload.get(
            "attachments",
            [],
        ),
    }

    try:

        classification = classify_email(
            email
        )

        return {
            "status": "OK",
            "email": email,
            "classification": classification,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Gmail classification failed: {exc}",
        )


# ============================================================
# HEALTH
# ============================================================


@router.get(
    "/health"
)
def gmail_health():

    status = account_status()

    return {
        "ok": True,
        "oauth_configured": status.get(
            "configured",
            False,
        ),
        "connected": status.get(
            "connected",
            False,
        ),
        "email": status.get(
            "email",
            "",
        ),
        "attachment_pipeline": True,
        "attachment_source": "Gmail API",
        "analyzer": "SI/BL semantic verification",
    }
