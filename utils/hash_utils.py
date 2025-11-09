# utils/hash_utils.py
import hashlib, re, os

HASH_SALT = os.getenv("HASH_SALT", "autosqli_default_salt")

SENSITIVE_KEYS = {"password", "token", "sessionid", "secret"}

def hash_value(value: str) -> str:
    if not value:
        return ""
    return "HASHED_" + hashlib.sha256((HASH_SALT + value).encode()).hexdigest()[:8]

def sanitize_params(params: dict) -> dict:
    sanitized = {}
    for k, v in params.items():
        if k.lower() in SENSITIVE_KEYS:
            sanitized[k] = hash_value(v)
        else:
            sanitized[k] = v
    return sanitized

def sanitize_body(body: str) -> str:
    # keep first 200 chars, redact sensitive patterns
    body = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}", "[REDACTED_EMAIL]", body)
    body = re.sub(r"\b\d{13,16}\b", "[REDACTED_CARD]", body)
    return body[:200]
