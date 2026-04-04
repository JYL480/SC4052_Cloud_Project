"""
Message serialization utilities for converting between
LangChain BaseMessage objects and plain dicts (JSON-safe).

Used by services to serialize/deserialize messages across HTTP boundaries.
"""

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)


def serialize_message(msg: BaseMessage) -> dict:
    """Convert a single LangChain message to a JSON-safe dict."""
    data: dict = {
        "type": msg.type,
        "content": msg.content or "",
    }

    if msg.id:
        data["id"] = msg.id
    if getattr(msg, "name", None):
        data["name"] = msg.name
    if getattr(msg, "tool_calls", None):
        data["tool_calls"] = msg.tool_calls
    if getattr(msg, "tool_call_id", None):
        data["tool_call_id"] = msg.tool_call_id
    if getattr(msg, "additional_kwargs", None):
        data["additional_kwargs"] = msg.additional_kwargs

    return data


def serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    """Convert a list of LangChain messages to JSON-safe dicts."""
    return [serialize_message(m) for m in messages]


def deserialize_message(data: dict) -> BaseMessage:
    """Reconstruct a LangChain message from a dict."""
    msg_type = data.get("type", "human")
    content = data.get("content", "")

    # Shared optional kwargs
    kwargs: dict = {}
    if data.get("id"):
        kwargs["id"] = data["id"]
    if data.get("name"):
        kwargs["name"] = data["name"]
    if data.get("additional_kwargs"):
        kwargs["additional_kwargs"] = data["additional_kwargs"]

    if msg_type == "human":
        return HumanMessage(content=content, **kwargs)

    elif msg_type == "ai":
        if data.get("tool_calls"):
            kwargs["tool_calls"] = data["tool_calls"]
        return AIMessage(content=content, **kwargs)

    elif msg_type == "system":
        return SystemMessage(content=content, **kwargs)

    elif msg_type == "tool":
        if data.get("tool_call_id"):
            kwargs["tool_call_id"] = data["tool_call_id"]
        return ToolMessage(content=content, **kwargs)

    # Fallback
    return HumanMessage(content=content, **kwargs)


def deserialize_messages(data: list[dict]) -> list[BaseMessage]:
    """Reconstruct a list of LangChain messages from dicts."""
    return [deserialize_message(d) for d in data]
