from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
import string
from typing import Annotated, List, Dict, Any, Optional, Union, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4
from typing_extensions import TypedDict
from operator import add
import os
import sys

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


# ===============================================
# 1. State Definition (Used natively by LangGraph)
# ===============================================
class AgentState(TypedDict):
    """
    This is the core state object that flows through the graph.
    Every node in the graph accepts this state and returns updates to it.
    """
    
    # Annotated with add_messages so LangGraph knows to APPEND new messages 
    # rather than overwrite the whole list every time.
    messages: Annotated[list[BaseMessage], add_messages]

    # Routing signal set by the orchestrator to tell the graph which worker to call next.
    # e.g. 'calendar', 'email', or None (meaning we are done)
    next_agent: Optional[str]

    requires_approval: Optional[bool]
    
    generation_state: Optional[str] #KIV for now LOL
    
#### Note i will not be adding the user_id, thread_id here. All will done in the config that is passde
# To the graph yeah to watch for the state changes

generation_state = {
    "idle",
    "routing",
    "processing",
    "waiting_approval",
    "generating",
    "completed",
    "error"
}