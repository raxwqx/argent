import pytest

from argent.asm import AssemblyError, assemble, assemble_file

SOURCE = """
# a comment
start:
    movi  r1, 0x1000      ; inline comment
    loadb r2, r1, 0
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
"""


def test_labels_resolve_to_instruction_indices():
    program = assemble(SOURCE)
    assert program.labels["start"] == 0
    assert program.labels["fail"] == 6
    assert program.labels["win"] == 8
    assert len(program) == 10


def test_comments_and_blank_lines_are_ignored():
    program = assemble("\n\n# only comments\n\n")
    assert len(program) == 0
    assert program.labels == {}


def test_numeric_targets_are_accepted():
    program = assemble("    jmp @2\n    nop\n    nop\n")
    assert program.instructions[0].imm == 2


def test_immediates_may_be_decimal_hex_or_negative():
    program = assemble("movi r1, 16\nmovi r2, 0x10\nmovi r3, -1\n")
    assert [instr.imm for instr in program.instructions] == [16, 16, 0xFFFFFFFF]


def test_hexdump_has_eight_bytes_per_instruction():
    program = assemble("nop\nhalt\n")
    assert len(program.hexdump()) == 32
    assert len(program.to_bytes()) == 16


def test_unknown_mnemonic():
    with pytest.raises(AssemblyError, match="unknown mnemonic"):
        assemble("frobnicate r1\n")


def test_wrong_operand_count():
    with pytest.raises(AssemblyError, match="expects 2 operand"):
        assemble("movi r1\n")


def test_invalid_register_name():
    with pytest.raises(AssemblyError, match="invalid register"):
        assemble("movi x1, 5\n")


def test_register_out_of_range():
    with pytest.raises(AssemblyError, match="r0-r15"):
        assemble("movi r16, 5\n")


def test_duplicate_label():
    with pytest.raises(AssemblyError, match="duplicate label"):
        assemble("a:\nnop\na:\nnop\n")


def test_empty_label():
    with pytest.raises(AssemblyError, match="empty label"):
        assemble(":\nnop\n")


def test_unknown_jump_label():
    with pytest.raises(AssemblyError, match="unknown label"):
        assemble("jmp nowhere\n")


def test_unknown_immediate_symbol():
    with pytest.raises(AssemblyError, match="invalid immediate"):
        assemble("movi r1, nowhere\n")


def test_line_numbers_are_reported():
    with pytest.raises(AssemblyError, match="line 3"):
        assemble("nop\nnop\nbogus\n")


def test_assemble_rejects_non_string():
    with pytest.raises(AssemblyError):
        assemble(b"nop")


def test_assemble_file(tmp_path):
    path = tmp_path / "tiny.sasm"
    path.write_text(SOURCE, encoding="utf-8")
    program = assemble_file(path)
    assert program.label("win") == 8
    assert program.source == SOURCE
