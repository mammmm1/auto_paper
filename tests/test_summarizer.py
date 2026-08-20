import json
from pathlib import Path
import tempfile
import unittest

from auto_paper.arxiv_client import parse_arxiv_feed
from auto_paper.code_scanner import scan_codebase
from auto_paper.database import Database
from auto_paper.deep_analyzer import (
    analysis_input_hash,
    build_rule_analysis,
    extract_response_text,
)
from auto_paper.evidence_extractor import (
    evidence_input_hash,
    extract_code_urls,
    extract_evidence_from_pages,
)
from auto_paper.exporter import papers_to_csv, papers_to_markdown
from auto_paper.materializer import build_material_card, build_project_query
from auto_paper.profile_validator import validate_project_profile
from auto_paper.quality import build_quality_metrics, rank_materials
from auto_paper.recommender import score_paper
from auto_paper.route_builder import build_experiment_route
from auto_paper.summarizer import summarize_paper
from auto_paper.synthesizer import build_research_synthesis
from auto_paper.venue_ranker import resolve_venue


class SummarizerTests(unittest.TestCase):
    def test_summary_prefers_contribution_signal(self):
        summary = summarize_paper(
            "Agent planning benchmark",
            "We introduce a benchmark for evaluating planning agents. The dataset covers multi-step reasoning tasks.",
            "agent planning benchmark",
        )

        self.assertIn("核心贡献", summary)
        self.assertIn("benchmark", summary.lower())


class RecommenderTests(unittest.TestCase):
    def test_score_returns_reason(self):
        score, reason = score_paper(
            "Large language model agent benchmark",
            "This benchmark includes code and evaluation for agent systems.",
            "agent benchmark",
            "2026-08-01T00:00:00Z",
        )

        self.assertGreater(score, 0)
        self.assertTrue(reason)


