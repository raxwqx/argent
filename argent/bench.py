"""Benchmark harness for the generated corpus."""

import time
from dataclasses import dataclass

from .corpus import build_corpus
from .engine import Explorer


@dataclass
class Case:
    """One solved (or failed) challenge."""

    name: str
    family: str
    solved: bool
    verified: bool
    elapsed_ms: float
    paths: int
    forks: int
    pruned: int
    steps: int
    solver_calls: int
    input_hex: str
    reason: str

    def as_dict(self):
        return {
            "name": self.name,
            "family": self.family,
            "solved": self.solved,
            "verified": self.verified,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "paths": self.paths,
            "forks": self.forks,
            "pruned": self.pruned,
            "steps": self.steps,
            "solver_calls": self.solver_calls,
            "input_hex": self.input_hex,
            "reason": self.reason,
        }


def run_case(crackme, max_paths=4096, max_steps=200_000, solver_timeout_ms=5000):
    """Solve a single challenge and time it."""
    program = crackme.program()
    started = time.perf_counter()
    result = Explorer(
        program,
        target=program.label(crackme.target),
        input_size=crackme.input_size,
        max_paths=max_paths,
        max_steps=max_steps,
        solver_timeout_ms=solver_timeout_ms,
    ).run()
    elapsed = (time.perf_counter() - started) * 1000.0

    return Case(
        name=crackme.name,
        family=crackme.family,
        solved=result.solved,
        verified=result.verified,
        elapsed_ms=elapsed,
        paths=result.paths,
        forks=result.forks,
        pruned=result.pruned,
        steps=result.steps,
        solver_calls=result.solver_calls,
        input_hex=result.input.hex(),
        reason=result.reason,
    )


def run_bench(per_family=None, seed=1337, **kwargs):
    """Run the whole corpus; returns a list of :class:`Case`."""
    return [run_case(item, **kwargs) for item in build_corpus(per_family, seed)]


def summarise(cases):
    """Aggregate per family and overall."""
    families = []
    order = []
    buckets = {}

    for case in cases:
        if case.family not in buckets:
            buckets[case.family] = []
            order.append(case.family)
        buckets[case.family].append(case)

    for family in order:
        group = buckets[family]
        solved = [c for c in group if c.solved]
        families.append(
            {
                "family": family,
                "cases": len(group),
                "solved": len(solved),
                "verified": sum(1 for c in group if c.verified),
                "mean_ms": _mean([c.elapsed_ms for c in group]),
                "max_ms": max(c.elapsed_ms for c in group),
                "mean_paths": _mean([c.paths for c in group]),
                "mean_forks": _mean([c.forks for c in group]),
                "pruned": sum(c.pruned for c in group),
            }
        )

    total = {
        "cases": len(cases),
        "solved": sum(1 for c in cases if c.solved),
        "verified": sum(1 for c in cases if c.verified),
        "mean_ms": _mean([c.elapsed_ms for c in cases]),
        "max_ms": max((c.elapsed_ms for c in cases), default=0.0),
        "mean_paths": _mean([c.paths for c in cases]),
        "mean_forks": _mean([c.forks for c in cases]),
        "pruned": sum(c.pruned for c in cases),
        "solver_calls": sum(c.solver_calls for c in cases),
        "steps": sum(c.steps for c in cases),
    }

    return {"families": families, "total": total, "cases": [c.as_dict() for c in cases]}


def render_table(summary):
    """Render a fixed-width table, no colour, no decoration."""
    head = (
        f"{'family':<12}{'n':>4}{'solved':>8}{'verified':>10}"
        f"{'mean ms':>10}{'max ms':>10}{'paths':>8}{'forks':>7}{'pruned':>8}"
    )
    rule = "-" * len(head)
    lines = [head, rule]

    for row in summary["families"]:
        lines.append(
            f"{row['family']:<12}{row['cases']:>4}{row['solved']:>8}"
            f"{row['verified']:>10}{row['mean_ms']:>10.1f}{row['max_ms']:>10.1f}"
            f"{row['mean_paths']:>8.1f}{row['mean_forks']:>7.1f}{row['pruned']:>8}"
        )

    total = summary["total"]
    lines.append(rule)
    lines.append(
        f"{'total':<12}{total['cases']:>4}{total['solved']:>8}"
        f"{total['verified']:>10}{total['mean_ms']:>10.1f}{total['max_ms']:>10.1f}"
        f"{total['mean_paths']:>8.1f}{total['mean_forks']:>7.1f}{total['pruned']:>8}"
    )
    return "\n".join(lines)


def _mean(values):
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)
