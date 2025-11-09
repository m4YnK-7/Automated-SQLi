#!/usr/bin/env python3
import uuid, json, os, hashlib, time
from datetime import datetime, timezone
from flask import Flask, request, Response
import requests
from urllib.parse import parse_qs, urlencode

app = Flask(__name__)
DVWA_HOST = "http://dvwa"  # service name in compose
LOG_PATH = "/app/logs/traces.jl"

@app.before_request
def ensure_trace_id():
    # prefer an incoming trace id (trusted proxies can set this)
    incoming = request.headers.get("X-Trace-ID")
    if incoming and len(incoming) == 36:
        request.trace_id = incoming
        # optional: you can validate it's a UUIDv4 if you want
    else:
        request.trace_id = str(uuid.uuid4())

@app.after_request
def attach_trace_id(response: Response):
    # ensure every outgoing response carries the trace id
    try:
        response.headers["X-Trace-ID"] = request.trace_id
    except Exception:
        # defensive: if request.trace_id is missing for some reason, ignore
        pass
    return response

def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def sha256_prefix(s):
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()[:40]

def build_record(trace_id, req, resp, sql_comment_added):
    params = []
    for i, (k, v) in enumerate(req.args.items()):
        params.append({
            "name": k, "position": i,
            "value_hash": sha256_prefix(v),
            "value_redacted": None
        })
    rec = {
        "version": "1.0",
        "timestamp": now_iso(),
        "trace_id": trace_id,
        "request": {
            "method": req.method,
            "uri": req.path,
            "params": params,
            "headers": {k: v for k, v in req.headers.items()},
            "body_snippet": (req.get_data()[:512].decode(errors='ignore') if req.get_data() else None),
            "client_ip": req.remote_addr
        },
        "payload": {"payload_id": None, "category": None, "vector": None, "template_ref": None, "raw_payload_redacted": None},
        "response": {
            "status": resp.status_code,
            "size_bytes": len(resp.content) if resp.content else 0,
            "content_hash": sha256_prefix(resp.text[:1024]),
            "key_substrings": [],
            "response_time_ms": 0.0,
            "semantic_diff_score": 0.0
        },
        "db": None,
        "outcome": {"success_confidence": 0.0, "data_extracted_count": 0, "notes": ""},
        "meta": {"tool": "manual", "tool_version": None, "round": "manual", "annotations": []},
        "injected_sql_comment": sql_comment_added
    }
    return rec

def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")

def inject_comment_into_params(params_dict, comment):
    """Return a new params dict with the comment appended to each value (string values only)."""
    new = {}
    for k, v in params_dict.items():
        # v may be multi-valued in Flask; request.args returns a MultiDict where .items() gives single values
        if isinstance(v, str) and v.strip():
            new[k] = f"{v} {comment}"
        else:
            new[k] = v
    return new

def inject_comment_into_body(body_bytes, content_type, comment):
    """If body is form-encoded, append comment to each param value and re-encode."""
    if not body_bytes:
        return body_bytes
    ctype = content_type.split(";")[0] if content_type else ""
    if ctype == "application/x-www-form-urlencoded":
        try:
            s = body_bytes.decode()
            parsed = parse_qs(s, keep_blank_values=True)
            # parse_qs gives lists; append comment to each list element
            new = {}
            for k, vals in parsed.items():
                new_vals = [ (val + " " + comment) if val.strip() else val for val in vals ]
                new[k] = new_vals
            # urlencode needs values as lists for multiple keys
            return urlencode(new, doseq=True).encode()
        except Exception:
            return body_bytes
    # otherwise, not handling JSON or multipart bodies for now
    return body_bytes

@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(path):
    trace_id = getattr(request, "trace_id", str(uuid.uuid4()))
    target = DVWA_HOST.rstrip("/") + "/" + path
    sql_comment = f"/* trace_id={trace_id} */"
    sql_comment_added = False

    # Properly copy incoming headers (use items())
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    headers["X-Trace-ID"] = trace_id
    headers["X-Forwarded-For"] = request.remote_addr or headers.get("X-Forwarded-For", "")

    # Inject into GET params
    modified_params = inject_comment_into_params(request.args.to_dict(flat=True), sql_comment)
    if modified_params != request.args.to_dict(flat=True):
        sql_comment_added = True

    # Inject into form-encoded POST body if present
    body = request.get_data()
    modified_body = body
    content_type = request.headers.get("Content-Type", "")
    if request.method in ("POST", "PUT", "PATCH"):
        new_body = inject_comment_into_body(body, content_type, sql_comment)
        if new_body != body:
            modified_body = new_body
            sql_comment_added = True

    try:
        resp = requests.request(
            method=request.method,
            url=target,
            params=modified_params if modified_params else None,
            headers=headers,
            data=modified_body if modified_body else None,
            cookies=request.cookies,
            allow_redirects=False,
            timeout=10,
        )
    except Exception as e:
        return Response(f"Upstream error: {e}", status=502)

    # Build and append our trace record
    record = build_record(trace_id, request, resp, sql_comment_added)
    append_log(record)

    excluded = ["content-encoding", "content-length", "transfer-encoding", "connection"]
    response_headers = [(name, value) for (name, value) in (resp.raw.headers.items() if resp.raw and resp.raw.headers else []) if name.lower() not in excluded]
    return Response(resp.content, status=resp.status_code, headers=response_headers)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