class ArxivClientTests(unittest.TestCase):
    def test_parses_publication_metadata(self):
        feed = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <id>https://arxiv.org/abs/2601.00001v2</id>
            <updated>2026-02-01T00:00:00Z</updated>
            <published>2026-01-01T00:00:00Z</published>
            <title>Scale-aware detector</title>
            <summary>A remote sensing detector.</summary>
            <author><name>Researcher One</name></author>
            <link title="pdf" href="https://arxiv.org/pdf/2601.00001" />
            <arxiv:comment>Accepted to CVPR 2026</arxiv:comment>
            <arxiv:journal_ref>Proceedings of CVPR 2026</arxiv:journal_ref>
            <arxiv:doi>10.1000/example</arxiv:doi>
          </entry>
        </feed>"""

        paper = parse_arxiv_feed(feed)[0]

        self.assertEqual(paper.journal_ref, "Proceedings of CVPR 2026")
        self.assertEqual(paper.comment, "Accepted to CVPR 2026")
        self.assertEqual(paper.doi, "10.1000/example")


class VenueRankerTests(unittest.TestCase):
    def test_recognizes_ccf_conference_from_comment(self):
        venue = resolve_venue(comment="Accepted to ECCV 2026 as a full paper")

        self.assertEqual(venue["venue_name"], "ECCV")
        self.assertEqual(venue["venue_type"], "conference")
        self.assertEqual(venue["venue_rank"], "CCF B")
        self.assertEqual(venue["venue_status"], "accepted")

    def test_recognizes_journal_with_ccf_and_jcr_ranks(self):
        venue = resolve_venue(
            journal_ref="IEEE Transactions on Pattern Analysis and Machine Intelligence, 2026"
        )

        rankings = json.loads(venue["venue_rankings_json"])
        self.assertEqual(venue["venue_name"], "IEEE TPAMI")
        self.assertEqual(venue["venue_rank"], "CCF A / JCR Q1")
        self.assertEqual([item["system"] for item in rankings], ["CCF", "JCR"])

    def test_remote_sensing_text_is_not_mistaken_for_journal(self):
        venue = resolve_venue(comment="A benchmark for remote sensing object detection")

        self.assertEqual(venue["venue_name"], "arXiv")
        self.assertEqual(venue["venue_status"], "preprint")
        self.assertEqual(venue["venue_rank"], "")

    def test_venue_mention_without_acceptance_stays_preprint(self):
        venue = resolve_venue(comment="Includes a comparison with CVPR 2025 methods")

        self.assertEqual(venue["venue_name"], "arXiv")
        self.assertEqual(venue["venue_status"], "preprint")

    def test_keeps_unknown_journal_without_inventing_rank(self):
        venue = resolve_venue(journal_ref="Journal of Emerging Geospatial Methods, 12(3), 2026")

        self.assertEqual(venue["venue_type"], "journal")
        self.assertEqual(venue["venue_status"], "published")
        self.assertEqual(venue["venue_rank"], "")


class DatabaseTests(unittest.TestCase):
    def test_persists_code_profile_and_invalidates_scan_when_path_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            topic = db.add_topic(
                "Code scan test",
                "all:test",
                idea="keep this idea",
                code_path="D:/work/model-a",
                code_repo_url="https://example.com/model-a",
            )
            with db.connect() as conn:
                paper_id = conn.execute(
                    """
                    INSERT INTO papers(
                        topic_id, external_id, title, authors, abstract, summary,
                        recommendation_score, recommendation_reason, published_at,
                        updated_at, pdf_url, entry_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        topic["id"], "paper-1", "Paper", "Author", "Abstract", "Summary",
                        80, "Relevant", "2026-01-01", "2026-01-01", "pdf", "entry",
                    ),
                ).lastrowid
            db.save_deep_analysis(paper_id, "{}", "rules", "rules-v1", "hash")
            db.save_code_scan(topic["id"], json.dumps({"status": "ready"}))

            unchanged = db.update_topic(topic["id"], {"code_path": "D:/work/model-a"})
            self.assertTrue(unchanged["code_scan_json"])

            updated = db.update_topic(
                topic["id"],
                {"idea": "keep this idea", "code_path": "D:/work/model-b"},
            )

            self.assertEqual(updated["code_path"], "D:/work/model-b")
            self.assertEqual(updated["code_repo_url"], "https://example.com/model-a")
            self.assertEqual(updated["code_scan_json"], "")
            self.assertEqual(updated["code_scan_updated_at"], "")
            self.assertEqual(db.get_paper(paper_id)["deep_analysis_json"], "{}")

    def test_upsert_persists_venue_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            topic = db.add_topic("Venue test", "all:test")
            venue = resolve_venue(comment="Accepted to CVPR 2026")
            db.upsert_paper(
                {
                    "topic_id": topic["id"],
                    "external_id": "2601.00001v1",
                    "title": "Venue-aware paper",
                    "authors": "Researcher",
                    "abstract": "Abstract",
                    "summary": "Summary",
                    "recommendation_score": 80,
                    "recommendation_reason": "Relevant",
                    "published_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "pdf_url": "https://arxiv.org/pdf/2601.00001",
                    "entry_url": "https://arxiv.org/abs/2601.00001",
                    "material_type": "idea",
                    "integration_area": "Experiment",
                    "integration_subtag": "Benchmark",
                    "stitch_action": "Compare the method",
                    "stitch_difficulty": "low",
                    "relevance_score": 80,
                    "stitchability_score": 75,
                    "code_availability_score": 25,
                    "evidence_sources": "title and abstract",
                    "evidence_quote": "Evidence",
                    "is_relevant": True,
                    "relevance_tier": "direct",
                    "filter_reason": "Direct match",
                    **venue,
                }
            )

            paper = db.list_papers(topic["id"], limit=1)[0]

            self.assertEqual(paper["venue_name"], "CVPR")
            self.assertEqual(paper["venue_rank"], "CCF A")
            self.assertEqual(paper["venue_status"], "accepted")


