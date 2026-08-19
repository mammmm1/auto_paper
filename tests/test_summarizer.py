import json
import unittest

from auto_paper.deep_analyzer import (
    analysis_input_hash,
    build_rule_analysis,
    extract_response_text,
)
from auto_paper.materializer import build_material_card, build_project_query
from auto_paper.profile_validator import validate_project_profile
from auto_paper.quality import build_quality_metrics, rank_materials
from auto_paper.recommender import score_paper
from auto_paper.route_builder import build_experiment_route
from auto_paper.summarizer import summarize_paper


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


if __name__ == "__main__":
    unittest.main()
