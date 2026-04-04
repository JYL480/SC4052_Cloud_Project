"""
Service client — async HTTP helpers used by graph worker nodes
to call service endpoints.

The SERVICE_BASE_URL defaults to the same FastAPI process (localhost:8000)
but can be overridden per-service via env vars for separate deployment.
"""

import os
import logging
import httpx

from services.base import ServiceRequest, ServiceResponse, ServiceResumeRequest
from services.serialization import serialize_messages, deserialize_messages
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

# ==========================================
# Service Registry
# ==========================================

_BASE = os.getenv("SERVICE_BASE_URL", "http://localhost:8000")

SERVICE_REGISTRY: dict[str, dict] = {
    "weather": {
        "invoke": f"{_BASE}/services/weather/invoke",
        "health": f"{_BASE}/services/weather/health",
    },
    "calendar": {
        "invoke": f"{_BASE}/services/calendar/invoke",
        "resume": f"{_BASE}/services/calendar/resume",
        "health": f"{_BASE}/services/calendar/health",
    },
    "email": {
        "invoke": f"{_BASE}/services/email/invoke",
        "resume": f"{_BASE}/services/email/resume",
        "health": f"{_BASE}/services/email/health",
    },
    "preferences": {
        "invoke": f"{_BASE}/services/preferences/invoke",
        "health": f"{_BASE}/services/preferences/health",
    },
    "general": {
        "invoke": f"{_BASE}/services/general/invoke",
        "health": f"{_BASE}/services/general/health",
    },
}

# Shared timeout (seconds) — agents can be slow (LLM + tool calls)
_TIMEOUT = float(os.getenv("SERVICE_TIMEOUT", "120"))


# ==========================================
# Public API
# ==========================================

async def call_service(
    service_name: str,
    messages: list[BaseMessage],
    config: RunnableConfig,
) -> ServiceResponse:
    """
    Invoke a service endpoint with serialized messages.
    Returns a ServiceResponse with status, messages, and optional interrupt info.
    """
    urls = SERVICE_REGISTRY.get(service_name)
    if not urls:
        return ServiceResponse(
            messages=[], status="error",
            error=f"Unknown service: '{service_name}'",
        )

    thread_id = config.get("configurable", {}).get("thread_id", "")
    user_id = config.get("configurable", {}).get("user_id", "")

    payload = ServiceRequest(
        messages=serialize_messages(messages),
        thread_id=thread_id,
        user_id=user_id,
    )

    logger.info(f"🌐 Calling service '{service_name}' at {urls['invoke']}")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(urls["invoke"], json=payload.model_dump())
            resp.raise_for_status()
            return ServiceResponse(**resp.json())
    except httpx.HTTPStatusError as e:
        logger.error(f"Service '{service_name}' returned {e.response.status_code}: {e.response.text}")
        return ServiceResponse(
            messages=[], status="error",
            error=f"Service '{service_name}' error: {e.response.status_code}",
        )
    except Exception as e:
        logger.exception(f"Failed to call service '{service_name}'")
        return ServiceResponse(
            messages=[], status="error",
            error=f"Service '{service_name}' unreachable: {str(e)}",
        )


async def resume_service(
    service_name: str,
    decision: str,
    config: RunnableConfig,
) -> ServiceResponse:
    """
    Resume a HITL-paused service with an approve/reject decision.
    Only applicable to services that support HITL (calendar, email).
    """
    urls = SERVICE_REGISTRY.get(service_name, {})
    resume_url = urls.get("resume")
    if not resume_url:
        return ServiceResponse(
            messages=[], status="error",
            error=f"Service '{service_name}' does not support resume.",
        )

    thread_id = config.get("configurable", {}).get("thread_id", "")
    user_id = config.get("configurable", {}).get("user_id", "")

    payload = ServiceResumeRequest(
        thread_id=thread_id,
        user_id=user_id,
        decision=decision,
    )

    logger.info(f"🔄 Resuming service '{service_name}' with decision='{decision}'")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(resume_url, json=payload.model_dump())
            resp.raise_for_status()
            return ServiceResponse(**resp.json())
    except Exception as e:
        logger.exception(f"Failed to resume service '{service_name}'")
        return ServiceResponse(
            messages=[], status="error",
            error=f"Service '{service_name}' resume failed: {str(e)}",
        )
