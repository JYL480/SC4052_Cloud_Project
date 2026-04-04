"""
Email Service Endpoint
──────────────────────
Exposes email agent capabilities as an independent HTTP service.
Supports HITL for sensitive operations (send/reply).

Endpoints:
  POST /services/email/invoke  → Run email agent on messages
  POST /services/email/resume  → Resume after HITL approval/rejection
  GET  /services/email/health  → Health check
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
from logic.agents.email_agent import _create_email_react_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services/email", tags=["service:email"])

# Persistent in-memory checkpointer for HITL state
_email_saver = MemorySaver()


def _get_agent():
    """Create email agent with shared checkpointer for HITL persistence."""
    return _create_email_react_agent(checkpointer=_email_saver)


def _make_config(thread_id: str, user_id: str) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": f"{thread_id}__email",
            "user_id": user_id,
        }
    }


# ==========================================
# Endpoints
# ==========================================

@router.post("/invoke", response_model=ServiceResponse)
async def invoke_email(request: ServiceRequest):
    """Run the email agent. May return 'interrupted' if HITL approval is needed."""
    logger.info(f"📧 Email service invoked (thread={request.thread_id})")

    try:
        agent = _get_agent()
        config = _make_config(request.thread_id, request.user_id)

        # Check for existing interrupted state
        snapshot = agent.get_state(config)
        if snapshot and snapshot.next:
            logger.info("📧 Email service: returning cached interrupt")
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

        # Check for HITL interrupt
        snapshot = agent.get_state(config)
        if snapshot and snapshot.next:
            logger.info("📧 Email service: HITL interrupt detected")
            interrupt_info = _extract_interrupt(snapshot)
            return ServiceResponse(
                messages=serialize_messages(result_messages),
                status="interrupted",
                interrupt_details=interrupt_info,
            )

        logger.info("📧 Email service completed successfully")
        return ServiceResponse(
            messages=serialize_messages(result_messages),
            status="success",
        )

    except Exception as e:
        logger.exception("Email service failed")
        return ServiceResponse(messages=[], status="error", error=str(e))


@router.post("/resume", response_model=ServiceResponse)
async def resume_email(request: ServiceResumeRequest):
    """Resume a HITL-paused email agent invocation."""
    logger.info(f"📧 Email service resuming (thread={request.thread_id}, decision={request.decision})")

    if request.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    try:
        agent = _get_agent()
        config = _make_config(request.thread_id, request.user_id)

        snapshot = agent.get_state(config)
        if not snapshot or not snapshot.next:
            raise HTTPException(status_code=400, detail="No paused email invocation for this thread.")

        response = agent.invoke(
            Command(resume={"decisions": [{"type": request.decision}]}),
            config=config,
        )
        result_messages = response.get("messages", []) if isinstance(response, dict) else []

        logger.info("📧 Email service resumed successfully")
        return ServiceResponse(
            messages=serialize_messages(result_messages),
            status="success",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Email service resume failed")
        return ServiceResponse(messages=[], status="error", error=str(e))


@router.get("/health", response_model=ServiceHealthResponse)
async def health_check():
    return ServiceHealthResponse(
        service="email",
        status="healthy",
        details={"hitl": True},
    )


def _extract_interrupt(snapshot) -> dict:
    try:
        tasks = snapshot.tasks
        if tasks and tasks[0].interrupts:
            raw = tasks[0].interrupts[0]
            return {"value": str(raw.value) if hasattr(raw, "value") else str(raw)}
    except Exception:
        pass
    return {"value": "Approval required"}
