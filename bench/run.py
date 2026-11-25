"""Benchmark the generated corpus and print a reproducible table.

    python bench/run.py             # default corpus
    python bench/run.py --per-family 4
    python bench/run.py --json bench/results.json

The JSON file records every case, so the numbers in the README can be
re-derived with a single command instead of being copied by hand.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from argent.bench import render_table, run_bench, summarise  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", "--per-family", type=int, default=None)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--max-paths", type=int, default=4096)
    args = parser.parse_args(argv)

    cases = run_bench(
        per_family=args.per_family,
        seed=args.seed,
        max_paths=args.max_paths,
    )
    summary = summarise(cases)

    print(render_table(summary))
    print()
    total = summary["total"]
    print(
        f"{total['solved']}/{total['cases']} solved, "
        f"{total['verified']} verified by concrete replay, "
        f"{total['solver_calls']} solver calls, {total['steps']} steps"
    )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "seed": args.seed,
                    "per_family": args.per_family,
                    **summary,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
