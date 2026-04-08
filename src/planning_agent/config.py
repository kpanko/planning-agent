"""Settings and API keys for the planning agent."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

TODOIST_API_KEY = os.environ.get("TODOIST_API_KEY", "")
USER_TZ = os.environ.get("USER_TZ", "America/New_York")

# Web auth
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get(
    "GOOGLE_CLIENT_SECRET", ""
)
ALLOWED_GOOGLE_EMAIL = os.environ.get(
    "ALLOWED_GOOGLE_EMAIL", ""
)
WEB_SECRET = os.environ.get("WEB_SECRET", "")
DEBUG_MODE = bool(os.environ.get("DEBUG_MODE", ""))
LOGFIRE_TOKEN = os.environ.get("LOGFIRE_TOKEN", "")
NIGHTLY_REPLAN_TOKEN = os.environ.get(
    "NIGHTLY_REPLAN_TOKEN", ""
)
BASE_URL = os.environ.get(
    "BASE_URL", "http://localhost:8080"
).rstrip("/")

_data_dir = Path(
    os.environ.get(
        "PLANNING_AGENT_DATA_DIR",
        Path.home() / ".planning-agent",
    )
)

GOOGLE_CALENDAR_CREDENTIALS = Path(
    os.environ.get(
        "GOOGLE_CALENDAR_CREDENTIALS",
        _data_dir / "google_credentials.json",
    )
)


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
        main = "anthropic:claude-opus-4-6"
        extraction = "anthropic:claude-opus-4-6"
    elif has_openai:
        main = "openai:gpt-5.4"
        extraction = "openai:gpt-5.4"
    else:
        # Fall back to Anthropic; will error at
        # runtime if no key is provided.
        main = "anthropic:claude-opus-4-6"
        extraction = "anthropic:claude-opus-4-6"

    return main, extraction


_default_main, _default_extraction = _default_models()

LLM_MODEL = os.environ.get("LLM_MODEL", _default_main)
EXTRACTION_MODEL = os.environ.get(
    "EXTRACTION_MODEL", _default_extraction
)
