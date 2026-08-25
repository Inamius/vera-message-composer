"""
Vera Message Composer Bot

Core message composition engine for merchant growth.
Composes contextually relevant messages based on category, merchant, trigger, and customer context.
"""

import json
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class CategoryContext:
    """Vertical knowledge pack (dentists, salons, etc.)"""
    slug: str
    offer_catalog: list
    voice: dict
    peer_stats: dict
    digest: list
    seasonal_beats: list
    trend_signals: list


@dataclass
class MerchantContext:
    """Per-merchant state"""
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
    """Event that prompts this message"""
    id: str
    scope: str
    kind: str
    source: str
    payload: dict
    urgency: int
    suppression_key: str
    expires_at: str


@dataclass
class CustomerContext:
    """Optional context for customer-facing messages"""
    customer_id: str
    merchant_id: str
    identity: dict
    relationship: dict
    state: str
    preferences: dict
    consent: dict


@dataclass
class ComposedMessage:
    """Output of the compose function"""
    body: str
    cta: str
    send_as: str
    suppression_key: str
    rationale: str


# ============================================================================
# Composer Engine
# ============================================================================

class VeraComposer:
    """Message composition engine using Claude via Omniroute gateway"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OMNIROUTE_API_KEY")
        self.base_url = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128")
        self.model = "claude/combo/narendra"
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
        """Compose a message based on context"""

        prompt = self._build_prompt(category, merchant, trigger, customer)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = None
        for block in response.content:
            if hasattr(block, 'text'):
                response_text = block.text
                break
            elif hasattr(block, 'thinking'):
                response_text = block.thinking
                break

        if not response_text:
            response_text = str(response.content[0]) if response.content else ""

        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "{" in response_text:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                json_str = response_text[start:end]
            else:
                json_str = response_text

            composed = json.loads(json_str)
        except (json.JSONDecodeError, IndexError, AttributeError) as e:
            composed = {
                "body": "Unable to compose message at this time.",
                "cta": "none",
                "send_as": "vera",
                "suppression_key": trigger.get("suppression_key", "error"),
                "rationale": f"Composition error: {str(e)}",
            }

        composed = self._validate_output(composed, trigger)
        return composed

    def _build_prompt(
        self, category: dict, merchant: dict, trigger: dict, customer: Optional[dict]
    ) -> str:
        """Build LLM prompt"""

        merchant_name = merchant.get("identity", {}).get("name", "Merchant")
        merchant_locality = merchant.get("identity", {}).get("locality", "")
        merchant_language = merchant.get("identity", {}).get("language", "en")
        category_slug = category.get("slug", "general")
        trigger_kind = trigger.get("kind", "general")
        trigger_source = trigger.get("source", "internal")

        conv_history = merchant.get("conversation_history", [])
        last_turns = "\n".join(
            [
                f"  {msg.get('role', 'user')}: {msg.get('body', '')[:100]}"
                for msg in conv_history[-3:]
            ]
        )

        offers_list = merchant.get("offers", [])
        offers_text = "\n".join(
            [f"  - {offer.get('service', '')} @ ₹{offer.get('price', '')}" for offer in offers_list[:5]]
        )

        digest_items = category.get("digest", [])[:3]
        digest_text = "\n".join(
            [f"  - {item.get('title', '')} ({item.get('source', '')})" for item in digest_items]
        )

        voice = category.get("voice", {})
        voice_text = voice.get("tone", "professional")
        taboos = voice.get("taboos", [])
        taboos_text = ", ".join(taboos) if taboos else "none listed"

        prompt = f"""You are Vera, an AI assistant helping merchants grow their business.

## TASK
Compose a single WhatsApp message for {merchant_name} in {merchant_locality}.

## CONSTRAINTS
1. Use REAL numbers, dates, and facts from context only
2. ONE clear call-to-action (binary YES/NO, open question, or none)
3. Match the {category_slug} tone and vocabulary
4. Personalize to this merchant's state
5. Match {merchant_language} preference
6. Temperature is 0; same input → same output

## CONTEXT

### Merchant
- Name: {merchant_name}
- Locality: {merchant_locality}
- Language: {merchant_language}
- Performance (30d): Views={merchant.get("performance", {}).get("views", 0)}, Calls={merchant.get("performance", {}).get("calls", 0)}, CTR={merchant.get("performance", {}).get("ctr", 0):.2%}
- Active offers:
{offers_text if offers_text else "  (none)"}

### Recent history
{last_turns if last_turns else "  (no prior messages)"}

### Category: {category_slug}
- Tone: {voice_text}
- Taboos: {taboos_text}

### Trigger
- Kind: {trigger_kind}
- Source: {trigger_source}
- Urgency: {trigger.get("urgency", 2)}/5

### Latest digest
{digest_text if digest_text else "  (none)"}

"""

        if customer:
            customer_name = customer.get("identity", {}).get("name", "Customer")
            customer_language = customer.get("identity", {}).get("language_pref", "en")
            customer_state = customer.get("state", "active")
            last_visit = customer.get("relationship", {}).get("last_visit", "unknown")

            prompt += f"""
### Customer (customer-facing message)
- Name: {customer_name}
- Language: {customer_language}
- State: {customer_state}
- Last visit: {last_visit}

Send as: merchant_on_behalf
"""
        else:
            prompt += """
### Scope: Merchant-facing
Send as: vera
"""

        if trigger_kind == "research_digest":
            prompt += """
## RESEARCH DIGEST PATTERN
- Open with headline + source citation
- Connect to merchant's customer cohort
- Offer to draft followup
- CTA: open_ended
"""
        elif trigger_kind == "recall_due":
            prompt += """
## RECALL PATTERN
- Warm greeting
- Time since last visit + recall window
- Real slot times or ask preference
- Price + bundled add-on
- CTA: binary or multi-choice
"""
        elif trigger_kind == "perf_spike":
            prompt += """
## SPIKE PATTERN
- Congratulate on spike (specific number)
- Suggest next action
- Offer concrete action
- CTA: binary
"""
        elif trigger_kind == "perf_dip":
            prompt += """
## DIP PATTERN
- Acknowledge dip + normalize it
- Reframe as opportunity
- Offer specific action
- CTA: binary
"""

        prompt += f"""

## OUTPUT
Return JSON only (no markdown, no preamble):
{{
  "body": "WhatsApp message (1-3 paragraphs)",
  "cta": "binary" or "open_ended" or "none",
  "send_as": "vera" or "merchant_on_behalf",
  "suppression_key": "{trigger.get("suppression_key", "default")}",
  "rationale": "one line: why this message"
}}

Compose now:
"""

        return prompt

    def _validate_output(self, composed: dict, trigger: dict) -> dict:
        """Validate output"""

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

        if composed["cta"] not in ["binary", "open_ended", "none"]:
            composed["cta"] = "open_ended"

        if composed["send_as"] not in ["vera", "merchant_on_behalf"]:
            composed["send_as"] = "vera"

        return composed


_composer = None


def get_composer():
    global _composer
    if _composer is None:
        _composer = VeraComposer()
    return _composer


def compose(category: dict, merchant: dict, trigger: dict, customer: dict = None) -> dict:
    """Main entry point for composition"""
    return get_composer().compose(category, merchant, trigger, customer)


if __name__ == "__main__":
    print("Vera Message Composer loaded successfully.")