class SynthesisTests(unittest.TestCase):
    def test_builds_comparison_compatibility_and_three_schemes(self):
        project = {
            "id": 1,
            "name": "遥感检测",
            "task_type": "目标检测",
            "idea": "分层尺度偏向增强小目标检测",
            "backbone": "Swin",
            "neck": "FPN",
            "head": "Detection Head",
        }
        materials = [
            self._material(1, "Neck", "Feature Fusion", "低", 88, 82),
            self._material(2, "Backbone", "Layer Attention", "中", 84, 78),
            self._material(3, "Neck", "Feature Fusion", "高", 80, 74),
        ]

        result = build_research_synthesis(project, materials)

        self.assertEqual(len(result["comparison"]), 3)
        self.assertEqual(len(result["schemes"]), 3)
        self.assertEqual(result["schemes"][0]["id"], "conservative")
        self.assertEqual(result["schemes"][0]["material_ids"], [1])
        self.assertEqual(result["recommendation"]["primary_scheme_id"], "balanced")
        self.assertTrue(
            any(item["status"] == "alternative" for item in result["compatibility"]["relationships"])
        )
        balanced_areas = {item["area"] for item in result["schemes"][1]["modules"]}
        self.assertIn("Backbone", balanced_areas)
        self.assertIn("Neck", balanced_areas)

    def test_reports_missing_evidence_and_analysis(self):
        result = build_research_synthesis(
            {"id": 1, "name": "项目"},
            [
                {
                    "id": 1,
                    "title": "Paper",
                    "is_relevant": 1,
                    "integration_area": "Experiment",
                    "integration_subtag": "Ablation",
                    "stitchability_score": 70,
                }
            ],
        )

        self.assertEqual(result["coverage"]["analyzed_count"], 0)
        self.assertEqual(result["coverage"]["evidence_count"], 0)
        self.assertTrue(any("缺少结构化" in item for item in result["limitations"]))

    def test_maps_scheme_modules_to_scanned_code_files(self):
        code_scan = {
            "status": "ready",
            "root": "D:/work/model",
            "repository_name": "model",
            "frameworks": ["PyTorch"],
            "areas": ["Neck"],
            "summary": {"files_scanned": 12, "component_count": 1},
            "components": [
                {
                    "area": "Neck",
                    "kind": "class",
                    "name": "FeaturePyramid",
                    "path": "models/necks/fpn.py",
                    "line": 18,
                    "confidence": 91,
                    "signals": ["neck", "fpn"],
                }
            ],
            "entrypoints": [],
            "warnings": [],
        }

        result = build_research_synthesis(
            {"id": 1, "name": "项目", "code_repo_url": "https://example.com/model"},
            [self._material(1, "Neck", "Feature Fusion", "低", 88, 82)],
            code_scan,
        )

        implementation = result["schemes"][0]["implementation_map"][0]
        self.assertEqual(implementation["status"], "mapped")
        self.assertEqual(implementation["target"]["path"], "models/necks/fpn.py")
        self.assertEqual(result["code_context"]["files_scanned"], 12)
        self.assertTrue(any("只读静态扫描" in item for item in result["limitations"]))

    @staticmethod
    def _material(
        material_id: int,
        area: str,
        subtag: str,
        difficulty: str,
        score: float,
        confidence: int,
    ) -> dict:
        analysis = {
            "integration_area": area,
            "reusable_module": f"{area} reusable module",
            "integration_interface": {
                "inputs": ["input features"],
                "outputs": ["output features"],
                "code_changes": ["add adapter"],
            },
            "minimal_implementation": ["freeze baseline", f"integrate {subtag}"],
            "expected_gain": "improve target scale performance",
            "risks": ["channel mismatch"],
            "evidence": ["method evidence"],
            "confidence": confidence,
        }
        evidence = {
            "status": "verified",
            "sections": [{"kind": "method", "page": 3, "text": "method section"}],
            "code": {"status": "verified_repository", "urls": []},
        }
        return {
            "id": material_id,
            "title": f"Paper {material_id}",
            "is_relevant": 1,
            "integration_area": area,
            "integration_subtag": subtag,
            "stitch_action": f"integrate {subtag}",
            "stitch_difficulty": difficulty,
            "ranking_score": score,
            "relevance_score": score,
            "deep_analysis_json": json.dumps(analysis),
            "full_text_status": "verified",
            "full_text_json": json.dumps(evidence),
        }


