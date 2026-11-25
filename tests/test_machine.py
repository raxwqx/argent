import pytest

from argent.asm import assemble
from argent.machine import INPUT_BASE, State, Unsupported, execute_step, word


def run(source, steps=1, data=b""):
    program = assemble(source)
    state = State()
    for offset, value in enumerate(data):
        state.mem[INPUT_BASE + offset] = word(value)
    for _ in range(steps):
        action = execute_step(state, program)
    return state, action


def value(state, index):
    return state.regs[index].as_long()


def test_movi_and_mov():
    state, _ = run("movi r1, 0x1234\nmov r2, r1\n", steps=2)
    assert value(state, 1) == 0x1234
    assert value(state, 2) == 0x1234


def test_arithmetic_wraps_at_32_bits():
    state, _ = run("movi r1, 0xffffffff\nmovi r2, 2\nadd r3, r1, r2\n", steps=3)
    assert value(state, 3) == 1


def test_sub_mul_and_bitwise():
    state, _ = run(
        "movi r1, 7\nmovi r2, 3\n"
        "sub r3, r1, r2\nmul r4, r1, r2\n"
        "xor r5, r1, r2\nand r6, r1, r2\nor r7, r1, r2\n",
        steps=7,
    )
    assert value(state, 3) == 4
    assert value(state, 4) == 21
    assert value(state, 5) == 4
    assert value(state, 6) == 3
    assert value(state, 7) == 7


def test_shifts():
    state, _ = run("movi r1, 1\nshl r2, r1, 4\nmovi r3, 0x80\nshr r4, r3, 3\n", steps=4)
    assert value(state, 2) == 16
    assert value(state, 4) == 16


def test_loadb_zero_extends():
    program = assemble("movi r1, 0x1000\nloadb r2, r1, 0\n")
    state = State()
    state.mem[INPUT_BASE] = word(0xFF)
    for _ in range(2):
        execute_step(state, program)
    assert value(state, 2) == 0xFF


def test_load_and_store_are_little_endian():
    program = assemble(
        "movi r1, 0x2000\nmovi r2, 0x11223344\n"
        "store r2, r1, 0\nload r3, r1, 0\n"
    )
    state = State()
    for _ in range(4):
        execute_step(state, program)
    assert value(state, 3) == 0x11223344
    assert state.mem[0x2000].as_long() == 0x44
    assert state.mem[0x2003].as_long() == 0x11


def test_store_of_symbolic_value_is_unsupported():
    program = assemble("movi r1, 0x2000\nstore r2, r1, 0\n")
    state = State()
    import z3

    state.regs[2] = z3.BitVec("secret", 32)
    execute_step(state, program)
    with pytest.raises(Unsupported):
        execute_step(state, program)


def test_symbolic_address_is_unsupported():
    import z3

    program = assemble("loadb r2, r1, 0\n")
    state = State()
    state.regs[1] = z3.BitVec("ptr", 32)
    with pytest.raises(Unsupported):
        execute_step(state, program)


def test_cmp_and_branch_flags():
    state, action = run("movi r1, 5\nmovi r2, 5\ncmp r1, r2\nje 9\n", steps=4)
    assert action[0] == "branch"
    assert action[2] == 9
    assert state.pc == 4  # fall-through pc, target is applied by the engine


def test_jne_and_jl():
    _, action = run("movi r1, 1\nmovi r2, 2\ncmp r1, r2\njl 7\n", steps=4)
    assert action[0] == "branch"

    _, action = run("movi r1, 2\nmovi r2, 1\ncmp r1, r2\njl 7\n", steps=4)
    import z3

    assert z3.is_false(action[1])


def test_branch_without_cmp_is_unsupported():
    program = assemble("je 4\n")
    with pytest.raises(Unsupported, match="without a preceding cmp"):
        execute_step(State(), program)


def test_syscall_one_halts_with_r0():
    _, action = run("movi r0, 7\nsyscall 1\n", steps=2)
    assert action == ("halt", 7)


def test_unknown_syscall_is_a_nop():
    state, action = run("syscall 9\n", steps=1)
    assert action[0] == "next"
    assert state.pc == 1


def test_pc_out_of_range_halts():
    program = assemble("nop\n")
    state = State(pc=5)
    assert execute_step(state, program) == ("halt", 0)


def test_jump_sets_pc():
    state, action = run("jmp 0\n", steps=1)
    assert action[0] == "jump"
    assert state.pc == 0


def test_fork_is_independent():
    state = State()
    state.regs[0] = word(1)
    clone = state.fork()
    clone.regs[0] = word(2)
    clone.constraints.append(True)
    assert value(state, 0) == 1
    assert value(clone, 0) == 2
    assert state.constraints == []
