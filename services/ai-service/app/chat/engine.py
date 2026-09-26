"""
Chat engine — conversational log Q&A with source citations.

Pipeline (PRD §6.2 Chat & Search Queries):
  1. Embed the user question via the cloud provider
  2. Run pgvector k-NN to retrieve top-k relevant log records
  3. Assemble a context block from the retrieved records
  4. Call the fast reasoning model with the system prompt + context + question
  5. Persist the chat session, message, and cited records
  6. Return a structured response with source citations

All retrieved records are already PII-redacted (guaranteed by the ingestion
pipeline) before any data reaches the AI provider.
"""
from __future__ import annotations

import time
import uuid
from typing import AsyncIterator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.schemas import ChatRequest, ChatResponse, CitedRecord
from app.config import settings
from app.prompts import (
    CHAT_SYSTEM_PROMPT,
    CONTEXT_BLOCK_FOOTER,
    CONTEXT_BLOCK_HEADER,
    CONTEXT_RECORD_TEMPLATE,
)
from app.providers import ChatProvider, EmbeddingProvider
from app.search.schemas import SearchMode, SearchRequest

log = structlog.get_logger()

_embedding_provider = EmbeddingProvider()
_chat_provider = ChatProvider()


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def execute_chat(
    request: ChatRequest,
    db: AsyncSession,
    *,
    actor_user_id: str | None = None,
) -> ChatResponse:
    """Handle a chat request end-to-end; return a structured response."""
    t0 = time.perf_counter()

    # Resolve or create session
    session_id = request.session_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    # Step 1 — Embed the question
    query_vector = await _embedding_provider.embed_one(request.question)

    # Step 2 — Retrieve relevant log records via vector similarity
    context_records = await _retrieve_context(
        db=db,
        query_vector=query_vector,
        request=request,
    )

    # Step 3 — Build context block
    context_text = _build_context_block(context_records)

    # Step 4 — Call the reasoning model
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": f"{context_text}\n\nQuestion: {request.question}"},
    ]

    answer = await _chat_provider.complete(messages)

    latency_ms = (time.perf_counter() - t0) * 1000

    # Step 5 — Persist session + message + cited records
    await _persist_chat(
        db=db,
        session_id=session_id,
        message_id=message_id,
        question=request.question,
        answer=answer,
        context_records=context_records,
        actor_user_id=actor_user_id,
        latency_ms=latency_ms,
    )

    log.info(
        "chat.completed",
        session_id=session_id,
        message_id=message_id,
        context_records=len(context_records),
        latency_ms=round(latency_ms, 2),
    )

    cited = [
        CitedRecord(
            id=r["id"],
            timestamp=r["timestamp"],
            service_name=r["service_name"],
            severity=r["severity"],
            message=r["message"],
            similarity_score=round(float(r["similarity_score"]), 4) if r.get("similarity_score") else None,
        )
        for r in context_records
    ]

    return ChatResponse(
        session_id=session_id,
        message_id=message_id,
        answer=answer,
        cited_records=cited,
        context_records_retrieved=len(context_records),
        latency_ms=round(latency_ms, 2),
    )


