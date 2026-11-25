"""Argent assembler: turns ``.sasm`` text into a :class:`Program`.

Syntax
------
::

    # comment
start:
    movi  r1, 0x1000
    load  r2, r1, 0
    movi  r3, 0x41
    cmp   r2, r3
    jne   fail
    jmp   win
fail:
    movi  r0, 0
    syscall 1
win:
    movi  r0, 1
    syscall 1

Labels resolve to absolute *instruction indices*. Both ``jmp win`` and
``jmp @12`` are accepted. Comments start with ``#`` or ``;``.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .isa import OPERANDS, WORD_MASK, Instruction

REGISTER_RE = re.compile(r"^r(\d{1,2})$")


class AssemblyError(ValueError):
    """A syntax or resolution error in assembly source."""


@dataclass
class Program:
    """An executable Argent program."""

    instructions: list
    labels: dict = field(default_factory=dict)
    source: str = ""

    def __len__(self):
        return len(self.instructions)

    def label(self, name):
        """Resolve a label to an instruction index."""
        try:
            return self.labels[name]
        except KeyError:
            raise AssemblyError(f"unknown label: {name}") from None

    def hexdump(self):
        """Return the encoded program as a hex string."""
        return b"".join(ins.encode() for ins in self.instructions).hex()

    def to_bytes(self):
        return b"".join(ins.encode() for ins in self.instructions)


def assemble(text):
    """Assemble source text into a :class:`Program`."""
    if not isinstance(text, str):
        raise AssemblyError("source must be a string")

    labels = {}
    body = []

    for number, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw).strip()
        if not line:
            continue

        if line.endswith(":"):
            name = line[:-1].strip()
            if not name:
                raise AssemblyError(f"line {number}: empty label name")
            if name in labels:
                raise AssemblyError(f"line {number}: duplicate label: {name}")
            labels[name] = len(body)
            continue

        body.append((number, line))

    instructions = [
        _parse_instruction(number, line, labels) for number, line in body
    ]
    return Program(instructions=instructions, labels=labels, source=text)


def assemble_file(path):
    """Read and assemble a file."""
    return assemble(Path(path).read_text(encoding="utf-8"))


def _strip_comment(line):
    for marker in ("#", ";"):
        index = line.find(marker)
        if index >= 0:
            line = line[:index]
    return line


def _parse_instruction(number, line, labels):
    parts = line.replace(",", " ").split()
    mnemonic = parts[0].lower()

    if mnemonic not in OPERANDS:
        raise AssemblyError(f"line {number}: unknown mnemonic: {mnemonic}")

    layout = OPERANDS[mnemonic]
    operands = parts[1:]
    if len(operands) != len(layout):
        raise AssemblyError(
            f"line {number}: {mnemonic} expects {len(layout)} operand(s), "
            f"got {len(operands)}"
        )

    values = {"a": 0, "b": 0, "c": 0, "imm": 0}
    for (kind, slot), operand in zip(layout, operands):
        if kind == "reg":
            values[slot] = _parse_register(number, operand)
        elif kind == "imm":
            values[slot] = _parse_immediate(number, operand, labels)
        elif kind == "target":
            values[slot] = _parse_target(number, operand, labels)

    return Instruction(mnemonic, **values)


def _parse_register(number, token):
    match = REGISTER_RE.match(token.lower())
    if not match:
        raise AssemblyError(f"line {number}: invalid register: {token}")
    index = int(match.group(1))
    if index >= 16:
        raise AssemblyError(f"line {number}: registers are r0-r15: {token}")
    return index


def _parse_immediate(number, token, labels):
    token = token.strip()
    if token.startswith("@"):
        token = token[1:]
    try:
        return int(token, 0) & WORD_MASK
    except ValueError:
        if token in labels:
            return labels[token]
        raise AssemblyError(f"line {number}: invalid immediate: {token}") from None


def _parse_target(number, token, labels):
    token = token.strip()
    if token.startswith("@"):
        token = token[1:]
        try:
            return int(token, 0) & WORD_MASK
        except ValueError:
            raise AssemblyError(f"line {number}: invalid target: {token}") from None

    if token in labels:
        return labels[token]
    try:
        return int(token, 0) & WORD_MASK
    except ValueError:
        raise AssemblyError(f"line {number}: unknown label: {token}") from None
