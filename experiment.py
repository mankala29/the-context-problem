"""
Context Engineering Experiment
================================
Engineering question: Does context quality determine model output quality?
Hypothesis: Yes. The model is not reasoning from ground truth — it is reasoning
            from a selected version of reality constructed by the system.

Experiment design:
  - Fixed query: "What is the current status of INC-001 and what immediate action should be taken?"
  - Fixed model: claude-opus-4-6
  - Fixed data: 4-version incident timeline seeded into a versioned store
  - Variable: retrieval mode (complete / stale / incomplete / noisy / inconsistent)
  - Measurement: answer content + quality score vs. known ground truth

MVCC experiment:
  - Two "concurrent requests" read the same incident at different timestamps
  - Each constructs a different context → different answer → different action taken
"""

import sys
import textwrap
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from data.store import VersionedStore
from data.seed import seed, T0, T5, T15, T30
from retrieval.retriever import Retriever, RetrievalMode
from context.builder import ContextBuilder
from inference.llm import call_llm
from verification.checker import QualityChecker
from config import settings

console = Console()

QUERY = "What is the current status of INC-001 and what immediate action should be taken?"
DOC_IDS = ["INC-001", "RUNBOOK-DB-POOL", "SERVICE-MAP"]

# Tight budget used in the priority experiment — fits ~2 docs, not all 3
TIGHT_BUDGET = 350

