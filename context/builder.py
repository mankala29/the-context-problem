"""
Context construction layer.

Responsibilities:
  1. Format raw documents into readable text
  2. Enforce a token budget — drop lower-priority docs if over limit
  3. Track exactly what was included and what was excluded
  4. Expose this metadata so the experiment can reason about coverage

Token counting is approximate (1 token ≈ 4 chars).
In production you would use tiktoken or the API's count_tokens endpoint.
"""

SYSTEM_PROMPT = """\
You are an incident response assistant for an engineering team.
Answer based ONLY on the context provided below.
Do not add information that is not present in the context.
Be specific: state the severity, current status, and exact recommended action.
If the context is missing information, say so explicitly.\
"""


def count_tokens(text: str) -> int:
    """Rough approximation: 1 token ≈ 4 characters."""
    return max(1, len(text) // 4)


class ContextBuilder:

    def __init__(self, token_budget: int = 600):
        self.token_budget = token_budget

    def build(self, query: str, documents: list) -> dict:
        """
        Construct the final prompt within the token budget.

        Priority order: documents are included in the order they are provided.
        If a document would push the prompt over budget it is dropped entirely
        (no partial inclusion — partial context is often worse than none).

        Returns a dict with:
          prompt          — the full string to send to the model
          included_docs   — list of doc_ids that made it in
          excluded_docs   — list of doc_ids that were dropped
          token_estimate  — estimated tokens in the prompt
          coverage        — fraction of provided docs that were included
        """
        overhead = count_tokens(SYSTEM_PROMPT) + count_tokens(query) + 60
        remaining = self.token_budget - overhead

        included = []
        excluded = []

        for doc in documents:
            text = self._format_doc(doc)
            cost = count_tokens(text)
            if cost <= remaining:
                included.append(doc)
                remaining -= cost
            else:
                excluded.append(doc.get("doc_id", "?"))

        context_block = "\n\n".join(self._format_doc(d) for d in included)

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"--- CONTEXT START ---\n"
            f"{context_block}\n"
            f"--- CONTEXT END ---\n\n"
            f"Question: {query}"
        )

        used = self.token_budget - remaining
        return {
            "prompt": prompt,
            "included_docs": [d.get("doc_id") for d in included],
            "excluded_docs": excluded,
            "token_estimate": used,
            "token_budget": self.token_budget,
            "coverage": round(len(included) / max(len(documents), 1), 2),
        }

    @staticmethod
    def _format_doc(doc: dict) -> str:
        lines = [f"[{doc.get('doc_id', 'unknown')} | v{doc.get('version', '?')} | "
                 f"age={doc.get('data_age_seconds', '?')}s]"]
        skip = {"doc_id", "version", "data_timestamp"}
        for k, v in doc.items():
            if k not in skip:
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)