async def stream_chat(
    request: ChatRequest,
    db: AsyncSession,
    *,
    actor_user_id: str | None = None,
) -> AsyncIterator[str]:
    """
    Streaming variant — yields tokens as they arrive from the model.
    Persists the message to DB after the stream completes.
    Used by the WebSocket endpoint.
    """
    session_id = request.session_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    query_vector = await _embedding_provider.embed_one(request.question)
    context_records = await _retrieve_context(db=db, query_vector=query_vector, request=request)
    context_text = _build_context_block(context_records)

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": f"{context_text}\n\nQuestion: {request.question}"},
    ]

    full_answer = ""

    # Yield session/message IDs first so the client can track the stream
    yield f"__meta__:{session_id}:{message_id}\n"

    async for token in _chat_provider.stream(messages):
        full_answer += token
        yield token

    latency_ms = (time.perf_counter() - t0) * 1000

    await _persist_chat(
        db=db,
        session_id=session_id,
        message_id=message_id,
        question=request.question,
        answer=full_answer,
        context_records=context_records,
        actor_user_id=actor_user_id,
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _retrieve_context(
    db: AsyncSession,
    query_vector: list[float],
    request: ChatRequest,
) -> list[dict]:
    """
    Run a pgvector k-NN query to retrieve the top-k most relevant records,
    applying any optional filters from the chat request.
    """
    vector_literal = f"[{','.join(str(v) for v in query_vector)}]"

    where = ["embedding IS NOT NULL"]
    params: dict = {
        "query_vector": vector_literal,
        "limit": settings.chat_context_top_k,
    }

    if request.service_name:
        where.append("service_name = :service_name")
        params["service_name"] = request.service_name
    if request.environment:
        where.append("environment = :environment")
        params["environment"] = request.environment
    if request.time_from:
        where.append("timestamp >= :time_from")
        params["time_from"] = request.time_from
    if request.time_to:
        where.append("timestamp <= :time_to")
        params["time_to"] = request.time_to

    where_clause = "WHERE " + " AND ".join(where)

    result = await db.execute(
        text(f"""
            SELECT
                id, timestamp, service_name, severity, message,
                environment, deployment_version, trace_id,
                pii_was_redacted,
                1 - (embedding <=> CAST(:query_vector AS vector)) AS similarity_score
            FROM log_records
            {where_clause}
            ORDER BY embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """),
        params,
    )

    return [dict(row._mapping) for row in result]


def _build_context_block(records: list[dict]) -> str:
    """Format retrieved records into a context block for the system prompt."""
    if not records:
        return "(No relevant log records found for this question.)"

    parts = [CONTEXT_BLOCK_HEADER]
    for r in records:
        parts.append(
            CONTEXT_RECORD_TEMPLATE.format_map({
                "id": r["id"],
                "timestamp": r["timestamp"] or "unknown",
                "severity": r["severity"],
                "service_name": r["service_name"] or "unknown",
                "message": (r["message"] or "")[:500],  # cap per record in context
                "environment": r["environment"] or "—",
                "deployment_version": r["deployment_version"] or "—",
                "trace_id": r["trace_id"] or "—",
                "pii_was_redacted": r["pii_was_redacted"],
            })
        )
    parts.append(CONTEXT_BLOCK_FOOTER)
    return "\n".join(parts)


async def _persist_chat(
    db: AsyncSession,
    session_id: str,
    message_id: str,
    question: str,
    answer: str,
    context_records: list[dict],
    actor_user_id: str | None,
    latency_ms: float,
) -> None:
    """
    Persist the chat session, message, and agent_action audit record.
    Upserts the session row so the same session_id can be reused across turns.
    """
    try:
        # Upsert chat session
        await db.execute(
            text("""
                INSERT INTO chat_sessions (id, user_id, created_at, updated_at)
                VALUES (CAST(:id AS uuid), CAST(:user_id AS uuid), now(), now())
                ON CONFLICT (id) DO UPDATE SET updated_at = now()
            """),
            {"id": session_id, "user_id": actor_user_id},
        )

        # Insert chat message
        cited_ids = [r["id"] for r in context_records]
        await db.execute(
            text("""
                INSERT INTO chat_messages (
                    id, session_id, role, content,
                    cited_record_ids, context_record_count, latency_ms, created_at
                ) VALUES (
                    CAST(:id AS uuid), CAST(:session_id AS uuid), 'assistant', :content,
                    :cited_ids, :context_count, :latency_ms, now()
                )
            """),
            {
                "id": message_id,
                "session_id": session_id,
                "content": answer,
                "cited_ids": cited_ids,
                "context_count": len(context_records),
                "latency_ms": round(latency_ms, 2),
            },
        )

        # Audit log
        await db.execute(
            text("""
                INSERT INTO agent_actions (
                    tool_name, trigger, autonomy_tier, actor_user_id,
                    input_summary, output_summary, status
                ) VALUES (
                    'chat', 'user', 'read_only', CAST(:user_id AS uuid),
                    :input_summary, :output_summary, 'completed'
                )
            """),
            {
                "user_id": actor_user_id,
                "input_summary": question[:500],
                "output_summary": f"answer_len={len(answer)}, cited={len(cited_ids)}, latency_ms={round(latency_ms)}",
            },
        )
    except Exception as exc:
        # Persistence failure must never break the chat response
        log.warning("chat.persist_failed", error=str(exc))
