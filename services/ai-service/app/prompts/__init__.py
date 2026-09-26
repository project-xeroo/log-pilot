"""
System and user prompt templates for the LogPilot chat tool.

All prompts are plain strings — no templating library required.
Variable interpolation is done with str.format_map() at call time.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Chat system prompt
# Instructs the model to act as a sourced, evidence-backed log analyst.
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = """\
You are LogPilot, an expert AI assistant that answers questions about \
production log data. You have been given a set of relevant log records \
retrieved from the system's database to use as evidence.

Rules you must follow:
1. Base your answer ONLY on the log records provided. Do not invent events, \
   error messages, or timestamps that are not present in the records.
2. Always cite your sources. For each claim, reference the record(s) using \
   the format [record:<id>] where <id> is the numeric record ID.
3. When quoting log messages, reproduce the text exactly as it appears in \
   the record — never paraphrase a log line if you can quote it.
4. If the provided records are insufficient to answer the question, say so \
   clearly rather than guessing.
5. Format your answer as plain prose. Use short bullet lists only when \
   listing multiple distinct items.
6. Keep your answer concise but complete — aim for 2–4 paragraphs unless \
   the question requires more detail.
7. If any record was PII-redacted (pii_was_redacted=true), note this when \
   referencing that record so the user understands some fields may be masked.
"""

# ---------------------------------------------------------------------------
# Context block template — injected between system prompt and user question
# ---------------------------------------------------------------------------

CONTEXT_RECORD_TEMPLATE = """\
[record:{id}] {timestamp} | {severity} | {service_name}
  message: {message}
  environment: {environment} | version: {deployment_version} | trace: {trace_id}
  pii_redacted: {pii_was_redacted}
"""

CONTEXT_BLOCK_HEADER = "--- RETRIEVED LOG RECORDS (use these as your evidence) ---\n"
CONTEXT_BLOCK_FOOTER = "\n--- END OF RECORDS ---\n"
