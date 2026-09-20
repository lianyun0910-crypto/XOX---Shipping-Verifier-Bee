import base64
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
RECORD_DIR = BASE_DIR / "data" / "records"
GMAIL_ATTACHMENT_DIR = BASE_DIR / "data" / "gmail_attachments"
TOKEN_PATH = RECORD_DIR / "gmail_oauth_token.json"
LEGACY_TOKEN_PATHS = [
    RECORD_DIR / "gmail_token.json",
    RECORD_DIR / "gmail" / "gmail_token.json",
    RECORD_DIR / "gmail" / "gmail_oauth_token.json",
]
STATE_PATH = RECORD_DIR / "gmail_oauth_states.json"
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=True)

# Google may return the union of scopes previously granted to this OAuth client
# (for example profile/email/openid plus gmail.readonly). oauthlib normally
# raises a Warning when the granted scope differs from the requested scope.
# For this local Gmail integration we only need to preserve the granted token;
# relax that strict scope-set check so token exchange can complete reliably.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
]
_LOCK = threading.Lock()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _require_google_libs():
    try:
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        return Flow, build, Credentials, Request
    except ImportError as exc:
        raise RuntimeError(
            "Gmail OAuth dependencies are missing. Install: "
            "google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc


def _client_config() -> dict:
    client_id = _env("GOOGLE_CLIENT_ID")
    client_secret = _env("GOOGLE_CLIENT_SECRET")
    if client_id and client_secret:
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [_env("GMAIL_REDIRECT_URI", "http://127.0.0.1:8000/api/gmail/oauth/callback")],
            }
        }

    credentials_file = BACKEND_DIR / "google_credentials.json"
    if credentials_file.exists():
        return json.loads(credentials_file.read_text(encoding="utf-8"))

    raise RuntimeError(
        "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and "
        "GOOGLE_CLIENT_SECRET in backend/.env, or add backend/google_credentials.json."
    )


def oauth_configured() -> bool:
    try:
        _client_config()
        return True
    except Exception:
        return False


def _load_states() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_states(value: dict) -> None:
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _token_candidates() -> list[Path]:
    return [TOKEN_PATH, *LEGACY_TOKEN_PATHS]


def _load_token() -> dict | None:
    for path in _token_candidates():
        if not path.exists():
            continue

        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(value, dict):
            continue

        if path != TOKEN_PATH:
            try:
                _save_token(value)
                print(f"[Gmail OAuth] Migrated token: {path} -> {TOKEN_PATH}")
            except Exception as exc:
                print(f"[Gmail OAuth] Token migration failed: {exc}")

        return value

    return None


def _save_token(record: dict) -> None:
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    try:
        TOKEN_PATH.chmod(0o600)
    except Exception:
        pass


def start_authorization() -> str:
    """Start a Gmail OAuth authorization flow with PKCE.

    The code verifier is generated here and persisted with the OAuth state so
    that the callback can complete the token exchange after the browser
    redirects back to FastAPI.  This fixes the "Missing code verifier" /
    invalid_grant error that occurs when PKCE is enabled but the verifier is
    not restored before ``fetch_token``.
    """
    Flow, _, _, _ = _require_google_libs()
    redirect_uri = _env(
        "GMAIL_REDIRECT_URI",
        "http://127.0.0.1:8000/api/gmail/oauth/callback",
    )

    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)

    # google-auth-oauthlib will use this verifier when generating the
    # authorization request.  We also store it ourselves because the Flow
    # object does not survive the browser redirect.
    flow.code_verifier = code_verifier

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        code_challenge_method="S256",
    )

    with _LOCK:
        states = _load_states()
        states[state] = {
            "created_at": time.time(),
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }

        cutoff = time.time() - 900
        states = {
            key: item
            for key, item in states.items()
            if item.get("created_at", 0) >= cutoff
        }
        _save_states(states)

    print("[Gmail OAuth] Authorization started; PKCE verifier stored.")
    return authorization_url


