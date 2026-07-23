from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env(env_file: Path | None = None) -> None:
    """Load .env from project root or an explicit path."""
    if env_file is not None:
        load_dotenv(env_file, override=False)
        return
    load_dotenv(override=False)


def default_output_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "output")).resolve()


def default_delays() -> tuple[float, float]:
    delay_min = float(os.getenv("SCRAPE_DELAY_MIN", "1.0"))
    delay_max = float(os.getenv("SCRAPE_DELAY_MAX", "3.0"))
    return delay_min, delay_max


def env(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key, default)
    if value is None or value == "":
        return default
    return value
