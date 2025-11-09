# AutomatedSQLi — Logging Schema v1 (schema.md)

## Purpose
This document explains the schema (`schema_v1.json`), trace propagation, hashing & redaction rules, and how to use the validator.

## Trace header (canonical)
- Header name: `X-Trace-ID`
- Format: UUIDv4 (lowercase). Example: `8f8b27d2-1abf-4a60-9f78-9e4d45ad00a1`
- Generation / propagation:
  - The reverse-proxy should generate a trace_id when absent and attach `X-Trace-ID` to every downstream HTTP call.
  - Downstream components must prefer the incoming `X-Trace-ID`. In code use: `trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4()`.
  - All log records MUST include the same `trace_id` string in the `trace_id` field.

## Field summary (high-level)
- `timestamp` — ISO8601 UTC, when record was emitted.
- `trace_id` — UUIDv4 string.
- `round` — integer (experiment/scan round).
- `tool` — component name (proxy, scanner, orchestrator, db_logger, analyzer).
- `payload_id` — local payload id used by component.
- `src_ip` — source IP (string). If internal, use `127.0.0.1`.
- `method`, `url`, `headers`, `params`, `body_snippet` — request metadata. See redaction rules below.
- `db_query`, `db_status` — DB-level data (queries should be redacted/hashed).
- `label`, `confidence` — analysis metadata.
- `meta.version` — schema/producer version (required).

## Hashing & redaction rules (canonical)
Goal: maximize debugging signal while preventing PII leakage.

1. **Hash algorithm**:
   - Use SHA-256 and output truncated hex prefix and marker: `HASHED_<8hex>`.
   - NEVER store the raw hash salt in logs. Use `meta.hash_salt_id` to identify the salt KMS/secret entry.

2. **Which fields to hash / redact**:
   - Always hash or redact full values for keys named (case-insensitive):
     - `password`, `passwd`, `pwd`, `token`, `sessionid`, `authorization`, `auth`, `secret`, `ssn`
   - For `params`:
     - For sensitive keys (above), replace value with `HASHED_<8hex>`.
     - For long or suspicious values (SQL metacharacters such as `' OR -- ; /*`), either hash or keep shortened `body_snippet`.
   - For `headers`:
     - Drop or mask full header values of `Authorization` and `Cookie`. Keep header names; store `headers["Authorization"] = "[REDACTED]"`.
   - `db_query`:
     - Do not log raw literals. Replace literal strings and numeric constants with `?` placeholders and append hashed mapping or hashed literal when useful:
       - Example: `SELECT * FROM users WHERE username='?'` and store `username_hash` = `HASHED_ab12cd34` as part of `meta` or `db_query` text itself (preferred pattern is to inline hashed literals).
   - `body_snippet`:
     - Keep up to 512 characters. Remove email addresses and card numbers:
       - email -> `[REDACTED_EMAIL]`
       - 13-16 digit numbers -> `[REDACTED_CARD]`
     - If body contains clear credentials, replace with `[REDACTED]` or hashed placeholders.

3. **Salt management**:
   - Salt must be stored in a secrets manager (KMS / vault).
   - `meta.hash_salt_id` is a short identifier (e.g., `salt-v1-202511`) that allows re-hashing or deterministic comparisons without exposing the salt value.
   - When rotating salts, create new salt id and update components. Old logs remain verifiable only if salt is retained offline.

4. **Why hashing (vs redaction)**:
   - Hashing preserves the ability to correlate identical secrets across events (same hashed prefix) without exposing the actual secret.

## Examples
- See `examples/requests.jsonl` and `examples/db.jsonl`.

## Validator
- Script: `schema/validate_logs.py`
- Requirements: `pip install jsonschema`
- Usage:
