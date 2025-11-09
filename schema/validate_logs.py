#!/usr/bin/env python3
"""
validate_logs.py
Usage:
  python3 validate_logs.py schema/schema_v1.json examples/requests.jsonl
Exit codes:
  0 - all records valid
  2 - one or more records invalid
"""

import sys
import json
from jsonschema import validate, ValidationError, Draft7Validator

def load_json(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def validate_jsonl(schema_file, data_file):
    schema = load_json(schema_file)
    validator = Draft7Validator(schema)
    invalid_found = False

    with open(data_file, 'r', encoding='utf-8') as df:
        for lineno, raw in enumerate(df, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"[ERROR] Line {lineno}: JSON decode error: {e}")
                invalid_found = True
                continue

            errors = list(validator.iter_errors(record))
            if errors:
                invalid_found = True
                print(f"[INVALID] Line {lineno}:")
                for err in errors:
                    # path -> human friendly
                    path = ".".join([str(p) for p in err.path]) or "<root>"
                    print(f"  - {path}: {err.message}")
            else:
                print(f"[OK] Line {lineno} valid.")

    return 0 if not invalid_found else 2

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 validate_logs.py schema/schema_v1.json examples/requests.jsonl")
        sys.exit(1)
    rc = validate_jsonl(sys.argv[1], sys.argv[2])
    sys.exit(rc)
