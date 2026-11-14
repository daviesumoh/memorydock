from __future__ import annotations

import logging

from memorydock_core.config import Settings


def configure(settings: Settings) -> None:
    """Send memorydock.* logs to stderr at LOG_LEVEL; uvicorn configures only its own loggers."""
    logger = logging.getLogger("memorydock")
    logger.setLevel(settings.log_level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
