"""
Calendar Service Endpoint
─────────────────────────
Exposes calendar agent capabilities as an independent HTTP service.
Supports HITL (Human-in-the-Loop) for sensitive operations
(create/delete events).

Endpoints:
  POST /services/calendar/invoke  → Run calendar agent on messages
  POST /services/calendar/resume  → Resume after HITL approval/rejection
  GET  /services/calendar/health  → Health check
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import logging
from fastapi import APIRouter, HTTPException
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from services.base import (
    ServiceRequest, ServiceResponse, ServiceResumeRequest, ServiceHealthResponse,
)
from services.serialization import serialize_messages, deserialize_messages
from logic.agents.calander_agent import _create_calendar_react_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services/calendar", tags=["service:calendar"])

# Persistent in-memory checkpointer for HITL state across requests.
# Keyed by thread_id so multiple conversations are independent.
_calendar_saver = MemorySaver()


def _get_agent():
    """Create calendar agent with shared checkpointer for HITL persistence."""
    return _create_calendar_react_agent(checkpointer=_calendar_saver)


def _make_config(thread_id: str, user_id: str) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": f"{thread_id}__calendar",
            "user_id": user_id,
        }
    }


# ==========================================
# Endpoints
# ==========================================

@router.post("/invoke", response_model=ServiceResponse)
async def invoke_calendar(request: ServiceRequest):
    """Run the calendar agent. May return 'interrupted' if HITL approval is needed."""
    logger.info(f"📅 Calendar service invoked (thread={request.thread_id})")

    try:
        agent = _get_agent()
        config = _make_config(request.thread_id, request.user_id)

        # Check if there's already an interrupted state for this thread
        snapshot = agent.get_state(config)
        if snapshot and snapshot.next:
            logger.info("📅 Calendar service: returning cached interrupt")
            interrupt_info = _extract_interrupt(snapshot)
            return ServiceResponse(
                messages=[],
                status="interrupted",
                interrupt_details=interrupt_info,
            )

        # Fresh invocation
        messages = deserialize_messages(request.messages)
        response = agent.invoke({"messages": messages}, config=config)
        result_messages = response.get("messages", []) if isinstance(response, dict) else []

        # Check if we hit a HITL interrupt
        snapshot = agent.get_state(config)
        if snapshot and snapshot.next:
            logger.info("📅 Calendar service: HITL interrupt detected")
            interrupt_info = _extract_interrupt(snapshot)
            return ServiceResponse(
                messages=serialize_messages(result_messages),
                status="interrupted",
                interrupt_details=interrupt_info,
            )

        logger.info("📅 Calendar service completed successfully")
        return ServiceResponse(
            messages=serialize_messages(result_messages),
            status="success",
        )

    except Exception as e:
        logger.exception("Calendar service failed")
        return ServiceResponse(messages=[], status="error", error=str(e))


@router.post("/resume", response_model=ServiceResponse)
async def resume_calendar(request: ServiceResumeRequest):
    """Resume a HITL-paused calendar agent invocation."""
    logger.info(f"📅 Calendar service resuming (thread={request.thread_id}, decision={request.decision})")

    if request.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    try:
        agent = _get_agent()
        config = _make_config(request.thread_id, request.user_id)

        # Verify paused state exists
        snapshot = agent.get_state(config)
        if not snapshot or not snapshot.next:
            raise HTTPException(status_code=400, detail="No paused calendar invocation for this thread.")

        # Resume
        response = agent.invoke(
            Command(resume={"decisions": [{"type": request.decision}]}),
            config=config,
        )
        result_messages = response.get("messages", []) if isinstance(response, dict) else []

        logger.info("📅 Calendar service resumed successfully")
        return ServiceResponse(
            messages=serialize_messages(result_messages),
            status="success",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Calendar service resume failed")
        return ServiceResponse(messages=[], status="error", error=str(e))


@router.get("/health", response_model=ServiceHealthResponse)
async def health_check():
    return ServiceHealthResponse(
        service="calendar",
        status="healthy",
        details={"hitl": True},
    )


# ==========================================
# Helpers
# ==========================================

def _extract_interrupt(snapshot) -> dict:
    """Pull interrupt details from a LangGraph state snapshot."""
    try:
        tasks = snapshot.tasks
        if tasks and tasks[0].interrupts:
            raw = tasks[0].interrupts[0]
            return {"value": str(raw.value) if hasattr(raw, "value") else str(raw)}
    except Exception:
        pass
    return {"value": "Approval required"}
