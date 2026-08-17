from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    query TEXT NOT NULL,
                    max_results INTEGER NOT NULL DEFAULT 10,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    authors TEXT NOT NULL,
                    abstract TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    recommendation_score REAL NOT NULL,
                    recommendation_reason TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pdf_url TEXT NOT NULL,
                    entry_url TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(topic_id, external_id),
                    FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    fetched_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE SET NULL
                );
                """
            )

    def ensure_seed_topic(self) -> None:
        with self.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
            if count == 0:
                conn.execute(
                    "INSERT INTO topics(name, query, max_results) VALUES (?, ?, ?)",
                    ("AI Agent", 'cat:cs.AI AND (agent OR "large language model")', 10),
                )

    def list_topics(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM topics"
        params: tuple[Any, ...] = ()
        if enabled_only:
            sql += " WHERE enabled = ?"
            params = (1,)
        sql += " ORDER BY created_at DESC, id DESC"
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def add_topic(self, name: str, query: str, max_results: int = 10) -> dict[str, Any]:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO topics(name, query, max_results) VALUES (?, ?, ?)",
                (name.strip(), query.strip(), max(1, min(max_results, 50))),
            )
            row = conn.execute("SELECT * FROM topics WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def delete_topic(self, topic_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))

    def upsert_paper(self, paper: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO papers (
                    topic_id, external_id, title, authors, abstract, summary,
                    recommendation_score, recommendation_reason, published_at,
                    updated_at, pdf_url, entry_url
                )
                VALUES (
                    :topic_id, :external_id, :title, :authors, :abstract, :summary,
                    :recommendation_score, :recommendation_reason, :published_at,
                    :updated_at, :pdf_url, :entry_url
                )
                ON CONFLICT(topic_id, external_id) DO UPDATE SET
                    title = excluded.title,
                    authors = excluded.authors,
                    abstract = excluded.abstract,
                    summary = excluded.summary,
                    recommendation_score = excluded.recommendation_score,
                    recommendation_reason = excluded.recommendation_reason,
                    published_at = excluded.published_at,
                    updated_at = excluded.updated_at,
                    pdf_url = excluded.pdf_url,
                    entry_url = excluded.entry_url
                """,
                paper,
            )

    def list_papers(self, topic_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = """
            SELECT papers.*, topics.name AS topic_name
            FROM papers
            JOIN topics ON topics.id = papers.topic_id
        """
        params: list[Any] = []
        if topic_id:
            sql += " WHERE topic_id = ?"
            params.append(topic_id)
        sql += " ORDER BY recommendation_score DESC, published_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def record_run(self, topic_id: int | None, status: str, message: str, fetched_count: int = 0) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO runs(topic_id, status, message, fetched_count) VALUES (?, ?, ?, ?)",
                (topic_id, status, message, fetched_count),
            )

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT runs.*, topics.name AS topic_name
                FROM runs
                LEFT JOIN topics ON topics.id = runs.topic_id
                ORDER BY runs.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
