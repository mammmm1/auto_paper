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
            self._ensure_column(conn, "topics", "domain", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "topics", "task_type", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "topics", "idea", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "topics", "keywords", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "topics", "backbone", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "topics", "neck", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "topics", "head", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "topics", "dataset", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "papers", "material_type", "TEXT NOT NULL DEFAULT 'idea'")
            self._ensure_column(conn, "papers", "integration_area", "TEXT NOT NULL DEFAULT 'Experiment'")
            self._ensure_column(conn, "papers", "integration_subtag", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "papers", "stitch_action", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "papers", "stitch_difficulty", "TEXT NOT NULL DEFAULT '中'")
            self._ensure_column(conn, "papers", "relevance_score", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "papers", "stitchability_score", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "papers", "code_availability_score", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "papers", "evidence_sources", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "papers", "evidence_quote", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "papers", "is_relevant", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "papers", "relevance_tier", "TEXT NOT NULL DEFAULT 'reference'")
            self._ensure_column(conn, "papers", "filter_reason", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "papers", "user_feedback", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "papers", "is_read", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "papers", "in_basket", "INTEGER NOT NULL DEFAULT 0")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def ensure_seed_topic(self) -> None:
        with self.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
            if count == 0:
                conn.execute(
                    """
                    INSERT INTO topics(
                        name, query, max_results, domain, task_type, idea,
                        keywords, backbone, neck, head, dataset
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "遥感 Transformer 分层偏向",
                        'cat:cs.CV AND ("remote sensing" OR "object detection" OR transformer OR "small object")',
                        20,
                        "遥感图像",
                        "目标检测",
                        "Transformer 浅层偏向小物体、深层偏向大物体，利用层间目标尺度偏向增强遥感目标检测。",
                        "remote sensing, transformer, small object, multi-scale feature, layer-wise attention",
                        "Swin Transformer",
                        "FPN",
                        "Detection Head",
                        "DOTA / DIOR",
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE topics
                    SET
                        name = ?,
                        query = ?,
                        max_results = ?,
                        domain = ?,
                        task_type = ?,
                        idea = ?,
                        keywords = ?,
                        backbone = ?,
                        neck = ?,
                        head = ?,
                        dataset = ?
                    WHERE name = 'AI Agent' AND domain = '' AND idea = ''
                    """,
                    (
                        "遥感 Transformer 分层偏向",
                        'cat:cs.CV AND ("remote sensing" OR "object detection" OR transformer OR "small object")',
                        20,
                        "遥感图像",
                        "目标检测",
                        "Transformer 浅层偏向小物体、深层偏向大物体，利用层间目标尺度偏向增强遥感目标检测。",
                        "remote sensing, transformer, small object, multi-scale feature, layer-wise attention",
                        "Swin Transformer",
                        "FPN",
                        "Detection Head",
                        "DOTA / DIOR",
                    ),
                )
                profile_count = conn.execute(
                    "SELECT COUNT(*) FROM topics WHERE idea != '' OR domain != '' OR backbone != ''"
                ).fetchone()[0]
                if profile_count == 0:
                    conn.execute(
                        """
                        INSERT INTO topics(
                            name, query, max_results, domain, task_type, idea,
                            keywords, backbone, neck, head, dataset
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "遥感 Transformer 分层偏向",
                            'cat:cs.CV AND ("remote sensing" OR "object detection" OR transformer OR "small object")',
                            20,
                            "遥感图像",
                            "目标检测",
                            "Transformer 浅层偏向小物体、深层偏向大物体，利用层间目标尺度偏向增强遥感目标检测。",
                            "remote sensing, transformer, small object, multi-scale feature, layer-wise attention",
                            "Swin Transformer",
                            "FPN",
                            "Detection Head",
                            "DOTA / DIOR",
                        ),
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

    def add_topic(self, name: str, query: str, max_results: int = 10, **fields: Any) -> dict[str, Any]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO topics(
                    name, query, max_results, domain, task_type, idea,
                    keywords, backbone, neck, head, dataset
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    query.strip(),
                    max(1, min(max_results, 50)),
                    fields.get("domain", "").strip(),
                    fields.get("task_type", "").strip(),
                    fields.get("idea", "").strip(),
                    fields.get("keywords", "").strip(),
                    fields.get("backbone", "").strip(),
                    fields.get("neck", "").strip(),
                    fields.get("head", "").strip(),
                    fields.get("dataset", "").strip(),
                ),
            )
            row = conn.execute("SELECT * FROM topics WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def update_topic(self, topic_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "name",
            "query",
            "max_results",
            "domain",
            "task_type",
            "idea",
            "keywords",
            "backbone",
            "neck",
            "head",
            "dataset",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if "max_results" in updates:
            updates["max_results"] = max(1, min(int(updates["max_results"]), 50))
        if not updates:
            with self.connect() as conn:
                row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
                return dict(row)
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [topic_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE topics SET {assignments} WHERE id = ?", params)
            row = conn.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
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
                    updated_at, pdf_url, entry_url, material_type,
                    integration_area, integration_subtag, stitch_action,
                    stitch_difficulty, relevance_score, stitchability_score,
                    code_availability_score, evidence_sources, evidence_quote,
                    is_relevant, relevance_tier, filter_reason
                )
                VALUES (
                    :topic_id, :external_id, :title, :authors, :abstract, :summary,
                    :recommendation_score, :recommendation_reason, :published_at,
                    :updated_at, :pdf_url, :entry_url, :material_type,
                    :integration_area, :integration_subtag, :stitch_action,
                    :stitch_difficulty, :relevance_score, :stitchability_score,
                    :code_availability_score, :evidence_sources, :evidence_quote,
                    :is_relevant, :relevance_tier, :filter_reason
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
                    entry_url = excluded.entry_url,
                    material_type = excluded.material_type,
                    integration_area = excluded.integration_area,
                    integration_subtag = excluded.integration_subtag,
                    stitch_action = excluded.stitch_action,
                    stitch_difficulty = excluded.stitch_difficulty,
                    relevance_score = excluded.relevance_score,
                    stitchability_score = excluded.stitchability_score,
                    code_availability_score = excluded.code_availability_score,
                    evidence_sources = excluded.evidence_sources,
                    evidence_quote = excluded.evidence_quote,
                    is_relevant = excluded.is_relevant,
                    relevance_tier = excluded.relevance_tier,
                    filter_reason = excluded.filter_reason
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
        sql += " ORDER BY stitchability_score DESC, recommendation_score DESC, published_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def update_paper_state(self, paper_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"user_feedback", "is_read", "in_basket"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if "user_feedback" in updates:
            feedback = str(updates["user_feedback"])
            if feedback not in {"", "useful", "stitchable", "irrelevant"}:
                raise ValueError("invalid feedback")
            updates["user_feedback"] = feedback
            if feedback == "irrelevant":
                updates["in_basket"] = 0
        for field in ["is_read", "in_basket"]:
            if field in updates:
                updates[field] = 1 if bool(updates[field]) else 0

        with self.connect() as conn:
            row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
            if row is None:
                return None
            if updates:
                assignments = ", ".join(f"{key} = ?" for key in updates)
                conn.execute(
                    f"UPDATE papers SET {assignments} WHERE id = ?",
                    [*updates.values(), paper_id],
                )
            updated = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
            return dict(updated)

    def update_paper_analysis(self, paper_id: int, analysis: dict[str, Any]) -> None:
        fields = [
            "material_type",
            "integration_area",
            "integration_subtag",
            "stitch_action",
            "stitch_difficulty",
            "relevance_score",
            "stitchability_score",
            "code_availability_score",
            "recommendation_reason",
            "evidence_sources",
            "evidence_quote",
            "is_relevant",
            "relevance_tier",
            "filter_reason",
        ]
        assignments = ", ".join(f"{field} = ?" for field in fields)
        values = [analysis[field] for field in fields]
        with self.connect() as conn:
            conn.execute(
                f"UPDATE papers SET {assignments} WHERE id = ?",
                [*values, paper_id],
            )

    def list_basket(self, topic_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT papers.*, topics.name AS topic_name
                FROM papers
                JOIN topics ON topics.id = papers.topic_id
                WHERE papers.topic_id = ? AND papers.in_basket = 1
                ORDER BY stitchability_score DESC, published_at DESC
                """,
                (topic_id,),
            ).fetchall()
            return [dict(row) for row in rows]

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