class CodeScannerTests(unittest.TestCase):
    def test_builds_component_map_and_ignores_artifact_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            files = {
                "models/backbones/swin.py": "import torch\nclass SwinTransformer(torch.nn.Module):\n    pass\n",
                "models/necks/fpn.py": "class FeaturePyramid:\n    pass\n",
                "models/losses.py": "class DiceLoss:\n    pass\n",
                "datasets/remote.py": "class RemoteSensingDataset:\n    pass\n",
                "train.py": "def train():\n    pass\n",
                "configs/model.json": json.dumps({"model": {"backbone": {}, "neck": {}, "head": {}}}),
                "checkpoints/secret.py": "class HiddenBackbone:\n    pass\n",
            }
            for relative_path, content in files.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            result = scan_codebase(str(root))

        self.assertEqual(result["status"], "ready")
        self.assertIn("PyTorch", result["frameworks"])
        self.assertIn("Backbone", result["areas"])
        self.assertIn("Neck", result["areas"])
        self.assertIn("Loss", result["areas"])
        self.assertIn("Data", result["areas"])
        self.assertTrue(any(item["path"] == "train.py" for item in result["entrypoints"]))
        self.assertFalse(any("checkpoints" in item["path"] for item in result["components"]))

    def test_reports_unconfigured_and_missing_directories(self):
        self.assertEqual(scan_codebase("")["status"], "not_configured")
        self.assertEqual(scan_codebase("Z:/path/that/does/not/exist")["status"], "not_found")


class MaterializerTests(unittest.TestCase):
    def test_material_card_prefers_neck_for_feature_fusion(self):
        class Candidate:
            title = "Multi-scale feature fusion for remote sensing object detection"
            abstract = (
                "We propose a feature pyramid fusion module for small object detection "
                "in remote sensing images. The method improves multi-scale representation."
            )

        project = {
            "domain": "遥感图像",
            "task_type": "目标检测",
            "idea": "层间大小目标偏向",
            "keywords": "remote sensing, small object, multi-scale feature",
            "backbone": "Swin Transformer",
            "neck": "FPN",
            "head": "Detection Head",
            "dataset": "DOTA",
        }
        card = build_material_card(Candidate(), project, "summary")

        self.assertEqual(card["integration_area"], "Neck")
        self.assertEqual(card["relevance_tier"], "direct")
        self.assertGreater(card["stitchability_score"], 0)
        self.assertIn("FPN", card["stitch_action"])

    def test_project_query_has_computer_vision_category(self):
        query = build_project_query(
            {"domain": "遥感图像", "task_type": "目标检测", "keywords": "remote sensing, small object"}
        )

        self.assertIn("cat:cs.CV", query)
        self.assertIn('all:"remote sensing"', query)
        self.assertIn(" AND ", query)

    def test_unrelated_remote_domain_is_filtered(self):
        class Candidate:
            title = "Transformer policies for remote robotic manipulation"
            abstract = "We study teleoperation and robotic manipulation with a transformer policy."

        project = {
            "domain": "遥感图像",
            "task_type": "目标检测",
            "idea": "增强遥感小目标检测",
            "keywords": "remote sensing, transformer, small object",
        }
        card = build_material_card(Candidate(), project, "summary")

        self.assertFalse(card["is_relevant"])
        self.assertEqual(card["relevance_tier"], "irrelevant")
        self.assertLessEqual(card["stitchability_score"], 35)

    def test_cross_domain_detection_method_is_kept(self):
        class Candidate:
            title = "Multi-scale transformer for small object detection"
            abstract = "A feature pyramid and attention improve small object detection."

        project = {
            "domain": "遥感图像",
            "task_type": "目标检测",
            "idea": "增强遥感小目标检测",
            "keywords": "remote sensing, transformer, small object",
        }
        card = build_material_card(Candidate(), project, "summary")

        self.assertTrue(card["is_relevant"])
        self.assertEqual(card["relevance_tier"], "transferable")
        self.assertIn("跨领域", card["filter_reason"])

    def test_remote_domain_without_task_or_method_is_reference(self):
        class Candidate:
            title = "A satellite imagery dataset for agricultural monitoring"
            abstract = "We release remote sensing observations for crop statistics."

        project = {
            "domain": "遥感图像",
            "task_type": "目标检测",
            "idea": "增强遥感小目标检测",
            "keywords": "remote sensing, transformer, small object",
        }
        card = build_material_card(Candidate(), project, "summary")

        self.assertFalse(card["is_relevant"])
        self.assertEqual(card["relevance_tier"], "reference")

    def test_other_remote_sensing_task_is_transferable_not_direct(self):
        class Candidate:
            title = "Attention transformer for remote sensing change detection"
            abstract = "We propose an attention architecture for satellite image change detection."

        project = {
            "domain": "遥感图像",
            "task_type": "语义分割",
            "idea": "增强遥感语义分割",
            "keywords": "remote sensing, transformer, semantic segmentation",
        }
        card = build_material_card(Candidate(), project, "summary")

        self.assertTrue(card["is_relevant"])
        self.assertEqual(card["relevance_tier"], "transferable")


