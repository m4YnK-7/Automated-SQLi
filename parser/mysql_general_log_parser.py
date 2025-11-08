#!/usr/bin/env python3
# parsers/mysql_general_log_parser.py
"""
Tail MySQL general log, normalize SQL, extract Connect entries, emit JSON records.
Usage: python3 mysql_general_log_parser.py /path/to/general.log /path/to/traces.jl
"""
import sys, re, json, time, argparse, os

parser = argparse.ArgumentParser()
parser.add_argument("logpath")
parser.add_argument("--out", default="/dev/stdout")
parser.add_argument("--follow", action="store_true", default=True)
args = parser.parse_args()

LOG_PATH = args.logpath

# Regexes: common MySQL general log formats
# Example formats:
# 2025-11-08T15:00:00.123456Z	  10 Connect	root@127.0.0.1 on
# 2025-11-08 15:00:00    10 Query    SELECT ...
connect_re = re.compile(r'(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+(?P<id>\d+)\s+Connect\s+(?P<user>[^@]+)@(?P<host>[\d\.:]+)')
query_re = re.compile(r'(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+(?P<id>\d+)\s+Query\s+(?P<sql>.*)', re.IGNORECASE)

# literal regexes
string_re = re.compile(r"'(?:\\'|[^'])*'")     # single-quoted strings
double_string_re = re.compile(r'"(?:\\"|[^"])*"')
number_re = re.compile(r'\b\d+(\.\d+)?\b')

def normalize(sql):
    s = string_re.sub("?", sql)
    s = double_string_re.sub("?", s)
    s = number_re.sub("?", s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def tail(f):
    f.seek(0, os.SEEK_END)
    while True:
        line = f.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line

# map conn_id -> client_host (from Connect lines)
conn_map = {}

def process_line(line):
    m = connect_re.search(line)
    if m:
        ts = m.group('ts')
        conn = m.group('id')
        host = m.group('host')
        return {"type":"connect","timestamp":ts,"conn_id":conn,"client":host}
    m2 = query_re.search(line)
    if m2:
        ts = m2.group('ts')
        conn = m2.group('id')
        sql = m2.group('sql').strip()
        return {"type":"query","timestamp":ts,"conn_id":conn,"raw":sql,"normalized":normalize(sql)}
    # fallback: unknown line
    return {"type":"unknown","line":line.strip()}

def main():
    outf = open(args.out, "a", encoding="utf-8")
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in tail(f):
            rec = process_line(line)
            if rec["type"] == "connect":
                conn_map[rec["conn_id"]] = {"client": rec["client"], "timestamp": rec["timestamp"]}
            elif rec["type"] == "query":
                rec["client"] = conn_map.get(rec["conn_id"], {}).get("client")
                rec["trace_id"] = None  # placeholder for later
            outf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            outf.flush()

if __name__ == "__main__":
    main()
