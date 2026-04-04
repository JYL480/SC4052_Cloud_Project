"""
Master Graph — LangGraph orchestrator with service-backed worker nodes.

Worker nodes no longer import agent logic directly. Instead, they call
independent service endpoints via HTTP, achieving separation of concerns
and enabling independent scaling/deployment per service.
"""

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import logging
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt

from logic.graph.state import AgentState
from logic.agents.ochestrator import orchestrator_node, orchestrator_router
from services.client import call_service, resume_service
from services.serialization import deserialize_messages

logger = logging.getLogger(__name__)


# ==========================================
# Service-backed Worker Nodes
# ==========================================
# Each worker node is now a thin async function that delegates to
# its corresponding service endpoint via HTTP. The actual agent logic,
# tools, and prompts live in the service layer.

async def weather_worker_node(state: dict, config: RunnableConfig) -> dict:
    """Call the weather service endpoint."""
    logger.info("⛅ Weather worker → calling service")
    response = await call_service("weather", state["messages"], config)

    if response.status == "error":
        logger.error(f"⛅ Weather service error: {response.error}")
        return {"messages": [AIMessage(content=f"Weather service error: {response.error}", name="weather_worker")]}

    return {"messages": deserialize_messages(response.messages)}


async def calendar_worker_node(state: dict, config: RunnableConfig) -> dict:
    """Call the calendar service endpoint. Supports HITL interrupts."""
    logger.info("📅 Calendar worker → calling service")
    response = await call_service("calendar", state["messages"], config)

    if response.status == "error":
        logger.error(f"📅 Calendar service error: {response.error}")
        return {"messages": [AIMessage(content=f"Calendar service error: {response.error}", name="calendar_worker")]}

    if response.status == "interrupted":
        logger.info("📅 Calendar service interrupted — relaying HITL to master graph")
        # Pause the master graph. When resumed, interrupt() returns the decision.
        decision_data = interrupt(response.interrupt_details or {"value": "Approval required"})

        # Extract the decision string
        decision = "approve"
        if isinstance(decision_data, dict):
            decision = decision_data.get("type", decision_data.get("decision", "approve"))
        elif isinstance(decision_data, str):
            decision = decision_data

        # Resume the calendar service with the user's decision
        resume_resp = await resume_service("calendar", decision, config)
        if resume_resp.status == "error":
            return {"messages": [AIMessage(content=f"Calendar resume error: {resume_resp.error}", name="calendar_worker")]}
        return {"messages": deserialize_messages(resume_resp.messages)}

    return {"messages": deserialize_messages(response.messages)}


async def email_worker_node(state: dict, config: RunnableConfig) -> dict:
    """Call the email service endpoint. Supports HITL interrupts."""
    logger.info("📧 Email worker → calling service")
    response = await call_service("email", state["messages"], config)

    if response.status == "error":
        logger.error(f"📧 Email service error: {response.error}")
        return {"messages": [AIMessage(content=f"Email service error: {response.error}", name="email_worker")]}

    if response.status == "interrupted":
        logger.info("📧 Email service interrupted — relaying HITL to master graph")
        decision_data = interrupt(response.interrupt_details or {"value": "Approval required"})

        decision = "approve"
        if isinstance(decision_data, dict):
            decision = decision_data.get("type", decision_data.get("decision", "approve"))
        elif isinstance(decision_data, str):
            decision = decision_data

        resume_resp = await resume_service("email", decision, config)
        if resume_resp.status == "error":
            return {"messages": [AIMessage(content=f"Email resume error: {resume_resp.error}", name="email_worker")]}
        return {"messages": deserialize_messages(resume_resp.messages)}

    return {"messages": deserialize_messages(response.messages)}


async def user_preference_worker_node(state: dict, config: RunnableConfig) -> dict:
    """Call the user preference service endpoint."""
    logger.info("🧠 Preference worker → calling service")
    response = await call_service("preferences", state["messages"], config)

    if response.status == "error":
        logger.error(f"🧠 Preference service error: {response.error}")
        return {"messages": [AIMessage(content=f"Preference service error: {response.error}", name="user_preference_worker")]}

    return {"messages": deserialize_messages(response.messages)}


async def general_worker_node(state: dict, config: RunnableConfig) -> dict:
    """Call the general assistant service endpoint."""
    logger.info("🧩 General worker → calling service")
    response = await call_service("general", state["messages"], config)

    if response.status == "error":
        logger.error(f"🧩 General service error: {response.error}")
        return {"messages": [AIMessage(content=f"General service error: {response.error}", name="general_worker")]}

    return {"messages": deserialize_messages(response.messages)}


# ==========================================
# Master Graph
# ==========================================
async def setup_graph(saver):
    graph_builder = StateGraph(AgentState)  # type: ignore

    # Add nodes — orchestrator is still direct, workers call services
    graph_builder.add_node("orchestrator", orchestrator_node)
    graph_builder.add_node("calendar_worker", calendar_worker_node)
    graph_builder.add_node("email_worker", email_worker_node)
    graph_builder.add_node("weather_worker", weather_worker_node)
    graph_builder.add_node("user_preference_worker", user_preference_worker_node)
    graph_builder.add_node("general_worker", general_worker_node)

    # Entry point: always start at the orchestrator
    graph_builder.set_entry_point("orchestrator")

    # Conditional edges: orchestrator decides where to go
    graph_builder.add_conditional_edges(
        "orchestrator",
        orchestrator_router,
        {
            "calendar_worker": "calendar_worker",
            "email_worker": "email_worker",
            "weather_worker": "weather_worker",
            "user_preference_worker": "user_preference_worker",
            "general_worker": "general_worker",
            "__end__": END,
        }
    )

    # After each worker finishes, route back to the orchestrator
    graph_builder.add_edge("calendar_worker", "orchestrator")
    graph_builder.add_edge("email_worker", "orchestrator")
    graph_builder.add_edge("weather_worker", "orchestrator")
    graph_builder.add_edge("user_preference_worker", "orchestrator")
    graph_builder.add_edge("general_worker", "orchestrator")

    # Compile the graph
    graph = graph_builder.compile(checkpointer=saver)

    return graph


if __name__ == "__main__":
    from langchain_core.messages import HumanMessage

    print("\n==========================================")
    print("Welcome to your Multi-Agent Terminal!")
    print("==========================================\n")
    ONBOARDING_WELCOME = """🧠 Welcome! I am your personal assistant onboarding helper.

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
    print(ONBOARDING_WELCOME)

    config: RunnableConfig = {"configurable": {"thread_id": "master_thread_1"}}
    user_input = input("You: ").strip()

    while True:
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        print(f"\nYou: {user_input}\n")

        # Invoke the master graph with the user's message
        response = graph.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config
        )

        # Print the AI's reply
        if response and "messages" in response:
            last_ai = response["messages"][-1]
            print(f"🤖 Agent: {last_ai.content}\n")

        # ==============================
        # Check if we hit an interrupt
        # ==============================
        snapshot = graph.get_state(config)
        if snapshot.next:
            print("💥 [INTERRUPT]: The agent wants to execute a tool. Approve or Reject?")
            approval = input("Your decision (approve/reject): ").strip().lower()

            decision_type = "approve" if approval == "approve" else "reject"
            resume_response = graph.invoke(
                Command(resume={"decisions": [{"type": decision_type}]}),
                config=config
            )
            if resume_response and "messages" in resume_response:
                print(f"🤖 Agent: {resume_response['messages'][-1].content}\n")

        # Get next user input
        user_input = input("You: ").strip()
