# validate_logs.py
import json
import sys
from jsonschema import validate, ValidationError

def validate_jsonl(schema_file, data_file):
    with open(schema_file) as sf:
        schema = json.load(sf)
    with open(data_file) as df:
        for i, line in enumerate(df, start=1):
            try:
                record = json.loads(line)
                validate(instance=record, schema=schema)
            except (json.JSONDecodeError, ValidationError) as e:
                print(f"[!] Line {i} invalid: {e}")
            else:
                print(f"[+] Line {i} valid.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python validate_logs.py schema_v1.json requests.jsonl")
        sys.exit(1)
    validate_jsonl(sys.argv[1], sys.argv[2])
