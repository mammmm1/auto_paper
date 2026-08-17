from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from auto_paper.arxiv_client import search_arxiv
from auto_paper.config import Settings, load_settings
from auto_paper.database import Database
from auto_paper.exporter import papers_to_csv, papers_to_markdown
from auto_paper.recommender import score_paper
from auto_paper.scheduler import DailyScheduler
from auto_paper.summarizer import summarize_paper


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"


class AutoPaperApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_path)
        self.db.ensure_seed_topic()

    def run_topics(self, topic_id: int | None = None) -> dict:
        topics = self.db.list_topics(enabled_only=True)
        if topic_id:
            topics = [topic for topic in topics if topic["id"] == topic_id]

        total = 0
        errors: list[str] = []
        for topic in topics:
            try:
                papers = search_arxiv(topic["query"], topic["max_results"])
                for candidate in papers:
                    summary = summarize_paper(candidate.title, candidate.abstract, topic["query"])
                    score, reason = score_paper(
                        candidate.title,
                        candidate.abstract,
                        topic["query"],
                        candidate.published_at,
                    )
                    self.db.upsert_paper(
                        {
                            "topic_id": topic["id"],
                            "external_id": candidate.external_id,
                            "title": candidate.title,
                            "authors": candidate.authors,
                            "abstract": candidate.abstract,
                            "summary": summary,
                            "recommendation_score": score,
                            "recommendation_reason": reason,
                            "published_at": candidate.published_at,
                            "updated_at": candidate.updated_at,
                            "pdf_url": candidate.pdf_url,
                            "entry_url": candidate.entry_url,
                        }
                    )
                total += len(papers)
                self.db.record_run(topic["id"], "success", "ok", len(papers))
            except Exception as exc:  # noqa: BLE001 - API failures should be captured in MVP runs.
                message = f"{topic['name']}: {exc}"
                errors.append(message)
                self.db.record_run(topic["id"], "failed", message, 0)

        status = "partial" if errors else "success"
        return {"status": status, "fetched_count": total, "errors": errors}


def create_handler(app: AutoPaperApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = urlparse(self.path)
            if route.path == "/api/topics":
                self._json(app.db.list_topics())
                return
            if route.path == "/api/papers":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("topic_id", [""])[0])
                limit = _optional_int(query.get("limit", ["100"])[0]) or 100
                self._json(app.db.list_papers(topic_id=topic_id, limit=limit))
                return
            if route.path == "/api/runs":
                self._json(app.db.list_runs())
                return
            if route.path == "/api/export":
                self._export(route.query)
                return
            self._static(route.path)

        def do_POST(self) -> None:
            route = urlparse(self.path)
            if route.path == "/api/topics":
                payload = self._read_json()
                try:
                    topic = app.db.add_topic(
                        payload["name"],
                        payload["query"],
                        int(payload.get("max_results", 10)),
                    )
                    self._json(topic, HTTPStatus.CREATED)
                except (KeyError, ValueError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                except Exception as exc:  # noqa: BLE001
                    self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
                return
            if route.path == "/api/run":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("topic_id", [""])[0])
                result = app.run_topics(topic_id)
                self._json(result)
                return
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_DELETE(self) -> None:
            route = urlparse(self.path)
            if route.path == "/api/topics":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("id", [""])[0])
                if not topic_id:
                    self._json({"error": "missing id"}, HTTPStatus.BAD_REQUEST)
                    return
                app.db.delete_topic(topic_id)
                self._json({"ok": True})
                return
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _export(self, raw_query: str) -> None:
            query = parse_qs(raw_query)
            topic_id = _optional_int(query.get("topic_id", [""])[0])
            papers = app.db.list_papers(topic_id=topic_id, limit=500)
            export_format = query.get("format", ["markdown"])[0]
            if export_format == "csv":
                body = papers_to_csv(papers).encode("utf-8-sig")
                filename = "auto-paper.csv"
                content_type = "text/csv; charset=utf-8"
            else:
                body = papers_to_markdown(papers).encode("utf-8")
                filename = "auto-paper.md"
                content_type = "text/markdown; charset=utf-8"

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _static(self, route_path: str) -> None:
            relative = "index.html" if route_path == "/" else route_path.lstrip("/")
            path = (PUBLIC_DIR / relative).resolve()
            if not str(path).startswith(str(PUBLIC_DIR.resolve())) or not path.exists():
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _optional_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto Paper MVP")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--run-once", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    if args.host:
        settings = Settings(args.host, settings.port, settings.database_path, settings.daily_hour)
    if args.port:
        settings = Settings(settings.host, args.port, settings.database_path, settings.daily_hour)

    app = AutoPaperApp(settings)
    if args.run_once:
        print(json.dumps(app.run_topics(), ensure_ascii=False, indent=2))
        return

    server = ThreadingHTTPServer((settings.host, settings.port), create_handler(app))
    scheduler = DailyScheduler(settings.daily_hour, app.run_topics)
    scheduler.start()
    print(f"Auto Paper running at http://{settings.host}:{settings.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        server.server_close()


if __name__ == "__main__":
    main()

