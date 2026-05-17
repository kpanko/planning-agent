"""Post-conversation memory extraction (observations-based)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from planning_context.conversations import save_summary
from planning_context.observations import write_observations
from planning_context.rules import write_rules

from .config import EXTRACTION_MODEL

logger = logging.getLogger("planning-agent")


class ExtractionResult(BaseModel):
    """Structured output from the extraction agent."""

    observations_doc: str = Field(
        description=(
            "Full replacement contents for observations.md."
            " Markdown bullets, each with confidence and"
            " evidence count. Empty string to clear."
        ),
    )
    rules_doc_update: str | None = Field(
        default=None,
        description=(
            "Full replacement contents for rules.md, OR null"
            " for no change. Only set when the user has"
            " explicitly stated or approved a new rule."
        ),
    )
    conversation_summary: str = Field(
        description="Brief summary of the conversation",
    )


EXTRACTION_PROMPT = """\
You are a memory extraction agent. Analyze the conversation
above between the user and their planning agent. You see the
*current* contents of observations.md and rules.md in the
conversation context (the planning agent surfaces them). Your
job is to produce three outputs.

1. **observations_doc**: a complete, updated body for
   observations.md. Carry forward any existing observations
   that remain valid. Add new soft inferences from the
   conversation. Remove observations the user contradicted.
   Each observation is a markdown bullet of the form:

       - <natural-language observation>
         - confidence: low | medium | high
         - evidence: <count> observation(s)
         - first seen: YYYY-MM-DD

   Be conservative. Only record patterns supported by the
   conversation. Observations are SOFT — they will be hedged
   when used. Wrong observations are worse than no
   observations.

2. **rules_doc_update**: usually null. Only set this when the
   user has explicitly stated a rule ("I never work past
   9pm") or explicitly approved a graduation from a soft
   observation to a hard rule. Returns the full new rules.md
   body when set.

3. **conversation_summary**: 2-4 sentences. What was
   discussed, what was decided, what tasks moved, the
   user's mood/energy if apparent.

Be selective. Do not record things already captured by
Todoist tasks. Do not invent rules the user did not state.\
"""


def _make_extraction_agent() -> Agent[None, ExtractionResult]:
    return Agent(
        EXTRACTION_MODEL,
        output_type=ExtractionResult,
    )


async def run_extraction(
    message_history: list[Any],
) -> ExtractionResult | None:
    """Run extraction on a conversation and apply results.

    Returns the ExtractionResult, or None if extraction fails.
    """
    n_msgs = len(message_history)
    logger.info(
        "Starting extraction (%d messages)", n_msgs
    )
    try:
        extraction_agent = _make_extraction_agent()
        result = await extraction_agent.run(
            EXTRACTION_PROMPT,
            message_history=message_history,
        )
        _apply(result.output)
        logger.info(
            "Extraction complete: observations %d chars,"
            " rules_update=%s, summary saved",
            len(result.output.observations_doc),
            result.output.rules_doc_update is not None,
        )
        return result.output
    except Exception:
        logger.warning("Extraction failed", exc_info=True)
        return None


def _apply(result: ExtractionResult) -> None:
    """Write extraction results to the planning context.

    Order matters: the conversation summary is persisted last,
    so a failure in observations/rules writes does not leave a
    summary referencing state that was never recorded.
    """
    write_observations(result.observations_doc)
    if result.rules_doc_update is not None:
        write_rules(result.rules_doc_update)
    save_summary(result.conversation_summary)
