#!/usr/bin/env python3
"""
Parse MySQL general query log into JSONL.

Usage:
  # one-shot parse (append)
  python3 scripts/parse_mysql_logs.py --input logs/mysql/general.log --output logs/db_traces.jsonl

  # tail/follow mode (keeps running)
  python3 scripts/parse_mysql_logs.py --input logs/mysql/general.log --output logs/db_traces.jsonl --follow
"""
import re
import json
import time
import argparse
import os
import io

# Regex attempt #1: timestamp ISO + thread id + Command + query
RE_ISO = re.compile(r"""
    ^\s*
    (?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)    # ISO-like timestamp
    \s+
    (?P<thread_id>\d+)
    \s+
    (?P<command>\w+)
    \s+
    (?P<query>.*)
    $
""", re.VERBOSE)

# Regex attempt #2: older format: TIME    Id Command    Argument
RE_SPACE = re.compile(r"""
    ^\s*
    (?P<time>\d{2}:\d{2}:\d{2})
    \s+
    (?P<thread_id>\d+)
    \s+
    (?P<command>\w+)
    \s+
    (?P<query>.*)
    $
""", re.VERBOSE)

# Extract trace_id from SQL comment: /* trace_id=... */ or SET @trace_id = '...'
RE_COMMENT_TRACE = re.compile(r"/\*\s*trace_id\s*=\s*([0-9a-fA-F\-]{8,36})\s*\*/", re.IGNORECASE)
RE_SET_TRACE = re.compile(r"SET\s+@trace_id\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)

def extract_trace_id(query: str):
    if not query:
        return None
    m = RE_COMMENT_TRACE.search(query)
    if m:
        return m.group(1)
    m = RE_SET_TRACE.search(query)
    if m:
        return m.group(1)
    return None

def parse_line(line: str):
    line = line.rstrip("\n")
    m = RE_ISO.match(line)
    if m:
        ts = m.group("timestamp")
        # try parse timestamp to epoch; if fails, keep as string
        try:
            # accept either with or without 'Z'
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in ts else "%Y-%m-%dT%H:%M:%SZ"
            epoch = time.mktime(time.strptime(ts.replace("Z", ""), "%Y-%m-%dT%H:%M:%S"))
            # if fractional seconds
            if "." in ts:
                frac = float("0." + ts.split(".")[1].rstrip("Z"))
                epoch = epoch + frac
        except Exception:
            epoch = None
        return {
            "raw_timestamp": ts,
            "timestamp": epoch,
            "thread_id": m.group("thread_id"),
            "command": m.group("command"),
            "query": m.group("query"),
            "trace_id": extract_trace_id(m.group("query"))
        }
    m = RE_SPACE.match(line)
    if m:
        # use current date with time for raw_timestamp (best-effort)
        raw_ts = time.strftime("%Y-%m-%dT") + m.group("time")
        return {
            "raw_timestamp": raw_ts,
            "timestamp": None,
            "thread_id": m.group("thread_id"),
            "command": m.group("command"),
            "query": m.group("query"),
            "trace_id": extract_trace_id(m.group("query"))
        }
    # fallback: try split by tab(s) or whitespace (some install variations)
    parts = re.split(r"\s{2,}|\t", line, maxsplit=3)
    if len(parts) >= 4:
        raw_ts = parts[0]
        thread_id = parts[1]
        command = parts[2]
        query = parts[3]
        return {
            "raw_timestamp": raw_ts,
            "timestamp": None,
            "thread_id": thread_id,
            "command": command,
            "query": query,
            "trace_id": extract_trace_id(query)
        }
    # If absolutely not parseable, return it as a generic log entry
    return {
        "raw": line,
        "timestamp": None,
        "thread_id": None,
        "command": None,
        "query": None,
        "trace_id": None
    }

def follow_file(fp):
    """Yield new lines appended to file (like tail -f)."""
    fp.seek(0, io.SEEK_END)
    while True:
        line = fp.readline()
        if not line:
            time.sleep(0.3)
            continue
        yield line

def main():
    p = argparse.ArgumentParser(description="Parse MySQL general log -> JSONL")
    p.add_argument("--input", "-i", default="logs/mysql/general.log", help="input general log")
    p.add_argument("--output", "-o", default="logs/db_traces.jsonl", help="output jsonl (appends)")
    p.add_argument("--follow", "-f", action="store_true", help="follow file (like tail -f)")
    args = p.parse_args()

    # ensure output dir exists
    out_dir = os.path.dirname(args.output) or "."
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(args.input):
        print(f"ERROR: input file not found: {args.input}")
        return

    mode = "a"
    with open(args.input, "r", encoding="utf-8", errors="ignore") as fin, \
         open(args.output, mode, encoding="utf-8") as fout:

        if args.follow:
            print(f"Following {args.input} -> {args.output} (ctrl-c to stop)")
            gen = follow_file(fin)
        else:
            # start from beginning
            fin.seek(0)
            gen = fin

        written = 0
        for line in gen:
            try:
                entry = parse_line(line)
                # add processing metadata
                entry["_ingested_at"] = time.time()
                fout.write(json.dumps(entry, ensure_ascii=False) + "\n")
                fout.flush()
                written += 1
            except KeyboardInterrupt:
                print("Interrupted.")
                break
            except Exception as e:
                # write fallback record with error
                err_entry = {"_error": str(e), "raw_line": line}
                fout.write(json.dumps(err_entry) + "\n")
                fout.flush()
        print(f"Done. Wrote {written} entries to {args.output}")

if __name__ == "__main__":
    main()
