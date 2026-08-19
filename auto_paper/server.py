from __future__ import annotations

import argparse
import concurrent.futures
import json
import mimetypes
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from auto_paper.arxiv_client import search_arxiv
from auto_paper.config import Settings, load_settings
from auto_paper.database import Database
from auto_paper.deep_analyzer import analysis_engine, analysis_input_hash, analyze_material
from auto_paper.exporter import papers_to_csv, papers_to_markdown
from auto_paper.evidence_extractor import (
    collect_paper_evidence,
    evidence_input_hash,
)
from auto_paper.materializer import build_material_card, build_project_query
from auto_paper.quality import build_quality_metrics, rank_materials
from auto_paper.recommender import score_paper
from auto_paper.route_builder import build_experiment_route
from auto_paper.profile_validator import validate_project_profile
from auto_paper.scheduler import DailyScheduler
from auto_paper.summarizer import summarize_paper
from auto_paper.venue_ranker import resolve_venue


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

    def project(self, topic_id: int) -> dict | None:
        return next((item for item in self.db.list_topics() if item["id"] == topic_id), None)

    def profile_check(self, topic_id: int) -> dict | None:
        project = self.project(topic_id)
        return validate_project_profile(project) if project else None

    def cached_deep_analysis(self, paper_id: int) -> dict | None:
        paper = self.db.get_paper(paper_id)
        if paper is None:
            return None
        project = self.project(int(paper["topic_id"]))
        if project is None:
            return None
        engine = analysis_engine(self.settings.openai_api_key, self.settings.openai_model)
        expected_hash = analysis_input_hash(paper, project, engine)
        raw = str(paper.get("deep_analysis_json") or "")
        is_current = bool(raw) and paper.get("deep_analysis_input_hash") == expected_hash
        if not is_current:
            return {
                "paper_id": paper_id,
                "analysis": None,
                "cache_hit": False,
                "stale": bool(raw),
            }
        try:
            analysis = json.loads(raw)
        except json.JSONDecodeError:
            analysis = None
        return {
            "paper_id": paper_id,
            "analysis": analysis,
            "source": paper.get("deep_analysis_source") or "",
            "model": paper.get("deep_analysis_model") or "",
            "updated_at": paper.get("deep_analysis_updated_at") or "",
            "cache_hit": analysis is not None,
            "stale": False,
            "warning": "",
        }

    def analyze_paper(self, paper_id: int, force: bool = False) -> dict | None:
        if not force:
            cached = self.cached_deep_analysis(paper_id)
            if cached and cached.get("analysis"):
                return cached
        paper = self.db.get_paper(paper_id)
        if paper is None:
            return None
        project = self.project(int(paper["topic_id"]))
        if project is None:
            return None
        result = analyze_material(
            paper,
            project,
            api_key=self.settings.openai_api_key,
            model=self.settings.openai_model,
        )
        self.db.save_deep_analysis(
            paper_id,
            json.dumps(result["analysis"], ensure_ascii=False),
            result["source"],
            result["model"],
            result["input_hash"],
        )
        return {
            "paper_id": paper_id,
            "analysis": result["analysis"],
            "source": result["source"],
            "model": result["model"],
            "updated_at": self.db.get_paper(paper_id).get("deep_analysis_updated_at", ""),
            "cache_hit": False,
            "stale": False,
            "warning": result.get("warning", ""),
        }

    def analyze_top(self, topic_id: int, force: bool = False, limit: int = 10) -> dict:
        metrics = self.quality_metrics(topic_id)
        paper_ids = metrics.get("top_material_ids", [])[: max(1, min(limit, 10))]
        results = []
        for paper_id in paper_ids:
            result = self.analyze_paper(int(paper_id), force=force)
            if result:
                results.append(result)
        return {
            "topic_id": topic_id,
            "analyzed_count": len(results),
            "cached_count": sum(1 for item in results if item.get("cache_hit")),
            "profile_check": self.profile_check(topic_id),
            "results": results,
        }

    def cached_evidence(self, paper_id: int) -> dict | None:
        paper = self.db.get_paper(paper_id)
        if paper is None:
            return None
        expected_hash = evidence_input_hash(paper)
        raw = str(paper.get("full_text_json") or "")
        is_current = bool(raw) and paper.get("full_text_input_hash") == expected_hash
        if not is_current:
            return {
                "paper_id": paper_id,
                "status": "pending",
                "evidence": None,
                "cache_hit": False,
                "stale": bool(raw),
                "error": "",
            }
        try:
            evidence = json.loads(raw)
        except json.JSONDecodeError:
            evidence = None
        return {
            "paper_id": paper_id,
            "status": paper.get("full_text_status") or "pending",
            "evidence": evidence,
            "cache_hit": evidence is not None,
            "stale": False,
            "error": paper.get("full_text_error") or "",
            "updated_at": paper.get("full_text_updated_at") or "",
        }

    def collect_evidence(self, paper_id: int, force: bool = False) -> dict | None:
        if not force:
            cached = self.cached_evidence(paper_id)
            if cached and cached.get("evidence"):
                return cached
        paper = self.db.get_paper(paper_id)
        if paper is None:
            return None
        input_hash = evidence_input_hash(paper)
        try:
            evidence = collect_paper_evidence(
                paper,
                self.settings.paper_cache_dir,
                force=force,
            )
            status = str(evidence.get("status") or "verified")
            error = ""
        except Exception as exc:  # noqa: BLE001 - surface per-paper extraction failure to the UI.
            status = "failed"
            error = _safe_message(exc)
            evidence = {
                "status": status,
                "pdf": {"url": paper.get("pdf_url") or ""},
                "sections": [],
                "code": {"status": "not_found", "urls": []},
                "limitations": [error],
            }
        self.db.save_full_text_evidence(
            paper_id,
            status,
            json.dumps(evidence, ensure_ascii=False),
            input_hash,
            error,
        )
        return {
            "paper_id": paper_id,
            "status": status,
            "evidence": evidence,
            "cache_hit": False,
            "stale": False,
            "error": error,
            "updated_at": self.db.get_paper(paper_id).get("full_text_updated_at", ""),
        }

    def collect_top_evidence(self, topic_id: int, force: bool = False, limit: int = 10) -> dict:
        metrics = self.quality_metrics(topic_id)
        paper_ids = [int(item) for item in metrics.get("top_material_ids", [])[: max(1, min(limit, 10))]]
        results_by_id: dict[int, dict] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(paper_ids) or 1)) as executor:
            futures = {
                executor.submit(self.collect_evidence, paper_id, force): paper_id
                for paper_id in paper_ids
            }
            for future in concurrent.futures.as_completed(futures):
                paper_id = futures[future]
                result = future.result()
                if result:
                    results_by_id[paper_id] = result
        results = [results_by_id[paper_id] for paper_id in paper_ids if paper_id in results_by_id]
        return {
            "topic_id": topic_id,
            "processed_count": len(results),
            "verified_count": sum(1 for item in results if item.get("status") == "verified"),
            "text_insufficient_count": sum(
                1 for item in results if item.get("status") == "text_insufficient"
            ),
            "failed_count": sum(1 for item in results if item.get("status") == "failed"),
            "cached_count": sum(1 for item in results if item.get("cache_hit")),
            "results": results,
        }

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
                    venue = resolve_venue(candidate.journal_ref, candidate.comment, candidate.doi)
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
                            **venue,
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
            if route.path == "/api/profile-check":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("topic_id", [""])[0])
                if not topic_id:
                    self._json({"error": "missing topic_id"}, HTTPStatus.BAD_REQUEST)
                    return
                result = app.profile_check(topic_id)
                if result is None:
                    self._json({"error": "project not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(result)
                return
            if route.path == "/api/deep-analysis":
                query = parse_qs(route.query)
                paper_id = _optional_int(query.get("paper_id", [""])[0])
                if not paper_id:
                    self._json({"error": "missing paper_id"}, HTTPStatus.BAD_REQUEST)
                    return
                result = app.cached_deep_analysis(paper_id)
                if result is None:
                    self._json({"error": "material not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(result)
                return
            if route.path == "/api/evidence":
                query = parse_qs(route.query)
                paper_id = _optional_int(query.get("paper_id", [""])[0])
                if not paper_id:
                    self._json({"error": "missing paper_id"}, HTTPStatus.BAD_REQUEST)
                    return
                result = app.cached_evidence(paper_id)
                if result is None:
                    self._json({"error": "material not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(result)
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
            if route.path == "/api/analyze":
                query = parse_qs(route.query)
                paper_id = _optional_int(query.get("paper_id", [""])[0])
                force = query.get("force", ["0"])[0] == "1"
                if not paper_id:
                    self._json({"error": "missing paper_id"}, HTTPStatus.BAD_REQUEST)
                    return
                result = app.analyze_paper(paper_id, force=force)
                if result is None:
                    self._json({"error": "material not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(result)
                return
            if route.path == "/api/analyze/top":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("topic_id", [""])[0])
                force = query.get("force", ["0"])[0] == "1"
                if not topic_id:
                    self._json({"error": "missing topic_id"}, HTTPStatus.BAD_REQUEST)
                    return
                if app.project(topic_id) is None:
                    self._json({"error": "project not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(app.analyze_top(topic_id, force=force))
                return
            if route.path == "/api/evidence":
                query = parse_qs(route.query)
                paper_id = _optional_int(query.get("paper_id", [""])[0])
                force = query.get("force", ["0"])[0] == "1"
                if not paper_id:
                    self._json({"error": "missing paper_id"}, HTTPStatus.BAD_REQUEST)
                    return
                result = app.collect_evidence(paper_id, force=force)
                if result is None:
                    self._json({"error": "material not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(result)
                return
            if route.path == "/api/evidence/top":
                query = parse_qs(route.query)
                topic_id = _optional_int(query.get("topic_id", [""])[0])
                force = query.get("force", ["0"])[0] == "1"
                if not topic_id:
                    self._json({"error": "missing topic_id"}, HTTPStatus.BAD_REQUEST)
                    return
                if app.project(topic_id) is None:
                    self._json({"error": "project not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._json(app.collect_top_evidence(topic_id, force=force))
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


def _safe_message(error: Exception) -> str:
    return " ".join(str(error).split())[:300]


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto Paper MVP")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--run-once", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    if args.host:
        settings = replace(settings, host=args.host)
    if args.port:
        settings = replace(settings, port=args.port)

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
