"""
Chat routes — FastAPI ↔ LangGraph master graph.

Endpoints:
  POST /api/thread        → Create a new conversation thread (returns thread_id)
  POST /api/chat/stream   → Stream AI response via Server-Sent Events (SSE)
  POST /api/chat/resume   → Resume a HITL-paused thread with approve/reject
"""
import os
import sys
# Fix import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))


from langchain_core.runnables import RunnableConfig

import uuid
import json
import asyncio
import re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

# Need to import the shared resources
from core.lifespan import shared_resources



# from logic.graph.graph import graph_builder

router = APIRouter(prefix="/api", tags=["chat"])

ONBOARDING_WELCOME = """Welcome! I am your personal assistant onboarding helper.

Before we begin, I need to collect your preferences so I can personalize calendar, email, and weather support.

Please share these in one message:
- Name
- Timezone
- Default meeting duration (minutes)
- Calendar buffer time (minutes)
- Preferred email tone
- Email signoff
- Weather unit (celsius or fahrenheit)
"""

PREFERENCES_PATH = Path(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), '../../data/user_preferences/preferences.md')
    )
)


# ==========================================
# Request / Response Schemas
# ==========================================

class CreateThreadResponse(BaseModel):
    thread_id: str
    user_id: str
    message: str
    onboarding_message: Optional[str] = None


class ChatRequest(BaseModel):
    thread_id: str
    user_id: str
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    user_id: str
    decision: str   # "approve" or "reject"


class ResumeResponse(BaseModel):
    thread_id: str
    user_id: str
    reply: str


# ==========================================
# Helpers
# ==========================================

def _make_config(thread_id: str, user_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "user_id": user_id}}


def _sse(payload: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def _has_saved_preferences() -> bool:
    """Return True when preferences markdown exists and contains a non-empty JSON block."""
    if not PREFERENCES_PATH.exists():
        return False

    try:
        content = PREFERENCES_PATH.read_text(encoding="utf-8")
    except OSError:
        return False

    match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", content)
    if not match:
        return False

    try:
        payload = json.loads(match.group(1))
        return bool(payload)
    except json.JSONDecodeError:
        return False


# ==========================================
# Endpoints
# ==========================================

@router.post("/thread", response_model=CreateThreadResponse)
def create_thread(user_id: str):
    """
    Create a new conversation thread for a specific user.
    Returns a unique thread_id to pass in all subsequent requests.
    """
    thread_id = str(uuid.uuid4())
    onboarding_message = ONBOARDING_WELCOME

    return CreateThreadResponse(
        thread_id=thread_id,
        user_id=user_id,
        message=f"Thread '{thread_id}' created for user '{user_id}'.",
        onboarding_message=onboarding_message,
    )


@router.post("/chat/stream")
async def chat_stream(api_request: Request, request: ChatRequest):
    """
    Send a message and stream the response via Server-Sent Events.
    """
    if 'graph' not in shared_resources or shared_resources['graph'] is None:
        print("ERROR: Graph not available in shared_resources")
        raise HTTPException(
            status_code=503, 
            detail="The graph application is not available or has not been initialized."
        )
 
    thread_id = request.thread_id
    graph = shared_resources['graph']
    config = _make_config(request.thread_id, request.user_id)

    async def event_generator():
        try:
            async for chunk in graph.astream(
                {"messages": [HumanMessage(content=request.message)]},
                config=config,
                stream_mode="updates",
            ):
                for node_name, node_output in chunk.items():
                    # Notify frontend which node is currently active
                    yield _sse({"type": "node", "node": node_name})

                    # Interrupt payloads are not regular node dict outputs.
                    # In stream_mode="updates", they may arrive as tuples/lists.
                    if node_name == "__interrupt__":
                        interrupt_info = {"value": str(node_output)}
                        yield _sse({"type": "interrupt", "details": interrupt_info})
                        continue

                    if not isinstance(node_output, dict):
                        # Skip unexpected payload shapes to keep the stream resilient.
                        continue

                    # Emit explicit routing decision from orchestrator.
                    next_agent = node_output.get("next_agent")
                    if isinstance(next_agent, str) and node_name == "orchestrator":
                        yield _sse({"type": "route", "from": node_name, "to": next_agent})

                    # Forward the last AI message from this node to the client
                    messages = node_output.get("messages", [])
                    if messages:
                        last = messages[-1]
                        content = getattr(last, "content", "") or ""
                        if content and isinstance(last, AIMessage):
                            yield _sse({
                                "type": "message",
                                "node": node_name,
                                "content": content,
                            })

            # ── After stream ends, check for HITL interrupt ──────────────────
            snapshot = await graph.aget_state(config)
            if snapshot.next:
                interrupt_info = {}
                try:
                    tasks = snapshot.tasks
                    if tasks and tasks[0].interrupts:
                        raw = tasks[0].interrupts[0]
                        interrupt_info = {
                            "value": str(raw.value) if hasattr(raw, "value") else str(raw)
                        }
                except Exception:
                    pass
                yield _sse({"type": "interrupt", "details": interrupt_info})

        except Exception as e:
            yield _sse({"type": "error", "content": str(e)})

        finally:
            yield _sse({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/resume", response_model=ResumeResponse)
async def resume_chat(api_request: Request, request: ResumeRequest):
    """
    Resume a HITL-paused thread.
    'decision' must be 'approve' or 'reject'.
    """
    if 'graph' not in shared_resources or shared_resources['graph'] is None:
        raise HTTPException(status_code=503, detail="The graph application has not been initialized.")

    if request.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    config = _make_config(request.thread_id, request.user_id)
    graph = shared_resources['graph']

    # Verify this thread is actually paused
    snapshot = await graph.aget_state(config)
    if not snapshot.next:
        raise HTTPException(
            status_code=400,
            detail="Thread is not paused. Send a new message via /chat/stream instead.",
        )

    response = await graph.ainvoke(
        Command(resume={"decisions": [{"type": request.decision}]}),
        config,
    )

    if not response or "messages" not in response:
        raise HTTPException(status_code=500, detail="Graph returned no messages after resume.")

    return ResumeResponse(
        thread_id=request.thread_id,
        user_id=request.user_id,
        reply=response["messages"][-1].content,
    )
