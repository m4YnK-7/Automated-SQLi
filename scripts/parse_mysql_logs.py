import re, json, time, os

log_path = "./logs/mysql/general.log"
output_path = "./logs/db_traces.jsonl"

pattern = re.compile(r"(\d+)\s+(\w+)\s+(\w+)\s+(.*)")

def parse_log():
    with open(log_path, "r") as f, open(output_path, "a") as out:
        for line in f:
            match = pattern.match(line.strip())
            if not match:
                continue
            thread_id, command, state, query = match.groups()
            data = {
                "timestamp": time.time(),
                "thread_id": thread_id,
                "command": command,
                "state": state,
                "query": query
            }
            out.write(json.dumps(data) + "\n")

if __name__ == "__main__":
    parse_log()
