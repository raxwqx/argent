"""Deterministic crackme corpus.

Programs are generated from a seed, so the benchmark is reproducible
without checking in a pile of generated source files. The secrets used to
build a program are thrown away: a solution is only accepted if the
explorer's input survives a concrete replay of the program itself.
"""

import random
from dataclasses import dataclass
from pathlib import Path

from .asm import assemble
from .isa import INPUT_BASE

BASE = INPUT_BASE

_HEADER = """\
# {name}
# family: {family}
# input: {size} byte(s) at {base}
"""


@dataclass(frozen=True)
class Crackme:
    """A generated challenge."""

    name: str
    family: str
    source: str
    input_size: int
    target: str = "win"

    def program(self):
        return assemble(self.source)

    def goal_index(self):
        return self.program().label(self.target)


def _wrap(name, family, source, size):
    header = _HEADER.format(name=name, family=family, size=size, base=hex(BASE))
    return header + source.lstrip("\n")


def _tail():
    return """
fail:
    movi  r0, 0
    syscall 1
win:
    movi  r0, 1
    syscall 1
"""


def _eq(secret):
    return f"""
start:
    movi  r1, {hex(BASE)}
    loadb r2, r1, 0
    movi  r3, {secret[0]:#x}
    cmp   r2, r3
    jne   fail
    jmp   win
""" + _tail()


def _xor(secret):
    key = 0x5A
    return f"""
start:
    movi  r1, {hex(BASE)}
    loadb r2, r1, 0
    movi  r3, {key:#x}
    xor   r2, r2, r3
    movi  r3, {secret[0] ^ key:#x}
    cmp   r2, r3
    jne   fail
    jmp   win
""" + _tail()


def _arith(secret):
    a, b = 3, 7
    want = ((secret[0] * a) + b) & 0xFF
    return f"""
start:
    movi  r1, {hex(BASE)}
    loadb r2, r1, 0
    movi  r3, {a}
    mul   r2, r2, r3
    movi  r3, {b}
    add   r2, r2, r3
    movi  r3, 0xff
    and   r2, r2, r3
    movi  r3, {want:#x}
    cmp   r2, r3
    jne   fail
    jmp   win
""" + _tail()


def _chain(secret):
    keys = [0x13, 0x37, 0x5B, 0x71]
    lines = ["", "start:", f"    movi  r1, {hex(BASE)}"]
    for index, value in enumerate(secret):
        lines += [
            f"    loadb r2, r1, {index}",
            f"    movi  r3, {keys[index]:#x}",
            "    xor   r2, r2, r3",
            f"    movi  r3, {value ^ keys[index]:#x}",
            "    cmp   r2, r3",
            "    jne   fail",
        ]
    lines += ["    jmp   win"]
    return "\n".join(lines) + "\n" + _tail()


def _sum(secret):
    total = sum(secret) & 0xFFFFFFFF
    return f"""
start:
    movi  r1, {hex(BASE)}
    movi  r2, 0
    movi  r4, 0
    movi  r5, {len(secret)}
loop:
    cmp   r4, r5
    je    check
    add   r6, r1, r4
    loadb r7, r6, 0
    add   r2, r2, r7
    movi  r8, 1
    add   r4, r4, r8
    jmp   loop
check:
    movi  r9, {total:#x}
    cmp   r2, r9
    jne   fail
    jmp   win
""" + _tail()


def _hash(secret):
    acc = 5381
    for value in secret:
        acc = ((acc * 33) + value) & 0xFFFFFFFF
    return f"""
start:
    movi  r1, {hex(BASE)}
    movi  r2, 5381
    movi  r4, 0
    movi  r5, {len(secret)}
    movi  r10, 33
loop:
    cmp   r4, r5
    je    check
    add   r6, r1, r4
    loadb r7, r6, 0
    mul   r2, r2, r10
    add   r2, r2, r7
    movi  r8, 1
    add   r4, r4, r8
    jmp   loop
check:
    movi  r9, {acc:#x}
    cmp   r2, r9
    jne   fail
    jmp   win
""" + _tail()


def _maze(secret):
    return f"""
start:
    movi  r1, {hex(BASE)}
    loadb r2, r1, 0
    movi  r3, {secret[0]:#x}
    cmp   r2, r3
    je    gate1
    movi  r3, {secret[0] ^ 0xFF:#x}
    cmp   r2, r3
    je    trap
    jmp   fail
trap:
    loadb r2, r1, 1
    movi  r3, 0x7f
    cmp   r2, r3
    je    fail
    jmp   fail
gate1:
    loadb r2, r1, 1
    movi  r3, {secret[1]:#x}
    cmp   r2, r3
    jne   fail
    loadb r2, r1, 2
    movi  r3, {secret[2]:#x}
    cmp   r2, r3
    jne   fail
    jmp   win
""" + _tail()


def _impossible(secret):
    return """
start:
    movi  r1, {base}
    loadb r2, r1, 0
    movi  r3, {k:#x}
    cmp   r2, r3
    jne   second
    jmp   fail
second:
    movi  r3, {k:#x}
    cmp   r2, r3
    je    win
    jmp   fail
""".format(base=hex(BASE), k=secret[0]) + _tail()


FAMILIES = {
    "eq": (_eq, 1, 8),
    "xor": (_xor, 1, 8),
    "arith": (_arith, 1, 8),
    "chain": (_chain, 4, 8),
    "sum": (_sum, 6, 8),
    "hash": (_hash, 6, 6),
    "maze": (_maze, 3, 8),
    "impossible": (_impossible, 1, 4),
}


def build_corpus(per_family=None, seed=1337):
    """Build the deterministic corpus.

    ``per_family`` may be an int applied to every family or a mapping of
    family name to count. Returns a list of :class:`Crackme`.
    """
    rng = random.Random(seed)
    items = []

    for family, (builder, size, default) in FAMILIES.items():
        if per_family is None:
            count = default
        elif isinstance(per_family, dict):
            count = per_family.get(family, default)
        else:
            count = per_family

        for index in range(count):
            secret = bytes(rng.randrange(0x20, 0x7F) for _ in range(size))
            name = f"{family}-{index:02d}"
            items.append(
                Crackme(
                    name=name,
                    family=family,
                    source=_wrap(name, family, builder(secret), size),
                    input_size=size,
                )
            )

    return items


def write_corpus(directory, per_family=None, seed=1337):
    """Materialise the corpus as ``.sasm`` files; returns written paths."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    for crackme in build_corpus(per_family=per_family, seed=seed):
        path = target / f"{crackme.name}.sasm"
        path.write_text(crackme.source, encoding="utf-8")
        paths.append(path)
    return paths
