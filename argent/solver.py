"""Thin z3 bridge: satisfiability checks and model extraction."""

import z3

SAT = z3.sat
UNSAT = z3.unsat


def check(constraints, timeout_ms=5000):
    """Solve a constraint set; returns ``(status, solver)``.

    ``status`` is the z3 sentinel ``sat``, ``unsat`` or ``unknown``.
    """
    solver = z3.Solver()
    if timeout_ms:
        solver.set("timeout", timeout_ms)
    solver.add(*constraints)
    return solver.check(), solver


def model_bytes(solver, names):
    """Read named 8-bit symbols out of a model, in declaration order."""
    model = solver.model()
    values = bytearray()
    for name in names:
        expr = z3.BitVec(name, 8)
        value = model.eval(expr, model_completion=True).as_long()
        values.append(value & 0xFF)
    return bytes(values)
