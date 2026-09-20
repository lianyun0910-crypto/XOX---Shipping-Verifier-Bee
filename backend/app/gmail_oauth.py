import base64
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# PATHS / ENV
# ============================================================

MODULE_DIR = Path(__file__).resolve().parent

# Try to locate the project root robustly.
# Typical structure:
#
# project/
#   backend/
#       ...
#   data/
#       records/
#
def _find_project_root() -> Path:
    candidates = [
        MODULE_DIR.parent.parent,
        MODULE_DIR.parent,
        MODULE_DIR,
    ]

    for candidate in candidates:
        if (
            (candidate / "data").exists()
            or (candidate / ".env").exists()
            or (candidate / "backend").exists()
        ):
            return candidate

    return MODULE_DIR.parent.parent


BASE_DIR = _find_project_root()

BACKEND_DIR = MODULE_DIR

RECORD_DIR = BASE_DIR / "data" / "records"

GMAIL_ATTACHMENT_DIR = (
    BASE_DIR
    / "data"
    / "gmail_attachments"
)

TOKEN_PATH = (
    RECORD_DIR
    / "gmail_oauth_token.json"
)

LEGACY_TOKEN_PATHS = [
    RECORD_DIR / "gmail_token.json",
    RECORD_DIR / "gmail" / "gmail_token.json",
    RECORD_DIR / "gmail" / "gmail_oauth_token.json",
]

STATE_PATH = (
    RECORD_DIR
    / "gmail_oauth_states.json"
)


# ============================================================
# LOAD ENV
# ============================================================

load_dotenv(
    BASE_DIR / ".env",
    override=False,
)

load_dotenv(
    BACKEND_DIR / ".env",
    override=True,
)


os.environ.setdefault(
    "OAUTHLIB_RELAX_TOKEN_SCOPE",
    "1",
)


# ============================================================
# GOOGLE SCOPES
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]


_LOCK = threading.Lock()


# ============================================================
# ENV HELPERS
# ============================================================

def _env(
    name: str,
    default: str = "",
) -> str:

    return (
        os.getenv(name, default)
        .strip()
    )


# ============================================================
# GOOGLE LIBRARIES
# ============================================================

def _require_google_libs():

    try:

        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        return (
            Flow,
            build,
            Credentials,
            Request,
        )

    except ImportError as exc:

        raise RuntimeError(
            "Gmail OAuth dependencies are missing. "
            "Install: "
            "google-api-python-client "
            "google-auth-httplib2 "
            "google-auth-oauthlib"
        ) from exc


# ============================================================
# GOOGLE OAUTH CONFIG
# ============================================================

def _client_config() -> dict:

    client_id = _env(
        "GOOGLE_CLIENT_ID"
    )

    client_secret = _env(
        "GOOGLE_CLIENT_SECRET"
    )

    redirect_uri = _env(
        "GMAIL_REDIRECT_URI",
        "http://127.0.0.1:8000/api/gmail/oauth/callback",
    )

    if client_id and client_secret:

        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": (
                    "https://accounts.google.com/o/oauth2/auth"
                ),
                "token_uri": (
                    "https://oauth2.googleapis.com/token"
                ),
                "redirect_uris": [
                    redirect_uri
                ],
            }
        }

    credentials_file = (
        BACKEND_DIR
        / "google_credentials.json"
    )

    if credentials_file.exists():

        return json.loads(
            credentials_file.read_text(
                encoding="utf-8"
            )
        )

    raise RuntimeError(
        "Google OAuth is not configured. "
        "Set GOOGLE_CLIENT_ID and "
        "GOOGLE_CLIENT_SECRET in backend/.env, "
        "or add backend/google_credentials.json."
    )


def oauth_configured() -> bool:

    try:

        _client_config()

        return True

    except Exception:

        return False


# ============================================================
# OAUTH STATE
# ============================================================