def finish_authorization(code: str, state: str) -> dict:
    """Finish the OAuth callback and persist a refreshable Gmail token."""
    Flow, build, _, _ = _require_google_libs()

    with _LOCK:
        states = _load_states()
        state_record = states.pop(state, None)
        _save_states(states)

    if not state_record:
        raise RuntimeError("OAuth state is missing or expired.")

    if time.time() - state_record.get("created_at", 0) > 900:
        raise RuntimeError("OAuth state is missing or expired.")

    redirect_uri = state_record["redirect_uri"]
    code_verifier = str(state_record.get("code_verifier") or "").strip()

    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        state=state,
        redirect_uri=redirect_uri,
    )

    # Restore the PKCE verifier created in start_authorization() before the
    # authorization code is exchanged for tokens.
    if code_verifier:
        flow.code_verifier = code_verifier

    try:
        # Pass the stored PKCE verifier explicitly.  We request only the
        # Gmail readonly scope so Google's returned scope set matches the
        # scope expected by google-auth-oauthlib.
        flow.fetch_token(
            code=code,
            code_verifier=code_verifier or None,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Gmail OAuth token exchange failed: {type(exc).__name__}: {exc}"
        ) from exc

    credentials = flow.credentials
    if not credentials or not credentials.token:
        raise RuntimeError("Google OAuth returned no access token.")

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    profile = service.users().getProfile(userId="me").execute()
    email_address = str(profile.get("emailAddress") or "").strip()

    if not email_address:
        raise RuntimeError("Google OAuth succeeded, but Gmail profile email was not returned.")

    _save_token({
        "email": email_address,
        "credentials": json.loads(credentials.to_json()),
        "connected_at": time.time(),
    })

    print(f"[Gmail OAuth] Connected Gmail account: {email_address}")
    print(f"[Gmail OAuth] Token saved to: {TOKEN_PATH}")

    return {
        "email": email_address,
        "connected": True,
    }


def get_credentials():
    _, _, Credentials, Request = _require_google_libs()
    record = _load_token()
    if not record:
        return None
    credentials_data = record.get("credentials") or {}
    credentials = Credentials.from_authorized_user_info(credentials_data, SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        record["credentials"] = json.loads(credentials.to_json())
        _save_token(record)
    return credentials


def get_gmail_service():
    _, build, _, _ = _require_google_libs()
    credentials = get_credentials()
    if not credentials:
        raise RuntimeError("Gmail is not connected. Click Connect Gmail first.")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def account_status() -> dict:
    record = _load_token()

    connected = False
    email = ""
    credential_state = "missing"

    if record:
        email = str(record.get("email") or "").strip()
        credentials_data = record.get("credentials") or {}
        credential_state = "present" if credentials_data else "missing_credentials"

        if email and credentials_data:
            try:
                credentials = get_credentials()
                connected = credentials is not None
                if credentials is not None and credentials.expired and not credentials.refresh_token:
                    credential_state = "expired_no_refresh_token"
                    connected = False
                elif credentials is not None and credentials.expired:
                    credential_state = "expired"
                else:
                    credential_state = "valid_or_refreshable"
            except Exception as exc:
                credential_state = f"invalid:{type(exc).__name__}"
                connected = False

    return {
        "configured": oauth_configured(),
        "connected": connected,
        "email": email,
        "token_path": str(TOKEN_PATH) if record else "",
        "credential_state": credential_state,
    }


def disconnect() -> None:
    with _LOCK:
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()


def _decode_b64(data: str | None) -> bytes:
    if not data:
        return b""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _header(headers: list[dict], name: str) -> str:
    wanted = name.lower()
    for item in headers or []:
        if str(item.get("name", "")).lower() == wanted:
            return str(item.get("value", ""))
    return ""


def _walk_parts(part: dict, text_parts: list[str], attachments: list[dict]) -> None:
    filename = str(part.get("filename") or "").strip()
    body = part.get("body") or {}
    mime = str(part.get("mimeType") or "application/octet-stream")

    if filename:
        attachments.append({
            "filename": filename,
            "mime_type": mime,
            "attachment_id": body.get("attachmentId"),
            "data": body.get("data"),
            "size": body.get("size", 0),
        })

    if not filename and mime in {"text/plain", "text/html"} and body.get("data"):
        try:
            text = _decode_b64(body.get("data")).decode("utf-8", errors="replace")
            if text.strip():
                text_parts.append(text)
        except Exception:
            pass

    for child in part.get("parts") or []:
        _walk_parts(child, text_parts, attachments)


def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._()\- ]+", "_", name).strip()
    return name or "attachment.bin"


