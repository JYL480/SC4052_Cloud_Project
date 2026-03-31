import sys
import os

# Add the 'backend' directory to Python's path so it can find the 'utils' folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from utils.main_utils import llm_generate_response, llm_model
# ==========================================
# 1. Define Tools for the Calendar Agent
# ==========================================

@tool
def get_calendar_events(date_str: str) -> str:
    """Fetch calendar events for a specific date."""
    # TODO: Implement Google Calendar API integration
    return f"Found 2 events on {date_str}..."

@tool
def create_calendar_event(title: str, start_time: str, end_time: str) -> str:
    """Create a new event in the Google Calendar."""
    # TODO: Implement Google Calendar API integration
    return f"Successfully created event: {title}"

# ==========================================
# 2. Setup the Agent
# ==========================================

# List of tools this specific agent can use
calendar_tools = [get_calendar_events, create_calendar_event]

# System prompt giving the agent its persona and rules
calendar_system_prompt = """You are a helpful calendar assistant. 
Use your tools to check events or create new ones based on the user's request.
Always confirm the time and details before creating an event."""

# You have to use langchain wrapped basemodel LLM in the ReAct Agent
# Initialize the LangGraph ReAct agent
calendar_react_agent = create_agent(
    model=llm_model, 
    system_prompt=calendar_system_prompt,
    tools=calendar_tools,
)

# ==========================================
# 3. LangGraph Node Wrapper
# ==========================================

def calendar_worker_node(state: dict) -> dict:
    """
    This is the node function that LangGraph will call.
    It takes the current graph state, runs the agent, and returns state updates.
    """
    print("📅 Calendar Agent is processing the request...")
    
    # Example of how you would invoke the agent with the current messages:
    response = calendar_react_agent.invoke({"messages": state["messages"]})
    
    # Return the new messages to be appended to the graph state's message list
    return {"messages": response["messages"]}
    

# ==========================================
# 4. Local Testing
# ==========================================

if __name__ == "__main__":
    # You can test the agent locally without running the whole graph!
    test_state = {
        "messages": [HumanMessage(content="create a reminder tmr on my calander to by an apple")]
    }
    
    print("Testing Calendar Agent locally...")
    result = calendar_worker_node(test_state)
    print("Result:", result["messages"][-1].content)

    all_tool_calls = []

    for msg in result["messages"]:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            all_tool_calls.extend(msg.tool_calls)

    print("All tool calls:", all_tool_calls)