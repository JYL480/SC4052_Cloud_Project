"""
General agent to fallback for any requests that do not fit the other agents. Will use the LLM directly to try to answer the question. This is useful for general knowledge questions, or if 
the user just wants to have a casual conversation with the assistant.

- Will always cross check with rules as well

"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import datetime
import logging
from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig

from utils.main_utils import llm_model

logger = logging.getLogger(__name__)
today = datetime.datetime.now().strftime("%Y-%m-%d")

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


def _build_general_system_prompt() -> str:
	"""Build general-agent system prompt dynamically with rules/preferences context."""
	rules_text = _safe_read_text(rules_md, "No additional rules file found.")
	preferences_text = _safe_read_text(
		user_preferences_md,
		"No user preferences file found yet. Use neutral defaults.",
	)

	return f"""You are a helpful general personal assistant fallback agent.
Today's date is {today}.

Before you carry on with your tasks:
Read through and follow rules strictly.
{rules_text}

Tailor your responses to user's locale and preferences.
{preferences_text}

Responsibilities:
1. Handle general conversation and broad PA requests that do not require specialist workers.
2. Answer capability questions (what you can do) and provide concise planning help.
3. If user asks for calendar/email/weather operations requiring specialist tools, tell them you will hand off and keep the response brief.

Style:
- Be concise, clear, and practical.
- Ask a short clarification question when necessary.
- Avoid making up facts.
"""


def _create_general_react_agent():
	"""Create general fallback agent with latest prompt context."""
	return create_agent(
		model=llm_model,
		system_prompt=_build_general_system_prompt(),
		tools=[],
	)


def general_worker_node(state: dict, config: RunnableConfig) -> dict:
	"""LangGraph node wrapper for the general fallback agent."""
	logger.info("🧩 General worker node invoked.")
	general_agent = _create_general_react_agent()
	response = general_agent.invoke({"messages": state["messages"]}, config=config)
	logger.info("🧩 General worker node finished.")
	messages = response.get("messages", []) if isinstance(response, dict) else []
	return {"messages": messages}