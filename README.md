# Vera Message Composer

A deterministic message engine for merchant growth on WhatsApp using Claude AI.

## Overview

Vera composes contextually relevant messages for merchants based on:
- **Category Context** — vertical knowledge (voice, offers, research digest)
- **Merchant Context** — merchant state (identity, performance, offers, history)
- **Trigger Context** — event that prompts the message (research digest, recall, performance spike, etc.)
- **Customer Context** (optional) — customer state for customer-facing messages

Messages are scored on:
- Specificity (real numbers, dates, offers)
- Category fit (matching voice and vocabulary)
- Merchant fit (personalized to merchant state)
- Trigger relevance (clear reason for messaging now)
- Engagement compulsion (strong CTA)

## Setup

### Prerequisites
- Python 3.11+
- Omniroute API key (for Claude access)

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Create `.env` file:
```
OMNIROUTE_API_KEY=your_key
OMNIROUTE_BASE_URL=http://localhost:20128
```

### Running

```bash
# Start server
python main.py

# Test locally
python test_local.py 30
```

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| /v1/context | POST | Store context (idempotent) |
| /v1/tick | POST | Compose messages from triggers |
| /v1/reply | POST | Handle merchant replies |
| /v1/healthz | GET | Health check |
| /v1/metadata | GET | Bot metadata |

## Design

### Deterministic Composition
- Temperature=0 for reproducibility
- Same input always produces same output
- No hardcoded patterns

### No Fabrication
All numbers must come from provided context. No inventing data.

### Idempotent Context Storage
- Contexts stored by (scope, context_id, version)
- Higher version replaces lower version
- Re-posting same version is no-op

## Dataset

```
expanded/
├── categories/    # 5 categories
├── merchants/     # 50 merchants
├── customers/     # 200 customers
├── triggers/      # 100 triggers
└── test_pairs.json
```

## Deployment

Deployed on Railway: https://vera-message-composer-production.up.railway.app

All 5 endpoints are live and responding.

## Testing

```bash
# Verify all endpoints work
python final_verification_test.py

# Run against judge simulator
python judge_simulator.py
```

## Submission

Bot URL: `https://vera-message-composer-production.up.railway.app`

Files included:
- bot.py — Message composition engine
- main.py — FastAPI server
- requirements.txt — Dependencies
- test_local.py — Local testing
- expanded/ — Dataset

---

Status: Ready for submission
Last updated: 2026-08-25