def _download_attachment(service, message_id: str, item: dict) -> bytes:
    data = item.get("data")
    if data:
        return _decode_b64(data)
    attachment_id = item.get("attachment_id")
    if not attachment_id:
        return b""
    response = (
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    return _decode_b64(response.get("data"))


def fetch_gmail_message(email_input: dict, run_id: str, index: int) -> tuple[dict, list[Path]]:
    service = get_gmail_service()
    message_id = str(email_input.get("gmail_message_id") or email_input.get("message_id") or "").strip()
    thread_id = str(email_input.get("gmail_thread_id") or email_input.get("thread_id") or email_input.get("email_id") or "").strip()

    if message_id:
        message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    elif thread_id:
        thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
        messages = thread.get("messages") or []
        if not messages:
            raise RuntimeError("Gmail thread contains no messages.")
        message = sorted(messages, key=lambda x: int(x.get("internalDate", "0")))[-1]
        message_id = str(message.get("id", ""))
        thread_id = str(thread.get("id", thread_id))
    else:
        raise RuntimeError("No Gmail message ID or thread ID was provided.")

    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    text_parts: list[str] = []
    attachment_meta: list[dict] = []
    _walk_parts(payload, text_parts, attachment_meta)

    subject = _header(headers, "Subject") or email_input.get("subject") or "Gmail email"
    sender = _header(headers, "From") or email_input.get("from") or ""
    recipient = _header(headers, "To") or email_input.get("to") or ""
    body = "\n\n".join(text_parts).strip() or str(email_input.get("body") or "")

    case_dir = GMAIL_ATTACHMENT_DIR / run_id / f"case_{index:04d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []
    attachment_names: list[dict] = []

    for attachment_index, item in enumerate(attachment_meta, start=1):
        filename = _safe_filename(item.get("filename", f"attachment_{attachment_index}"))
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        candidate = case_dir / filename
        if candidate.exists():
            candidate = case_dir / f"{stem}_{attachment_index}{suffix}"
        content = _download_attachment(service, message_id, item)
        if not content:
            continue
        if len(content) > 30 * 1024 * 1024:
            attachment_names.append({"filename": filename, "mime_type": item.get("mime_type", ""), "downloaded": False, "error": "Attachment exceeds 30 MB demo limit."})
            continue
        candidate.write_bytes(content)
        saved_paths.append(candidate)
        attachment_names.append({"filename": candidate.name, "mime_type": item.get("mime_type", ""), "downloaded": True, "local_path": str(candidate)})

    normalized = {
        "email_id": message_id or thread_id,
        "gmail_message_id": message_id,
        "gmail_thread_id": thread_id,
        "message_id": message_id,
        "thread_id": thread_id,
        "from": sender,
        "to": recipient,
        "subject": subject,
        "body": body[:30000],
        "attachments": [item["filename"] for item in attachment_names if item.get("downloaded")],
        "attachment_details": attachment_names,
        "source": "gmail_oauth",
        "gmail_url": f"https://mail.google.com/mail/u/0/#all/{message_id}" if message_id else str(email_input.get("gmail_url") or ""),
    }
    return normalized, saved_paths
