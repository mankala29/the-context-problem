"""
Dependency graph visualizer.

Renders the codebase as a directed graph:
  - Node size     : proportional to PageRank (hubs are larger)
  - Node color    : red = hub (top 30% by PageRank), blue = standard node
  - Edge direction: A → B means A imports from B (data flows B → A)
  - Labels        : shortened file paths for readability

Output: saved as a PNG file.
"""

import os
import networkx as nx
import matplotlib
matplotlib.use("Agg")   # non-interactive backend — works without a display
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from graph.store import CodeGraph


def shorten_label(path: str) -> str:
    """e.g. data/store.py → data/\nstore.py for readability."""
    parts = path.replace("\\", "/").split("/")
    if len(parts) > 1:
        return "/".join(parts[:-1]) + "/\n" + parts[-1]
    return path


def visualize(code_graph: CodeGraph, output_path: str = "codebase_graph.png",
              title: str = "Codebase Dependency Graph") -> str:
    G  = code_graph.graph
    pr = code_graph.pagerank()

    if len(G.nodes()) == 0:
        print("Graph is empty — nothing to visualize.")
        return output_path

    max_pr    = max(pr.values()) if pr else 1
    threshold = max_pr * 0.30   # top 30% by PageRank = hub

    node_sizes  = [max(300, pr.get(n, 0) / max_pr * 3000) for n in G.nodes()]
    node_colors = ["#e74c3c" if pr.get(n, 0) >= threshold else "#3498db"
                   for n in G.nodes()]

    labels = {n: shorten_label(n) for n in G.nodes()}

    pos = nx.spring_layout(G, seed=42, k=2.5)

    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#1a1a2e")

    nx.draw_networkx_edges(
        G, pos, ax=ax,
        edge_color="#7f8c8d", arrows=True,
        arrowstyle="-|>", arrowsize=15,
        connectionstyle="arc3,rad=0.1", width=1.2, alpha=0.7,
    )
    nx.draw_networkx_nodes(
        G, pos, ax=ax,
        node_size=node_sizes, node_color=node_colors, alpha=0.95,
    )
    nx.draw_networkx_labels(
        G, pos, labels=labels, ax=ax,
        font_size=7, font_color="white", font_weight="bold",
    )

    hub_patch  = mpatches.Patch(color="#e74c3c", label="Hub — high centrality (top 30% PageRank)")
    leaf_patch = mpatches.Patch(color="#3498db", label="Standard node")
    ax.legend(handles=[hub_patch, leaf_patch], loc="upper left",
              facecolor="#2c2c54", labelcolor="white", framealpha=0.8)

    ax.set_title(title + "\n(node size = PageRank centrality · edge = import dependency)",
                 color="white", fontsize=11, pad=15)
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()

    return output_path
