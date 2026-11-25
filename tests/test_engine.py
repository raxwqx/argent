import time

import pytest

from argent.asm import assemble
from argent.corpus import build_corpus
from argent.engine import Explorer, Result, run_concrete, verify


def crackme(family, index=0):
    items = build_corpus(per_family={family: index + 1})
    return next(item for item in items if item.name == f"{family}-{index:02d}")


def solve(family, index=0, **kwargs):
    item = crackme(family, index)
    program = item.program()
    explorer = Explorer(
        program,
        target=program.label(item.target),
        input_size=item.input_size,
        **kwargs,
    )
    return item, program, explorer.run()


@pytest.mark.parametrize("family", ["eq", "xor", "arith"])
def test_solves_single_byte_families(family):
    item, program, result = solve(family)
    assert result.solved
    assert result.verified
    assert len(result.input) == item.input_size
    assert verify(program, result.input, target=program.label(item.target))


def test_solves_chain_of_four_bytes():
    item, program, result = solve("chain")
    assert result.solved
    assert len(result.input) == 4
    assert result.forks >= 3
    assert verify(program, result.input, target=program.label("win"))


def test_solves_sum_loop():
    item, program, result = solve("sum")
    assert result.solved
    assert verify(program, result.input, target=program.label("win"))


def test_solves_maze_with_dead_ends():
    item, program, result = solve("maze")
    assert result.solved
    assert verify(program, result.input, target=program.label("win"))


def test_solves_nonlinear_hash():
    item, program, result = solve("hash", solver_timeout_ms=30000)
    assert result.solved
    assert verify(program, result.input, target=program.label("win"))


def test_impossible_program_is_proved_infeasible():
    item, program, result = solve("impossible")
    assert not result.solved
    assert result.pruned >= 1
    assert result.reason == "target not reached"


def test_verify_rejects_wrong_input():
    item, program, _ = solve("eq")
    target = program.label("win")
    assert verify(program, b"\x00", target=target) is False


def test_target_none_accepts_nonzero_exit():
    program = assemble(
        """
start:
    movi  r1, 0x1000
    loadb r2, r1, 0
    movi  r3, 0x7f
    cmp   r2, r3
    je    win
    movi  r0, 0
    syscall 1
win:
    movi  r0, 1
    syscall 1
"""
    )
    result = Explorer(program, target=None, input_size=1).run()
    assert result.solved
    assert result.input == b"\x7f"


def test_avoid_prevents_solution():
    item, program, _ = solve("eq")
    result = Explorer(
        program,
        target=program.label("win"),
        avoid=[program.label("win")],
        input_size=1,
    ).run()
    assert not result.solved


def test_step_budget_is_reported():
    item = crackme("sum")
    program = item.program()
    result = Explorer(
        program,
        target=program.label("win"),
        input_size=item.input_size,
        max_steps=3,
    ).run()
    assert not result.solved
    assert "step budget" in result.reason


def test_time_budget_is_reported():
    item = crackme("sum")
    program = item.program()
    result = Explorer(
        program,
        target=program.label("win"),
        input_size=item.input_size,
        deadline=time.perf_counter() - 1,
    ).run()
    assert not result.solved
    assert "time budget" in result.reason


def test_path_budget_is_reported():
    item = crackme("chain")
    program = item.program()
    result = Explorer(
        program,
        target=program.label("win"),
        input_size=item.input_size,
        max_paths=0,
    ).run()
    assert not result.solved
    assert "path budget" in result.reason


def test_unsupported_memory_access_drops_the_path():
    program = assemble(
        "movi r1, 0x1000\nloadb r2, r1, 0\nloadb r3, r2, 0\njmp 0\n"
    )
    result = Explorer(program, target=3, input_size=1).run()
    assert not result.solved
    assert result.reason == "target not reached"


def test_run_concrete_reports_exit_code():
    program = assemble("movi r0, 1\nsyscall 1\n")
    trace = run_concrete(program, b"")
    assert trace["halted"] is True
    assert trace["code"] == 1


def test_run_concrete_respects_step_limit():
    program = assemble("jmp 0\n")
    trace = run_concrete(program, b"", max_steps=10)
    assert trace["halted"] is False
    assert trace["steps"] == 10


def test_result_as_dict_contains_report_fields():
    item, _, result = solve("eq")
    payload = result.as_dict()
    assert payload["solved"] is True
    assert payload["verified"] is True
    assert payload["input_hex"] == result.input.hex()
    assert set(payload) >= {
        "paths", "forks", "pruned", "steps", "solver_calls", "elapsed", "reason",
    }


def test_result_defaults():
    result = Result(solved=False)
    assert result.input == b""
    assert result.as_dict()["input_ascii"] == ""
