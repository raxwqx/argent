"""Machine state and instruction semantics.

Register and memory values are z3 bit-vectors. A concrete word is a
``BitVecVal``, a symbolic word is a ``BitVec``; the same interpreter
therefore serves both normal execution and symbolic exploration.
"""

import z3

from .isa import INPUT_BASE, WORD_BITS, WORD_MASK, WORD_SIZE

__all__ = [
    "INPUT_BASE",
    "State",
    "Unsupported",
    "byte",
    "execute_step",
    "word",
]

BYTE_BITS = 8


class Unsupported(Exception):
    """A state the explorer cannot handle (symbolic pointer arithmetic)."""


def word(value):
    """Concretise a Python int as a 32-bit bit-vector."""
    return z3.BitVecVal(value & WORD_MASK, WORD_BITS)


def byte(value):
    """Concretise a Python int as an 8-bit bit-vector."""
    return z3.BitVecVal(value & 0xFF, BYTE_BITS)


class State:
    """One execution path: registers, memory, flags, constraints."""

    __slots__ = ("pc", "regs", "mem", "zf", "sf", "constraints", "steps")

    def __init__(self, pc=0, regs=None, mem=None, constraints=None):
        self.pc = pc
        self.regs = regs if regs is not None else [word(0) for _ in range(16)]
        self.mem = mem if mem is not None else {}
        self.zf = None
        self.sf = None
        self.constraints = constraints if constraints is not None else []
        self.steps = 0

    def fork(self):
        """Return an independent copy, used when a branch forks the path."""
        clone = State(
            pc=self.pc,
            regs=list(self.regs),
            mem=dict(self.mem),
            constraints=list(self.constraints),
        )
        clone.zf = self.zf
        clone.sf = self.sf
        clone.steps = self.steps
        return clone

    def read_word(self, address):
        """Read four bytes little endian."""
        if not z3.is_bv_value(address):
            raise Unsupported("load through a symbolic address")
        base = address.as_long()
        chunks = [self.mem.get(base + offset, byte(0)) for offset in range(WORD_SIZE)]
        return z3.simplify(z3.Concat(chunks[3], chunks[2], chunks[1], chunks[0]))

    def read_byte(self, address):
        """Read one byte, zero extended to a word."""
        if not z3.is_bv_value(address):
            raise Unsupported("loadb through a symbolic address")
        raw = self.mem.get(address.as_long(), byte(0))
        return z3.simplify(z3.ZeroExt(WORD_BITS - BYTE_BITS, raw))

    def write_word(self, address, value):
        """Write four bytes little endian."""
        if not z3.is_bv_value(address):
            raise Unsupported("store through a symbolic address")
        if not z3.is_bv_value(value):
            raise Unsupported("store of a symbolic value")
        base = address.as_long()
        raw = value.as_long() & WORD_MASK
        for offset in range(WORD_SIZE):
            self.mem[base + offset] = byte((raw >> (8 * offset)) & 0xFF)

    def map_input(self, count, base=INPUT_BASE, prefix="in"):
        """Place ``count`` symbolic bytes and return their symbol names."""
        names = []
        for offset in range(count):
            name = f"{prefix}_{offset}"
            self.mem[base + offset] = z3.BitVec(name, BYTE_BITS)
            names.append(name)
        return names


def execute_step(state, program):
    """Execute one instruction.

    Returns an action tuple:

    * ``("next", None)`` - pc advanced
    * ``("jump", target)`` - unconditional jump (pc already set)
    * ``("branch", condition, target)`` - conditional jump not yet decided
    * ``("halt", code)`` - program stopped with an exit code
    """
    if not 0 <= state.pc < len(program.instructions):
        return ("halt", 0)

    instr = program.instructions[state.pc]
    op = instr.op
    regs = state.regs
    state.steps += 1

    if op == "nop":
        state.pc += 1
        return ("next", None)

    if op == "halt":
        return ("halt", 0)

    if op == "movi":
        regs[instr.a] = word(instr.imm)
        state.pc += 1
        return ("next", None)

    if op == "mov":
        regs[instr.a] = regs[instr.b]
        state.pc += 1
        return ("next", None)

    if op in ("add", "sub", "mul"):
        left, right = regs[instr.b], regs[instr.c]
        result = {
            "add": left + right,
            "sub": left - right,
            "mul": left * right,
        }[op]
        regs[instr.a] = z3.simplify(result)
        state.pc += 1
        return ("next", None)

    if op in ("xor", "and", "or"):
        left, right = regs[instr.b], regs[instr.c]
        result = {
            "xor": left ^ right,
            "and": left & right,
            "or": left | right,
        }[op]
        regs[instr.a] = z3.simplify(result)
        state.pc += 1
        return ("next", None)

    if op == "shl":
        regs[instr.a] = z3.simplify(regs[instr.b] << instr.imm)
        state.pc += 1
        return ("next", None)

    if op == "shr":
        regs[instr.a] = z3.simplify(z3.LShR(regs[instr.b], instr.imm))
        state.pc += 1
        return ("next", None)

    if op == "load":
        address = z3.simplify(regs[instr.b] + word(instr.imm))
        regs[instr.a] = state.read_word(address)
        state.pc += 1
        return ("next", None)

    if op == "loadb":
        address = z3.simplify(regs[instr.b] + word(instr.imm))
        regs[instr.a] = state.read_byte(address)
        state.pc += 1
        return ("next", None)

    if op == "store":
        address = z3.simplify(regs[instr.b] + word(instr.imm))
        state.write_word(address, regs[instr.a])
        state.pc += 1
        return ("next", None)

    if op == "cmp":
        state.zf = z3.simplify(regs[instr.a] == regs[instr.b])
        state.sf = z3.simplify(regs[instr.a] < regs[instr.b])
        state.pc += 1
        return ("next", None)

    if op in ("je", "jne", "jl"):
        if state.zf is None:
            raise Unsupported(f"{op} without a preceding cmp")

        if op == "je":
            condition = state.zf
        elif op == "jne":
            condition = z3.Not(state.zf)
        else:
            condition = state.sf

        state.pc += 1
        return ("branch", z3.simplify(condition), instr.imm)

    if op == "jmp":
        state.pc = instr.imm
        return ("jump", instr.imm)

    if op == "syscall":
        if instr.imm == 1:
            code = regs[0]
            return ("halt", code.as_long() if z3.is_bv_value(code) else 1)
        state.pc += 1
        return ("next", None)

    raise Unsupported(f"unknown instruction: {op}")
