#!/usr/bin/env python3
"""
Normalize DB queries and correlate HTTP <-> DB traces.
Outputs logs/combined_trace.jsonl
"""
import re, json, time, os
from datetime import datetime

HTTP_LOG = "logs/traces.jl"
DB_LOG   = "logs/db_traces.jsonl"
OUT_FILE = "logs/combined_trace.jsonl"

# Regexes for normalization
re_str = re.compile(r"'(?:\\'|[^'])*'")
re_num = re.compile(r"\b\d+(\.\d+)?\b")

def normalize_sql(q):
    if not q:
        return None
    q = re_str.sub("?", q)
    q = re_num.sub("?", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return [json.loads(x) for x in f if x.strip()]

def correlate():
    http = {h["trace_id"]: h for h in load_jsonl(HTTP_LOG) if "trace_id" in h}
    dbs = load_jsonl(DB_LOG)
    out = []

    for d in dbs:
        d["normalized_query"] = normalize_sql(d.get("query"))
        tid = d.get("trace_id")
        if tid and tid in http:
            combined = {**http[tid], **d}
            combined["_correlation"] = "trace_id"
            out.append(combined)
        else:
            # fallback: nearest timestamp
            best = None
            if d.get("timestamp"):
                for tid2, h in http.items():
                    if abs(d["timestamp"] - h["timestamp"]) < 2:
                        best = h
                        break
            if best:
                combined = {**best, **d}
                combined["_correlation"] = "time_window"
                out.append(combined)
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"[+] Combined {len(out)} correlated traces → {OUT_FILE}")

if __name__ == "__main__":
    correlate()
