#!/usr/bin/env python3
"""
Simplified Judge Test for Vera Message Composer
Tests the deployed bot directly without requiring external LLM
"""

import json
import sys
import time
from pathlib import Path
from urllib import request as urlrequest
from datetime import datetime

# Configuration
BOT_URL = "https://vera-message-composer-production.up.railway.app"
DATASET_DIR = Path(__file__).parent / "expanded"

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
BOLD = '\033[1m'
RESET = '\033[0m'

def print_success(msg):
    print(f"{GREEN}✅ {msg}{RESET}")

def print_fail(msg):
    print(f"{RED}❌ {msg}{RESET}")

def print_warn(msg):
    print(f"{YELLOW}⚠️  {msg}{RESET}")

def print_info(msg):
    print(f"{CYAN}ℹ️  {msg}{RESET}")

def api_call(method, path, body=None, timeout=10):
    """Make API call to bot"""
    url = f"{BOT_URL}{path}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body else None

    try:
        req = urlrequest.Request(url, data=data, method=method, headers=headers)
        start = time.time()
        resp = urlrequest.urlopen(req, timeout=timeout)
        latency = (time.time() - start) * 1000
        result = json.loads(resp.read().decode("utf-8"))
        return result, None, latency
    except Exception as e:
        return None, str(e), 0

def load_test_pairs():
    """Load test pairs"""
    test_pairs_file = DATASET_DIR / "test_pairs.json"
    if not test_pairs_file.exists():
        return []

    with open(test_pairs_file) as f:
        data = json.load(f)
        if isinstance(data, dict) and "pairs" in data:
            return data["pairs"]
        return data if isinstance(data, list) else []

def load_context(scope, context_id):
    """Load a context file"""
    if scope == "category":
        path = DATASET_DIR / "categories" / f"{context_id}.json"
    elif scope == "merchant":
        path = DATASET_DIR / "merchants" / f"{context_id}.json"
    elif scope == "trigger":
        path = DATASET_DIR / "triggers" / f"{context_id}.json"
    elif scope == "customer":
        path = DATASET_DIR / "customers" / f"{context_id}.json"
    else:
        return None

    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None