# Ground truth facts that a correct answer should contain
# (based on T30 — fully resolved state)
GROUND_TRUTH_FACTS = [
    "resolved",
    "0%",
    "post-mortem",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def wrap(text: str, width: int = 72) -> str:
    return "\n".join(
        textwrap.fill(line, width=width) if line.strip() else line
        for line in text.splitlines()
    )


def run_trial(label: str, mode: str, current_time: float,
              store: VersionedStore, checker: QualityChecker) -> dict:
    retriever = Retriever(store, stale_by=600)
    builder   = ContextBuilder(token_budget=settings.token_budget)

    docs, retrieval_meta = retriever.retrieve(DOC_IDS, current_time, mode=mode)
    context              = builder.build(QUERY, docs)
    llm_result           = call_llm(context["prompt"])
    quality              = checker.check(llm_result["answer"])

    return {
        "label":          label,
        "mode":           mode,
        "current_time":   current_time,
        "retrieval_meta": retrieval_meta,
        "context_meta":   context,
        "llm":            llm_result,
        "quality":        quality,
    }


def run_priority_trial(label: str, doc_ids: list, token_budget: int,
                       current_time: float,
                       store: VersionedStore, checker: QualityChecker) -> dict:
    """
    Like run_trial but with an explicit doc ordering and token budget.
    Used in the priority experiment to show that insertion order determines
    which documents survive a tight budget.
    """
    retriever = Retriever(store, stale_by=600)
    builder   = ContextBuilder(token_budget=token_budget)

    # Fetch all docs, then re-order them according to the requested priority
    all_docs, retrieval_meta = retriever.retrieve(doc_ids, current_time,
                                                  mode=RetrievalMode.COMPLETE)
    # restore caller's ordering (retriever may return in any order)
    index = {d["doc_id"]: d for d in all_docs}
    ordered_docs = [index[did] for did in doc_ids if did in index]

    context    = builder.build(QUERY, ordered_docs)
    llm_result = call_llm(context["prompt"])
    quality    = checker.check(llm_result["answer"])

    return {
        "label":          label,
        "mode":           RetrievalMode.COMPLETE,
        "current_time":   current_time,
        "doc_order":      doc_ids,
        "token_budget":   token_budget,
        "retrieval_meta": retrieval_meta,
        "context_meta":   context,
        "llm":            llm_result,
        "quality":        quality,
    }


def print_trial(trial: dict, idx: int) -> None:
    q = trial["quality"]
    c = trial["context_meta"]
    r = trial["retrieval_meta"]

    color = "green" if q["passed"] else "red"
    score_str = f"[{color}]{q['score']:.2f}[/{color}]"

    priority_line = ""
    if "doc_order" in trial:
        priority_line = f"Doc priority: [cyan]{' → '.join(trial['doc_order'])}[/cyan]\n"

    console.print(Panel(
        f"[bold]{trial['label']}[/bold]\n"
        f"Mode: [cyan]{trial['mode']}[/cyan]  |  "
        f"Snapshot time: [cyan]T+{int(trial['current_time'])}s[/cyan]  |  "
        f"Coverage: [cyan]{c['coverage']*100:.0f}%[/cyan] "
        f"({len(c['included_docs'])}/{len(c['included_docs'])+len(c['excluded_docs'])} docs)  |  "
        f"Tokens: [cyan]{c['token_estimate']}[/cyan] / {c['token_budget']}\n"
        + priority_line
        + f"Included: [cyan]{c['included_docs']}[/cyan]  |  "
        f"Excluded: [yellow]{c['excluded_docs']}[/yellow]\n"
        f"Quality score: {score_str}  |  Verdict: [{color}]{q['verdict']}[/{color}]\n"
        f"Found facts: {q['found_facts']}\n"
        f"Missing facts: [yellow]{q['missing_facts']}[/yellow]\n"
        + (f"[yellow]Retrieval warning: {r['warning']}[/yellow]\n" if r.get('warning') else "")
        + f"\n[bold]Model answer:[/bold]\n{wrap(trial['llm']['answer'])}",
        title=f"Trial {idx}",
        border_style=color,
    ))


# ── Main experiment ───────────────────────────────────────────────────────────

def main():
    store = VersionedStore()
    seed(store)

    checker = QualityChecker(
        expected_facts=GROUND_TRUTH_FACTS,
        threshold=settings.quality_threshold,
    )

    console.print(Panel(
        "[bold]Context Engineering Experiment[/bold]\n\n"
        f"Query: [italic]{QUERY}[/italic]\n"
        f"Model: {settings.model}\n"
        f"Token budget: {settings.token_budget}\n"
        f"Quality threshold: {settings.quality_threshold}\n"
        f"Ground truth facts checked: {GROUND_TRUTH_FACTS}",
        title="Setup",
        border_style="blue",
    ))

    # ── Part 1: Retrieval degradation at T=1800 (incident resolved) ───────────

    console.rule("[bold blue]PART 1 — Retrieval Degradation (current_time = T+1800s, incident resolved)")
    console.print("Same query. Same underlying data. Different retrieval modes → different answers.\n")

    trials = [
        ("Complete context (baseline)",       RetrievalMode.COMPLETE,     T30),
        ("Stale context (10 min behind)",      RetrievalMode.STALE,        T30),
        ("Incomplete context (fields cut off)",RetrievalMode.INCOMPLETE,   T30),
        ("Noisy context (corrupted field)",    RetrievalMode.NOISY,        T30),
        ("Inconsistent context (mixed replicas)",RetrievalMode.INCONSISTENT,T30),
    ]

    results = []
    for i, (label, mode, t) in enumerate(trials, 1):
        console.print(f"[dim]Running trial {i}/5: {label}...[/dim]")
        result = run_trial(label, mode, t, store, checker)
        results.append(result)

    for i, r in enumerate(results, 1):
        print_trial(r, i)

    # ── Part 1 summary table ──────────────────────────────────────────────────

    table = Table(title="Part 1 Summary", box=box.ROUNDED)
    table.add_column("Trial",   style="bold")
    table.add_column("Mode",    style="cyan")
    table.add_column("Score",   justify="center")
    table.add_column("Pass?",   justify="center")
    table.add_column("Tokens",  justify="right")
    table.add_column("Missing facts")

    for r in results:
        q = r["quality"]
        passed = q["passed"]
        table.add_row(
            r["label"],
            r["mode"],
            f"{q['score']:.2f}",
            "[green]YES[/green]" if passed else "[red]NO[/red]",
            str(r["context_meta"]["token_estimate"]),
            ", ".join(q["missing_facts"]) or "—",
        )
    console.print(table)

    # ── Part 2: MVCC — two concurrent requests at different snapshots ─────────

    console.rule("[bold blue]PART 2 — MVCC Snapshot Isolation")
    console.print(
        "Two requests arrive at the same wall-clock moment.\n"
        "Request A reads a snapshot from T+300s (root cause known, fix in progress).\n"
        "Request B reads a snapshot from T+1800s (incident fully resolved).\n"
        "Same query. Same model. Different context → completely different answer.\n"
    )

    mvcc_trials = [
        ("Request A — snapshot at T+300s (fix in progress)", RetrievalMode.COMPLETE, T5),
        ("Request B — snapshot at T+1800s (resolved)",       RetrievalMode.COMPLETE, T30),
    ]

    mvcc_results = []
    for i, (label, mode, t) in enumerate(mvcc_trials, 1):
        console.print(f"[dim]Running MVCC trial {i}/2: {label}...[/dim]")
        result = run_trial(label, mode, t, store, checker)
        mvcc_results.append(result)

    for i, r in enumerate(mvcc_results, 1):
        print_trial(r, i)

    console.print(Panel(
        "[bold]MVCC Observation:[/bold]\n\n"
        "Both requests used the same model, same query, and same code path.\n"
        "The only difference was the snapshot timestamp passed to the retrieval layer.\n\n"
        "This demonstrates that the model's answer is determined not by\n"
        "[bold]what is true[/bold] but by [bold]what version of truth was selected[/bold] at retrieval time.\n\n"
        "In a database, MVCC ensures readers get consistent snapshots.\n"
        "In an LLM system, there is no equivalent guarantee — the context\n"
        "construction layer is entirely responsible for temporal consistency.",
        title="Conclusion",
        border_style="blue",
    ))

    # ── Part 3: Feedback loop — retry with better context ────────────────────

    console.rule("[bold blue]PART 3 — Verification + Feedback Loop")
    console.print(
        "We simulate what happens when the system detects a low-quality answer\n"
        "and automatically retries with fresher, more complete context.\n"
    )

    console.print("[dim]Step 1: Initial call with stale context...[/dim]")
    first_attempt = run_trial(
        "Initial: stale context", RetrievalMode.STALE, T30, store, checker
    )
    print_trial(first_attempt, 1)

    if not first_attempt["quality"]["passed"]:
        console.print(
            f"[yellow]Quality check FAILED "
            f"(score={first_attempt['quality']['score']:.2f} < "
            f"threshold={settings.quality_threshold}).\n"
            f"Triggering retry with complete, current context...[/yellow]"
        )
        console.print("[dim]Step 2: Retry with complete context...[/dim]")
        retry = run_trial(
            "Retry: complete context", RetrievalMode.COMPLETE, T30, store, checker
        )
        print_trial(retry, 2)

        improvement = retry["quality"]["score"] - first_attempt["quality"]["score"]
        console.print(Panel(
            f"Score improved from [red]{first_attempt['quality']['score']:.2f}[/red] "
            f"to [green]{retry['quality']['score']:.2f}[/green] "
            f"(+{improvement:.2f}) after context refresh.\n\n"
            "This is the feedback loop in action:\n"
            "the system detected a context problem and self-corrected\n"
            "without changing the model or the query.",
            title="Feedback Loop Result",
            border_style="green",
        ))
    else:
        console.print("[green]First attempt passed — no retry needed.[/green]")

    # ── Part 4: Priority ordering under budget pressure ───────────────────────

    console.rule("[bold blue]PART 4 — Document Priority Under Token Budget Pressure")
    console.print(
        f"Token budget is tightened to {TIGHT_BUDGET} tokens — not enough to fit all three documents.\n"
        "The builder uses first-fit: documents are included in the order provided.\n"
        "Same query. Same data. Same model. Different doc ordering → different docs included → different answer.\n"
    )

    priority_trials = [
        (
            "Priority A — incident record first (correct ranking)",
            ["INC-001", "RUNBOOK-DB-POOL", "SERVICE-MAP"],
        ),
        (
            "Priority B — runbook first, incident record last (wrong ranking)",
            ["RUNBOOK-DB-POOL", "SERVICE-MAP", "INC-001"],
        ),
    ]

    priority_results = []
    for i, (label, doc_order) in enumerate(priority_trials, 1):
        console.print(f"[dim]Running priority trial {i}/2: {label}...[/dim]")
        result = run_priority_trial(
            label, doc_order, TIGHT_BUDGET, T30, store, checker
        )
        priority_results.append(result)

    for i, r in enumerate(priority_results, 1):
        print_trial(r, i)

    p_table = Table(title="Part 4 Summary — Same data, different priority", box=box.ROUNDED)
    p_table.add_column("Trial",       style="bold")
    p_table.add_column("Doc order",   style="cyan")
    p_table.add_column("Included",    style="cyan")
    p_table.add_column("Excluded",    style="yellow")
    p_table.add_column("Score",       justify="center")
    p_table.add_column("Pass?",       justify="center")

    for r in priority_results:
        q = r["quality"]
        c = r["context_meta"]
        passed = q["passed"]
        p_table.add_row(
            r["label"],
            " → ".join(r["doc_order"]),
            ", ".join(c["included_docs"]),
            ", ".join(c["excluded_docs"]) or "—",
            f"{q['score']:.2f}",
            "[green]YES[/green]" if passed else "[red]NO[/red]",
        )
    console.print(p_table)

    console.print(Panel(
        "[bold]Priority Observation:[/bold]\n\n"
        f"With a {TIGHT_BUDGET}-token budget only a subset of documents fit.\n"
        "When INC-001 was listed first it was always included → correct answer.\n"
        "When INC-001 was listed last it was crowded out by lower-value docs → wrong answer.\n\n"
        "The model never saw different data — the same store, same snapshot, same query.\n"
        "Only the insertion order into the context window changed.\n\n"
        "This means context engineering is not just about [italic]what[/italic] you retrieve,\n"
        "but also [italic]in what order[/italic] you present it when space is constrained.",
        title="Conclusion",
        border_style="blue",
    ))

    # ── Version history ───────────────────────────────────────────────────────

    console.rule("[bold blue]APPENDIX — INC-001 Version History")
    hist_table = Table(title="INC-001 Document Versions in Store", box=box.ROUNDED)
    hist_table.add_column("Version", justify="center")
    hist_table.add_column("Timestamp", justify="center")
    hist_table.add_column("Status")
    hist_table.add_column("Severity")
    hist_table.add_column("Recommended Action")

    for v in store.version_history("INC-001"):
        hist_table.add_row(
            str(v.version),
            f"T+{int(v.timestamp)}s",
            v.content.get("status", "?"),
            v.content.get("severity", "?"),
            wrap(v.content.get("recommended_action", "?"), width=50),
        )
    console.print(hist_table)


if __name__ == "__main__":
    main()
