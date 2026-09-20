import json
import os
from pathlib import Path
from typing import Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from supabase import Client, create_client


BASE_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=True)

RECORD_DIR = BASE_DIR / "data" / "records"
RECORD_DIR.mkdir(parents=True, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _settings() -> dict:
    try:
        expires = int(_env("CLOUD_LINK_EXPIRES_SECONDS", "86400"))
    except ValueError:
        expires = 86400

    return {
        "url": _env("SUPABASE_URL"),
        "secret_key": _env("SUPABASE_SECRET_KEY"),
        "bucket": _env("SUPABASE_BUCKET", "shipping-verifier"),
        "expires_in": expires,
        "archive_files": _env(
            "CLOUD_ARCHIVE_FILES",
            "true"
        ).lower() == "true",
    }


def cloud_storage_enabled() -> bool:
    settings = _settings()

    return bool(
        settings["url"]
        and settings["secret_key"]
        and settings["bucket"]
    )


def _client() -> Client:
    settings = _settings()

    if not cloud_storage_enabled():
        raise RuntimeError(
            "Supabase Storage is not configured."
        )

    return create_client(
        settings["url"],
        settings["secret_key"],
    )


def cloud_object_path(filename: str) -> str:
    return f"reports/{Path(filename).name}"


def _signed_url(object_path: str) -> str | None:
    settings = _settings()

    response = (
        _client()
        .storage
        .from_(settings["bucket"])
        .create_signed_url(
            object_path,
            settings["expires_in"],
        )
    )

    if isinstance(response, dict):
        return (
            response.get("signedURL")
            or response.get("signedUrl")
            or response.get("url")
        )

    return None


def get_cloud_url(path: Path) -> str | None:
    if not cloud_storage_enabled():
        return None

    return _signed_url(
        cloud_object_path(path.name)
    )


def upload_bytes(
    object_path: str,
    content: bytes,
    content_type: str,
) -> dict:
    settings = _settings()

    if not cloud_storage_enabled():
        return {
            "uploaded": False,
            "cloud_url": None,
            "reason": "supabase_not_configured",
        }

    response = (
        _client()
        .storage
        .from_(settings["bucket"])
        .upload(
            object_path,
            content,
            {
                "content-type": content_type,
                "cache-control": "3600",
                "upsert": "true",
            },
        )
    )

    return {
        "uploaded": True,
        "response": response,
        "path": object_path,
        "cloud_url": _signed_url(object_path),
    }


def upload_file(
    path: Path,
    object_path: str | None = None,
) -> dict:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"File not found: {path}"
        )

    object_path = (
        object_path
        or cloud_object_path(path.name)
    )

    suffix = path.suffix.lower()

    content_type = (
        "application/octet-stream"
    )

    if suffix in {".xlsx", ".xlsm"}:
        content_type = (
            "application/"
            "vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )

    elif suffix == ".json":
        content_type = "application/json"

    elif suffix == ".pdf":
        content_type = "application/pdf"

    elif suffix == ".txt":
        content_type = "text/plain"

    elif suffix == ".csv":
        content_type = "text/csv"

    elif suffix == ".docx":
        content_type = (
            "application/"
            "vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )

    elif suffix == ".eml":
        content_type = "message/rfc822"

    elif suffix in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".tiff",
        ".tif",
    }:
        content_type = (
            f"image/"
            f"{'jpeg' if suffix in {'.jpg', '.jpeg'} else suffix.lstrip('.')}"
        )

    return upload_bytes(
        object_path,
        path.read_bytes(),
        content_type,
    )


def save_excel(path: Path) -> dict:
    return upload_file(
        path,
        cloud_object_path(path.name),
    )


def get_excel_cloud_url() -> str | None:
    path = (
        RECORD_DIR
        / "shipping_verification_audit.xlsx"
    )

    if not path.exists():
        return None

    return get_cloud_url(path)


# ============================================================
# HUMAN-READABLE SUPABASE RUN NAME
# ============================================================

def friendly_cloud_run_name(
    source: str | None,
) -> str:
    """
    Create a short, human-readable Supabase run name.

    Examples:

        gmail_2026-09-20_165642
        web_2026-09-20_170105
    """

    source_name = str(
        source or "web"
    ).strip().lower()

    if source_name not in {
        "gmail",
        "web",
    }:
        source_name = "web"

    # Malaysia local time.
    timestamp = datetime.now(
        ZoneInfo("Asia/Kuala_Lumpur")
    ).strftime(
        "%Y-%m-%d_%H%M%S"
    )

    return (
        f"{source_name}_{timestamp}"
    )


def archive_run_to_cloud(
    run_id: str,
    results: list[dict],
    summary: dict,
    source_paths: Iterable[Path] | None = None,
    source: str | None = None,
) -> dict:

    if not cloud_storage_enabled():
        return {
            "enabled": False,
            "uploaded": False,
            "files": [],
        }

    uploaded = []

    # --------------------------------------------------------
    # Human-readable Supabase folder name
    #
    # Internal run_id remains unchanged.
    #
    # Example:
    # runs/
    #   gmail/
    #       gmail_2026-09-20_165642/
    #
    #   web/
    #       web_2026-09-20_170105/
    # --------------------------------------------------------

    friendly_name = (
        friendly_cloud_run_name(
            source
        )
    )

    source_name = str(
        source or "web"
    ).strip().lower()

    if source_name not in {
        "gmail",
        "web",
    }:
        source_name = "web"

    base = (
        f"runs/"
        f"{source_name}/"
        f"{friendly_name}"
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary_payload = json.dumps(
        {
            "run_id": run_id,
            "run_name": friendly_name,
            "summary": summary,
            "source": source_name,
        },
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    summary_path = (
        f"{base}/summary.json"
    )

    upload_bytes(
        summary_path,
        summary_payload,
        "application/json",
    )

    uploaded.append(
        summary_path
    )

    # --------------------------------------------------------
    # Individual verification cases
    # --------------------------------------------------------

    for index, result in enumerate(
        results,
        start=1,
    ):

        case_payload = json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        result_name = Path(
            str(
                result.get(
                    "filename"
                )
                or f"case_{index}"
            )
        ).stem[:80]

        object_path = (
            f"{base}/cases/"
            f"{index:04d}_"
            f"{result_name}.json"
        )

        upload_bytes(
            object_path,
            case_payload,
            "application/json",
        )

        uploaded.append(
            object_path
        )

    # --------------------------------------------------------
    # Original documents / attachments
    # --------------------------------------------------------

    settings = _settings()

    paths = list(
        source_paths or []
    )

    if settings["archive_files"]:

        seen = set()

        for path in paths:

            path = Path(path)

            cleaned_name = path.name

            if (
                cleaned_name in seen
                or not path.exists()
            ):
                continue

            seen.add(
                cleaned_name
            )

            object_path = (
                f"{base}/files/"
                f"{cleaned_name}"
            )

            upload_file(
                path,
                object_path,
            )

            uploaded.append(
                object_path
            )

    # --------------------------------------------------------
    # Return archive information
    # --------------------------------------------------------

    return {
        "enabled": True,
        "uploaded": True,
        "run_id": run_id,
        "run_name": friendly_name,
        "source": source_name,
        "base_path": base,
        "files": uploaded,
    }


# ---------------------------------------------------------------------------
# Verification history (shared by Web + Gmail)
# ---------------------------------------------------------------------------

HISTORY_PATH = (
    RECORD_DIR
    / "verification_history.jsonl"
)

_HISTORY_LOCK = __import__(
    "threading"
).Lock()


def _history_now() -> str:
    from datetime import (
        datetime,
        timezone,
    )

    return (
        datetime.now(
            timezone.utc
        ).isoformat()
    )


def _slim_history(value):

    if isinstance(value, dict):

        return {
            key: _slim_history(item)
            for key, item in value.items()
            if key not in {
                "body",
                "_source_path",
            }
        }

    if isinstance(value, list):
        return [
            _slim_history(item)
            for item in value
        ]

    return value


def append_history(
    run_id: str,
    source: str,
    results: list[dict],
    summary: dict | None = None,
) -> dict:

    entry = {
        "run_id": run_id,
        "timestamp_utc": _history_now(),
        "source": source,
        "summary": summary or {},
        "results": [
            _slim_history(item)
            for item in results
        ],
    }

    RECORD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _HISTORY_LOCK:

        with HISTORY_PATH.open(
            "a",
            encoding="utf-8",
        ) as handle:

            handle.write(
                json.dumps(
                    entry,
                    ensure_ascii=False,
                )
                + "\n"
            )

    return entry


def list_history(
    limit: int = 100,
) -> list[dict]:

    if not HISTORY_PATH.exists():
        return []

    limit = max(
        1,
        min(
            int(limit),
            500,
        ),
    )

    entries = []

    with _HISTORY_LOCK:

        with HISTORY_PATH.open(
            "r",
            encoding="utf-8",
        ) as handle:

            for line in handle:

                line = line.strip()

                if not line:
                    continue

                try:

                    entries.append(
                        json.loads(line)
                    )

                except json.JSONDecodeError:
                    continue

    return list(
        reversed(
            entries[-limit:]
        )
    )


def get_history(
    run_id: str,
) -> dict | None:

    for entry in list_history(500):

        if entry.get(
            "run_id"
        ) == run_id:

            return entry

    return None


def clear_history() -> None:

    with _HISTORY_LOCK:

        if HISTORY_PATH.exists():
            HISTORY_PATH.unlink()


def update_history_case(
    case_id: str,
    final_status: str,
    reviewer: str,
    review_note: str = "",
    human_decision: str = "",
    reviewed_at: str | None = None,
) -> dict | None:

    """
    Update a case inside the shared
    JSONL verification history.
    """

    if not HISTORY_PATH.exists():
        return None

    from datetime import (
        datetime,
        timezone,
    )

    reviewed_at = (
        reviewed_at
        or datetime.now(
            timezone.utc
        ).isoformat()
    )

    changed: dict | None = None

    with _HISTORY_LOCK:

        entries: list[dict] = []

        with HISTORY_PATH.open(
            "r",
            encoding="utf-8",
        ) as handle:

            for line in handle:

                line = line.strip()

                if not line:
                    continue

                try:

                    entries.append(
                        json.loads(line)
                    )

                except json.JSONDecodeError:

                    entries.append({})

        for entry in entries:

            for result in entry.get(
                "results",
                [],
            ):

                if (
                    result.get(
                        "case_id"
                    )
                    != case_id
                ):
                    continue

                result[
                    "human_review"
                ] = {
                    "decision": human_decision,
                    "reviewer": reviewer,
                    "review_note": review_note,
                    "reviewed_at": reviewed_at,
                }

                result[
                    "final_status"
                ] = final_status

                changed = result

                break

            if changed is not None:
                break

        tmp = HISTORY_PATH.with_suffix(
            ".tmp"
        )

        with tmp.open(
            "w",
            encoding="utf-8",
        ) as handle:

            for entry in entries:

                handle.write(
                    json.dumps(
                        entry,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        tmp.replace(
            HISTORY_PATH
        )

    return changed