class QualityTests(unittest.TestCase):
    def test_feedback_ranking_influences_similar_materials(self):
        materials = [
            self._material(1, "Neck", "module", "Feature Fusion", "stitchable"),
            self._material(2, "Neck", "module", "Feature Fusion", ""),
            self._material(3, "Backbone", "architecture", "Representation", ""),
        ]

        ranked = rank_materials(materials)
        similar = next(item for item in ranked if item["id"] == 2)

        self.assertGreater(similar["feedback_adjustment"], 3)
        self.assertIn("同类素材", similar["ranking_reason"])

    def test_quality_metrics_reports_label_gap(self):
        materials = [
            self._material(1, "Neck", "module", "Feature Fusion", "useful"),
            self._material(2, "Backbone", "architecture", "Representation", ""),
            self._material(3, "Loss", "module", "Optimization", "irrelevant"),
        ]

        metrics = build_quality_metrics(materials)

        self.assertEqual(metrics["labeled_count"], 2)
        self.assertEqual(metrics["positive_count"], 1)
        self.assertEqual(metrics["irrelevant_count"], 1)
        self.assertEqual(metrics["remaining_labels"], 1)
        self.assertEqual(metrics["status"], "collecting")

    @staticmethod
    def _material(
        material_id: int,
        area: str,
        material_type: str,
        subtag: str,
        feedback: str,
    ) -> dict:
        return {
            "id": material_id,
            "integration_area": area,
            "material_type": material_type,
            "integration_subtag": subtag,
            "user_feedback": feedback,
            "relevance_tier": "direct",
            "is_relevant": 1,
            "stitchability_score": 70,
            "relevance_score": 75,
            "code_availability_score": 55,
            "stitch_difficulty": "中",
            "published_at": "2026-08-01T00:00:00Z",
        }


class RouteBuilderTests(unittest.TestCase):
    def test_route_orders_materials_by_pipeline(self):
        project = {
            "name": "遥感检测",
            "idea": "分层尺度偏向",
            "backbone": "Swin",
            "neck": "FPN",
            "head": "Detection Head",
            "dataset": "DOTA",
        }
        materials = [
            {
                "title": "Loss idea",
                "integration_area": "Loss",
                "stitch_action": "Add loss",
                "stitch_difficulty": "低",
                "stitchability_score": 80,
                "code_availability_score": 25,
            },
            {
                "title": "Backbone idea",
                "integration_area": "Backbone",
                "stitch_action": "Change backbone",
                "stitch_difficulty": "高",
                "stitchability_score": 70,
                "code_availability_score": 55,
            },
        ]

        route = build_experiment_route(project, materials)

        self.assertEqual(route["steps"][0]["area"], "Backbone")
        self.assertEqual(route["steps"][1]["area"], "Loss")
        self.assertIn("Swin", route["baseline"])

    def test_route_prefers_cached_deep_analysis_action(self):
        analysis = {
            "integration_area": "Neck",
            "minimal_implementation": ["冻结基线", "接入尺度路由模块"],
            "risks": ["特征通道可能不匹配"],
        }
        route = build_experiment_route(
            {"name": "遥感检测", "idea": "分层尺度偏向"},
            [
                {
                    "title": "Scale router",
                    "integration_area": "Neck",
                    "stitch_action": "旧动作",
                    "stitch_difficulty": "中",
                    "stitchability_score": 80,
                    "code_availability_score": 60,
                    "deep_analysis_json": json.dumps(analysis, ensure_ascii=False),
                    "deep_analysis_source": "rules",
                }
            ],
        )

        self.assertEqual(route["steps"][0]["action"], "接入尺度路由模块")
        self.assertIn("特征通道可能不匹配", route["risks"])


