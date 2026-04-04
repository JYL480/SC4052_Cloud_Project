"""
General Assistant Service Endpoint
───────────────────────────────────
Exposes the general fallback agent as an independent HTTP service.
Handles general conversation and PA requests. No HITL.

Endpoints:
  POST /services/general/invoke  → Run general agent on messages
  GET  /services/general/health  → Health check
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import logging
from fastapi import APIRouter
from langchain_core.runnables import RunnableConfig

from services.base import ServiceRequest, ServiceResponse, ServiceHealthResponse
from services.serialization import serialize_messages, deserialize_messages
from logic.agents.general_agent import _create_general_react_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services/general", tags=["service:general"])


@router.post("/invoke", response_model=ServiceResponse)
async def invoke_general(request: ServiceRequest):
    """Run the general fallback agent with the given conversation messages."""
    logger.info(f"🧩 General service invoked (thread={request.thread_id})")

    try:
        messages = deserialize_messages(request.messages)
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"{request.thread_id}__general",
                "user_id": request.user_id,
            }
        }

        agent = _create_general_react_agent()
        response = agent.invoke({"messages": messages}, config=config)
        result_messages = response.get("messages", []) if isinstance(response, dict) else []

        logger.info("🧩 General service completed successfully")
        return ServiceResponse(
            messages=serialize_messages(result_messages),
            status="success",
        )

    except Exception as e:
        logger.exception("General service failed")
        return ServiceResponse(messages=[], status="error", error=str(e))


@router.get("/health", response_model=ServiceHealthResponse)
async def health_check():
    return ServiceHealthResponse(
        service="general",
        status="healthy",
        details={"hitl": False},
    )
