import json
import os
import random
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=True)

_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_TIME = 0.0


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _client() -> OpenAI:
    key = os.getenv("AI_API_KEY", "").strip()
    base = os.getenv("AI_BASE_URL", "").strip()
    if not key:
        raise RuntimeError("AI_API_KEY is missing. Put it in backend/.env")
    kwargs = {"api_key": key}
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


def model() -> str:
    value = os.getenv("AI_MODEL", "").strip()
    if not value:
        raise RuntimeError("AI_MODEL is missing. Put it in backend/.env")
    return value


def clean_json_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start:end + 1]
    return text


def _wait_before_request() -> None:
    global _LAST_REQUEST_TIME
    interval = _float_env("AI_MIN_REQUEST_INTERVAL", 2.0)
    with _REQUEST_LOCK:
        now = time.monotonic()
        wait = interval - (now - _LAST_REQUEST_TIME)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_TIME = time.monotonic()


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "rate exceeds" in text or "too many requests" in text


def call_ai(system_prompt: str, user_prompt: str) -> str:
    max_retries = max(0, _int_env("AI_MAX_RETRIES", 2))
    initial_delay = max(0.5, _float_env("AI_RETRY_DELAY", 5.0))

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            _wait_before_request()
            response = _client().chat.completions.create(
                model=model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("AI returned an empty response.")
            return content.strip()
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit_error(exc) or attempt >= max_retries:
                raise
            delay = initial_delay * (2 ** attempt) + random.uniform(0, 1.5)
            print(f"[AI] Rate limit (429). Retry {attempt + 1}/{max_retries} in {delay:.1f}s...")
            time.sleep(delay)

    raise last_exc or RuntimeError("AI request failed.")


def call_json(system_prompt: str, user_prompt: str) -> dict:
    raw = clean_json_text(call_ai(system_prompt, user_prompt))
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AI returned invalid JSON: {raw}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"AI returned JSON that is not an object: {value}")
    return value
