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

import logging
logger = logging.getLogger(__name__)


# Sqlite checkpointer
conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
saver = SqliteSaver(conn)


# Build the graph
graph_builder = StateGraph(AgentState)  # type: ignore , lol you can just ignore like this?? the error gone

# Add nodes
graph_builder.add_node("calendar_worker", calendar_worker_node)

# Add edges
graph_builder.set_entry_point("calendar_worker")
graph_builder.add_edge("calendar_worker", END)

# Compile the graph
graph = graph_builder.compile(checkpointer=saver)



if __name__ == "__main__":
    # You can test the agent locally without running the whole graph!
    test_state = {
        "messages": [HumanMessage(content="create a reminder tmr on my calander to by an apple")]
    }
    config: RunnableConfig = {
        "configurable": {
            "thread_id": "test-thread-1",
            "user_id": "test-user-1"
        }
    }

    result = graph.invoke(
        test_state,
        config=config
    )

    print("Result:", result["messages"][-1].content)