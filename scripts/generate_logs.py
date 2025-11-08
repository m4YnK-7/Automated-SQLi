#!/usr/bin/env python3
# Minimal deterministic JSON-lines sample generator for schema v1
import argparse, json, random, hashlib, uuid
from datetime import datetime, timezone, timedelta

def sha256_prefix(s):
    import hashlib
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()[:40]

def now_iso(dt=None):
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.isoformat().replace("+00:00","Z")

def normalize_query(q):
    return " ".join(q.replace("'", "?").split())

def make_record(seed_dt, idx, seed):
    rand = random.Random(seed + idx)
    trace_id = str(uuid.UUID(int=rand.getrandbits(128), version=4))
    method = rand.choice(["GET","POST"])
    uri = rand.choice(["/login","/product","/search"])
    params = []
    if method == "POST":
        params = [{"name":"username","position":0,"value_hash":sha256_prefix("admin")}]
    resp_status = rand.choice([200,200,500])
    db = {"connection_id":"conn-{}".format(rand.randint(1,999)),
          "normalized_query": normalize_query("SELECT * FROM users WHERE username = 'X'"),
          "query_params_count":1, "execution_time_ms": rand.random()*20, "query_plan_id":"qp-1"}
    rec = {
        "version":"1.0","timestamp":now_iso(seed_dt + timedelta(seconds=idx)),
        "trace_id":trace_id,
        "request":{"method":method,"uri":uri,"params":params,"headers":{"User-Agent":"sqlmap/1.6"},"body_snippet":None,"client_ip":"10.0.0.5"},
        "payload":{"payload_id":"pl-000","category":"error-based","vector":"param","template_ref":"tpl/err001","raw_payload_redacted":None},
        "response":{"status":resp_status,"size_bytes":rand.randint(200,4000),"content_hash":sha256_prefix(trace_id+uri),"key_substrings":["SQL"] if resp_status==500 else [],"response_time_ms":rand.randint(10,400),"semantic_diff_score":0.1},
        "db":db,"outcome":{"success_confidence":0.9 if resp_status==500 else 0.02,"data_extracted_count":0,"notes":""},
        "meta":{"tool":"sqlmap","tool_version":"1.6","round":"automated-breadth-1","annotations":[]}
    }
    return rec

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--count","-n",type=int,default=20)
    p.add_argument("--seed","-s",type=int,default=0)
    args=p.parse_args()
    seed_dt = datetime.now(timezone.utc)
    for i in range(args.count):
        print(json.dumps(make_record(seed_dt,i,args.seed), separators=(",",":")))

if __name__=="__main__":
    main()
