"""Settings and API keys for the planning agent."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

TODOIST_API_KEY = os.environ.get("TODOIST_API_KEY", "")


def _default_models() -> tuple[str, str]:
    """Pick default models based on available API keys.

    Explicit LLM_MODEL / EXTRACTION_MODEL env vars
    always win. Otherwise, use Anthropic if
    ANTHROPIC_API_KEY is set, then OpenAI if
    OPENAI_API_KEY is set.
    """
    has_anthropic = bool(
        os.environ.get("ANTHROPIC_API_KEY")
    )
    has_openai = bool(
        os.environ.get("OPENAI_API_KEY")
    )

    if has_anthropic:
        main = "anthropic:claude-sonnet-4-6"
        extraction = "anthropic:claude-haiku-4-5"
    elif has_openai:
        main = "openai:gpt-4o"
        extraction = "openai:gpt-4o-mini"
    else:
        # Fall back to Anthropic; will error at
        # runtime if no key is provided.
        main = "anthropic:claude-sonnet-4-6"
        extraction = "anthropic:claude-haiku-4-5"

    return main, extraction


_default_main, _default_extraction = _default_models()

LLM_MODEL = os.environ.get("LLM_MODEL", _default_main)
EXTRACTION_MODEL = os.environ.get(
    "EXTRACTION_MODEL", _default_extraction
)
