"""
Graph analysis layer.

Computes centrality metrics and surfaces architectural insights:
  - Which nodes are hubs (high PageRank / high in-degree)
  - Which nodes are leaves (nothing depends on them)
  - The data loop path through the system
"""

from graph.store import CodeGraph


class GraphAnalyzer:

    def __init__(self, code_graph: CodeGraph):
        self.cg       = code_graph
        self._pagerank = None   # cached

    def pagerank(self) -> dict:
        if self._pagerank is None:
            self._pagerank = self.cg.pagerank()
        return self._pagerank

    def ranked_nodes(self) -> list:
        """All nodes sorted by PageRank descending."""
        pr = self.pagerank()
        return sorted(pr.items(), key=lambda x: x[1], reverse=True)

    def hubs(self, top_n: int = 3) -> list:
        return self.ranked_nodes()[:top_n]

    def leaves(self) -> list:
        """Nodes with in-degree 0 — nothing depends on them."""
        in_deg = self.cg.in_degree()
        return [n for n, d in in_deg.items() if d == 0]

    def centrality_score(self, node: str) -> float:
        return self.pagerank().get(node, 0.0)

    def rank_docs(self, doc_ids: list) -> list:
        """
        Given a list of doc_ids, return them sorted by PageRank descending.
        This is the core ranking function for graph-aware retrieval.
        """
        pr = self.pagerank()
        return sorted(doc_ids, key=lambda d: pr.get(d, 0.0), reverse=True)

    def hub_report(self) -> str:
        lines = ["Hub Analysis (by PageRank centrality):"]
        in_deg = self.cg.in_degree()
        for node, score in self.hubs(top_n=5):
            deps = self.cg.dependents_of(node)
            lines.append(
                f"  {node:<35} score={score:.4f}  "
                f"depended on by {in_deg[node]} file(s): {deps}"
            )
        return "\n".join(lines)