def _load_states() -> dict:

    if not STATE_PATH.exists():

        return {}

    try:

        value = json.loads(
            STATE_PATH.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(value, dict):

            return value

    except Exception:

        pass

    return {}


def _save_states(
    value: dict,
) -> None:

    RECORD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE_PATH.write_text(
        json.dumps(
            value,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# TOKEN STORAGE
# ============================================================

def _token_candidates() -> list[Path]:

    return [
        TOKEN_PATH,
        *LEGACY_TOKEN_PATHS,
    ]


def _load_token() -> dict | None:

    candidates = _token_candidates()

    print(
        "[Gmail OAuth] Looking for token:"
    )

    for path in candidates:

        print(
            f"  {path} "
            f"exists={path.exists()}"
        )

    for path in candidates:

        if not path.exists():

            continue

        try:

            value = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as exc:

            print(
                "[Gmail OAuth] "
                f"Failed reading token {path}: "
                f"{type(exc).__name__}"
            )

            continue

        if not isinstance(
            value,
            dict,
        ):

            continue

        if path != TOKEN_PATH:

            try:

                _save_token(
                    value
                )

                print(
                    "[Gmail OAuth] "
                    f"Migrated token: "
                    f"{path} -> {TOKEN_PATH}"
                )

            except Exception as exc:

                print(
                    "[Gmail OAuth] "
                    f"Token migration failed: "
                    f"{exc}"
                )

        print(
            "[Gmail OAuth] "
            f"Token loaded from: {path}"
        )

        return value

    print(
        "[Gmail OAuth] "
        "No Gmail OAuth token found."
    )

    return None


def _save_token(
    record: dict,
) -> None:

    RECORD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    TOKEN_PATH.write_text(
        json.dumps(
            record,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:

        TOKEN_PATH.chmod(
            0o600
        )

    except Exception:

        pass

    print(
        "[Gmail OAuth] "
        f"Token saved: {TOKEN_PATH}"
    )


# ============================================================
# START OAUTH
# ============================================================

def start_authorization() -> str:

    Flow, _, _, _ = (
        _require_google_libs()
    )

    redirect_uri = _env(
        "GMAIL_REDIRECT_URI",
        "http://127.0.0.1:8000/api/gmail/oauth/callback",
    )

    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    state = secrets.token_urlsafe(
        32
    )

    code_verifier = secrets.token_urlsafe(
        64
    )

    flow.code_verifier = (
        code_verifier
    )

    authorization_url, _ = (
        flow.authorization_url(
            access_type="offline",
            prompt="consent",
            state=state,
            code_challenge_method="S256",
        )
    )

    with _LOCK:

        states = _load_states()

        states[state] = {
            "created_at": time.time(),
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }

        cutoff = (
            time.time() - 900
        )

        states = {
            key: item
            for key, item in states.items()
            if item.get(
                "created_at",
                0,
            ) >= cutoff
        }

        _save_states(
            states
        )

    print(
        "[Gmail OAuth] "
        "Authorization started."
    )

    return authorization_url


# ============================================================
# FINISH OAUTH
# ============================================================

def finish_authorization(
    code: str,
    state: str,
) -> dict:

    Flow, build, _, _ = (
        _require_google_libs()
    )

    with _LOCK:

        states = _load_states()

        state_record = states.pop(
            state,
            None,
        )

        _save_states(
            states
        )

    if not state_record:

        raise RuntimeError(
            "OAuth state is missing or expired."
        )

    if (
        time.time()
        - state_record.get(
            "created_at",
            0,
        )
        > 900
    ):

        raise RuntimeError(
            "OAuth state is missing or expired."
        )

    redirect_uri = str(
        state_record.get(
            "redirect_uri"
        )
        or ""
    ).strip()

    code_verifier = str(
        state_record.get(
            "code_verifier"
        )
        or ""
    ).strip()

    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        redirect_uri=redirect_uri,
    )

    if code_verifier:

        flow.code_verifier = (
            code_verifier
        )

    try:

        flow.fetch_token(
            code=code,
            code_verifier=(
                code_verifier or None
            ),
        )

    except Exception as exc:

        raise RuntimeError(
            "Gmail OAuth token exchange failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    credentials = (
        flow.credentials
    )

    if (
        not credentials
        or not credentials.token
    ):

        raise RuntimeError(
            "Google OAuth returned no access token."
        )

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    profile = (
        service
        .users()
        .getProfile(
            userId="me"
        )
        .execute()
    )

    email_address = str(
        profile.get(
            "emailAddress"
        )
        or ""
    ).strip()

    if not email_address:

        raise RuntimeError(
            "Google OAuth succeeded, "
            "but Gmail profile email "
            "was not returned."
        )

    credential_json = json.loads(
        credentials.to_json()
    )

    # Make sure refresh token is retained.
    if (
        not credential_json.get(
            "refresh_token"
        )
    ):

        old_record = _load_token()

        if old_record:

            old_credentials = (
                old_record.get(
                    "credentials"
                )
                or {}
            )

            old_refresh_token = (
                old_credentials.get(
                    "refresh_token"
                )
            )

            if old_refresh_token:

                credential_json[
                    "refresh_token"
                ] = old_refresh_token

    _save_token(
        {
            "email": email_address,
            "credentials": credential_json,
            "connected_at": time.time(),
        }
    )

    print(
        "[Gmail OAuth] "
        f"Connected Gmail account: "
        f"{email_address}"
    )

    return {
        "email": email_address,
        "connected": True,
    }


# ============================================================
# GET CREDENTIALS
# ============================================================

def get_credentials():

    _, _, Credentials, Request = (
        _require_google_libs()
    )

    record = _load_token()

    if not record:

        return None

    credentials_data = (
        record.get(
            "credentials"
        )
        or {}
    )

    if not credentials_data:

        return None

    try:

        credentials = (
            Credentials
            .from_authorized_user_info(
                credentials_data,
                SCOPES,
            )
        )

    except Exception as exc:

        print(
            "[Gmail OAuth] "
            "Could not restore credentials: "
            f"{type(exc).__name__}: {exc}"
        )

        return None

    # --------------------------------------------------------
    # Refresh expired credentials
    # --------------------------------------------------------

    if credentials.expired:

        if not credentials.refresh_token:

            print(
                "[Gmail OAuth] "
                "Access token expired and "
                "no refresh token exists."
            )

            return credentials

        try:

            print(
                "[Gmail OAuth] "
                "Refreshing expired access token..."
            )

            credentials.refresh(
                Request()
            )

            record[
                "credentials"
            ] = json.loads(
                credentials.to_json()
            )

            _save_token(
                record
            )

            print(
                "[Gmail OAuth] "
                "Access token refreshed successfully."
            )

        except Exception as exc:

            print(
                "[Gmail OAuth] "
                "Token refresh failed: "
                f"{type(exc).__name__}: {exc}"
            )

            return None

    return credentials


# ============================================================
# GMAIL SERVICE
# ============================================================

def get_gmail_service():

    _, build, _, _ = (
        _require_google_libs()
    )

    credentials = (
        get_credentials()
    )

    if not credentials:

        raise RuntimeError(
            "Gmail is not connected. "
            "Click Connect Gmail first."
        )

    if (
        credentials.expired
        and not credentials.refresh_token
    ):

        raise RuntimeError(
            "Gmail access token has expired "
            "and no refresh token is available. "
            "Click Connect Gmail again."
        )

    return build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )


# ============================================================
# ACCOUNT STATUS
# ============================================================

def account_status() -> dict:

    record = _load_token()

    connected = False
    email = ""
    credential_state = "missing"

    if not record:

        return {
            "configured": oauth_configured(),
            "connected": False,
            "email": "",
            "token_path": str(
                TOKEN_PATH
            ),
            "credential_state": "missing",
        }

    email = str(
        record.get(
            "email"
        )
        or ""
    ).strip()

    credentials_data = (
        record.get(
            "credentials"
        )
        or {}
    )

    if not credentials_data:

        return {
            "configured": oauth_configured(),
            "connected": False,
            "email": email,
            "token_path": str(
                TOKEN_PATH
            ),
            "credential_state": (
                "missing_credentials"
            ),
        }

    try:

        credentials = (
            get_credentials()
        )

        if credentials is None:

            credential_state = (
                "invalid_credentials"
            )

            connected = False

        elif (
            credentials.expired
            and not credentials.refresh_token
        ):

            credential_state = (
                "expired_no_refresh_token"
            )

            connected = False

        elif credentials.expired:

            credential_state = (
                "expired"
            )

            connected = False

        else:

            credential_state = (
                "valid_or_refreshable"
            )

            connected = True

    except Exception as exc:

        credential_state = (
            f"invalid:{type(exc).__name__}"
        )

        connected = False

        print(
            "[Gmail OAuth] "
            f"Account status error: {exc}"
        )

    return {
        "configured": oauth_configured(),
        "connected": connected,
        "email": email,
        "token_path": str(
            TOKEN_PATH
        ),
        "credential_state": credential_state,
    }


# ============================================================
# DISCONNECT
# ============================================================

def disconnect() -> None:

    with _LOCK:

        for path in _token_candidates():

            try:

                if path.exists():

                    path.unlink()

                    print(
                        "[Gmail OAuth] "
                        f"Removed token: {path}"
                    )

            except Exception as exc:

                print(
                    "[Gmail OAuth] "
                    f"Could not remove {path}: "
                    f"{exc}"
                )


# ============================================================
# HELPERS
# ============================================================

def _decode_b64(
    data: str | None,
) -> bytes:

    if not data:

        return b""

    padding = "=" * (
        -len(data) % 4
    )

    return base64.urlsafe_b64decode(
        data + padding
    )


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


def _walk_parts(
    part: dict,
    text_parts: list[str],
    attachments: list[dict],
) -> None:

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

        attachments.append(
            {
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
            }
        )

    if (
        not filename
        and mime in {
            "text/plain",
            "text/html",
        }
        and body.get("data")
    ):

        try:

            text = _decode_b64(
                body.get("data")
            ).decode(
                "utf-8",
                errors="replace",
            )

            if text.strip():

                text_parts.append(
                    text
                )

        except Exception:

            pass

    for child in (
        part.get(
            "parts"
        )
        or []
    ):

        _walk_parts(
            child,
            text_parts,
            attachments,
        )


def _safe_filename(
    name: str,
) -> str:

    name = Path(
        name
    ).name

    name = re.sub(
        r"[^A-Za-z0-9._()\- ]+",
        "_",
        name,
    ).strip()

    return (
        name
        or "attachment.bin"
    )


def _download_attachment(
    service,
    message_id: str,
    item: dict,
) -> bytes:

    data = item.get(
        "data"
    )

    if data:

        return _decode_b64(
            data
        )

    attachment_id = item.get(
        "attachment_id"
    )

    if not attachment_id:

        return b""

    response = (
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

    return _decode_b64(
        response.get(
            "data"
        )
    )


# ============================================================
# GMAIL MESSAGE FETCH
# ============================================================

def fetch_gmail_message(
    email_input: dict,
    run_id: str,
    index: int,
):

    service = get_gmail_service()

    message_id = str(
        email_input.get(
            "gmail_message_id"
        )
        or email_input.get(
            "message_id"
        )
        or ""
    ).strip()

    thread_id = str(
        email_input.get(
            "gmail_thread_id"
        )
        or email_input.get(
            "thread_id"
        )
        or ""
    ).strip()

    # Never send our synthetic application IDs
    # to Gmail API.
    if message_id.startswith(
        "gmail-"
    ):

        message_id = ""

    if thread_id.startswith(
        "gmail-"
    ):

        thread_id = ""

    if message_id:

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

    elif thread_id:

        thread = (
            service
            .users()
            .threads()
            .get(
                userId="me",
                id=thread_id,
                format="full",
            )
            .execute()
        )

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

        message = sorted(
            messages,
            key=lambda x: int(
                x.get(
                    "internalDate",
                    "0",
                )
            ),
        )[-1]

        message_id = str(
            message.get(
                "id",
                "",
            )
        )

        thread_id = str(
            thread.get(
                "id",
                thread_id,
            )
        )

    else:

        raise RuntimeError(
            "No valid Gmail message ID "
            "or Gmail thread ID was provided."
        )

    payload = (
        message.get(
            "payload"
        )
        or {}
    )

    headers = (
        payload.get(
            "headers"
        )
        or []
    )

    text_parts = []

    attachment_meta = []

    _walk_parts(
        payload,
        text_parts,
        attachment_meta,
    )

    subject = (
        _header(
            headers,
            "Subject",
        )
        or email_input.get(
            "subject"
        )
        or "Gmail email"
    )

    sender = (
        _header(
            headers,
            "From",
        )
        or email_input.get(
            "from"
        )
        or ""
    )

    recipient = (
        _header(
            headers,
            "To",
        )
        or email_input.get(
            "to"
        )
        or ""
    )

    body = (
        "\n\n".join(
            text_parts
        ).strip()
        or str(
            email_input.get(
                "body"
            )
            or ""
        )
    )

    case_dir = (
        GMAIL_ATTACHMENT_DIR
        / run_id
        / f"case_{index:04d}"
    )

    case_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    saved_paths = []

    attachment_names = []

    for attachment_index, item in enumerate(
        attachment_meta,
        start=1,
    ):

        filename = _safe_filename(
            item.get(
                "filename",
                f"attachment_{attachment_index}",
            )
        )

        stem = Path(
            filename
        ).stem

        suffix = Path(
            filename
        ).suffix

        candidate = (
            case_dir
            / filename
        )

        if candidate.exists():

            candidate = (
                case_dir
                / f"{stem}_{attachment_index}{suffix}"
            )

        content = _download_attachment(
            service,
            message_id,
            item,
        )

        if not content:

            continue

        if len(content) > 30 * 1024 * 1024:

            attachment_names.append(
                {
                    "filename": filename,
                    "mime_type": item.get(
                        "mime_type",
                        "",
                    ),
                    "downloaded": False,
                    "error": (
                        "Attachment exceeds "
                        "30 MB demo limit."
                    ),
                }
            )

            continue

        candidate.write_bytes(
            content
        )

        saved_paths.append(
            candidate
        )

        attachment_names.append(
            {
                "filename": candidate.name,
                "mime_type": item.get(
                    "mime_type",
                    "",
                ),
                "downloaded": True,
                "local_path": str(
                    candidate
                ),
                "size": len(
                    content
                ),
            }
        )

    normalized = {
        "email_id": (
            message_id
            or thread_id
        ),
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
            for item in attachment_names
            if item.get(
                "downloaded"
            )
        ],
        "attachment_details": attachment_names,
        "source": "gmail_oauth",
        "gmail_url": (
            f"https://mail.google.com/mail/u/0/#all/{message_id}"
            if message_id
            else str(
                email_input.get(
                    "gmail_url"
                )
                or ""
            )
        ),
    }

    return (
        normalized,
        saved_paths,
    )