#!/usr/bin/env python3
"""
Local test runner for the Vera Message Composer.

Tests the bot against a subset of the 30 canonical test pairs.
Runs locally before judge evaluation.
"""

import json
import sys
from pathlib import Path
from bot import compose

# Load expanded dataset
BASE_DIR = Path(__file__).parent / "expanded"


def load_test_pairs():
    """Load the 30 canonical test pairs"""
    test_pairs_file = BASE_DIR / "test_pairs.json"
    with open(test_pairs_file) as f:
        data = json.load(f)
        # Handle both formats: {"pairs": [...]} and [...]
        if isinstance(data, dict) and "pairs" in data:
            return data["pairs"]
        return data if isinstance(data, list) else []


def load_context(scope, context_id):
    """Load a context file by scope and context_id"""
    if scope == "category":
        path = BASE_DIR / "categories" / f"{context_id}.json"
    elif scope == "merchant":
        path = BASE_DIR / "merchants" / f"{context_id}.json"
    elif scope == "trigger":
        path = BASE_DIR / "triggers" / f"{context_id}.json"
    elif scope == "customer":
        path = BASE_DIR / "customers" / f"{context_id}.json"
    else:
        raise ValueError(f"Unknown scope: {scope}")

    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def run_local_test(limit=5):
    """
    Run composition tests on the first N test pairs.
    """
    test_pairs = load_test_pairs()
    print(f"\nLoaded {len(test_pairs)} test pairs. Running first {limit}...\n")

    passed = 0
    failed = 0

    for i, test_pair in enumerate(test_pairs[:limit]):
        test_id = test_pair.get("test_id", f"T{i+1:02d}")
        merchant_id = test_pair.get("merchant_id")
        trigger_id = test_pair.get("trigger_id")
        customer_id = test_pair.get("customer_id")

        print(f"[{test_id}] Merchant: {merchant_id}, Trigger: {trigger_id}", end="")
        if customer_id:
            print(f", Customer: {customer_id}", end="")
        print()

        try:
            # Load contexts
            merchant = load_context("merchant", merchant_id)
            if not merchant:
                print(f"  ❌ Merchant not found: {merchant_id}\n")
                failed += 1
                continue

            trigger = load_context("trigger", trigger_id)
            if not trigger:
                print(f"  ❌ Trigger not found: {trigger_id}\n")
                failed += 1
                continue

            category_slug = merchant.get("identity", {}).get("category", "dentists")
            category = load_context("category", category_slug)
            if not category:
                print(f"  ❌ Category not found: {category_slug}\n")
                failed += 1
                continue

            customer = None
            if customer_id:
                customer = load_context("customer", customer_id)
                if not customer:
                    print(f"  ⚠️  Customer not found: {customer_id}, proceeding without it\n")

            # Compose
            composed = compose(
                category=category,
                merchant=merchant,
                trigger=trigger,
                customer=customer,
            )

            # Validate output
            required_fields = ["body", "cta", "send_as", "suppression_key", "rationale"]
            missing = [f for f in required_fields if f not in composed]
            if missing:
                print(f"  ❌ Missing fields: {missing}\n")
                failed += 1
                continue

            # Check CTA validity
            if composed["cta"] not in ["binary", "open_ended", "none"]:
                print(f"  ⚠️  Invalid CTA: {composed['cta']}\n")

            # Print composition
            print(f"  ✅ Composed successfully")
            print(f"     Body: {composed['body'][:80]}...")
            print(f"     CTA: {composed['cta']}")
            print(f"     Send as: {composed['send_as']}")
            print(f"     Suppression key: {composed['suppression_key']}")
            print(f"     Rationale: {composed['rationale']}\n")

            passed += 1

        except Exception as e:
            print(f"  ❌ Error: {e}\n")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {limit} tests")
    return passed, failed


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    passed, failed = run_local_test(limit=limit)
    sys.exit(0 if failed == 0 else 1)
