
import sys
import os

# Add the 'backend' directory to Python's path so it can find the 'utils' folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import HumanMessage, ToolMessage

from langchain_core.runnables import RunnableConfig
from langchain.agents.middleware import HumanInTheLoopMiddleware 

from langgraph.types import Command

from utils.main_utils import llm_generate_response, llm_model

import datetime
import logging
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

#Get the memory state sqlite

from datetime import timedelta

today = datetime.datetime.now().strftime("%Y-%m-%d")

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ==========================================
# 1. Define Tools for the Calendar Agent
# ==========================================

# Use read/write scope since this agent needs to both view and create events!
SCOPES = ['https://www.googleapis.com/auth/calendar',
'https://www.googleapis.com/auth/calendar.events'
]
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../client_secret.json'))
TOKEN_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../token.json'))

def _get_calendar_service():
    """Helper function to load or generate auth tokens and return the API service."""
    creds = None
    # 1. Try to load an existing token so the user doesn't have to login every time
    if os.path.exists(TOKEN_PATH):
        logger.info("Loading credentials from token.json")
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        
    # 2. If no valid token, prompt login and save it
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google credentials")
            creds.refresh(Request())
        else:
            logger.info("Initiating new Google OAuth flow")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=8080)
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

@tool
def get_calendar_events(date_str: str) -> str:
    """Fetch calendar events for a specific date (Format: YYYY-MM-DD or upcoming)."""
    logger.info(f"Checking calendar events for: {date_str}")
    service = _get_calendar_service()
    
    # If the user asks for "upcoming", just get the next 5 from right now
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Ensure it ends with 'Z' for the Google API format
    if now.endswith('+00:00'):
        now = now[:-6] + 'Z'
    
    logger.info("Executing Google API read request...")
    events_result = service.events().list(
        calendarId='primary', 
        timeMin=now,
        maxResults=5, 
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    if not events:
        logger.info("No upcoming events found.")
        return 'No upcoming events found on your calendar.'
        
    output = "Here are your upcoming events:\n"
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        output += f"- [{start}] {event['summary']}\n"
        
    logger.info(f"Successfully retrieved {len(events)} events.")
    return output

@tool
def create_calendar_event(title: str, start_time: str, end_time: str) -> str:
    """Create a new event in the Google Calendar.
    start_time and end_time MUST be in ISO format
    """
    logger.info(f"Creating calendar event: '{title}' from {start_time} to {end_time}")
    service = _get_calendar_service()
    
    event_body = {
      'summary': title,
      'start': {
        'dateTime': start_time,
        'timeZone': 'Asia/Singapore', # You can make this dynamic later
      },
      'end': {
        'dateTime': end_time,
        'timeZone': 'Asia/Singapore',
      },
    }

    logger.info("Executing Google API insert request...")
    event = service.events().insert(calendarId='primary', body=event_body).execute()
    logger.info(f"Event created successfully. Link: {event.get('htmlLink')}")
    return f"Successfully created event: {title}. Link: {event.get('htmlLink')}"

@tool
def delete_calendar_event(event_id: str) -> str:
    """Delete an event from the Google Calendar.
    event_id is the ID of the event to delete
    """
    logger.info(f"Deleting calendar event: {event_id}")
    service = _get_calendar_service()
    service.events().delete(calendarId='primary', eventId=event_id).execute()
    logger.info(f"Event deleted successfully.")
    return f"Successfully deleted event: {event_id}"

@tool
def conflict_calender_event(start_time: str, end_time: str) -> str:
    """Check if there is a conflict in calendar events.
    start_time and end_time MUST be in ISO format
    """
    logger.info(f"Checking for conflicts in calendar events from {start_time} to {end_time}")
    
    # Ensure they have timezone data for Google API
    if not start_time.endswith('Z') and '+' not in start_time[-6:]:
        start_time += 'Z'
    if not end_time.endswith('Z') and '+' not in end_time[-6:]:
        end_time += 'Z'
        
    service = _get_calendar_service()
    events = service.events().list(calendarId='primary', timeMin=start_time, timeMax=end_time).execute()
    if events.get('items'):
        return f"There is a conflict in the calendar events from {start_time} to {end_time}"
    else:
        return f"No conflicts found in the calendar events from {start_time} to {end_time}"

@tool
def find_events_by_name(event_name: str):
    """Find calendar events matching a name within the next 60 days."""
    service = _get_calendar_service()

    # Use datetime objects (NOT the global `today` string!)
    now = datetime.datetime.now(datetime.timezone.utc)
    two_months_later = now + datetime.timedelta(days=60)

    events_result = service.events().list(
        calendarId='primary',
        timeMin=now.isoformat(),
        timeMax=two_months_later.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    logger.info(f"Found {len(events)} events total, searching for '{event_name}'.")
    logger.info(f"Events: {events}")

    matches = []
    for event in events:
        summary = event.get('summary', '')
        if event_name.lower() in summary.lower():
            matches.append({
                "id": event.get('id'),
                "summary": summary,
                "start": event['start'].get('dateTime', event['start'].get('date'))
            })

    logger.info(f"Matched {len(matches)} events for '{event_name}'.")
    return matches


@tool
def delete_selected_event(event_id: str) -> str:
    """Delete an event using its ID."""
    service = _get_calendar_service()
    service.events().delete(calendarId='primary', eventId=event_id).execute()
    return f"Successfully deleted event with ID: {event_id}"

# ==========================================
# 2. Setup the Agent
# ==========================================

# List of tools this specific agent can use
calendar_tools = [
    get_calendar_events, 
    create_calendar_event,
    delete_calendar_event,
    conflict_calender_event,
    find_events_by_name,
    delete_selected_event
]

rules_md = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/rules/rules.md'))
user_preferences_md = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/user_preferences/preferences.md'))


def _safe_read_text(path: str, missing_message: str) -> str:
    """Read file content safely and return fallback text if missing/unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        logger.warning("Context file not found: %s", path)
        return missing_message
    except OSError:
        logger.exception("Failed to read context file: %s", path)
        return missing_message


def _build_calendar_system_prompt() -> str:
    """Build system prompt dynamically so updated preferences are picked up."""
    rules_text = _safe_read_text(rules_md, "No additional rules file found.")
    preferences_text = _safe_read_text(
        user_preferences_md,
        "No user preferences file found yet. Use neutral defaults and ask brief clarifying questions when needed.",
    )

    return f"""You are a helpful calendar assistant. 
Before you carry on with your tasks:
Read through and follow rules strictly.
{rules_text}

Tailor your responses to user's locale and preferences. Always confirm details before creating or deleting events.
{preferences_text}


Today's date is {today}.
Rules:
1. ALWAYS use `conflict_calender_event` to check for conflicts BEFORE creating an event.
2. If there is a conflict, DO NOT create the event. Instead, inform the user about the conflict and ask them for an alternative date or time.
3. Always confirm the time and details before creating an event.

When deleting an event:
1. First call find_events_by_name
2. If multiple matches are returned:
   - Present the list to the user clearly with numbers
   - Ask the user to choose one
3. Only delete AFTER the user selects an option
4. Use delete_selected_event with the chosen event ID
"""


def _create_calendar_react_agent(checkpointer=None):
    """Create calendar agent with latest prompt context for each invocation.
    
    Args:
        checkpointer: Optional LangGraph checkpointer for HITL state persistence.
                      When called from the service layer, a shared MemorySaver is
                      passed so interrupt state survives across HTTP requests.
    """
    kwargs = dict(
        model=llm_model,
        system_prompt=_build_calendar_system_prompt(),
        tools=calendar_tools,
        middleware=[HumanInTheLoopMiddleware(
            interrupt_on={
                "create_calendar_event": True,
                "delete_selected_event": True,
                "get_calendar_events": False,
                "conflict_calender_event": False,
                "find_events_by_name": False
            },
            description_prefix="Tool execution pending approval",
        )],
    )
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    return create_agent(**kwargs)

# ==========================================
# 3. LangGraph Node Wrapper
# ==========================================

def calendar_worker_node(state: dict, config: RunnableConfig) -> dict:
    """
    This is the node function that LangGraph will call.
    It takes the current graph state, runs the agent, and returns state updates.
    """
    logger.info("📅 Calendar worker node invoked.")
    calendar_react_agent = _create_calendar_react_agent()
    
    # Run the compiled LangGraph ReAct agent using version v2 to get the full GraphOutput
    # which includes the `.interrupts` field!
    response = calendar_react_agent.invoke({"messages": state["messages"]}, config=config)
    
    # If the response doesn't have interrupts natively, we can grab them directly from the state!
    agent_state_snapshot = calendar_react_agent.get_state(config)
    
    if hasattr(agent_state_snapshot, 'tasks') and agent_state_snapshot.tasks and agent_state_snapshot.tasks[0].interrupts:
        print("\n💥 INTERRUPT DETECTED: 💥")
        print(agent_state_snapshot.tasks[0].interrupts)
    else:
        print("No interrupts detected.")
    
    logger.info("📅 Calendar worker node finished processing.")
    
    # Safely extract the messages depending on if response is a dict or GraphOutput
    messages = response.get("messages", []) if isinstance(response, dict) else getattr(response, 'value', {}).get("messages", [])
    
    # Return the new messages to be appended to the graph state's message list
    return {"messages": messages}
    

# ==========================================
# 4. Local Testing
# ==========================================

if __name__ == "__main__":
    # # You can test the agent locally without running the whole graph!
    # test_state = {
    #     "messages": [HumanMessage(content="Help place a reminder on friday to go for a run")]
    # }
    
    # print("Testing Calendar Agent locally...")
    # config: RunnableConfig= {"configurable": {"thread_id": "demo_thread_1"}}
    # result = calendar_worker_node(test_state, config)
    # print("Result:", result["messages"][-1].content)

    # all_tool_calls = []

    # for msg in result["messages"]:
    #     if hasattr(msg, "tool_calls") and msg.tool_calls:
    #         all_tool_calls.extend(msg.tool_calls)

    # print("All tool calls:", all_tool_calls)
    

#     config: RunnableConfig = {"configurable": {"thread_id": "some_id"}}

#     result = calendar_react_agent.invoke(
#         test_state,
#         config=config)

    
#     results = calendar_react_agent.invoke(
#     Command(
#         # Decisions are provided as a list, one per action under review.
#         # The order of decisions must match the order of actions
#         # in the interrupt request.
#         resume={
#             "decisions": [
#                 {
#                     "type": "approve",
#                 }
#             ]
#         }
#     ),
#     config=config  # Same thread ID to resume the paused conversation
# )
#     print(results)

    print("\n🚀 Calendar Agent Chat (type 'quit' to exit)\n")

    config: RunnableConfig = {"configurable": {"thread_id": "demo_chat_v1"}}
    first_message = "delete the calendar event called 'gym' tomorrow at 6pm"
    user_input = first_message  # Start with a pre-set first message

    while True:
        print(f"You: {user_input}\n")
        calendar_react_agent = _create_calendar_react_agent()
        
        # Invoke the agent with the current user message
        response = calendar_react_agent.invoke(
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
        state = calendar_react_agent.get_state(config)
        if state.tasks and state.tasks[0].interrupts:
            print("💥 [INTERRUPT]: The agent wants to execute a tool. Approve or Reject?")
            approval = input("Your decision (approve/reject): ").strip().lower()
            
            decision_type = "approve" if approval == "approve" else "reject"
            resume_response = calendar_react_agent.invoke(
                Command(resume={"decisions": [{"type": decision_type}]}),
                config=config
            )
            if resume_response and "messages" in resume_response:
                print(f"🤖 Agent: {resume_response['messages'][-1].content}\n")

        # ==============================
        # Get next user input
        # ==============================
        user_input = input("You: ").strip()
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break