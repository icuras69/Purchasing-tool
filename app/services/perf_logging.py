from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator


logger = logging.getLogger("app.performance")


@contextmanager
def perf_timer(endpoint: str, **metadata: Any) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    context: dict[str, Any] = {}
    try:
        yield context
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        combined = {**metadata, **context}
        details = " ".join(f"{key}={_format_value(value)}" for key, value in combined.items())
        logger.info("PERF %s elapsed_ms=%s%s", endpoint, elapsed_ms, f" {details}" if details else "")


def _format_value(value: Any) -> str:
    if value is None:
        return "None"
    text = str(value).replace("\n", " ").replace("\r", " ")
    if len(text) > 120:
        return f"{text[:117]}..."
    return text
