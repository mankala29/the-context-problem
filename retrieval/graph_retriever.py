"""
Graph-aware retriever.

Two retrieval strategies, both returning the same document format
so they can be fed directly into the existing ContextBuilder:

  FLAT  : files ordered alphabetically — no structural awareness.
          Simulates a naive RAG system that treats code as a bag of files.

  GRAPH : files ordered by PageRank centrality — hubs surface first.
          Ensures the most architecturally important files claim their
          slot in the context window before budget is exhausted.

The document format matches what ContextBuilder.build() expects,
so experiment 2 can reuse the same pipeline as experiment 1.
"""

import os
from graph.store import CodeGraph
from graph.analyzer import GraphAnalyzer


class GraphRetriever:

    def __init__(self, code_graph: CodeGraph, base_dir: str):
        self.cg       = code_graph
        self.base_dir = base_dir
        self.analyzer = GraphAnalyzer(code_graph)

    # ── Retrieval modes ───────────────────────────────────────────────────────

    def retrieve_flat(self, doc_ids: list) -> tuple:
        """Alphabetical order — no graph awareness."""
        ordered = sorted(doc_ids)
        docs    = [self._build_doc(d) for d in ordered if d in self.cg._summaries]
        meta    = {"mode": "flat", "order": ordered,
                   "note": "alphabetical — no structural ranking"}
        return docs, meta

    def retrieve_graph(self, doc_ids: list) -> tuple:
        """PageRank-ranked order — hubs first."""
        ordered = self.analyzer.rank_docs(
            [d for d in doc_ids if d in self.cg._summaries]
        )
        docs = [self._build_doc(d) for d in ordered]
        pr   = self.analyzer.pagerank()
        meta = {
            "mode":    "graph",
            "order":   ordered,
            "scores":  {d: round(pr.get(d, 0), 4) for d in ordered},
            "note":    "PageRank centrality — architectural hubs first",
        }
        return docs, meta

    # ── Document builder ──────────────────────────────────────────────────────

    def _build_doc(self, doc_id: str) -> dict:
        """
        Convert a parsed file summary into the format ContextBuilder expects.
        Uses the module docstring + class/function names as the document body
        — compact enough to fit multiple files in the token budget.
        """
        info  = self.cg.summary(doc_id)
        pr    = self.analyzer.pagerank()

        body_parts = []
        if info.get("docstring"):
            body_parts.append(info["docstring"].strip())
        if info.get("classes"):
            body_parts.append("classes: " + ", ".join(info["classes"]))
        if info.get("functions"):
            body_parts.append("functions: " + ", ".join(info["functions"]))
        imports = info.get("imports", [])
        if imports:
            body_parts.append("imports_from: " + ", ".join(imports))

        return {
            "doc_id":           doc_id,
            "version":          1,
            "data_age_seconds": 0,
            "pagerank_score":   round(pr.get(doc_id, 0), 4),
            "summary":          "\n".join(body_parts) if body_parts else "(no docstring)",
        }
