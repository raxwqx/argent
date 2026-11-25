# Design notes

This document describes what Argent actually implements. Every claim below is
visible in `argent/` and exercised by the test suite.

---

## 1. Scope

Argent is a symbolic executor for a synthetic 32-bit RISC-like ISA. It exists to
make the whole pipeline readable in one sitting: assembler, interpreter, path
explorer, solver bridge, and a concrete replay check.

Non-goals, deliberately:

- no ELF or PE loading, no real syscalls;
- no symbolic memory addressing;
- no path merging, no coverage-guided search;
- no floating point, no exceptions, no interrupts.

---

## 2. Instruction encoding

Every instruction is eight bytes, little endian:

```
offset  size  field
0       1     opcode
1       1     a
2       1     b
3       1     c
4       4     immediate
```

Registers are `r0`-`r15` and hold 32-bit words. `pc` is an **instruction
index**, not a byte address, so branches store indices and the assembler can
resolve labels in a single pass. An index outside the program array is treated
as a halt with code 0.

| mnemonic | operands | semantics |
|---|---|---|
| `movi` | `rd, imm` | `rd = imm` |
| `mov` | `rd, rs` | `rd = rs` |
| `add` / `sub` / `mul` | `rd, rs, rt` | wrapping 32-bit arithmetic |
| `xor` / `and` / `or` | `rd, rs, rt` | bitwise |
| `shl` / `shr` | `rd, rs, imm` | shift by immediate |
| `load` | `rd, rs, imm` | little-endian 32-bit load from `rs + imm` |
| `loadb` | `rd, rs, imm` | zero-extended byte load from `rs + imm` |
| `store` | `rs, rb, imm` | little-endian 32-bit store to `rb + imm` |
| `cmp` | `ra, rb` | sets `zf = (ra == rb)`, `sf = (ra < rb)` |
| `je` / `jne` / `jl` | `target` | conditional branch on the flags |
| `jmp` | `target` | unconditional branch |
| `syscall` | `n` | `n = 1` halts with `r0`; anything else is a no-op |
| `nop`, `halt` | - | no operation, halt with code 0 |

`sf` is an unsigned comparison (`ULT`). There is no greater-than branch; write
`cmp b, a` and use `jl`.

---

## 3. Machine state

A `State` holds:

```
pc           instruction index
regs[16]     z3 bit-vectors, 32 bits
mem          dict[int, BitVec(8)]
zf, sf       cached flags from the last cmp
constraints  path condition
steps        instructions retired on this path
```

Concrete values are `BitVecVal` and symbolic values are `BitVec`, so the same
interpreter runs both modes. Input bytes are placed at `0x1000` as named 8-bit
symbols `in_0`, `in_1`, ... and read with `loadb`.

Memory is a sparse byte map. Loads and stores through a non-constant address
raise `Unsupported`; storing a symbolic value raises `Unsupported` as well. The
explorer drops such paths instead of guessing.

---

## 4. Exploration

```
root  = state with symbolic input bytes
stack = [root]

while stack and within budgets:
    state = stack.pop()
    loop:
        if pc == goal:  solve constraints -> candidate
        step(state) -> action

        action == halt      -> dead (or solved for target=None and code != 0)
        action == dead      -> drop
        action == branch    -> guard = simplify(condition)
                               guard is true  -> pc = target, continue
                               guard is false -> continue
                               otherwise      -> fork:
                                   taken     : pc = target, add guard
                                   not taken : add !guard
                                   keep each side only if z3 says sat

    candidate = model of state.constraints
    accept only if run_concrete(candidate) reaches the goal
```

Properties that follow from this loop:

- **Soundness by construction.** A reported input has been replayed
  concretely; the model alone is never trusted. `verify()` drives the same
  `execute_step` used by the explorer.
- **Pruning happens before work.** Each fork is checked for satisfiability
  before it is queued, which is why the deliberately contradictory
  `impossible` family costs four paths and zero solutions.
- **Search order is DFS.** Memory use is proportional to path depth, not to
  the number of paths. There is no global cache, so a loop that is unrolled
  `n` times costs `O(n)` interpreter steps per path, not `O(1)`.
- **Budgets are explicit.** `max_paths`, `max_steps`, `solver_timeout_ms` and
  an optional wall-clock `deadline` produce a `Result` with a reason string
  instead of an exception.

### Cost

For the loop families the dominant cost is nonlinear bit-vector arithmetic
inside z3 (`mul` on 32-bit words), not the interpreter. The `hash` family
therefore sets the upper bound of the benchmark at roughly half a second per
program on the machine used to produce `bench/results.json`.

---

## 5. Verification contract

`solve` returns success only when all of the following hold:

1. a model exists for the accumulated path constraints;
2. replaying that model through `run_concrete` halts;
3. the goal index appears in the replay trace, and no `avoid` index does;
   or, when `target is None`, the exit code is non-zero.

If replay disagrees with the model, the result is `solved=False` with
`reason="model failed concrete replay"`. The benchmark counts solved and
verified separately for that reason; in the shipped corpus the two numbers are
equal, which is the only state of affairs worth publishing.

---

## 6. Corpus

Programs are generated from a seed and never checked in. Each family is a
different shape of constraint:

| family | input | shape |
|---|---|---|
| `eq` | 1 | single equality |
| `xor` | 1 | one-byte XOR gate |
| `arith` | 1 | multiply, add, mask |
| `chain` | 4 | four sequential XOR comparisons |
| `sum` | 6 | loop over bytes, compare the sum |
| `hash` | 6 | djb2-style loop, nonlinear in the bytes |
| `maze` | 3 | decoy branch that leads to a trap |
| `impossible` | 1 | contradictory guards; must stay unsolved |

The `impossible` family is part of the benchmark on purpose. An engine that
"solves" it has a bug, and the table makes that visible.

---

## 7. What would come next

- symbolic addresses via a memory model with `Select`/`Store`;
- concrete-symbolic concretisation for `store`;
- path merging at join points;
- instruction-level taint to shrink expressions before solving;
- a real loader for a toy binary format.

These are listed as future work, not as features. None of them are implemented.
