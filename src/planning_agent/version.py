"""Auto-version from build-time git commit."""

import os

GIT_COMMIT: str = os.environ.get("GIT_COMMIT", "dev")
