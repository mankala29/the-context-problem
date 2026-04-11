"""
Networkx-backed code graph.

Nodes  : Python files (relative paths)
Edges  : directed dependency — A → B means A imports from B
                               (A depends on B; B is upstream of A)

In-degree of a node = number of files that depend on it.
High in-degree = architectural hub.
"""

import networkx as nx
from graph.parser import parse_file, collect_python_files


class CodeGraph:

    def __init__(self):
        self.graph    = nx.DiGraph()
        self._summaries: dict[str, dict] = {}   # doc_id → parsed file info

    def build(self, base_dir: str, exclude: list = None) -> None:
        """Parse all Python files under base_dir and construct the graph."""
        files = collect_python_files(base_dir, exclude=exclude)
        for file_path in files:
            info = parse_file(file_path, base_dir)
            doc_id = info["doc_id"]
            self._summaries[doc_id] = info
            self.graph.add_node(doc_id)
            for dep in info["imports"]:
                self.graph.add_edge(doc_id, dep)   # A → B: A depends on B

    # ── Queries ───────────────────────────────────────────────────────────────

    def pagerank(self) -> dict:
        return nx.pagerank(self.graph)

    def in_degree(self) -> dict:
        return dict(self.graph.in_degree())

    def hubs(self, top_n: int = 5) -> list:
        """Return top_n nodes ranked by PageRank (most architecturally central)."""
        scores = self.pagerank()
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def dependents_of(self, node: str) -> list:
        """Files that depend ON this node (predecessors in the import graph)."""
        return list(self.graph.predecessors(node))

    def dependencies_of(self, node: str) -> list:
        """Files this node depends on (successors in the import graph)."""
        return list(self.graph.successors(node))

    def summary(self, doc_id: str) -> dict:
        return self._summaries.get(doc_id, {})

    def all_nodes(self) -> list:
        return list(self.graph.nodes())

    # ── Data loop path ────────────────────────────────────────────────────────

    def find_data_loop_path(self, start: str, end: str) -> list:
        """
        Find the shortest dependency path between two nodes.
        Used to surface the data loop in experiment 2.
        """
        try:
            return nx.shortest_path(self.graph, start, end)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []
