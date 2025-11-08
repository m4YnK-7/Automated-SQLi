#!/usr/bin/env python3
# Very small orchestrator wrapper: run sqlmap with a custom header and capture metadata
import subprocess, uuid, json, sys, time
trace = str(uuid.uuid4())
url = sys.argv[1] if len(sys.argv)>1 else "http://localhost:8080/login.php"
cmd = ["docker","run","--rm","--network","host","sqlmapproject/sqlmap","-u",url,"--batch","--headers","X-Trace-Id: {}".format(trace)]
print("Running:", " ".join(cmd))
t0=time.time()
subprocess.run(cmd)
t1=time.time()
meta={"trace_id":trace,"url":url,"duration_s":t1-t0,"tool":"sqlmap"}
print(json.dumps(meta))