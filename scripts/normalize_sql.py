import re, json

def normalize(query):
    query = re.sub(r"'[^']*'", "?", query)
    query = re.sub(r"\b\d+\b", "?", query)
    return query

with open("./logs/db_traces.jsonl") as f, open("./logs/db_traces_normalized.jsonl", "w") as out:
    for line in f:
        entry = json.loads(line)
        entry["normalized_query"] = normalize(entry["query"])
        out.write(json.dumps(entry) + "\n")
