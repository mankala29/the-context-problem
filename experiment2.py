"""
Experiment 2 — Graph-Aware RAG vs Flat RAG
==========================================
Theme: Data Loops

A data loop is a system where outputs are evaluated and fed back
as inputs to improve the next iteration. The quality of each loop
iteration depends entirely on what information enters it.

In this experiment the "codebase" is the context-lab itself.
We ask the model to explain the system's foundational data layer.

The data loop path in this system is:
  store.py → retriever.py → builder.py → llm.py → checker.py
             └─────────────────────────────────────┘ (feedback retry)

Graph RAG surfaces store.py first because it has the highest in-degree
(3 files import it). Flat RAG surfaces it late or not at all — it gets
crowded out by alphabetically earlier files in the token budget.

Connection to Experiment 1 — Part 4:
  Part 4 proved that insertion order determines which documents survive
  a tight token budget. This experiment shows that graph centrality is
  the principled solution to that ordering problem.
"""

import os
import sys
import textwrap
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from graph.store import CodeGraph
from graph.analyzer import GraphAnalyzer
from graph.visualizer import visualize
from retrieval.graph_retriever import GraphRetriever
from context.builder import ContextBuilder
from inference.llm import call_llm
from verification.checker import QualityChecker
from config import settings

console = Console()

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
TIGHT_BUDGET = 450   # tight enough that not all files fit

QUERY = (
    "What is the foundational data component in this system, "
    "how does data flow through it, and which file should an engineer "
    "read first to understand the entire pipeline?"
)

# Ground truth: a correct answer (with store.py in context) will mention
# the versioned store, snapshots, and the MVCC pattern.
GROUND_TRUTH_FACTS = ["VersionedStore", "snapshot", "version"]

# Files that represent the core pipeline — what we ask the retriever to rank
PIPELINE_FILES = [
    "config.py",
    "context/builder.py",
    "data/seed.py",
    "data/store.py",
    "experiment.py",
    "inference/llm.py",
    "retrieval/retriever.py",
    "verification/checker.py",
]


def wrap(text: str, width: int = 72) -> str:
    return "\n".join(
        textwrap.fill(line, width=width) if line.strip() else line
        for line in text.splitlines()
    )


def run_trial(label: str, docs: list, meta: dict,
              checker: QualityChecker) -> dict:
    builder    = ContextBuilder(token_budget=TIGHT_BUDGET)
    context    = builder.build(QUERY, docs)
    llm_result = call_llm(context["prompt"])
    quality    = checker.check(llm_result["answer"])
    return {
        "label":         label,
        "retrieval_meta": meta,
        "context_meta":  context,
        "llm":           llm_result,
        "quality":       quality,
    }


def print_trial(trial: dict, idx: int) -> None:
    q     = trial["quality"]
    c     = trial["context_meta"]
    m     = trial["retrieval_meta"]
    color = "green" if q["passed"] else "red"

    order_str = " → ".join(m.get("order", []))

    console.print(Panel(
        f"[bold]{trial['label']}[/bold]\n"
        f"Retrieval mode: [cyan]{m['mode']}[/cyan]  |  "
        f"Note: [dim]{m['note']}[/dim]\n"
        f"Doc order: [cyan]{order_str}[/cyan]\n"
        f"Included: [cyan]{c['included_docs']}[/cyan]  |  "
        f"Excluded: [yellow]{c['excluded_docs']}[/yellow]\n"
        f"Coverage: [cyan]{c['coverage']*100:.0f}%[/cyan]  |  "
        f"Tokens: [cyan]{c['token_estimate']}[/cyan] / {c['token_budget']}\n"
        f"Quality score: [{color}]{q['score']:.2f}[/{color}]  |  "
        f"Verdict: [{color}]{q['verdict']}[/{color}]\n"
        f"Found facts: {q['found_facts']}\n"
        f"Missing facts: [yellow]{q['missing_facts']}[/yellow]\n"
        f"\n[bold]Model answer:[/bold]\n{wrap(trial['llm']['answer'])}",
        title=f"Trial {idx}",
        border_style=color,
    ))


