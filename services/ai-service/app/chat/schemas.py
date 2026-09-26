"""
Chat request/response schemas.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000, description="User's plain-language question")
    session_id: str | None = Field(None, description="Chat session UUID for conversation continuity")
    # Optional search filters — applied to the vector retrieval step
    service_name: str | None = None
    environment: str | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None


class CitedRecord(BaseModel):
    """A log record that was retrieved as evidence and cited in the response."""
    id: int
    timestamp: datetime | None
    service_name: str | None
    severity: str
    message: str | None
    similarity_score: float | None = None


class ChatResponse(BaseModel):
    session_id: str                         # UUID of the chat session
    message_id: str                         # UUID of this specific message
    answer: str                             # The model's response text
    cited_records: list[CitedRecord]        # Records referenced in the answer
    context_records_retrieved: int          # How many records were retrieved
    latency_ms: float                       # End-to-end server latency


class ChatRatingRequest(BaseModel):
    message_id: str = Field(..., description="UUID of the chat message to rate")
    helpful: bool = Field(..., description="True = thumbs up, False = thumbs down")
    comment: str | None = Field(None, max_length=1000)
