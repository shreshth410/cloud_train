"""Logging configuration and helper utilities for CloudTrain."""

import logging
import os
from typing import Any

try:
    from aws_lambda_powertools import Logger as PowertoolsLogger

    _HAS_POWERTOOLS = True
except ImportError:
    _HAS_POWERTOOLS = False


def get_logger(service_name: str | None = None) -> Any:
    """Return a configured structured logger.

    Falls back to standard library logging if aws_lambda_powertools is not available.
    """
    service = service_name or os.getenv("SERVICE_NAME", "cloudtrain")
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    if _HAS_POWERTOOLS:
        return PowertoolsLogger(service=service, level=log_level)

    logger = logging.getLogger(service)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    return logger
