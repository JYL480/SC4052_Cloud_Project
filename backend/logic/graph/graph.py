import os
import sys
# Add the 'backend' directory to Python's path so it can find the 'utils' folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# For now we will use Sqlite for prototyping yah
# I will build the sqlite checkpointer here synchronousely here from prototyping
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

from logic.graph.state import AgentState
from logic.agents.calander_agent import calendar_worker_node
from logic.agents.ochestrator import orchestrator_node, orchestrator_router
from logic.agents.email_agent import email_worker_node
from logic.agents.weather_agent import weather_worker_node
from logic.agents.user_preference_agent import user_preference_worker_node
from logic.agents.general_agent import general_worker_node
from langgraph.types import Command

import logging
logger = logging.getLogger(__name__)


# ==========================================
# Master Graph
# ==========================================
async def setup_graph(saver):
    graph_builder = StateGraph(AgentState)  # type: ignore

    # Add nodes
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

    # After the calendar worker finishes, always route back to the orchestrator
    # The orchestrator will see the AI response and route to END
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
