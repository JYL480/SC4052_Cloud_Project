"""
User Preference Service Endpoint
─────────────────────────────────
Exposes user preference agent capabilities as an independent HTTP service.
No HITL needed.

Endpoints:
  POST /services/preferences/invoke  → Run preference agent on messages
  GET  /services/preferences/health  → Health check
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import logging
from fastapi import APIRouter
from langchain_core.runnables import RunnableConfig

from services.base import ServiceRequest, ServiceResponse, ServiceHealthResponse
from services.serialization import serialize_messages, deserialize_messages
from logic.agents.user_preference_agent import get_user_preference_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services/preferences", tags=["service:preferences"])


@router.post("/invoke", response_model=ServiceResponse)
async def invoke_preferences(request: ServiceRequest):
    """Run the user preference agent with the given conversation messages."""
    logger.info(f"🧠 Preference service invoked (thread={request.thread_id})")

    try:
        messages = deserialize_messages(request.messages)
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"{request.thread_id}__preferences",
                "user_id": request.user_id,
            }
        }

        response = get_user_preference_agent.invoke(
            {"messages": messages}, config=config
        )
        result_messages = response.get("messages", []) if isinstance(response, dict) else []

        logger.info("🧠 Preference service completed successfully")
        return ServiceResponse(
            messages=serialize_messages(result_messages),
            status="success",
        )

    except Exception as e:
        logger.exception("Preference service failed")
        return ServiceResponse(messages=[], status="error", error=str(e))


@router.get("/health", response_model=ServiceHealthResponse)
async def health_check():
    return ServiceHealthResponse(
        service="preferences",
        status="healthy",
        details={"hitl": False},
    )