class ProfileValidatorTests(unittest.TestCase):
    def test_detects_segmentation_and_detection_profile_conflict(self):
        result = validate_project_profile(
            {
                "name": "遥感工作台",
                "domain": "遥感图像",
                "task_type": "语义分割",
                "idea": "增强遥感小目标检测",
                "keywords": "remote sensing, object detection",
                "backbone": "Swin Transformer",
                "neck": "FPN",
                "head": "Detection Head",
                "dataset": "DOTA",
            }
        )

        self.assertEqual(result["status"], "warning")
        self.assertIn("task_idea_mismatch", [item["code"] for item in result["issues"]])

    def test_consistent_profile_is_ready(self):
        result = validate_project_profile(
            {
                "name": "遥感检测",
                "domain": "遥感图像",
                "task_type": "目标检测",
                "idea": "通过多尺度特征增强小目标检测",
                "keywords": "remote sensing, object detection",
                "backbone": "Swin Transformer",
                "neck": "FPN",
                "head": "Detection Head",
                "dataset": "DOTA",
            }
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["readiness_score"], 100)


class DeepAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "name": "遥感检测",
            "domain": "遥感图像",
            "task_type": "目标检测",
            "idea": "分层尺度偏向",
            "keywords": "small object, multi-scale",
            "backbone": "Swin Transformer",
            "neck": "FPN",
            "head": "Detection Head",
            "dataset": "DOTA",
        }
        self.paper = {
            "title": "Scale-aware feature fusion for remote sensing detection",
            "abstract": "We propose a scale-aware fusion module for small object detection in aerial images. " * 5,
            "summary": "该工作通过尺度感知融合增强小目标特征。",
            "material_type": "module",
            "integration_area": "Neck",
            "integration_subtag": "Feature Fusion",
            "stitch_action": "在 FPN 中增加尺度路由分支。",
            "evidence_quote": "scale-aware fusion module for small object detection",
        }

    def test_rule_analysis_returns_executable_structure(self):
        analysis = build_rule_analysis(self.paper, self.project)

        self.assertEqual(analysis["integration_area"], "Neck")
        self.assertGreaterEqual(len(analysis["minimal_implementation"]), 3)
        self.assertEqual(len(analysis["experiment_plan"]), 3)
        self.assertIn("mAP", analysis["experiment_plan"][0]["metrics"])
        self.assertIn("尚未核验", analysis["limitations"])

    def test_cache_hash_changes_with_project_idea(self):
        first = analysis_input_hash(self.paper, self.project, "rules-v1")
        changed = {**self.project, "idea": "另一条研究假设"}
        second = analysis_input_hash(self.paper, changed, "rules-v1")

        self.assertNotEqual(first, second)

    def test_extracts_structured_response_text(self):
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"ok": true}'}],
                }
            ]
        }

        self.assertEqual(extract_response_text(response), '{"ok": true}')

    def test_full_text_evidence_increases_grounding(self):
        paper = {
            **self.paper,
            "full_text_json": json.dumps(
                {
                    "status": "verified",
                    "sections": [
                        {
                            "kind": "method",
                            "label": "方法/架构",
                            "page": 4,
                            "text": "Our method routes multi-scale features through adaptive branches.",
                        }
                    ],
                    "code": {
                        "status": "verified_repository",
                        "urls": [{"url": "https://github.com/example/model", "verified": True}],
                    },
                    "limitations": [],
                },
                ensure_ascii=False,
            ),
        }

        analysis = build_rule_analysis(paper, self.project)

        self.assertIn("全文方法证据", analysis["method_summary"])
        self.assertTrue(any("第 4 页" in item for item in analysis["evidence"]))
        self.assertGreater(analysis["confidence"], 72)
        self.assertIn("尚未解析公式", analysis["limitations"])


