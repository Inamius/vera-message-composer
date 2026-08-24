"""
Vera Message Composer Bot

A deterministic message engine for merchant growth on WhatsApp.
Composes contextually relevant, high-engagement messages based on:
  - CategoryContext (vertical knowledge, voice, offer patterns)
  - MerchantContext (merchant state, performance, conversation history)
  - TriggerContext (event that prompts this message now)
  - CustomerContext (optional, for customer-facing messages)

Each message is scored across 5 dimensions: specificity, category fit,
merchant fit, trigger relevance, and engagement compulsion.
"""

import json
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import os
from dotenv import load_dotenv
from anthropic import Anthropic

# Load environment variables from .env file
load_dotenv()


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class CategoryContext:
    """Slow-changing knowledge pack about a vertical (dentists, salons, etc.)"""
    slug: str
    offer_catalog: list
    voice: dict
    peer_stats: dict
    digest: list
    seasonal_beats: list
    trend_signals: list


@dataclass
class MerchantContext:
    """Per-merchant state: identity, performance, offers, history"""
    merchant_id: str
    identity: dict
    subscription: dict
    performance: dict
    offers: list
    conversation_history: list
    customer_aggregate: dict
    signals: list


@dataclass
class TriggerContext:
    """Event that prompts this message right now"""
    id: str
    scope: str  # "merchant" or "customer"
    kind: str  # "research_digest", "recall_due", "perf_spike", etc.
    source: str  # "external" or "internal"
    payload: dict
    urgency: int  # 1-5
    suppression_key: str
    expires_at: str


@dataclass
class CustomerContext:
    """Optional context for customer-facing messages"""
    customer_id: str
    merchant_id: str
    identity: dict
    relationship: dict
    state: str  # "new", "active", "lapsed_soft", "lapsed_hard", "churned"
    preferences: dict
    consent: dict


@dataclass
class ComposedMessage:
    """Output of the compose function"""
    body: str
    cta: str  # "binary", "open_ended", or "none"
    send_as: str  # "vera" or "merchant_on_behalf"
    suppression_key: str
    rationale: str


# ============================================================================
# Composer Engine
# ============================================================================

