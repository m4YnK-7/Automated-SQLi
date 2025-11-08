import uuid, json, os, hashlib
from datetime import datetime, timezone
from flask import Flask, request, Response
import requests

app = Flask(__name__)
DVWA_HOST = "http://dvwa"  # service name in compose
LOG_PATH = "/app/logs/traces.jl"

def now_iso(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def sha256_prefix(s): return "sha256:" + hashlib.sha256(s.encode()).hexdigest()[:40]

def build_record(trace_id, req, resp):
    params=[]
    for i,(k,v) in enumerate(req.args.items()):
        params.append({"name":k,"position":i,"value_hash":sha256_prefix(v),"value_redacted":None})
    rec = {
      "version":"1.0","timestamp":now_iso(),"trace_id":trace_id,
      "request":{"method":req.method,"uri":req.path,"params":params,"headers":{k:v for k,v in req.headers.items()},"body_snippet":None,"client_ip":req.remote_addr},
      "payload": {"payload_id":None,"category":None,"vector":None,"template_ref":None,"raw_payload_redacted":None},
      "response":{"status":resp.status_code,"size_bytes":len(resp.content) if resp.content else 0,"content_hash":sha256_prefix(resp.text[:1024]),"key_substrings":[],"response_time_ms":0.0,"semantic_diff_score":0.0},
      "db": None,
      "outcome":{"success_confidence":0.0,"data_extracted_count":0,"notes":""},
      "meta":{"tool":"manual","tool_version":None,"round":"manual","annotations":[]}
    }
    return rec

def append_log(record):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH,"a") as f:
        f.write(json.dumps(record,separators=(',',':')) + "\n")

@app.route("/", defaults={"path":""}, methods=["GET","POST","PUT","DELETE","PATCH"])
@app.route("/<path:path>", methods=["GET","POST","PUT","DELETE","PATCH"])
def proxy(path):
    trace_id = str(uuid.uuid4())
    target = DVWA_HOST.rstrip("/") + "/" + path
    headers = {k:v for k,v in request.headers if k.lower() != "host"}
    headers["X-Trace-Id"] = trace_id
    try:
        resp = requests.request(method=request.method, url=target, params=request.args, headers=headers, data=request.get_data(), cookies=request.cookies, allow_redirects=False, timeout=10)
    except Exception as e:
        return Response(f"Upstream error: {e}", status=502)
    record = build_record(trace_id, request, resp)
    append_log(record)
    excluded = ['content-encoding','content-length','transfer-encoding','connection']
    response_headers = [(name,value) for (name,value) in (resp.raw.headers.items() if resp.raw and resp.raw.headers else []) if name.lower() not in excluded]
    return Response(resp.content, status=resp.status_code, headers=response_headers)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=8080)

