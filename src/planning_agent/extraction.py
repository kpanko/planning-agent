"""Post-conversation memory extraction."""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from planning_context.conversations import save_summary
from planning_context.memories import (
    add_memory,
    resolve_memory,
)
from planning_context.values import write_values

from .config import EXTRACTION_MODEL


class Memory(BaseModel):
    """A single memory to save."""

    content: str
    category: str = Field(
        description=(
            "One of: fact, observation,"
            " open_thread, preference"
        )
    )
    expiry_date: str | None = Field(
        default=None,
        description="Optional YYYY-MM-DD expiry date",
    )


class ExtractionResult(BaseModel):
    """Structured output from extraction agent."""

    new_memories: list[Memory] = Field(
        default_factory=list,
        description="New memories to save",
    )
    resolved_memory_ids: list[str] = Field(
        default_factory=list,
        description="Memory IDs to mark resolved",
    )
    values_doc_update: str | None = Field(
        default=None,
        description=(
            "New values doc content, or null for"
            " no change"
        ),
    )
    conversation_summary: str = Field(
        description="Brief summary of the conversation",
    )


EXTRACTION_PROMPT = """\
You are a memory extraction agent. Analyze the \
conversation above between Kevin and his planning agent. \
Extract:

1. **new_memories**: Facts, preferences, observations, \
or open threads worth remembering for future \
conversations. Categories: fact, observation, \
open_thread, preference. Set expiry_date (YYYY-MM-DD) \
for time-sensitive items, null otherwise.

2. **resolved_memory_ids**: IDs of any memories that \
were addressed or are no longer relevant (memory IDs \
look like "m_001").

3. **values_doc_update**: New content for the values \
document ONLY if priorities clearly shifted during the \
conversation. Set to null if no update needed (the \
common case).

4. **conversation_summary**: A 2-4 sentence summary of \
what was discussed, what was decided, what tasks were \
rescheduled, and Kevin's general mood/energy if apparent.

Be selective with memories — only save things that will \
be useful in future planning conversations. Don't save \
things that are already in Todoist as tasks.\
"""

def _make_extraction_agent() -> Agent:
    return Agent(
        EXTRACTION_MODEL,
        output_type=ExtractionResult,
    )


async def run_extraction(
    message_history: list,
) -> ExtractionResult | None:
    """Run extraction on a conversation and apply
    results.

    Returns the ExtractionResult, or None if extraction
    fails.
    """
    try:
        extraction_agent = _make_extraction_agent()
        result = await extraction_agent.run(
            EXTRACTION_PROMPT,
            message_history=message_history,
        )
        _apply(result.output)
        return result.output
    except Exception:
        import logging
        logging.getLogger("planning-agent").warning(
            "Extraction failed", exc_info=True
        )
        return None


def _apply(result: ExtractionResult) -> None:
    """Write extraction results to planning context."""
    # Save conversation summary
    save_summary(result.conversation_summary)

    # Save new memories
    for mem in result.new_memories:
        add_memory(
            mem.content,
            mem.category,
            mem.expiry_date,
        )

    # Resolve old memories
    for mid in result.resolved_memory_ids:
        resolve_memory(mid)

    # Update values doc if needed
    if result.values_doc_update is not None:
        write_values(result.values_doc_update)
