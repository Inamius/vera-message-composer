# Vera Message Composer — Architecture Design

**Status**: Design phase  
**Last updated**: 2026-08-24  
**Goal**: Build a deterministic, LLM-backed message composer that scores well across all 5 judge dimensions.

---

## High-level shape

```
POST /v1/context → Store context (category, merchant, customer, trigger)
POST /v1/tick    → Compose messages using stored context
POST /v1/reply   → Handle merchant replies (multi-turn)
GET  /v1/healthz → Health check
GET  /v1/metadata → Bot metadata
```

The bot maintains **stateful context storage** (in-memory or Redis) and **conversation state** (what's been said, what the merchant replied).

---

## Core composition pipeline

```
Input: (category, merchant, trigger, customer?)
  ↓
[1] Signal Selection
    - Extract trigger kind, payload, urgency
    - Route to trigger-specific prompt variant
    ↓
[2] Decision Logic
    - Does this trigger apply to this merchant NOW?
    - Any suppression rules? (conversation_history, dormancy, repetition)
    - Urgency vs other pending triggers
    ↓
[3] Context Enrichment
    - Extract merchant: name, locality, performance, offers, language_pref
    - Extract category: voice profile, peer stats, offer catalog, digest items
    - If customer scope: name, language, relationship, consent
    ↓
[4] Compulsion Assembly
    - Identify which levers to use (specificity, social proof, loss aversion, curiosity, effort ext, reciprocity, ask-merchant)
    - Anchor on real numbers from contexts (never fabricate)
    - Select offer from merchant.offers if applicable
    ↓
[5] LLM Prompt Dispatch
    - Route to variant prompt based on trigger.kind (research_digest, recall_due, perf_spike, etc.)
    - Inject merchant/customer context, category voice rules, example patterns
    - Set temperature=0 for determinism
    ↓
[6] Post-LLM Validation
    - Parse body, cta, send_as
    - Check CTA shape (binary/open_ended/none)
    - Verify no hallucinations (check offer exists, citations are valid)
    - Check language preference honored
    ↓
Output: {body, cta, send_as, suppression_key, rationale}
    ↓
[7] Conversation State Update
    - Record this message in conversation_history
    - Set suppression_key for dedup
    - Mark suppress_until timestamp
```

---

## Tech stack decision

### Language: Python 3.11+
- FastAPI for HTTP server (async, fast, type-safe)
- Pydantic for context validation
- LiteLLM or anthropic-sdk for LLM calls (Claude for composition, fallback to local smaller model if needed)
- In-memory dict for context storage (reset on crash, but fine for 60-min test window)
- dataclasses for context structures

### Model: Claude (frontier model)
- Deterministic behavior with temperature=0
- Strong instruction-following + chain-of-thought reasoning
- Can handle complex context + routing logic
- Cost acceptable for competition (API usage budget provided)

### Local testing: judge_simulator.py
- Included in starter pack
- Validates all 5 endpoints under judge conditions
- Scores output across all dimensions
- 30s timeout per call, 20 actions/tick cap

---

## Data structures

```python
# contexts.py
@dataclass
class CategoryContext:
    slug: str
    offer_catalog: list[dict]        # [{id, service, price}, ...]
    voice: dict                       # {tone, taboos, vocabulary, examples}
    peer_stats: dict                  # {avg_rating, avg_reviews, avg_ctr}
    digest: list[dict]                # [{title, source, payload}]
    seasonal_beats: list[dict]
    trend_signals: list[dict]

@dataclass
class MerchantContext:
    merchant_id: str
    identity: dict                    # name, place_id, locality, city, language
    subscription: dict
    performance: dict                 # views, calls, ctr, leads, directions, deltas
    offers: list[dict]                # active + paused
    conversation_history: list[dict]  # last N turns w/ engagement tags
    customer_aggregate: dict
    signals: list[str]                # derived flags

@dataclass
class TriggerContext:
    id: str
    scope: str                        # "merchant" | "customer"
    kind: str                         # "research_digest", "recall_due", etc.
    source: str                       # "external" | "internal"
    payload: dict
    urgency: int                      # 1-5
    suppression_key: str
    expires_at: str                   # ISO datetime

@dataclass
class CustomerContext:
    customer_id: str
    merchant_id: str
    identity: dict                    # name, phone, language_pref
    relationship: dict
    state: str                        # "new" | "active" | "lapsed_soft" | ...
    preferences: dict
    consent: dict

@dataclass
class ComposedMessage:
    body: str
    cta: str                          # "binary" | "open_ended" | "none"
    send_as: str                      # "vera" | "merchant_on_behalf"
    suppression_key: str
    rationale: str
```

---

## Prompt strategy

One master prompt template with dispatch logic:

```
You are Vera, an AI assistant helping merchants grow their business.

Your task: compose a WhatsApp message for a merchant (or their customer).

## Constraints
1. Be specific: use real numbers, dates, offers from the context
2. Single CTA: binary YES/NO or one open-ended ask
3. Voice match: adopt the tone/vocabulary of the category
4. Merchant fit: personalize to this merchant's state
5. No fabrication: never invent offers, research, or competitor names
6. Deterministic: same input → same output (you use temperature=0)

## Context provided
- Category: {category_slug} — {category_voice_profile}
- Merchant: {merchant_name}, {locality}, {merchant_state_summary}
- Trigger: {trigger_kind} — {trigger_payload}
- Customer: {customer_name if present, else "none"}

## Category voice rules
{voice_profile}

## Category offer catalog
{offer_catalog}

## Merchant's active offers
{merchant_offers}

## Merchant's conversation history (last 3 turns)
{conversation_history}

## Recent category digest items
{digest_items}

## Trigger details
{trigger_details}

## Compose the message
- Output a JSON object with: body, cta, send_as, suppression_key, rationale
- cta must be one of: "binary" (YES/NO), "open_ended" (open question), "none"
- send_as must be: "vera" (merchant-facing) or "merchant_on_behalf" (customer-facing)
- suppression_key: unique key for dedup, e.g., "research:category:W{week_num}"
- rationale: one-line explanation of why this message, what it should achieve

## Examples from your category
[Example 1: successful message + score rationale]
[Example 2: high-engagement message + score rationale]
```

**Variant prompts** per trigger kind:
- `research_digest`: emphasize source citation, peer relevance, offer to draft followup
- `recall_due`: emphasize warmth + slot specificity + language preference
- `perf_spike`: emphasize congratulations + what to do next
- `perf_dip`: emphasize it's normal + reframe as opportunity
- `curious_ask`: keep merchant engagement high, ask for insight they can answer quickly
- `compliance_alert`: emphasize trust + precision + clear artifact offer

---

## Conversation state & multi-turn

Store per-conversation:
```python
@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str
    customer_id: str | None
    scope: str                       # "merchant" | "customer"
    messages: list[{
        role: "vera" | "merchant" | "customer",
        body: str,
        timestamp: str,
        intent_detected: str | None, # "engaged", "auto_reply", "decline", "question", ...
    }]
    last_vera_message: dict          # last thing Vera sent
    merchant_intent: str | None      # "interested", "not_interested", "needs_clarification"
    suppression_until: datetime | None
```

**Multi-turn rules**:
1. After merchant reply, analyze intent
2. If auto-reply detected (same msg verbatim 2+ times): route to graceful exit
3. If "I want to join" / "yes let's do it": route to action immediately
4. If question: answer directly, don't pitch again
5. If decline: respect it, don't re-pitch
6. If silence after 3 nudges: gracefully exit

---

## API endpoints

### POST /v1/context
```json
{
  "scope": "category" | "merchant" | "customer" | "trigger",
  "context_id": "dentists" | "m_001_drmeera" | "c_001_priya" | "trg_research_dentists_w17",
  "version": 3,
  "payload": { /* full context object */ },
  "delivered_at": "2026-04-26T10:00:00Z"
}
```
Response: `{accepted: true, ack_id: "ack_abc123", stored_at: "2026-04-26T10:00:00.123Z"}`

### POST /v1/tick
```json
{
  "now": "2026-04-26T10:30:00Z",
  "available_triggers": ["trg_research_dentists", "trg_recall_priya"]
}
```
Response: 
```json
{
  "actions": [
    {
      "conversation_id": "conv_001",
      "merchant_id": "m_001_drmeera",
      "customer_id": null,
      "send_as": "vera",
      "trigger_id": "trg_research_dentists",
      "template_name": "vera_research_digest_v1",
      "template_params": ["Dr. Meera", "JIDA Oct issue"],
      "body": "Dr. Meera, JIDA's Oct issue landed...",
      "cta": "open_ended",
      "suppression_key": "research:dentists:2026-W17",
      "rationale": "External research digest with merchant-relevant clinical anchor..."
    }
  ]
}
```

### POST /v1/reply
```json
{
  "conversation_id": "conv_001",
  "message": "Yes, send me the link",
  "timestamp": "2026-04-26T10:35:00Z"
}
```
Response:
```json
{
  "action": {
    "conversation_id": "conv_001",
    "body": "Dr. Meera, here's the JIDA Oct abstract...",
    "cta": "binary",
    "suppression_key": "research:dentists:follow_up:001",
    "rationale": "Merchant replied affirmatively; delivering promised artifact"
  }
}
```

### GET /v1/healthz
Response: `{status: "ok", timestamp: "2026-04-26T10:30:00Z"}`

### GET /v1/metadata
Response:
```json
{
  "name": "Vera Message Composer",
  "version": "1.0.0",
  "model": "claude-3-5-sonnet",
  "capability_tags": ["merchant_engagement", "customer_recall", "research_digest", "performance_insights", "compliance_alert"],
  "supports_multi_turn": true
}
```

---

## Validation & safety

### Pre-send checks
1. **CTA shape**: is it "binary", "open_ended", or "none"?
2. **Fabrication check**: does every number/offer/source appear in contexts?
3. **Language match**: does the message match merchant's language_pref?
4. **Repetition check**: is this message verbatim what was sent before?
5. **Tone match**: does the message match category voice profile?
6. **Length**: no hard cap, but keep concise

### Failure modes
- LLM timeout (30s cap) → return 500 error
- Context not found → return 404
- Invalid CTA → re-prompt with fix
- Fabrication detected → re-prompt with "only use facts from context"

---

## Deployment

### Local development
```bash
python -m pip install fastapi uvicorn anthropic pydantic python-dotenv
python main.py
# http://localhost:8000/
```

### Test against judge_simulator
```bash
python judge_simulator.py
# Sets LLM_PROVIDER, LLM_API_KEY, BOT_URL in the script
# Scores the 30 canonical test pairs
```

### Cloud deployment
- Deploy to Railway, Fly.io, or AWS Lambda + API Gateway
- Expose single public URL (e.g., https://vera-bot-xyz.fly.dev)
- Keep bot URL stable for the duration of the test (60 min)

---

## Success criteria

- All 5 endpoints respond correctly
- Context storage is idempotent by (context_id, version)
- Compose output scores 40+ / 50 on average across 30 test pairs
- No fabrication, no repetition, no off-voice messages
- Multi-turn capability (bonus): handle merchant replies intelligently
- Timeout compliance: all responses < 30s

---

## Next steps

1. Scaffold FastAPI server with 5 endpoints
2. Load + parse the 30 test pairs from dataset
3. Build prompt template with trigger-specific variants
4. Integrate Claude API (temperature=0)
5. Add post-LLM validation layer
6. Test locally against judge_simulator.py
7. Iterate on scoring and prompt tuning
8. Deploy to cloud
9. Submit bot URL
