"""
Service contracts — shared Pydantic schemas for all service endpoints.

Every service receives a `ServiceRequest` and returns a `ServiceResponse`.
HITL-capable services also accept `ServiceResumeRequest`.
"""

from typing import Optional, Any
from pydantic import BaseModel


# ==========================================
# Request Schemas
# ==========================================

class ServiceRequest(BaseModel):
    """Standard request sent to any service endpoint."""
    messages: list[dict]       # Serialized LangChain messages
    thread_id: str
    user_id: str


class ServiceResumeRequest(BaseModel):
    """Resume a HITL-paused service invocation."""
    thread_id: str
    user_id: str
    decision: str              # "approve" or "reject"


# ==========================================
# Response Schemas
# ==========================================

class ServiceResponse(BaseModel):
    """Standard response returned by every service endpoint."""
    messages: list[dict]                       # Serialized LangChain messages
    status: str                                # "success" | "error" | "interrupted"
    error: Optional[str] = None
    interrupt_details: Optional[dict] = None


class ServiceHealthResponse(BaseModel):
    """Health check response for individual services."""
    service: str
    status: str                                # "healthy" | "unhealthy"
    details: Optional[dict] = None
