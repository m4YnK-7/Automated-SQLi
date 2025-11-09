import json

http_traces = {}
with open("./logs/traces.jl") as f:
    for line in f:
        d = json.loads(line)
        http_traces[d["trace_id"]] = d

with open("./logs/db_traces_normalized.jsonl") as f, open("./logs/combined_trace.jsonl", "w") as out:
    for line in f:
        d = json.loads(line)
        trace_id = d.get("trace_id")
        if trace_id and trace_id in http_traces:
            combined = {**http_traces[trace_id], **d}
            out.write(json.dumps(combined) + "\n")
