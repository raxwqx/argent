"""Argent instruction set: encoding, decoding and formatting.

Layout
------
Every instruction is exactly eight bytes::

    offset 0   opcode      uint8
    offset 1   operand a   uint8
    offset 2   operand b   uint8
    offset 3   operand c   uint8
    offset 4   immediate   uint32 (little endian)

Registers are ``r0``-``r15`` and hold 32-bit words. ``pc`` is an
*instruction index*, not a byte address, so jump targets are simply
indices into the instruction array. That keeps the assembler single pass
and the machine model small enough to reason about by hand.
"""

import struct
from dataclasses import dataclass

OPCODES = {
    "nop": 0x00,
    "movi": 0x01,
    "mov": 0x02,
    "add": 0x03,
    "sub": 0x04,
    "mul": 0x05,
    "xor": 0x06,
    "and": 0x07,
    "or": 0x08,
    "shl": 0x09,
    "shr": 0x0A,
    "load": 0x0B,
    "store": 0x0C,
    "cmp": 0x0D,
    "je": 0x0E,
    "jne": 0x0F,
    "jl": 0x10,
    "jmp": 0x11,
    "halt": 0x12,
    "syscall": 0x13,
    "loadb": 0x14,
}

NAMES = {code: name for name, code in OPCODES.items()}

INSTRUCTION_SIZE = 8
REGISTER_COUNT = 16
WORD_SIZE = 4
WORD_BITS = 32
WORD_MASK = (1 << WORD_BITS) - 1

#: The address the explorer maps symbolic input bytes to.
INPUT_BASE = 0x1000

#: Operand layout per mnemonic: ``(kind, field)`` pairs, in source order.
#: ``kind`` is one of ``reg``, ``imm`` or ``target``.
OPERANDS = {
    "nop": (),
    "halt": (),
    "movi": (("reg", "a"), ("imm", "imm")),
    "mov": (("reg", "a"), ("reg", "b")),
    "add": (("reg", "a"), ("reg", "b"), ("reg", "c")),
    "sub": (("reg", "a"), ("reg", "b"), ("reg", "c")),
    "mul": (("reg", "a"), ("reg", "b"), ("reg", "c")),
    "xor": (("reg", "a"), ("reg", "b"), ("reg", "c")),
    "and": (("reg", "a"), ("reg", "b"), ("reg", "c")),
    "or": (("reg", "a"), ("reg", "b"), ("reg", "c")),
    "shl": (("reg", "a"), ("reg", "b"), ("imm", "imm")),
    "shr": (("reg", "a"), ("reg", "b"), ("imm", "imm")),
    "load": (("reg", "a"), ("reg", "b"), ("imm", "imm")),
    "store": (("reg", "a"), ("reg", "b"), ("imm", "imm")),
    "cmp": (("reg", "a"), ("reg", "b")),
    "je": (("target", "imm"),),
    "jne": (("target", "imm"),),
    "jl": (("target", "imm"),),
    "jmp": (("target", "imm"),),
    "syscall": (("imm", "imm"),),
    "loadb": (("reg", "a"), ("reg", "b"), ("imm", "imm")),
}

#: Backwards friendly alias used by tests and docs.
SIGNATURES = OPERANDS


@dataclass(frozen=True)
class Instruction:
    """A single Argent instruction."""

    op: str
    a: int = 0
    b: int = 0
    c: int = 0
    imm: int = 0

    def encode(self):
        """Encode the instruction into eight bytes."""
        if self.op not in OPCODES:
            raise ValueError(f"unknown opcode: {self.op}")
        return struct.pack(
            "<BBBBI",
            OPCODES[self.op],
            self.a & 0xFF,
            self.b & 0xFF,
            self.c & 0xFF,
            self.imm & WORD_MASK,
        )

    @classmethod
    def decode(cls, data, offset=0):
        """Decode one instruction from a byte buffer."""
        op, a, b, c, imm = struct.unpack_from("<BBBBI", data, offset)
        if op not in NAMES:
            raise ValueError(f"unknown opcode: 0x{op:02x} at offset {offset}")
        return cls(NAMES[op], a, b, c, imm)

    def __str__(self):
        return format_instruction(self)


def _hex(value):
    return f"0x{value & WORD_MASK:x}"


def format_instruction(instr):
    """Render an instruction as a readable assembly line."""
    name = instr.op
    if name in ("nop", "halt"):
        return name
    if name == "movi":
        return f"movi   r{instr.a}, {_hex(instr.imm)}"
    if name == "mov":
        return f"mov    r{instr.a}, r{instr.b}"
    if name in ("add", "sub", "mul", "xor", "and", "or"):
        return f"{name:<6} r{instr.a}, r{instr.b}, r{instr.c}"
    if name in ("shl", "shr"):
        return f"{name:<6} r{instr.a}, r{instr.b}, {instr.imm}"
    if name == "load":
        return f"load   r{instr.a}, r{instr.b}, {_hex(instr.imm)}"
    if name == "loadb":
        return f"loadb  r{instr.a}, r{instr.b}, {_hex(instr.imm)}"
    if name == "store":
        return f"store  r{instr.a}, r{instr.b}, {_hex(instr.imm)}"
    if name == "cmp":
        return f"cmp    r{instr.a}, r{instr.b}"
    if name in ("je", "jne", "jl", "jmp"):
        return f"{name:<6} @{instr.imm}"
    if name == "syscall":
        return f"syscall {instr.imm}"
    return name


def assemble_bytes(instructions):
    """Encode a sequence of instructions."""
    return b"".join(instr.encode() for instr in instructions)


def disassemble_bytes(data):
    """Decode a byte buffer into instructions."""
    if len(data) % INSTRUCTION_SIZE:
        raise ValueError("data length must be a multiple of 8")
    return [
        Instruction.decode(data, offset)
        for offset in range(0, len(data), INSTRUCTION_SIZE)
    ]
