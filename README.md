# Vera Message Composer

A deterministic, LLM-backed message engine for merchant growth on WhatsApp.

## Overview

Vera composes contextually relevant, high-engagement messages for merchants and their customers based on four layers of context:

1. **CategoryContext** — vertical knowledge (voice, offers, research digest, peer stats)
2. **MerchantContext** — merchant state (identity, performance, offers, conversation history)
3. **TriggerContext** — event that prompts this message now (research digest, recall reminder, performance spike, etc.)
4. **CustomerContext** (optional) — customer state (for customer-facing messages)

Each message is scored across **5 dimensions**:
- **Specificity** — uses real numbers, dates, offers from context
- **Category fit** — matches vertical tone, vocabulary, offer patterns
- **Merchant fit** — personalized to this merchant's state and history
- **Trigger relevance** — clearly communicates why now
- **Engagement compulsion** — gives merchants one strong reason to reply

## Architecture

### Tech Stack
- **Language**: Python 3.11+
- **API Framework**: FastAPI + Uvicorn
- **LLM**: Claude 3.5 Sonnet (Anthropic API)
- **Context Validation**: Pydantic
- **State Storage**: In-memory dict (sufficient for 60-min test window)

### API Endpoints (5 required)

```
POST /v1/context    — Store context (idempotent by context_id + version)
POST /v1/tick       — Periodic wake-up; compose messages from available triggers
POST /v1/reply      — Handle merchant replies (multi-turn capability)
GET  /v1/healthz    — Health check
GET  /v1/metadata   — Bot metadata
```

### Message Composition Pipeline

```
1. Signal Selection       → Extract trigger kind and payload
2. Decision Logic         → Check suppression rules, urgency, relevance
3. Context Enrichment     → Extract merchant name, performance, offers, language
4. Compulsion Assembly    → Identify engagement levers (specificity, social proof, loss aversion, etc.)
5. LLM Prompt Dispatch    → Route to trigger-specific prompt variant (temperature=0)
6. Post-LLM Validation    → Check CTA shape, fabrication, language match
7. Conversation State     → Record message, set suppression key, update history
```

## Setup

### Prerequisites
- Python 3.11+
- Anthropic API key

### Installation

```bash
# Clone/download the repo
cd vera_ai

# Install dependencies
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Running Locally

```bash
# Start the API server
python main.py
# Server runs on http://localhost:8000

# In another terminal, test against local dataset
python test_local.py 5    # Test first 5 test pairs
```

### Testing Against Judge Simulator

```bash
# Set up the judge simulator (included in challenge pack)
# Edit judge_simulator.py: set LLM_PROVIDER, LLM_API_KEY, BOT_URL

