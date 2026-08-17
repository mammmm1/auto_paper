from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_path: Path
    daily_hour: int


def load_settings() -> Settings:
    return Settings(
        host=os.getenv("AUTO_PAPER_HOST", "127.0.0.1"),
        port=int(os.getenv("AUTO_PAPER_PORT", "8000")),
        database_path=Path(os.getenv("AUTO_PAPER_DB", "data/auto_paper.sqlite3")),
        daily_hour=int(os.getenv("AUTO_PAPER_DAILY_HOUR", "8")),
    )