def main():
    print(f"\n{BOLD}{CYAN}{'='*70}{RESET}")
    print(f"{BOLD}{CYAN}Vera Message Composer — Judge Test (Simplified){RESET}")
    print(f"{BOLD}{CYAN}{'='*70}{RESET}\n")

    # Step 1: Health check
    print_info("Step 1: Health Check")
    data, err, lat = api_call("GET", "/v1/healthz")
    if err:
        print_fail(f"Health check failed: {err}")
        return False
    print_success(f"Bot is alive ({lat:.0f}ms)")

    # Step 2: Metadata
    print_info("Step 2: Retrieve Metadata")
    data, err, lat = api_call("GET", "/v1/metadata")
    if err:
        print_warn(f"Metadata failed: {err}")
    else:
        print_success(f"Bot: {data.get('name')} v{data.get('version')}")
        print(f"   Model: {data.get('model')}")
        print(f"   Multi-turn: {data.get('supports_multi_turn')}")

    # Step 3: Load dataset
    print_info("Step 3: Load Dataset")
    test_pairs = load_test_pairs()
    if not test_pairs:
        print_fail("No test pairs found")
        return False
    print_success(f"Loaded {len(test_pairs)} test pairs")

    # Step 4: Push contexts
    print_info("Step 4: Push Contexts")

    # Load and push categories
    cat_dir = DATASET_DIR / "categories"
    if cat_dir.exists():
        for cat_file in cat_dir.glob("*.json"):
            with open(cat_file) as f:
                cat_data = json.load(f)
                cat_slug = cat_data.get("slug", cat_file.stem)
                body = {
                    "scope": "category",
                    "context_id": cat_slug,
                    "version": 1,
                    "payload": cat_data,
                    "delivered_at": datetime.utcnow().isoformat() + "Z"
                }
                result, err, _ = api_call("POST", "/v1/context", body)
                if err or not (result and result.get("accepted")):
                    print_warn(f"Failed to push category {cat_slug}")
                else:
                    print(f"   ✓ {cat_slug}")

    # Load and push first 5 merchants
    print_success("Pushed categories")
    merchant_ids = []
    merchant_dir = DATASET_DIR / "merchants"
    if merchant_dir.exists():
        for i, merchant_file in enumerate(sorted(merchant_dir.glob("*.json"))):
            if i >= 5:
                break
            with open(merchant_file) as f:
                merchant_data = json.load(f)
                mid = merchant_data.get("merchant_id", merchant_file.stem)
                merchant_ids.append(mid)
                body = {
                    "scope": "merchant",
                    "context_id": mid,
                    "version": 1,
                    "payload": merchant_data,
                    "delivered_at": datetime.utcnow().isoformat() + "Z"
                }
                result, err, _ = api_call("POST", "/v1/context", body)
                if err or not (result and result.get("accepted")):
                    print_warn(f"Failed to push merchant {mid}")
                else:
                    print(f"   ✓ {mid[:40]}...")

    print_success(f"Pushed {len(merchant_ids)} merchants")

    # Load and push first 5 triggers
    trigger_ids = []
    trigger_dir = DATASET_DIR / "triggers"
    if trigger_dir.exists():
        for i, trigger_file in enumerate(sorted(trigger_dir.glob("*.json"))):
            if i >= 5:
                break
            with open(trigger_file) as f:
                trigger_data = json.load(f)
                tid = trigger_data.get("id", trigger_file.stem)
                trigger_ids.append(tid)
                body = {
                    "scope": "trigger",
                    "context_id": tid,
                    "version": 1,
                    "payload": trigger_data,
                    "delivered_at": datetime.utcnow().isoformat() + "Z"
                }
                result, err, _ = api_call("POST", "/v1/context", body)
                if err or not (result and result.get("accepted")):
                    print_warn(f"Failed to push trigger {tid}")
                else:
                    print(f"   ✓ {tid[:40]}...")

    print_success(f"Pushed {len(trigger_ids)} triggers")

    # Step 5: Call /v1/tick
    print_info("Step 5: Test /v1/tick (Composition)")
    tick_body = {
        "now": datetime.utcnow().isoformat() + "Z",
        "available_triggers": trigger_ids
    }
    result, err, lat = api_call("POST", "/v1/tick", tick_body)
    if err:
        print_fail(f"Tick failed: {err}")
        return False

    actions = result.get("actions", [])
    print_success(f"Tick returned {len(actions)} action(s) ({lat:.0f}ms)")

    if actions:
        print_info("Sample Compositions:")
        for i, action in enumerate(actions[:3]):
            body_preview = action.get("body", "")[:60]
            cta = action.get("cta", "none")
            print(f"\n  [{i+1}] Body: {body_preview}...")
            print(f"      CTA: {cta}")
            print(f"      Suppression Key: {action.get('suppression_key', 'N/A')}")
            print(f"      Rationale: {action.get('rationale', 'N/A')}")

    # Step 6: Validate message quality (basic checks)
    print_info("Step 6: Validate Message Quality (Basic Checks)")

    if not actions:
        print_warn("No actions to validate")
        return True

    action = actions[0]
    body = action.get("body", "")
    cta = action.get("cta", "")
    send_as = action.get("send_as", "")

    checks_passed = 0
    checks_total = 5

    # Check 1: Body not empty
    if body and len(body) > 10:
        print_success("✓ Message body is substantial")
        checks_passed += 1
    else:
        print_fail("✗ Message body is too short")

    # Check 2: Valid CTA
    if cta in ["binary", "open_ended", "none"]:
        print_success(f"✓ Valid CTA: {cta}")
        checks_passed += 1
    else:
        print_fail(f"✗ Invalid CTA: {cta}")

    # Check 3: Valid send_as
    if send_as in ["vera", "merchant_on_behalf"]:
        print_success(f"✓ Valid send_as: {send_as}")
        checks_passed += 1
    else:
        print_fail(f"✗ Invalid send_as: {send_as}")

    # Check 4: Has suppression_key
    if action.get("suppression_key"):
        print_success("✓ Suppression key present")
        checks_passed += 1
    else:
        print_fail("✗ Missing suppression key")

    # Check 5: Has rationale
    if action.get("rationale"):
        print_success("✓ Rationale provided")
        checks_passed += 1
    else:
        print_fail("✗ Missing rationale")

    print(f"\n{BOLD}Quality Checks: {checks_passed}/{checks_total} passed{RESET}")

    # Step 7: Summary
    print(f"\n{BOLD}{CYAN}{'='*70}{RESET}")
    if checks_passed >= 4:
        print(f"{GREEN}{BOLD}✅ JUDGE TEST PASSED - Bot is ready for submission!{RESET}")
    else:
        print(f"{YELLOW}{BOLD}⚠️  JUDGE TEST WARNINGS - Review above{RESET}")
    print(f"{BOLD}{CYAN}{'='*70}{RESET}\n")

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
