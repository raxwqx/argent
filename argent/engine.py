"""Symbolic exploration.

The explorer walks the program path by path. At a conditional branch the
guard is simplified; if it is concretely true or false the path simply
continues, otherwise the state forks and each side is checked for
satisfiability with z3 before it is queued. Infeasible paths are dropped
before they cost any instructions.

Every solution is re-executed concretely before it is reported, so a
returned input is a witnessed input, not a model that merely looks right.
"""

import time
from dataclasses import dataclass

import z3

from .machine import INPUT_BASE, State, Unsupported, byte, execute_step
from .solver import SAT, UNSAT, check, model_bytes


@dataclass
class Result:
    """Outcome of one exploration run."""

    solved: bool
    input: bytes = b""
    paths: int = 0
    forks: int = 0
    pruned: int = 0
    steps: int = 0
    solver_calls: int = 0
    elapsed: float = 0.0
    reason: str = "target not reached"
    verified: bool = False

    def as_dict(self):
        return {
            "solved": self.solved,
            "input_hex": self.input.hex(),
            "input_ascii": _printable(self.input),
            "paths": self.paths,
            "forks": self.forks,
            "pruned": self.pruned,
            "steps": self.steps,
            "solver_calls": self.solver_calls,
            "elapsed": round(self.elapsed, 4),
            "reason": self.reason,
            "verified": self.verified,
        }


class Explorer:
    """Breadth-free, depth-first symbolic executor."""

    def __init__(
        self,
        program,
        target=None,
        avoid=(),
        input_size=4,
        input_base=INPUT_BASE,
        max_paths=4096,
        max_steps=200_000,
        solver_timeout_ms=5000,
        deadline=None,
    ):
        """
        ``target`` is an instruction index to reach, or ``None`` to accept
        any halt with a non-zero exit code. ``avoid`` is a set of indices
        that invalidate a path.
        """
        self.program = program
        self.target = target
        self.avoid = set(avoid)
        self.input_size = input_size
        self.input_base = input_base
        self.max_paths = max_paths
        self.max_steps = max_steps
        self.solver_timeout_ms = solver_timeout_ms
        self.deadline = deadline
        self.names = []

    # -- public API ---------------------------------------------------

    def run(self):
        """Explore until the goal is reached or the limits are hit."""
        started = time.perf_counter()

        root = State()
        self.names = root.map_input(self.input_size, self.input_base)

        stack = [root]
        stats = {"paths": 0, "forks": 0, "pruned": 0, "steps": 0, "solver_calls": 0}
        reason = "target not reached"

        while stack:
            if self.deadline is not None and time.perf_counter() > self.deadline:
                reason = "time budget exhausted"
                break

            state = stack.pop()
            stats["paths"] += 1

            if stats["paths"] > self.max_paths:
                reason = "path budget exhausted"
                break

            outcome = self._advance(state)
            stats["steps"] += state.steps

            kind = outcome[0]

            if kind == "solved":
                status, solver = check(state.constraints, self.solver_timeout_ms)
                stats["solver_calls"] += 1
                if status != SAT:
                    continue

                candidate = model_bytes(solver, self.names)
                ok = verify(
                    self.program,
                    candidate,
                    target=self.target,
                    avoid=self.avoid,
                    input_base=self.input_base,
                    max_steps=self.max_steps,
                )
                if not ok:
                    reason = "model failed concrete replay"
                    continue

                return Result(
                    solved=True,
                    input=candidate,
                    verified=True,
                    elapsed=time.perf_counter() - started,
                    reason="goal reached",
                    **stats,
                )

            if kind == "dead":
                continue

            if kind == "budget":
                reason = outcome[1]
                break

            _, condition, target = outcome
            simplified = z3.simplify(condition)

            if z3.is_true(simplified):
                state.pc = target
                stack.append(state)
                continue

            if z3.is_false(simplified):
                stack.append(state)
                continue

            stats["forks"] += 1
            for taken in (True, False):
                child = state.fork()
                if taken:
                    child.pc = target
                    child.constraints.append(simplified)
                else:
                    child.constraints.append(z3.Not(simplified))

                status, _ = check(child.constraints, self.solver_timeout_ms)
                stats["solver_calls"] += 1
                if status == SAT:
                    stack.append(child)
                elif status == UNSAT:
                    stats["pruned"] += 1

        return Result(
            solved=False,
            elapsed=time.perf_counter() - started,
            reason=reason,
            **stats,
        )

    # -- internals ----------------------------------------------------

    def _advance(self, state):
        """Run until the next branch, halt, goal or budget limit."""
        while True:
            if self.deadline is not None and time.perf_counter() > self.deadline:
                return ("budget", "time budget exhausted")

            if state.steps > self.max_steps:
                return ("budget", "step budget exhausted")

            if state.pc in self.avoid:
                return ("dead",)

            if self.target is None:
                pass
            elif state.pc == self.target:
                return ("solved",)

            try:
                action, *payload = execute_step(state, self.program)
            except Unsupported:
                return ("dead",)

            if action == "halt":
                code = payload[0] if payload else 0
                if self.target is None and code:
                    return ("solved",)
                return ("dead",)

            if action == "branch":
                return ("branch", payload[0], payload[1])


def _printable(data):
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def run_concrete(program, data, input_base=INPUT_BASE, max_steps=200_000):
    """Execute a program with concrete input bytes.

    Returns a dict with ``halted``, ``code``, ``visited`` and ``steps``.
    """
    state = State()
    for offset, value in enumerate(data):
        state.mem[input_base + offset] = byte(value)

    visited = []

    while state.steps < max_steps:
        visited.append(state.pc)

        if not 0 <= state.pc < len(program.instructions):
            return {
                "halted": True,
                "code": 0,
                "visited": visited,
                "steps": state.steps,
            }

        action, *payload = execute_step(state, program)

        if action == "halt":
            return {
                "halted": True,
                "code": payload[0] if payload else 0,
                "visited": visited,
                "steps": state.steps,
            }

        if action == "branch":
            condition, target = payload
            if z3.is_true(z3.simplify(condition)):
                state.pc = target

    return {"halted": False, "code": None, "visited": visited, "steps": state.steps}


def verify(program, data, target=None, avoid=(), input_base=INPUT_BASE,
           max_steps=200_000):
    """Replay ``data`` concretely and confirm the goal is met."""
    trace = run_concrete(program, data, input_base=input_base, max_steps=max_steps)
    if not trace["halted"]:
        return False
    if target is None:
        return bool(trace["code"])
    if any(pc in set(avoid) for pc in trace["visited"]):
        return False
    return target in trace["visited"]