def main():
    # ── Build the code graph ──────────────────────────────────────────────────

    console.print(Panel(
        "[bold]Experiment 2 — Graph-Aware RAG vs Flat RAG[/bold]\n\n"
        f"Query: [italic]{QUERY}[/italic]\n"
        f"Model: {settings.model}\n"
        f"Token budget: {TIGHT_BUDGET} (tight — not all files will fit)\n"
        f"Target codebase: [cyan]{BASE_DIR}[/cyan]\n"
        f"Ground truth facts: {GROUND_TRUTH_FACTS}\n\n"
        "[dim]Theme: Data Loops — the graph reveals the data flow path;\n"
        "graph-aware retrieval surfaces the loop's origin first.[/dim]",
        title="Setup",
        border_style="blue",
    ))

    console.print("[dim]Building code graph...[/dim]")
    cg = CodeGraph()
    cg.build(BASE_DIR, exclude=["experiment.py", "experiment2.py"])

    analyzer  = GraphAnalyzer(cg)
    retriever = GraphRetriever(cg, BASE_DIR)
    checker   = QualityChecker(
        expected_facts=GROUND_TRUTH_FACTS,
        threshold=settings.quality_threshold,
    )

    # ── Hub analysis ──────────────────────────────────────────────────────────

    console.rule("[bold blue]GRAPH ANALYSIS — Hub Detection")
    console.print(analyzer.hub_report())
    console.print()

    # Data loop path
    loop_path = cg.find_data_loop_path("retrieval/retriever.py", "verification/checker.py")
    if loop_path:
        console.print(
            f"[bold]Data loop path detected:[/bold] "
            + " → ".join(f"[cyan]{p}[/cyan]" for p in loop_path)
        )
    console.print()

    # ── Visualization ─────────────────────────────────────────────────────────

    console.print("[dim]Generating dependency graph visualization...[/dim]")
    img_path = visualize(
        cg,
        output_path=os.path.join(BASE_DIR, "codebase_graph.png"),
        title="The Context Problem — Codebase Dependency Graph",
    )
    console.print(f"[green]Graph saved → {img_path}[/green]\n")

    # ── Retrieval trials ──────────────────────────────────────────────────────

    console.rule("[bold blue]TRIAL 1 — Flat RAG (alphabetical order)")
    console.print(
        "Files retrieved in alphabetical order — no graph awareness.\n"
        "Under a tight token budget, late-alphabetical files get crowded out.\n"
    )
    flat_docs, flat_meta = retriever.retrieve_flat(PIPELINE_FILES)
    console.print("[dim]Calling model with flat context...[/dim]")
    flat_result = run_trial("Flat RAG — alphabetical", flat_docs, flat_meta, checker)
    print_trial(flat_result, 1)

    console.rule("[bold blue]TRIAL 2 — Graph RAG (PageRank-ranked order)")
    console.print(
        "Files retrieved ranked by PageRank centrality — hubs first.\n"
        "The most architecturally critical file (data/store.py) is guaranteed\n"
        "a slot in the context window before budget is exhausted.\n"
    )
    graph_docs, graph_meta = retriever.retrieve_graph(PIPELINE_FILES)
    console.print("[dim]Calling model with graph-ranked context...[/dim]")
    graph_result = run_trial("Graph RAG — PageRank ranked", graph_docs, graph_meta, checker)
    print_trial(graph_result, 2)

    # ── Summary table ─────────────────────────────────────────────────────────

    console.rule("[bold blue]SUMMARY")

    table = Table(title="Experiment 2 — Flat vs Graph RAG", box=box.ROUNDED)
    table.add_column("Retrieval",    style="bold")
    table.add_column("Doc order",    style="cyan")
    table.add_column("Included",     style="cyan")
    table.add_column("Excluded",     style="yellow")
    table.add_column("Score",        justify="center")
    table.add_column("Pass?",        justify="center")
    table.add_column("Missing facts")

    for r in [flat_result, graph_result]:
        q = r["quality"]
        c = r["context_meta"]
        m = r["retrieval_meta"]
        table.add_row(
            m["mode"],
            " → ".join(m["order"][:3]) + ("..." if len(m["order"]) > 3 else ""),
            ", ".join(c["included_docs"]),
            ", ".join(c["excluded_docs"]) or "—",
            f"{q['score']:.2f}",
            "[green]YES[/green]" if q["passed"] else "[red]NO[/red]",
            ", ".join(q["missing_facts"]) or "—",
        )
    console.print(table)

    # ── Connection to experiment 1 ────────────────────────────────────────────

    console.print(Panel(
        "[bold]Connection to Experiment 1 — Part 4:[/bold]\n\n"
        "Part 4 proved that under token budget pressure, insertion order\n"
        "determines which documents survive — and therefore determines the answer.\n\n"
        "Experiment 2 shows the principled solution:\n"
        "[bold]use the dependency graph to rank documents by centrality[/bold],\n"
        "so the most architecturally important files always claim their slot first.\n\n"
        "[bold]The data loop connection:[/bold]\n"
        "The graph makes the data loop path explicit:\n"
        "  store → retriever → builder → llm → checker → (retry) → retriever\n\n"
        "Graph RAG doesn't just improve retrieval — it surfaces the origin of\n"
        "the data loop (store.py) so the model understands the full flow.\n"
        "Flat RAG retrieves files without knowing their role in the loop.",
        title="Conclusion",
        border_style="blue",
    ))

    console.print(Panel(
        f"[green]Dependency graph saved:[/green] {img_path}\n\n"
        "Share this visualization with your article — it shows:\n"
        "  · Red nodes  = architectural hubs (high PageRank)\n"
        "  · Blue nodes = standard nodes\n"
        "  · Node size  = centrality score\n"
        "  · Edges      = import dependencies (data flow direction)",
        title="Visualization",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
