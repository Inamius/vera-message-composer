import requests
import json

BASE_URL = "http://localhost:8000"

# 1. Health check
print("=== Health Check ===")
response = requests.get(f"{BASE_URL}/v1/healthz")
print(response.json())

# 2. Metadata
print("\n=== Bot Metadata ===")
response = requests.get(f"{BASE_URL}/v1/metadata")
print(json.dumps(response.json(), indent=2))

# 3. Store a category context
print("\n=== Storing Dentist Category===")
category_payload = {
    "scope": "category",
    "context_id": "dentists",
    "version": 1,
    "payload": {
        "slug": "dentists",
        "offer_catalog": [
            {"service": "Dental Cleaning", "price": 299},
            {"service": "Consultation", "price": "Free"}
        ],
        "voice": {"tone": "clinical", "taboos": ["cure", "guaranteed"]},
        "peer_stats": {"avg_rating": 4.4, "avg_ctr": 0.030},
        "digest": [],
        "seasonal_beats": [],
        "trend_signals": []
    },
    "delivered_at": "2026-08-24T17:10:40Z"
}
response = requests.post(f"{BASE_URL}/v1/context", json=category_payload)
print(response.json())

# 4. Tick (compose messages)
print("\n=== Composing Messages ===")
tick_payload = {
    "now": "2026-08-24T17:10:40Z",
    "available_triggers": ["trg_013_corporate_thali_planning"]
}
response = requests.post(f"{BASE_URL}/v1/tick", json=tick_payload)
result = response.json()
print(json.dumps(result, indent=2))

print("\n✅ All tests completed!")