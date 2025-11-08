#!/usr/bin/env python3
"""
Simple MySQL general log tailer + normalizer -> JSON
Usage: python3 mysql_general_log_parser.py /path/to/general.log
"""
import sys, re, json, time

LOG_PATH = sys.argv[1] if len(sys.argv) > 1 else "/var/lib/mysql/general.log"

# Regex patterns (MySQL general log lines often: YYYY-MM-DD HH:MM:SS  Id:  Command:  Statement)
# Adjust depending on your MySQL general log format.
line_re = re.compile(r'^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<id>\d+)\s+(?P<type>[A-Z]+)\s+(?P<rest>.*)$')

# Simple normalizer: replace strings and numbers with '?'
string_re = re.compile(r"'(?:\\'|[^'])*'")  # single-quoted strings
number_re = re.compile(r'\b\d+(\.\d+)?\b')

def normalize(sql: str) -> str:
    s = string_re.sub("?", sql)
    s = number_re.sub("?", s)
    # collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def tail(f):
    f.seek(0,2)
    while True:
        line = f.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line

def parse_line(line):
    m = line_re.match(line.strip())
    if m:
        ts = m.group('ts')
        conn = m.group('id')
        typ = m.group('type')
        rest = m.group('rest').strip()
        return ts, conn, typ, rest
    # fallback: treat whole line as statement with current time
    return time.strftime("%Y-%m-%d %H:%M:%S"), None, "UNKNOWN", line.strip()

def main():
    print(f"Starting parser -> reading {LOG_PATH}", file=sys.stderr)
    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in tail(f):
            ts, conn, typ, rest = parse_line(line)
            normalized = normalize(rest)
            rec = {
                "timestamp": ts,
                "conn_id": conn,
                "entry_type": typ,
                "raw": rest,
                "normalized_sql": normalized,
                # placeholder for trace_id; filled later when trace_id propagation implemented
                "trace_id": None
            }
            print(json.dumps(rec, ensure_ascii=False))
            sys.stdout.flush()

if __name__ == "__main__":
    main()
