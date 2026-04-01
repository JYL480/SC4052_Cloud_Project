"""
Orchestrator Node — reads the user's intent and sets `next_agent` in the graph state
to route to the correct worker node.

This is a ROUTING node, not an execution node.
It does NOT do any calendar/email work itself.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import logging
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from utils.main_utils import llm_model

logger = logging.getLogger(__name__)

# ==========================================
# Routing Logic
# ==========================================
# Add new agent node-names here as you build them.
# These must match the node names registered in graph.py!
SUPPORTED_AGENTS = ["calendar_worker", "email_worker", "weather_worker"]

def _classify_intent(messages: list[BaseMessage]) -> str:
    """
    Ask the LLM to classify the last user message into one of the
    supported agent categories or 'end' if the task is complete.
    """
    # Pull the last human message
    last_human = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        None
    )

    if not last_human:
        return "end"

    routing_prompt = f"""You are a task router. Based on the user's request, pick the most appropriate agent.

Available agents:
- calendar_worker: Use for anything related to scheduling events, reminders, viewing calendar, deleting events, or checking conflicts.
- email_worker: Use for anything related to reading, sending, or managing emails.
- weather_worker: Use for anything related to weather information.

User request: "{last_human}"

Rules:
1. Respond with ONLY one of the following:
   - calendar_worker
   - email_worker
   - weather_worker
   - end

2. Do NOT explain your choice.
3. Do NOT ask questions.
4. If the request is unclear or does not match any agent, respond with 'end'.

"""

    response = llm_model.invoke(routing_prompt)
    decision = response.content.strip().lower()
    print(f"[Orchestrator] LLM routing decision raw: '{decision}'")

    # Guard: only return known agents, else fall back to "end"
    for agent in SUPPORTED_AGENTS:
        if agent in decision:
            return agent

    return "end"


def orchestrator_node(state: dict) -> dict:
    """
    LangGraph node for the orchestrator.
    Analyzes the current message state and sets `next_agent` for the conditional edge.
    """
    messages = state["messages"]
    last_message = messages[-1]

    # If the last message is from a worker (AI), the task is done — route to END
    if isinstance(last_message, AIMessage):
        logger.info("🎯 Orchestrator: Last message is AI (worker result). Routing to END.")
        print("\n[Orchestrator] ✅ Task complete — routing to END")
        return {"next_agent": "end"}

    # Otherwise analyze the latest human message and decide which worker to call
    next_agent = _classify_intent(messages)
    logger.info(f"🎯 Orchestrator: Routing to '{next_agent}'")
    print(f"\n[Orchestrator] 🔀 Routing to: '{next_agent}'")

    return {"next_agent": next_agent}


# ==========================================
# Conditional Edge Function (used in graph.py)
# ==========================================

def orchestrator_router(state: dict) -> str:
    """
    LangGraph conditional edge function.
    Reads `next_agent` from state and returns the graph node name to route to.
    """
    next_agent = state.get("next_agent", "end")

    if next_agent == "calendar_worker":
        return "calendar_worker"
    elif next_agent == "email_worker":
        return "email_worker"
    elif next_agent == "weather_worker":
        return "weather_worker"

    # Default: end the graph
    return "__end__"
