"""
Weather Service Endpoint
────────────────────────
Exposes weather agent capabilities as an independent HTTP service.
No HITL needed — all weather reads are safe and passive.

Endpoints:
  POST /services/weather/invoke   → Run weather agent on messages
  GET  /services/weather/health   → Health check
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import logging
from fastapi import APIRouter
from langchain_core.runnables import RunnableConfig

from services.base import ServiceRequest, ServiceResponse, ServiceHealthResponse
from services.serialization import serialize_messages, deserialize_messages
from logic.agents.weather_agent import _create_weather_react_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services/weather", tags=["service:weather"])


# ==========================================
# Endpoints
# ==========================================

@router.post("/invoke", response_model=ServiceResponse)
async def invoke_weather(request: ServiceRequest):
    """Run the weather agent with the given conversation messages."""
    logger.info(f"⛅ Weather service invoked (thread={request.thread_id})")

    try:
        # Deserialize messages from the HTTP request
        messages = deserialize_messages(request.messages)
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"{request.thread_id}__weather",
                "user_id": request.user_id,
            }
        }

        # Create a fresh agent (picks up latest system prompt / preferences)
        agent = _create_weather_react_agent()
        response = agent.invoke({"messages": messages}, config=config)

        # Extract result messages
        result_messages = response.get("messages", []) if isinstance(response, dict) else []

        logger.info(f"⛅ Weather service completed successfully")
        return ServiceResponse(
            messages=serialize_messages(result_messages),
            status="success",
        )

    except Exception as e:
        logger.exception("Weather service failed")
        return ServiceResponse(
            messages=[],
            status="error",
            error=str(e),
        )


@router.get("/health", response_model=ServiceHealthResponse)
async def health_check():
    """Check if the weather service is operational."""
    return ServiceHealthResponse(
        service="weather",
        status="healthy",
        details={"hitl": False},
    )
