"""
Vera Message Composer API Server

Exposes 5 endpoints for the judge harness:
  - POST /v1/context    → Store context (idempotent by context_id + version)
  - POST /v1/tick       → Compose messages using available triggers
  - POST /v1/reply      → Handle merchant replies (multi-turn)
  - GET  /v1/healthz    → Health check
  - GET  /v1/metadata   → Bot metadata
"""

import json
import os
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from bot import compose

# ============================================================================
# Request/Response Models
# ============================================================================


class ContextPayload(BaseModel):
    """POST /v1/context request"""

    scope: str  # "category", "merchant", "customer", "trigger"
    context_id: str
    version: int
    payload: dict
    delivered_at: str


class ContextResponse(BaseModel):
    """POST /v1/context response"""

    accepted: bool
    ack_id: Optional[str] = None
    stored_at: Optional[str] = None
    reason: Optional[str] = None
    details: Optional[str] = None


class TickRequest(BaseModel):
    """POST /v1/tick request"""

    now: str
    available_triggers: List[str]


class ComposedAction(BaseModel):
    """Action object in /v1/tick response"""

    conversation_id: str
    merchant_id: str
    customer_id: Optional[str]
    send_as: str
    trigger_id: str
    template_name: str
    template_params: List[str]
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    """POST /v1/tick response"""

    actions: List[ComposedAction]


class ReplyRequest(BaseModel):
    """POST /v1/reply request"""

    conversation_id: str
    message: str
    timestamp: str


class ReplyAction(BaseModel):
    """Action object in /v1/reply response"""

    conversation_id: str
    body: str
    cta: str
    suppression_key: str
    rationale: str


class ReplyResponse(BaseModel):
    """POST /v1/reply response"""

    action: ReplyAction


class HealthResponse(BaseModel):
    """GET /v1/healthz response"""

    status: str
    timestamp: str


class MetadataResponse(BaseModel):
    """GET /v1/metadata response"""

    name: str
    version: str
    model: str
    capability_tags: List[str]
    supports_multi_turn: bool


# ============================================================================
# In-Memory State
# ============================================================================


class StateStore:
    """In-memory storage for contexts and conversations"""

    def __init__(self):
        self.contexts = {}  # {context_id: {version: N, payload: {...}, stored_at: ...}}
        self.conversations = {}  # {conversation_id: {messages: [...], merchant_id, customer_id, ...}}

    def store_context(self, scope: str, context_id: str, version: int, payload: dict):
        """Store context, rejecting if version is stale"""
        key = f"{scope}:{context_id}"

        if key in self.contexts:
            current_version = self.contexts[key]["version"]
            if version < current_version:
                return False, current_version  # Stale version

        self.contexts[key] = {
            "version": version,
            "payload": payload,
            "stored_at": datetime.utcnow().isoformat() + "Z",
        }
        return True, version

    def get_context(self, scope: str, context_id: str):
        """Get context by scope and context_id"""
        key = f"{scope}:{context_id}"
        if key in self.contexts:
            return self.contexts[key]["payload"]
        return None

    def start_conversation(self, conversation_id: str, merchant_id: str, customer_id: Optional[str]):
        """Start a new conversation"""
        self.conversations[conversation_id] = {
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "messages": [],
        }

    def add_message(self, conversation_id: str, role: str, body: str, timestamp: str):
        """Add a message to a conversation"""
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        self.conversations[conversation_id]["messages"].append(
            {"role": role, "body": body, "timestamp": timestamp}
        )

    def get_conversation(self, conversation_id: str):
        """Get conversation state"""
        return self.conversations.get(conversation_id)


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(title="Vera Message Composer", version="1.0.0")
state_store = StateStore()


@app.post("/v1/context", response_model=ContextResponse)
async def receive_context(payload: ContextPayload):
    """
    Receive and store context (idempotent by scope + context_id + version)
    """
    try:
        accepted, current_or_new_version = state_store.store_context(
            payload.scope, payload.context_id, payload.version, payload.payload
        )

        if not accepted:
            # Stale version
            return ContextResponse(
                accepted=False,
                reason="stale_version",
                details=f"Already have version {current_or_new_version}",
            )

        stored_at = datetime.utcnow().isoformat() + "Z"
        ack_id = f"ack_{payload.scope}_{payload.context_id}_{payload.version}"

        return ContextResponse(
            accepted=True, ack_id=ack_id, stored_at=stored_at
        )
    except Exception as e:
        return ContextResponse(
            accepted=False, reason="error", details=str(e)
        )