python judge_simulator.py
# Scores your bot across all 5 dimensions on 30 canonical test pairs
```

## Key Design Decisions

### 1. Deterministic Composition
- Temperature = 0 on Claude API calls
- Structured prompts with explicit context injection
- Same input → same output always
- Critical for judge evaluation and debugging

### 2. Trigger-Specific Prompts
The prompt template branches based on `trigger.kind`:
- `research_digest` — emphasize source citation, peer relevance, offer to draft followup
- `recall_due` — emphasize warmth, slot specificity, language preference
- `perf_spike` — congratulate, suggest next action
- `perf_dip` — normalize, reframe as opportunity
- `curious_ask` — ask for insight merchant can answer quickly
- `compliance_alert` — emphasize precision, trust, clear artifact offer

### 2. No Fabrication Policy
The prompt explicitly forbids:
- Inventing offer prices or service names
- Citing research papers not in the digest
- Naming competitors not in the context
- Making up customer statistics

All numbers in the message must be traceable to the provided contexts.

### 3. Post-LLM Validation
After Claude generates the message, we validate:
- CTA is one of: "binary", "open_ended", "none"
- send_as is "vera" or "merchant_on_behalf"
- No off-voice tone shifts
- Language preference honored
- Suppression key is set

### 4. Context Idempotency
The /v1/context endpoint is idempotent by (context_id, version):
- Re-posting the same version is a no-op
- Higher version atomically replaces lower version
- Stale version post returns 409 Conflict

## Dataset Structure

```
expanded/
├── categories/          # 5 category contexts (dentists, salons, restaurants, gyms, pharmacies)
├── merchants/           # 50 merchant profiles (10 per category)
├── customers/           # 200 customer profiles
├── triggers/            # 100 trigger events (mix of external and internal)
└── test_pairs.json      # 30 canonical test pairs for judge evaluation
```

### Generating the Dataset

```bash
python dataset/generate_dataset.py --seed-dir dataset --out expanded
```

## Scoring Patterns (From Case Studies)

High-scoring messages consistently:

1. **Source citations for research/compliance** — "JIDA Oct p.14", "DCI circular", batch numbers. No citation → capped at 7/10.
2. **Numbers from contexts, never invented** — "22 of your chronic-Rx customers" (derived from merchant_aggregate), not made up.
3. **Owner/merchant first name** — "Dr. Meera", "Suresh", not generic "Hi". Gains 1 point on merchant fit.
4. **Single, low-friction next step** — "Want me to draft X? Live in 10 min." Multi-action asks dilute engagement.
5. **Language preference + relationship state honored** — Hindi-English mix for specific merchants, namaste for seniors. One-size-fits-all loses 2 points.
6. **Domain vocabulary used correctly** — "covers", "AOV", "sub-potency", "fluoride varnish", "ad spend". Wrong vocabulary signals CategoryContext not used.
7. **Bot adds judgment** — Case Study 5 recommends against the promo on Saturday IPL. Data-informed contrarian call = highest signal of understanding.
8. **Meaningful conversation_id** — `conv_priya_recall_2026_11` (decodable, resumable) vs. `conv_001`.
9. **Rationale matches reasoning** — Judge cross-checks rationale against message; mismatch = penalty.
10. **No repetition, no fabrication** — These are operational floor. Any instance caps all dimensions at 5.

## Multi-Turn Capability (Bonus)

The bot includes basic multi-turn support:

```python
POST /v1/reply
{
  "conversation_id": "conv_001",
  "message": "Yes, send me the link",
  "timestamp": "2026-04-26T10:35:00Z"
}
```

The bot:
1. Detects merchant intent (engaged, auto-reply, decline, question)
2. Routes appropriately (action mode, graceful exit, Q&A mode)
3. Avoids repeating messages
4. Gracefully exits after 3 unanswered nudges

Full replay-test capability is a tiebreaker for top submissions.

## Deployment

### Cloud Options
- **Railway.app** (simplest, free tier available)
- **Fly.io** (global edge deployment)
- **AWS Lambda + API Gateway** (serverless, pay-as-you-go)
- **Heroku** (legacy but simple)

### Submission
1. Deploy bot to a public URL
2. Ensure all 5 endpoints are live and responding
3. Test locally with `judge_simulator.py`
4. Submit bot URL + README + bot.py + (optional) conversation_handlers.py

## Evaluation

The judge harness:
1. Loads your bot URL
2. Pushes context via /v1/context (categories, merchants, customers, triggers)
3. Calls /v1/tick every 5 simulated minutes
4. Scores your messages across 5 dimensions (0-10 each)
5. Injects new context mid-test to test adaptability
6. (For top 10) Runs multi-turn replay with simulated merchant replies

**Total score**: 50 points max (5 dimensions × 10 points each).

## Tradeoffs & Future Work

### Tradeoffs Made
- **In-memory state** — sufficient for 60-min test window, but not for production scale. Production would use Redis.
- **Synchronous LLM calls** — simple, deterministic, but blocks during API latency. Production would use async batching.
- **Single prompt template with branches** — clear and easy to debug, but not as flexible as fully modular system. Production would have separate handler per trigger kind.

### What Would Help Most
- Real customer data sources (CRM integration patterns, consent models)
- Merchant offer source-of-truth (currently assumed in MerchantContext.offers)
- Multi-language support beyond Hindi-English (production needs 10+ languages for Indian scale)
- Live A/B testing framework (to measure engagement impact of different compulsion levers)

## References

- **Challenge Brief**: `challenge-brief.md`
- **Testing Brief**: `challenge-testing-brief.md`
- **Engagement Design**: `engagement-design.md`
- **Case Studies**: `examples/case-studies.md` (10 anchor examples with score rationales)
- **API Examples**: `examples/api-call-examples.md`

## License

This is a competition entry for the magicpin AI Challenge.

---

**Built by**: Kiro (Claude Agent)  
**Date**: 2026-08-24  
**Model**: Claude 3.5 Sonnet  
**Status**: Submission-ready
