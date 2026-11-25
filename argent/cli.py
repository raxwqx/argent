"""Command line interface for Argent."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .asm import AssemblyError, assemble_file
from .bench import render_table, run_bench, summarise
from .corpus import write_corpus
from .engine import Explorer, run_concrete
from .isa import disassemble_bytes


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except AssemblyError as error:
        print(f"assembly error: {error}", file=sys.stderr)
        return 2
    except FileNotFoundError as error:
        print(f"file not found: {error.filename}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="argent",
        description="Symbolic execution for the Argent ISA.",
    )
    parser.add_argument("--version", action="version", version=f"argent {__version__}")
    subs = parser.add_subparsers(dest="command", required=True)

    solve = subs.add_parser("solve", help="recover an input that reaches a goal")
    solve.add_argument("path", help="assembly source (.sasm)")
    solve.add_argument("-n", "--input-size", type=int, default=4,
                       help="number of symbolic input bytes (default: 4)")
    solve.add_argument("-t", "--target", default=None,
                       help="goal label or @index (default: 'win' if present)")
    solve.add_argument("-a", "--avoid", action="append", default=[],
                       help="label that invalidates a path (repeatable)")
    solve.add_argument("--max-paths", type=int, default=4096)
    solve.add_argument("--max-steps", type=int, default=200_000)
    solve.add_argument("--timeout", type=float, default=None,
                       help="wall-clock budget in seconds")
    solve.add_argument("--json", action="store_true")
    solve.set_defaults(handler=_cmd_solve)

    run = subs.add_parser("run", help="execute a program with concrete input")
    run.add_argument("path")
    group = run.add_mutually_exclusive_group(required=True)
    group.add_argument("--hex", dest="hex_input", help="input bytes as hex")
    group.add_argument("--text", dest="text_input", help="input bytes as text")
    run.add_argument("--json", action="store_true")
    run.set_defaults(handler=_cmd_run)

    disasm = subs.add_parser("disasm", help="disassemble a program")
    disasm.add_argument("path")
    disasm.set_defaults(handler=_cmd_disasm)

    corpus = subs.add_parser("corpus", help="write the generated corpus")
    corpus.add_argument("-o", "--out", default="corpus")
    corpus.add_argument("-p", "--per-family", type=int, default=None)
    corpus.add_argument("--seed", type=int, default=1337)
    corpus.set_defaults(handler=_cmd_corpus)

    bench = subs.add_parser("bench", help="solve the corpus and report timings")
    bench.add_argument("-p", "--per-family", type=int, default=None)
    bench.add_argument("--seed", type=int, default=1337)
    bench.add_argument("--max-paths", type=int, default=4096)
    bench.add_argument("--timeout", type=float, default=None)
    bench.add_argument("--json", action="store_true")
    bench.set_defaults(handler=_cmd_bench)

    return parser


# -- commands ---------------------------------------------------------


def _cmd_solve(args):
    program = assemble_file(args.path)

    if args.target is None:
        target = program.labels.get("win")
    else:
        target = _resolve(program, args.target)

    avoid = [_resolve(program, name) for name in args.avoid]

    explorer = Explorer(
        program,
        target=target,
        avoid=avoid,
        input_size=args.input_size,
        max_paths=args.max_paths,
        max_steps=args.max_steps,
        deadline=_deadline(args.timeout),
    )
    result = explorer.run()

    if args.json:
        payload = result.as_dict()
        payload["program"] = str(args.path)
        payload["goal"] = target
        print(json.dumps(payload, indent=2))
        return 0 if result.solved else 1

    _print_solve_report(args.path, program, target, result, args.input_size)
    return 0 if result.solved else 1


def _cmd_run(args):
    program = assemble_file(args.path)
    data = _decode_input(args)
    trace = run_concrete(program, data)

    if args.json:
        payload = dict(trace)
        payload["input_hex"] = data.hex()
        print(json.dumps(payload, indent=2))
        return 0 if trace["halted"] else 1

    print(f"program    {args.path}")
    print(f"input      {_hex_bytes(data)}")
    print(f"halted     {'yes' if trace['halted'] else 'no'}")
    print(f"exit code  {trace['code']}")
    print(f"steps      {trace['steps']}")
    print(f"trace      {' -> '.join(str(pc) for pc in trace['visited'][:24])}"
          + (" ..." if len(trace["visited"]) > 24 else ""))
    return 0 if trace["halted"] else 1


def _cmd_disasm(args):
    path = Path(args.path)
    if path.suffix in (".sasm", ".asm"):
        program = assemble_file(path)
        instructions = program.instructions
    else:
        instructions = disassemble_bytes(path.read_bytes())

    for index, instr in enumerate(instructions):
        raw = instr.encode().hex()
        print(f"{index:04d}  {raw[0:2]} {raw[2:4]} {raw[4:6]} {raw[6:8]} "
              f"{raw[8:16]}  {instr}")
    return 0


def _cmd_corpus(args):
    paths = write_corpus(args.out, per_family=args.per_family, seed=args.seed)
    families = sorted({path.name.rsplit("-", 1)[0] for path in paths})
    print(f"wrote {len(paths)} program(s) to {args.out}")
    print(f"families   {', '.join(families)}")
    return 0


def _cmd_bench(args):
    cases = run_bench(
        per_family=args.per_family,
        seed=args.seed,
        max_paths=args.max_paths,
        solver_timeout_ms=5000,
    )
    summary = summarise(cases)

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"argent {__version__}  corpus benchmark  seed={args.seed}")
    print()
    print(render_table(summary))
    print()
    total = summary["total"]
    print(f"{total['solved']}/{total['cases']} solved, "
          f"{total['verified']} verified by concrete replay, "
          f"{total['solver_calls']} solver calls")
    return 0


# -- helpers ----------------------------------------------------------


def _resolve(program, token):
    token = token.strip()
    if token.startswith("@"):
        return int(token[1:], 0)
    if token in program.labels:
        return program.labels[token]
    return int(token, 0)


def _decode_input(args):
    if args.hex_input is not None:
        cleaned = args.hex_input.replace(" ", "").replace("0x", "")
        return bytes.fromhex(cleaned)
    return args.text_input.encode("utf-8")


def _deadline(seconds):
    if seconds is None:
        return None
    import time

    return time.perf_counter() + seconds


def _hex_bytes(data):
    return " ".join(f"{value:02x}" for value in data)


def _print_solve_report(path, program, target, result, input_size):
    print(f"argent {__version__}")
    print()
    print(f"  program    {path}")
    if target is None:
        print("  goal       any non-zero exit code")
    else:
        name = next(
            (label for label, index in program.labels.items() if index == target),
            None,
        )
        suffix = f" ({name})" if name else ""
        print(f"  goal       @{target}{suffix}")
    print(f"  input size {input_size} byte(s)")
    print()

    if result.solved:
        print("  status     sat")
        print(f"  input      {_hex_bytes(result.input)}")
        ascii_view = "".join(chr(b) if 32 <= b < 127 else "." for b in result.input)
        print(f"  ascii      {ascii_view}")
        print("  verified   yes, concrete replay reached the goal")
    else:
        print("  status     no model")
        print(f"  reason     {result.reason}")

    print()
    print(f"  paths      {result.paths}")
    print(f"  forks      {result.forks}")
    print(f"  pruned     {result.pruned}")
    print(f"  steps      {result.steps}")
    print(f"  solver     {result.solver_calls} call(s)")
    print(f"  time       {result.elapsed:.3f} s")
