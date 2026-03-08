"""Allow running as `python -m planning_context`."""

import sys

try:
    from .server import main

    main()
except Exception:
    import logging
    import traceback

    traceback.print_exc(file=sys.stderr)
    logging.getLogger("planning-context").critical(
        "Fatal error during startup", exc_info=True
    )
    sys.exit(1)
