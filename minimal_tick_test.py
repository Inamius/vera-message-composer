#!/usr/bin/env python3
"""Minimal tick test"""
import json
import urllib.request as urlrequest
from datetime import datetime

url = "http://localhost:8000/v1/tick"
body = {
    "now": datetime.utcnow().isoformat() + "Z",
    "available_triggers": ["trg_001_research_digest_dentists"]
}

print("Calling /v1/tick with:", json.dumps(body, indent=2))
print()

req = urlrequest.Request(
    url,
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    resp = urlrequest.urlopen(req, timeout=30)
    result = json.loads(resp.read().decode("utf-8"))
    print("Response:")
    print(json.dumps(result, indent=2))
except Exception as e:
    print(f"Error: {e}")
