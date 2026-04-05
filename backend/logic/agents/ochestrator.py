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
SUPPORTED_AGENTS = ["calendar_worker", "email_worker", "weather_worker", "user_preference_worker", "general_worker"]
AGENTS_MD_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/agents/agents.md'))


def _safe_read_text(path: str, fallback: str) -> str:
    """Read file content safely, return fallback if missing."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        logger.warning("Context file not found: %s", path)
        return fallback

def _detect_last_active_agent(messages: list[BaseMessage]) -> str | None:
    """
    Look backwards through message history to find which agent was
    most recently active, by checking which node's AIMessage appears last.
    We infer this from the conversation pattern:
    every AIMessage after the first HumanMessage was produced by a worker.
    We track this via the `name` attribute if present, or fall back to None.
    """
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            # LangGraph sets `name` on AIMessages to the node that produced them
            if hasattr(m, "name") and m.name in SUPPORTED_AGENTS:
                return m.name
    return None


# Short replies that are clearly just confirmations/continuations, not new tasks
_CONTINUATION_WORDS = {
    "yes", "no", "ok", "okay", "sure", "nope", "yep", "yeah",
    "proceed", "go ahead", "send it", "confirm", "cancel", "done",
    "fine", "alright", "correct", "right", "wrong", "good", "great",
}

def _is_short_continuation(text: str) -> bool:
    """Return True if the message looks like a yes/no/confirmation reply."""
    words = text.strip().lower().split()
    if len(words) <= 3:
        normalized = " ".join(words)
        return any(word in normalized for word in _CONTINUATION_WORDS)
    return False


def _classify_intent(messages: list[BaseMessage]) -> str:
    """
    Route the latest message to the correct agent.

    Priority order:
    1. If the message is a short yes/no/confirmation → skip LLM, reuse last active agent
    2. Otherwise → call LLM with conversation history as context
    """
    if not messages:
        return "end"

    last_human = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        None
    )
    if not last_human:
        return "end"

    # ── Heuristic: short continuation replies ────────────────────────────────
    if isinstance(last_human, str) and _is_short_continuation(last_human):
        last_agent = _detect_last_active_agent(messages)
        if last_agent:
            print(f"[Orchestrator] ⚡ Short reply detected — continuing with '{last_agent}'")
            return last_agent
        # No prior agent found, fall through to LLM routing

    # ── LLM routing with conversation history ────────────────────────────────
    recent = messages[-6:]
    history_lines = []
    for m in recent:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        content = (m.content or "")[:300]
        history_lines.append(f"{role}: {content}")
    history_text = "\n".join(history_lines)

    # Read agent descriptions from disk (picks up any new agents added to the file)
    agents_text = _safe_read_text(
        AGENTS_MD_PATH,
        "calendar_worker, email_worker, weather_worker, user_preference_worker, general_worker",
    )

    routing_prompt = f"""You are a strict task router. Assign the latest user message to the most appropriate agent.

{agents_text}

--- Conversation history ---
{history_text}
----------------------------

Latest user message: "{last_human}"

RULES:
1. Output ONLY ONE of: calendar_worker | email_worker | weather_worker | user_preference_worker | general_worker | end
2. No explanation. No questions.
3. Follow-ups ("make it friendlier", "change the subject", "add more") → same agent as previous turn.
4. Use general_worker for requests that do not clearly fit specialist workers.
5. Use 'end' ONLY when conversation is clearly complete (for example: "thanks bye").
"""

    response = llm_model.invoke(routing_prompt)
    decision = response.content.strip().lower()
    print(f"[Orchestrator] LLM routing decision raw: '{decision}'")

    for agent in SUPPORTED_AGENTS:
        if agent in decision:
            return agent

    return "general_worker"


def orchestrator_node(state: dict) -> dict:
    """
    LangGraph node for the orchestrator.
    Analyzes the current message state and sets `next_agent` for the conditional edge.
    """
    messages = state["messages"]
    last_message = messages[-1]
    logger.info(f"🎯 Orchestrator received message: '{last_message.content[:100]}' (type: {type(last_message).__name__})")

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
    elif next_agent == "user_preference_worker":
        return "user_preference_worker"
    elif next_agent == "general_worker":
        return "general_worker"

    # Default: end the graph
    return "__end__"
