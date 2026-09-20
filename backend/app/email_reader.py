import json
from email import policy
from email.parser import BytesParser
from pathlib import Path

def _decode(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return value.decode("utf-8", errors="replace")
    except Exception:
        return str(value)

def read_json_email(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON email must contain an object.")
    return data

def read_eml(path: Path) -> dict:
    with path.open("rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    body_parts = []
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            disp = part.get_content_disposition()
            filename = part.get_filename()
            if disp == "attachment" or filename:
                if filename:
                    attachments.append(filename)
                continue
            if part.get_content_type() == "text/plain":
                body_parts.append(_decode(part.get_payload(decode=True)))
    else:
        body_parts.append(_decode(msg.get_payload(decode=True)))

    return {
        "email_id": path.stem,
        "from": msg.get("From", ""),
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "body": "\n".join(x for x in body_parts if x),
        "attachments": attachments,
    }

def read_msg(path: Path) -> dict:
    import extract_msg
    msg = extract_msg.Message(str(path))
    attachments = []
    for att in msg.attachments:
        name = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None)
        if name:
            attachments.append(name)
    return {
        "email_id": path.stem,
        "from": msg.sender or "",
        "to": msg.to or "",
        "subject": msg.subject or "",
        "body": msg.body or "",
        "attachments": attachments,
    }

def read_email(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return read_json_email(path)
    if suffix == ".eml":
        return read_eml(path)
    if suffix == ".msg":
        return read_msg(path)
    raise ValueError(f"Unsupported email format: {suffix}")