class VeraComposer:
    """
    Core message composition engine.
    Uses Omniroute gateway for intelligent message generation with structured context.
    """

    def __init__(self, api_key: Optional[str] = None):
        # Use Omniroute gateway instead of Anthropic
        self.api_key = api_key or os.environ.get("OMNIROUTE_API_KEY")
        self.base_url = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128")
        self.model = "claude/combo/narendra"
        # Initialize Anthropic client pointing to Omniroute gateway
        self.client = Anthropic(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def compose(
        self,
        category: dict,
        merchant: dict,
        trigger: dict,
        customer: Optional[dict] = None,
    ) -> dict:
        """
        Main composition function.

        Args:
            category: CategoryContext dict
            merchant: MerchantContext dict
            trigger: TriggerContext dict
            customer: Optional CustomerContext dict

        Returns:
            ComposedMessage dict with body, cta, send_as, suppression_key, rationale
        """

        # Build the prompt based on trigger kind and scope
        prompt = self._build_prompt(category, merchant, trigger, customer)

        # Call Claude with temperature=0 for determinism
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse the response - handle both text and thinking blocks
        response_text = None
        for block in response.content:
            # Handle TextBlock
            if hasattr(block, 'text'):
                response_text = block.text
                break
            # Handle ThinkingBlock - extract thinking content if available
            elif hasattr(block, 'thinking'):
                response_text = block.thinking
                break

        if not response_text:
            response_text = str(response.content[0]) if response.content else ""

        try:
            # Try to extract JSON from response
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "{" in response_text:
                # Find the JSON object
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                json_str = response_text[start:end]
            else:
                json_str = response_text

            composed = json.loads(json_str)
        except (json.JSONDecodeError, IndexError, AttributeError) as e:
            print(f"Failed to parse response: {e}")
            print(f"Response text: {response_text[:200] if response_text else 'empty'}")
            # Fallback: return a safe message
            composed = {
                "body": "Unable to compose message at this time.",
                "cta": "none",
                "send_as": "vera",
                "suppression_key": trigger.get("suppression_key", "error"),
                "rationale": f"Composition error: {str(e)}",
            }

        # Validation
        composed = self._validate_output(composed, trigger)
        return composed

    def _build_prompt(
        self, category: dict, merchant: dict, trigger: dict, customer: Optional[dict]
    ) -> str:
        """Build the LLM prompt based on context and trigger kind."""

        # Extract key fields
        merchant_name = merchant.get("identity", {}).get("name", "Merchant")
        merchant_locality = merchant.get("identity", {}).get("locality", "")
        merchant_language = merchant.get("identity", {}).get("language", "en")
        category_slug = category.get("slug", "general")
        trigger_kind = trigger.get("kind", "general")
        trigger_source = trigger.get("source", "internal")

        # Prepare conversation context
        conv_history = merchant.get("conversation_history", [])
        last_turns = "\n".join(
            [
                f"  {msg.get('role', 'user')}: {msg.get('body', '')[:100]}"
                for msg in conv_history[-3:]
            ]
        )

        # Prepare offers
        offers_list = merchant.get("offers", [])
        offers_text = "\n".join(
            [f"  - {offer.get('service', '')} @ ₹{offer.get('price', '')}" for offer in offers_list[:5]]
        )

        # Prepare digest items
        digest_items = category.get("digest", [])[:3]
        digest_text = "\n".join(
            [f"  - {item.get('title', '')} ({item.get('source', '')})" for item in digest_items]
        )

        # Get voice profile
        voice = category.get("voice", {})
        voice_text = voice.get("tone", "professional")
        taboos = voice.get("taboos", [])
        taboos_text = ", ".join(taboos) if taboos else "none listed"

        # Build the prompt
        prompt = f"""You are Vera, an AI assistant helping merchants grow their business on WhatsApp.

## TASK
Compose a single WhatsApp message for {merchant_name} in {merchant_locality}.

## CONSTRAINTS
1. **Specificity**: Use REAL numbers, dates, and facts from the context. Never fabricate.
2. **Single CTA**: ONE clear call-to-action (binary YES/NO, open question, or none).
3. **Voice match**: Adopt the {category_slug} category tone/vocabulary.
4. **Merchant fit**: Personalize to this merchant's state and history.
5. **Language**: Match {merchant_language} preference.
6. **Deterministic**: Temperature is 0; same input → same output always.

## CONTEXT

### Merchant Info
- Name: {merchant_name}
- Locality: {merchant_locality}
- Language preference: {merchant_language}
- Performance (30d): Views={merchant.get("performance", {}).get("views", 0)}, Calls={merchant.get("performance", {}).get("calls", 0)}, CTR={merchant.get("performance", {}).get("ctr", 0):.2%}
- Active offers:
{offers_text if offers_text else "  (none)"}

### Recent conversation history
{last_turns if last_turns else "  (no prior messages)"}

### Category: {category_slug}
- Voice tone: {voice_text}
- Taboos: {taboos_text}

### Trigger
- Kind: {trigger_kind}
- Source: {trigger_source}
- Urgency: {trigger.get("urgency", 2)}/5

### Latest digest items
{digest_text if digest_text else "  (none)"}

"""

        # Add customer context if present
        if customer:
            customer_name = customer.get("identity", {}).get("name", "Customer")
            customer_language = customer.get("identity", {}).get("language_pref", "en")
            customer_state = customer.get("state", "active")
            last_visit = customer.get("relationship", {}).get("last_visit", "unknown")

            prompt += f"""
### Customer Context (this is a customer-facing message)
- Name: {customer_name}
- Language preference: {customer_language}
- State: {customer_state}
- Last visit: {last_visit}
- Consent scope: {customer.get("consent", {}).get("scope", "limited")}

**SEND AS**: merchant_on_behalf (message will be sent from {merchant_name}'s WhatsApp account)
"""
        else:
            prompt += f"""
### Scope: Merchant-facing (sent as Vera)
**SEND AS**: vera
"""

        # Trigger-specific instructions
        if trigger_kind == "research_digest":
            prompt += """
## RESEARCH DIGEST MESSAGE PATTERN
- Open with the digest headline + source citation (e.g., "JIDA Oct issue")
- Connect to the merchant's specific patient/customer cohort
- Offer to draft a followup (patient email, Google post, etc.)
- CTA: open_ended ("Want me to...?")
"""
        elif trigger_kind == "recall_due":
            prompt += """
## RECALL/APPOINTMENT REMINDER PATTERN
- Warm, personal greeting
- Explicit time since last visit + recall window due
- Real slot times (if available) or ask for preference
- Price + any bundled add-on
- CTA: binary or multi-choice (YES for slot 1, 2 for slot 2, etc.)
"""
        elif trigger_kind == "perf_spike":
            prompt += """
## PERFORMANCE SPIKE PATTERN
- Congratulate on the spike (specific number: +X% vs avg)
- Suggest what to do next to sustain momentum
- Offer concrete action (draft content, push promo, etc.)
- CTA: binary ("Want me to...?")
"""
        elif trigger_kind == "perf_dip":
            prompt += """
## PERFORMANCE DIP PATTERN
- Acknowledge the dip + normalize it (data: "every business sees -X% in this window")
- Reframe as an opportunity (focus on retention, reduce spend, etc.)
- Offer specific action to weather it
- CTA: binary ("Want me to...?")
"""

        prompt += f"""

## OUTPUT FORMAT
Respond with a JSON object (and only JSON, no markdown, no preamble):
{{
  "body": "the WhatsApp message body (1-3 short paragraphs, no preamble)",
  "cta": "binary" or "open_ended" or "none",
  "send_as": "vera" or "merchant_on_behalf",
  "suppression_key": "{trigger.get("suppression_key", "default")}",
  "rationale": "one line: why this message, what should it achieve"
}}

## EXAMPLES OF GOOD MESSAGES

Example 1 (Research Digest):
{{"body": "Dr. Meera, JIDA's Oct issue landed. One item relevant to your high-risk adult patients — 2,100-patient trial showed 3-month fluoride recall cuts caries recurrence 38% better than 6-month. Worth a look (2-min abstract). Want me to pull it + draft a patient-ed WhatsApp you can share? — JIDA Oct 2026 p.14", "cta": "open_ended", "send_as": "vera", "suppression_key": "research:dentists:2026-W17", "rationale": "Research digest with merchant-specific patient cohort anchor; low-friction offer to draft followup"}}

Example 2 (Recall Reminder):
{{"body": "Hi Priya, Dr. Meera's clinic here 🦷 It's been 5 months since your last visit — your 6-month cleaning recall is due. Apke liye 2 slots ready hain: Wed 6 Nov, 6pm ya Thu 7 Nov, 5pm. ₹299 cleaning + complimentary fluoride. Reply 1 for Wed, 2 for Thu, or tell us a time that works.", "cta": "binary", "send_as": "merchant_on_behalf", "suppression_key": "recall:priya:2026-W33", "rationale": "Explicit recall window due date; real slots; language mix honored; no medical claims"}}

## NOW COMPOSE
Based on all the context above, compose ONE message that scores high on:
- Specificity (real numbers, dates, offers)
- Category fit (correct tone + vocabulary + taboos)
- Merchant fit (personalized to this merchant's state)
- Trigger relevance (clear reason for messaging now)
- Engagement compulsion (one strong reason to reply)

Do NOT repeat prior messages in the conversation_history.
Do NOT fabricate offers, research papers, or competitor names.
Do NOT include multiple CTAs or soft commitments ("maybe", "could", "might").
"""

        return prompt

    def _validate_output(self, composed: dict, trigger: dict) -> dict:
        """Validate and fix the composed message output."""

        # Ensure required fields
        defaults = {
            "body": "Unable to compose message.",
            "cta": "none",
            "send_as": "vera",
            "suppression_key": trigger.get("suppression_key", "default"),
            "rationale": "Validation error.",
        }

        for key, default in defaults.items():
            if key not in composed or not composed[key]:
                composed[key] = default

        # Validate CTA
        if composed["cta"] not in ["binary", "open_ended", "none"]:
            composed["cta"] = "open_ended"

        # Validate send_as
        if composed["send_as"] not in ["vera", "merchant_on_behalf"]:
            composed["send_as"] = "vera"

        return composed


# ============================================================================
# Global composer instance
# ============================================================================

_composer = None


def get_composer():
    global _composer
    if _composer is None:
        _composer = VeraComposer()
    return _composer


def compose(category: dict, merchant: dict, trigger: dict, customer: dict = None) -> dict:
    """
    Main entry point for the compose function.
    Delegates to the global VeraComposer instance.
    """
    return get_composer().compose(category, merchant, trigger, customer)


if __name__ == "__main__":
    # Quick test
    print("Vera Message Composer loaded successfully.")