@app.post("/v1/tick", response_model=TickResponse)
async def tick(request: TickRequest):
    """
    Periodic wake-up. Bot inspects available triggers and composes messages.
    """
    actions = []

    try:
        # Iterate through available triggers
        for trigger_id in request.available_triggers:
            # Fetch trigger context
            trigger_payload = state_store.get_context("trigger", trigger_id)
            if not trigger_payload:
                continue  # Trigger not loaded yet

            # Determine merchant and customer
            merchant_id = trigger_payload.get("payload", {}).get("merchant_id")
            customer_id = trigger_payload.get("scope") == "customer" and trigger_payload.get("payload", {}).get("customer_id")

            if not merchant_id:
                continue

            # Fetch merchant and category contexts
            merchant_payload = state_store.get_context("merchant", merchant_id)
            if not merchant_payload:
                continue

            category_slug = merchant_payload.get("identity", {}).get("category")
            if not category_slug:
                category_slug = "dentists"  # Default

            category_payload = state_store.get_context("category", category_slug)
            if not category_payload:
                continue

            # Fetch customer context if needed
            customer_payload = None
            if customer_id:
                customer_payload = state_store.get_context("customer", customer_id)

            # Compose message
            composed = compose(
                category=category_payload,
                merchant=merchant_payload,
                trigger=trigger_payload,
                customer=customer_payload,
            )

            # Create conversation if not exists
            conversation_id = f"conv_{merchant_id}_{trigger_id}_{datetime.utcnow().timestamp()}"
            state_store.start_conversation(conversation_id, merchant_id, customer_id)
            state_store.add_message(conversation_id, "vera", composed["body"], request.now)

            # Build action
            action = ComposedAction(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id if customer_id else None,
                send_as=composed.get("send_as", "vera"),
                trigger_id=trigger_id,
                template_name=f"vera_{trigger_payload.get('kind', 'general')}_v1",
                template_params=[
                    merchant_payload.get("identity", {}).get("name", "Merchant"),
                    trigger_payload.get("payload", {}).get("title", ""),
                ],
                body=composed["body"],
                cta=composed["cta"],
                suppression_key=composed["suppression_key"],
                rationale=composed["rationale"],
            )
            actions.append(action)

    except Exception as e:
        print(f"Error in /v1/tick: {e}")
        pass  # Continue with other triggers

    return TickResponse(actions=actions)


@app.post("/v1/reply", response_model=ReplyResponse)
async def handle_reply(request: ReplyRequest):
    """
    Handle merchant reply (multi-turn capability).
    For now, a simple echo; full implementation would do intent detection.
    """
    try:
        # Get conversation state
        conv = state_store.get_conversation(request.conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Add merchant message to conversation
        state_store.add_message(request.conversation_id, "merchant", request.message, request.timestamp)

        # For now, return a simple follow-up
        # Full implementation would do intent detection and route accordingly
        reply_body = (
            f"Thanks for your message. This is a placeholder multi-turn reply. "
            f"Full intent detection coming soon."
        )

        action = ReplyAction(
            conversation_id=request.conversation_id,
            body=reply_body,
            cta="none",
            suppression_key=f"reply:{request.conversation_id}",
            rationale="Placeholder reply during multi-turn conversation",
        )

        return ReplyResponse(action=action)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/healthz", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@app.get("/v1/metadata", response_model=MetadataResponse)
async def get_metadata():
    """Return bot metadata"""
    return MetadataResponse(
        name="Vera Message Composer",
        version="1.0.0",
        model="claude-3-5-sonnet",
        capability_tags=[
            "merchant_engagement",
            "customer_recall",
            "research_digest",
            "performance_insights",
            "compliance_alert",
            "multi_turn",
        ],
        supports_multi_turn=True,
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Vera Message Composer API",
        "endpoints": [
            "POST /v1/context — store context",
            "POST /v1/tick — compose messages",
            "POST /v1/reply — handle replies",
            "GET /v1/healthz — health check",
            "GET /v1/metadata — bot info",
        ],
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Vera Message Composer on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
