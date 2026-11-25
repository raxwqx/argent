import json
import shutil
from pathlib import Path

import pytest

from argent.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture()
def eq_program(tmp_path):
    target = tmp_path / "eq.sasm"
    shutil.copy(EXAMPLES / "eq.sasm", target)
    return target


def test_version(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert "argent" in capsys.readouterr().out


def test_solve_prints_a_verified_solution(eq_program, capsys):
    code = main(["solve", str(eq_program), "-n", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "status     sat" in out
    assert "input      41" in out
    assert "verified   yes" in out


def test_solve_json(eq_program, capsys):
    code = main(["solve", str(eq_program), "-n", "1", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["solved"] is True
    assert payload["input_hex"] == "41"
    assert payload["verified"] is True


def test_solve_unsolved_program_exits_one(tmp_path, capsys):
    path = tmp_path / "impossible.sasm"
    path.write_text(
        """
start:
    movi  r1, 0x1000
    loadb r2, r1, 0
    movi  r3, 1
    cmp   r2, r3
    jne   second
    jmp   fail
second:
    cmp   r2, r3
    je    win
fail:
    movi  r0, 0
    syscall 1
win:
    movi  r0, 1
    syscall 1
""",
        encoding="utf-8",
    )
    code = main(["solve", str(path), "-n", "1"])
    out = capsys.readouterr().out
    assert code == 1
    assert "no model" in out


def test_solve_assembly_error_exits_two(tmp_path, capsys):
    path = tmp_path / "bad.sasm"
    path.write_text("bogus r1\n", encoding="utf-8")
    code = main(["solve", str(path)])
    assert code == 2
    assert "assembly error" in capsys.readouterr().err


def test_missing_file_exits_two(capsys):
    code = main(["solve", "/nonexistent/nope.sasm"])
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_run_with_hex_input(eq_program, capsys):
    code = main(["run", str(eq_program), "--hex", "41"])
    out = capsys.readouterr().out
    assert code == 0
    assert "exit code  1" in out


def test_run_with_text_input(eq_program, capsys):
    code = main(["run", str(eq_program), "--text", "A"])
    assert code == 0
    assert "exit code  1" in capsys.readouterr().out


def test_run_reports_guest_exit_code(eq_program, capsys):
    assert main(["run", str(eq_program), "--hex", "42"]) == 0
    assert "exit code  0" in capsys.readouterr().out


def test_run_reports_a_program_that_does_not_halt(tmp_path, capsys):
    path = tmp_path / "spin.sasm"
    path.write_text("jmp 0\n", encoding="utf-8")
    assert main(["run", str(path), "--hex", ""]) == 1
    assert "halted     no" in capsys.readouterr().out


def test_disasm_prints_one_line_per_instruction(eq_program, capsys):
    code = main(["disasm", str(eq_program)])
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert code == 0
    assert len(lines) == 10
    assert lines[0].startswith("0000")


def test_corpus_writes_files(tmp_path, capsys):
    out_dir = tmp_path / "corpus"
    code = main(["corpus", "-o", str(out_dir), "-p", "1"])
    assert code == 0
    assert len(list(out_dir.glob("*.sasm"))) == 8
    assert "wrote 8 program(s)" in capsys.readouterr().out


def test_bench_json(capsys):
    code = main(["bench", "-p", "1", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["total"]["cases"] == 8
    assert payload["total"]["solved"] == 7
    assert len(payload["cases"]) == 8


def test_bench_table(capsys):
    code = main(["bench", "-p", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "7/8 solved" in out
    assert "verified by concrete replay" in out
