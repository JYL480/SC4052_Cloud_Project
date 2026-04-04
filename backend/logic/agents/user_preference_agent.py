"""User preference agent.

This module stores and retrieves user preferences in Markdown files.
It is designed to support a lightweight onboarding flow and persistent
preferences that can be loaded before tool calls.

Will start the flow off first then in the future when the user 
wants to update their preferences they can trigger this agent again and it will update the markdown
file with the new preferences.

"""

import sys
import os
import json
import datetime
import logging
import re
from pathlib import Path
from typing import Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from utils.main_utils import llm_model

logger = logging.getLogger(__name__)

PREFERENCE_DIR = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/user_preferences')))
SINGLE_USER_FILE = PREFERENCE_DIR / "preferences.md"


def _preference_file_path() -> Path:
    """Return the single-user preference markdown path."""
    return SINGLE_USER_FILE


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries."""
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _extract_preferences_from_md(content: str) -> dict[str, Any]:
    """Extract JSON preferences payload from markdown file content."""
    match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", content)
    if not match:
        return {}

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.exception("Failed to parse preferences JSON block from markdown")
        return {}


def _render_preferences_markdown(preferences: dict[str, Any]) -> str:
    """Render markdown with embedded JSON payload for reliable parsing."""
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pretty = json.dumps(preferences, indent=2, ensure_ascii=True)
    return (
        "# User Preferences\n\n"
        f"- updated_at_utc: {ts}\n\n"
        "## Preferences JSON\n\n"
        "```json\n"
        f"{pretty}\n"
        "```\n"
    )


def get_user_preference() -> dict[str, Any]:
    """Retrieve user preference dictionary from markdown storage."""
    file_path = _preference_file_path()
    if not file_path.exists():
        return {}

    try:
        content = file_path.read_text(encoding="utf-8")
        return _extract_preferences_from_md(content)
    except OSError:
        logger.exception("Failed reading preference file")
        return {}


@tool
def create_md_preference(preference_info: dict[str, Any]) -> str:
    """Create (overwrite) the single user's markdown preference profile.

    Args:
        preference_info: New preference fields to persist.
    """
    if not isinstance(preference_info, dict):
        return "Error: preference_info must be a dictionary."

    PREFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    target = _preference_file_path()
    body = _render_preferences_markdown(preferences=preference_info)

    try:
        target.write_text(body, encoding="utf-8")
        logger.info("Saved preferences to %s", target)
        return "Preferences saved successfully."
    except OSError:
        logger.exception("Failed writing preference file")
        return "Error: failed to persist preferences."


preference_tools = [create_md_preference]

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

preference_system_prompt = """You are a user preference onboarding assistant.

Goal:
1. Ask one concise onboarding question to collect stable user preferences in one shot.
2. Once you have enough information, call create_md_preference exactly once to save it.

Collect at least these fields if possible (FORMAT NICELY IN MARKDOWN):
- profile.name
- locale.timezone
- calendar.default_meeting_minutes
- calendar.buffer_minutes
- email.tone
- email.signoff
- weather.unit (celsius or fahrenheit)

Rules:
- Do NOT ask for user_id. It is handled by the backend.
- On the very first assistant message, start with "Welcome" + a short introduction,
  then ask for all required fields in one shot.
- If user already provided values, do not ask again.
- Accept user-provided text as-is. Do not claim typos or reject unusual names.
- Before calling the tool, summarize what will be saved and ask for confirmation.
- After confirmation, call create_md_preference.
- If preferences were already saved in this conversation and the user replies with
    closure text (e.g., "nope that's good", "all good", "thanks"), respond with a
    short acknowledgment and do NOT ask for confirmation again.
- If user rejects a pre-save summary, ask what they want to change instead of saving.

After Saving the Preferences:
- Respond with a short confirmation message and end the conversation.
- Tell the user they can update their preferences anytime by messaging you again with changes.
- They can continue with the PA's calendar, email, and weather support, which will use these preferences for personalization.
"""


get_user_preference_agent = create_agent(
    model=llm_model,
    tools=preference_tools,
    system_prompt=preference_system_prompt,
)


def user_preference_worker_node(state: dict, config: RunnableConfig) -> dict:
    """LangGraph node wrapper for the user preference agent."""
    logger.info("🧠 User preference worker node invoked.")
    response = get_user_preference_agent.invoke({"messages": state["messages"]}, config=config)
    logger.info("🧠 User preference worker node finished.")
    messages = response.get("messages", []) if isinstance(response, dict) else []
    return {"messages": messages}


if __name__ == "__main__":
    print("\n🧠 User Preference Agent Chat (type 'quit' to exit)\n")
    print(ONBOARDING_WELCOME)
    config: RunnableConfig = {"configurable": {"thread_id": "pref_test_1"}}
    conversation: list[BaseMessage] = []
    user_input = input("You: ").strip()

    while True:
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        conversation.append(HumanMessage(content=user_input))

        response = get_user_preference_agent.invoke(
            {"messages": conversation},
            config=config,
        )
        if response and "messages" in response:
            conversation = response["messages"]
            print(f"\n🧠 Agent: {response['messages'][-1].content}\n")

        user_input = input("You: ").strip()