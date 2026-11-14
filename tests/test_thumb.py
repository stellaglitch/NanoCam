import pytest

from nanocam import thumb

# Real instructions copied from RetailOS (address -> bytes), checked in Ghidra.
#   0x080c85d6  bl 0x0818eda4      (camera dispatcher's strcmp call)
#   0x080c860e  b  0x080c8668
#   0x080c85d2  adr r1, 0x080c8680


def test_bl_matches_firmware():
    assert thumb.bl(0x080C85D6, 0x0818EDA4) == bytes.fromhex("c6f0e5fb")


def test_b_matches_firmware():
    assert thumb.b(0x080C860E, 0x080C8668) == bytes.fromhex("2be0")


def test_adr_matches_firmware():
    assert thumb.adr(0x080C85D2, 1, 0x080C8680) == bytes.fromhex("2ba1")


def test_bl_backwards():
    # A backwards call decodes back to the same target.
    code = thumb.bl(0x08276B1E, 0x0809C3E6)
    h1, h2 = int.from_bytes(code[:2], "little"), int.from_bytes(code[2:], "little")
    off = ((h1 & 0x7FF) << 12) | ((h2 & 0x7FF) << 1)
    off -= 0x800000 if off & 0x400000 else 0
    assert 0x08276B1E + 4 + off == 0x0809C3E6


def test_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        thumb.b(0x08000000, 0x08001000)
    with pytest.raises(ValueError):
        thumb.adr(0x08000002, 0, 0x08000006)  # not 4-aligned


def test_more_instructions_match_firmware():
    # 0x080c8602 adds r5,#0xff ; 0x080c8604 adds r5,#5 ; 0x080c8606 ldrb r0,[r5,#1]
    assert thumb.adds_imm(5, 0xFF) + thumb.adds_imm(5, 5) == bytes.fromhex("ff350535")
    assert thumb.ldrb(0, 5, 1) == bytes.fromhex("6878")
    # 0x080c866e movs r0,#1 ; 0x080c8670 pop {r1-r7,pc}
    assert thumb.movs_imm(0, 1) == bytes.fromhex("0120")
    assert thumb.pop([1, 2, 3, 4, 5, 6, 7], pc=True) == bytes.fromhex("febd")
    # 0x080c85c4 push {r0,r1,r2,r4,r5,r6,r7,lr}
    assert thumb.push([0, 1, 2, 4, 5, 6, 7], lr=True) == bytes.fromhex("f7b5")
    # 0x080c860a bne 0x080c8610
    assert thumb.bcond("ne", 0x080C860A, 0x080C8610) == bytes.fromhex("01d1")


def test_asm_forward_labels():
    a = thumb.Asm(0x1000)
    a.ref(2, lambda addr, L: thumb.b(addr, L["end"]))
    a(thumb.movs_imm(0, 1))
    a("end")
    code, labels = a.build()
    assert labels["end"] == 0x1004
    assert code == thumb.b(0x1000, 0x1004) + thumb.movs_imm(0, 1)


def test_photo_mode_cave_fits():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "patches"))
    import photo_mode
    code, labels = photo_mode.build_cave()
    assert photo_mode.CAVE + len(code) <= photo_mode.CAVE_END
    assert labels["fmt"] % 4 == 0
    assert code.endswith(photo_mode.FMT)
