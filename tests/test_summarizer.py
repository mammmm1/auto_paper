import unittest

from auto_paper.materializer import build_material_card, build_project_query
from auto_paper.recommender import score_paper
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
        query = build_project_query({"keywords": "remote sensing, small object"})

        self.assertIn("cat:cs.CV", query)
        self.assertIn("remote", query)


if __name__ == "__main__":
    unittest.main()
