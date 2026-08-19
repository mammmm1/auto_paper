from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from auto_paper.arxiv_client import search_arxiv
from auto_paper.config import Settings, load_settings
from auto_paper.database import Database
from auto_paper.exporter import papers_to_csv, papers_to_markdown
from auto_paper.materializer import build_material_card, build_project_query
from auto_paper.quality import build_quality_metrics, rank_materials
from auto_paper.recommender import score_paper
from auto_paper.route_builder import build_experiment_route
from auto_paper.scheduler import DailyScheduler
from auto_paper.summarizer import summarize_paper


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"


class AutoPaperApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_path)
        self.db.ensure_seed_topic()

    def ranked_papers(self, topic_id: int | None = None, limit: int = 100) -> list[dict]:
        papers = self.db.list_papers(topic_id=topic_id, limit=500)
        return rank_materials(papers)[:limit]

    def quality_metrics(self, topic_id: int) -> dict:
        papers = self.db.list_papers(topic_id=topic_id, limit=500)
        return build_quality_metrics(papers)

    def run_topics(self, topic_id: int | None = None) -> dict:
        topics = self.db.list_topics(enabled_only=True)
        if topic_id:
            topics = [topic for topic in topics if topic["id"] == topic_id]

        total = 0
        relevant_total = 0
        tier_total = {"direct": 0, "transferable": 0, "reference": 0, "irrelevant": 0}
        errors: list[str] = []
        for topic in topics:
            try:
                has_profile = any(topic.get(field) for field in ["domain", "task_type", "idea", "keywords"])
                query = build_project_query(topic) if has_profile else topic["query"]
                for existing in self.db.list_papers(topic_id=topic["id"], limit=500):
                    material = build_material_card(
                        SimpleNamespace(title=existing["title"], abstract=existing["abstract"]),
                        topic,
                        existing["summary"],
                    )
                    self.db.update_paper_analysis(existing["id"], material)
                recall_size = min(50, max(30, int(topic["max_results"]) * 2))
                papers = search_arxiv(query, recall_size)
                for candidate in papers:
                    summary = summarize_paper(candidate.title, candidate.abstract, query)
                    score, reason = score_paper(
                        candidate.title,
                        candidate.abstract,
                        query,
                        candidate.published_at,
                    )
                    material = build_material_card(candidate, topic, summary)
                    self.db.upsert_paper(
                        {
                            "topic_id": topic["id"],
                            "external_id": candidate.external_id,
                            "title": candidate.title,
                            "authors": candidate.authors,
                            "abstract": candidate.abstract,
                            "summary": material["summary"],
                            "recommendation_score": max(score, material["recommendation_score"]),
                            "recommendation_reason": material["recommendation_reason"] or reason,
                            "published_at": candidate.published_at,
                            "updated_at": candidate.updated_at,
                            "pdf_url": candidate.pdf_url,
                            "entry_url": candidate.entry_url,
                            "material_type": material["material_type"],
                            "integration_area": material["integration_area"],
                            "integration_subtag": material["integration_subtag"],
                            "stitch_action": material["stitch_action"],
                            "stitch_difficulty": material["stitch_difficulty"],
                            "relevance_score": material["relevance_score"],
                            "stitchability_score": material["stitchability_score"],
                            "code_availability_score": material["code_availability_score"],
                            "evidence_sources": material["evidence_sources"],
                            "evidence_quote": material["evidence_quote"],
                            "is_relevant": material["is_relevant"],
                            "relevance_tier": material["relevance_tier"],
                            "filter_reason": material["filter_reason"],
                        }
                    )
                    relevant_total += int(material["is_relevant"])
                    tier_total[material["relevance_tier"]] += 1
                total += len(papers)
                self.db.record_run(topic["id"], "success", "ok", len(papers))
            except Exception as exc:  # noqa: BLE001 - API failures should be captured in MVP runs.
                message = f"{topic['name']}: {exc}"
                errors.append(message)
                self.db.record_run(topic["id"], "failed", message, 0)

        status = "partial" if errors else "success"
        return {
            "status": status,
            "fetched_count": total,
            "relevant_count": relevant_total,
            "filtered_count": total - relevant_total,
            "tier_counts": tier_total,
            "errors": errors,
        }


def create_handler(app: AutoPaperApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = urlparse(self.path)
            if route.path == "/api/projects":
                self._json(app.db.list_topics())
                return
            if route.path == "/api/topics":
                self._json(app.db.list_topics())
                return
            if route.path == "/api/papers":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("topic_id", [""])[0])
                limit = _optional_int(query.get("limit", ["100"])[0]) or 100
                self._json(app.ranked_papers(topic_id=topic_id, limit=limit))
                return
            if route.path == "/api/quality":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("topic_id", [""])[0])
                if not topic_id:
                    self._json({"error": "missing topic_id"}, HTTPStatus.BAD_REQUEST)
                    return
                self._json(app.quality_metrics(topic_id))
                return
            if route.path == "/api/runs":
                self._json(app.db.list_runs())
                return
            if route.path == "/api/basket/route":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("topic_id", [""])[0])
                if not topic_id:
                    self._json({"error": "missing topic_id"}, HTTPStatus.BAD_REQUEST)
                    return
                project = next(
                    (item for item in app.db.list_topics() if item["id"] == topic_id),
                    None,
                )
                if project is None:
                    self._json({"error": "project not found"}, HTTPStatus.NOT_FOUND)
                    return
                materials = app.db.list_basket(topic_id)
                self._json(build_experiment_route(project, materials))
                return
            if route.path == "/api/export":
                self._export(route.query)
                return
            self._static(route.path)

        def do_POST(self) -> None:
            route = urlparse(self.path)
            if route.path == "/api/projects":
                payload = self._read_json()
                try:
                    query = payload.get("query") or build_project_query(payload)
                    project = app.db.add_topic(
                        payload["name"],
                        query,
                        int(payload.get("max_results", 20)),
                        domain=payload.get("domain", ""),
                        task_type=payload.get("task_type", ""),
                        idea=payload.get("idea", ""),
                        keywords=payload.get("keywords", ""),
                        backbone=payload.get("backbone", ""),
                        neck=payload.get("neck", ""),
                        head=payload.get("head", ""),
                        dataset=payload.get("dataset", ""),
                    )
                    self._json(project, HTTPStatus.CREATED)
                except (KeyError, ValueError) as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                except Exception as exc:  # noqa: BLE001
                    self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
                return
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

        def do_PUT(self) -> None:
            route = urlparse(self.path)
            if route.path == "/api/projects":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("id", [""])[0])
                if not topic_id:
                    self._json({"error": "missing id"}, HTTPStatus.BAD_REQUEST)
                    return
                payload = self._read_json()
                if not payload.get("query"):
                    payload["query"] = build_project_query(payload)
                try:
                    project = app.db.update_topic(topic_id, payload)
                    self._json(project)
                except Exception as exc:  # noqa: BLE001
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_PATCH(self) -> None:
            route = urlparse(self.path)
            if route.path == "/api/materials":
                query = parse_qs(route.query)
                paper_id = _optional_int(query.get("id", [""])[0])
                if not paper_id:
                    self._json({"error": "missing id"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    material = app.db.update_paper_state(paper_id, self._read_json())
                except ValueError as exc:
                    self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                if material is None:
                    self._json({"error": "material not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(material)
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
            papers = app.ranked_papers(topic_id=topic_id, limit=500)
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
