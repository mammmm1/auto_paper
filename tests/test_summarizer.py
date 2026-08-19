import unittest

from auto_paper.materializer import build_material_card, build_project_query
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
        self.assertIn("跨领域", card["filter_reason"])


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


if __name__ == "__main__":
    unittest.main()
