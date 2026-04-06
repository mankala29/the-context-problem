"""
Verification and feedback layer.

After the model produces an answer, we check its quality against a set of
expected facts. If quality is below the threshold, the system flags it for
context retry — this is the feedback loop.

In production this could be:
  - Regex / keyword match (used here)
  - A second LLM call that grades the first answer
  - A human-in-the-loop review queue
  - A structured output validator
"""

from config import settings


class QualityChecker:

    def __init__(self, expected_facts: list, threshold: float = None):
        """
        expected_facts: list of strings that should appear in a correct answer.
        threshold: minimum score (0-1) to pass. Defaults to settings value.
        """
        self.expected_facts = expected_facts
        self.threshold = threshold or settings.quality_threshold

    def check(self, answer: str) -> dict:
        answer_lower = answer.lower()
        found    = [f for f in self.expected_facts if f.lower() in answer_lower]
        missing  = [f for f in self.expected_facts if f.lower() not in answer_lower]
        score    = round(len(found) / max(len(self.expected_facts), 1), 2)
        passed   = score >= self.threshold

        return {
            "score":        score,
            "threshold":    self.threshold,
            "passed":       passed,
            "found_facts":  found,
            "missing_facts": missing,
            "verdict":      "PASS" if passed else "FAIL — retry with better context",
        }