class EvidenceExtractorTests(unittest.TestCase):
    def test_extracts_method_experiment_and_ablation_sections(self):
        pages = [
            "Introduction. This paper studies remote sensing detection.",
            "Proposed Method. Our method introduces an adaptive scale router and feature fusion module.",
            "Experiments. We evaluate on DOTA. Ablation Study. Removing the router reduces accuracy.",
        ]

        sections = extract_evidence_from_pages(pages)
        kinds = {item["kind"] for item in sections}

        self.assertIn("method", kinds)
        self.assertIn("experiment", kinds)
        self.assertIn("ablation", kinds)
        method = next(item for item in sections if item["kind"] == "method")
        self.assertEqual(method["page"], 2)

    def test_section_heading_wins_over_abstract_mention(self):
        sections = extract_evidence_from_pages(
            [
                "Experiments on four benchmarks show strong performance in the abstract.",
                "V. EXPERIMENTALRESULTS\nWe compare against controlled baselines on DOTA.",
            ]
        )

        experiment = next(item for item in sections if item["kind"] == "experiment")
        self.assertEqual(experiment["page"], 2)
        self.assertEqual(experiment["matched_term"], "EXPERIMENTALRESULTS")

    def test_extracts_and_normalizes_supported_code_urls(self):
        urls = extract_code_urls(
            "Code: https://github.com/Example/ScaleNet). Mirror: https://example.com/not-code"
        )

        self.assertEqual(urls, ["https://github.com/Example/ScaleNet"])

    def test_evidence_hash_changes_with_pdf_version(self):
        first = evidence_input_hash(
            {"pdf_url": "https://arxiv.org/pdf/1", "external_id": "1", "updated_at": "v1"}
        )
        second = evidence_input_hash(
            {"pdf_url": "https://arxiv.org/pdf/1", "external_id": "1", "updated_at": "v2"}
        )

        self.assertNotEqual(first, second)


class ExporterTests(unittest.TestCase):
    def test_exports_full_text_and_deep_analysis_evidence(self):
        paper = {
            "topic_name": "遥感检测",
            "title": "Scale Router",
            "authors": "Author",
            "published_at": "2026-08-01",
            "venue_name": "CVPR",
            "venue_type": "conference",
            "venue_rank": "CCF A",
            "venue_status": "published",
            "venue_source": "arXiv journal_ref",
            "venue_rankings_json": json.dumps(
                [{"system": "CCF", "rank": "A", "label": "CCF A", "year": "2026"}]
            ),
            "doi": "10.1000/example",
            "journal_ref": "Proceedings of CVPR 2026",
            "comments": "Accepted to CVPR 2026",
            "recommendation_score": 80,
            "ranking_score": 82,
            "relevance_tier": "direct",
            "stitchability_score": 85,
            "relevance_score": 90,
            "code_availability_score": 70,
            "material_type": "module",
            "integration_area": "Neck",
            "integration_subtag": "Feature Fusion",
            "stitch_difficulty": "中",
            "stitch_action": "接入尺度路由",
            "evidence_sources": "全文",
            "evidence_quote": "scale-aware routing",
            "summary": "摘要",
            "entry_url": "https://arxiv.org/abs/1",
            "pdf_url": "https://arxiv.org/pdf/1",
            "full_text_status": "verified",
            "full_text_json": json.dumps(
                {
                    "pdf": {"page_count": 10},
                    "sections": [{"label": "方法/架构", "page": 4, "text": "method evidence"}],
                    "code": {
                        "status": "verified_repository",
                        "urls": [{"url": "https://github.com/example/model", "verified": True}],
                    },
                },
                ensure_ascii=False,
            ),
            "deep_analysis_source": "rules",
            "deep_analysis_json": json.dumps(
                {
                    "reusable_module": "尺度路由模块",
                    "project_match": "可接入 FPN",
                    "confidence": 84,
                    "minimal_implementation": ["冻结基线", "接入模块"],
                    "limitations": "尚未运行代码",
                },
                ensure_ascii=False,
            ),
        }

        markdown = papers_to_markdown([paper])
        csv_output = papers_to_csv([paper])

        self.assertIn("第 4 页", markdown)
        self.assertIn("github.com/example/model", markdown)
        self.assertIn("深度缝合分析", markdown)
        self.assertIn("发表源：CVPR", markdown)
        self.assertIn("刊会等级：CCF A", markdown)
        self.assertIn("full_text_pages", csv_output)
        self.assertIn("verified_repository", csv_output)
        self.assertIn("venue_rankings_json", csv_output)


if __name__ == "__main__":
    unittest.main()
