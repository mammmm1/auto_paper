from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_path: Path
    daily_hour: int
    openai_api_key: str = field(default="", repr=False)
    openai_model: str = "gpt-5-mini"
    paper_cache_dir: Path = Path("data/papers")


def load_settings() -> Settings:
    return Settings(
        host=os.getenv("AUTO_PAPER_HOST", "127.0.0.1"),
        port=int(os.getenv("AUTO_PAPER_PORT", "8000")),
        database_path=Path(os.getenv("AUTO_PAPER_DB", "data/auto_paper.sqlite3")),
        daily_hour=int(os.getenv("AUTO_PAPER_DAILY_HOUR", "8")),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        paper_cache_dir=Path(os.getenv("AUTO_PAPER_CACHE", "data/papers")),
    )
