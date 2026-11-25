import pytest

from argent.isa import (
    INPUT_BASE,
    INSTRUCTION_SIZE,
    OPCODES,
    OPERANDS,
    Instruction,
    assemble_bytes,
    disassemble_bytes,
    format_instruction,
)


def test_instruction_roundtrip_all_opcodes():
    for opcode in OPCODES:
        instr = Instruction(opcode, a=1, b=2, c=3, imm=0xDEADBEEF)
        decoded = Instruction.decode(instr.encode())
        assert decoded == instr
        assert len(instr.encode()) == INSTRUCTION_SIZE


def test_encode_masks_immediate_to_32_bits():
    instr = Instruction("movi", a=1, imm=0x1_0000_0041)
    assert Instruction.decode(instr.encode()).imm == 0x41


def test_encode_rejects_unknown_opcode():
    with pytest.raises(ValueError, match="unknown opcode"):
        Instruction("bogus").encode()


def test_decode_rejects_unknown_opcode():
    with pytest.raises(ValueError, match="unknown opcode"):
        Instruction.decode(b"\xff\x00\x00\x00\x00\x00\x00\x00")


def test_formatting_is_stable():
    assert str(Instruction("movi", a=1, imm=0x10)) == "movi   r1, 0x10"
    assert str(Instruction("add", a=1, b=2, c=3)) == "add    r1, r2, r3"
    assert str(Instruction("je", imm=7)) == "je     @7"
    assert str(Instruction("loadb", a=2, b=1, imm=4)) == "loadb  r2, r1, 0x4"
    assert str(Instruction("syscall", imm=1)) == "syscall 1"
    assert str(Instruction("nop")) == "nop"


def test_formatting_negative_immediate_wraps():
    rendered = format_instruction(Instruction("movi", a=1, imm=-1))
    assert rendered == "movi   r1, 0xffffffff"


def test_operand_layout_matches_encoding():
    # movi must place its immediate in the imm field, not in b.
    instr = Instruction("movi", a=3, imm=0x1000)
    assert instr.b == 0
    assert instr.imm == 0x1000
    assert OPERANDS["movi"] == (("reg", "a"), ("imm", "imm"))


def test_assemble_and_disassemble_bytes():
    program = [Instruction("movi", a=1, imm=INPUT_BASE), Instruction("halt")]
    raw = assemble_bytes(program)
    assert len(raw) == 2 * INSTRUCTION_SIZE
    assert disassemble_bytes(raw) == program


def test_disassemble_rejects_partial_instruction():
    with pytest.raises(ValueError, match="multiple of 8"):
        disassemble_bytes(b"\x00" * 4)
