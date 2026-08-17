import unittest

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


if __name__ == "__main__":
    unittest.main()

