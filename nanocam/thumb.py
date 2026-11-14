"""A tiny assembler for the handful of Thumb (16-bit ARM) instructions our patches use.

The nano 5G's CPU is an ARMv5 core running mostly Thumb code. Each function
here returns the instruction's bytes for a given address, because branches and
PC-relative loads are encoded as distances from the instruction itself.

Thumb's "PC" reads as the instruction address + 4. Loads and `adr` also round
that down to a multiple of 4.
"""

from __future__ import annotations

import struct


def _h(*halfwords: int) -> bytes:
    return struct.pack(f"<{len(halfwords)}H", *halfwords)


def _pc(addr: int) -> int:
    return addr + 4


def _pc_aligned(addr: int) -> int:
    return (addr + 4) & ~3


def bl(addr: int, target: int) -> bytes:
    """bl target: call a Thumb function (two halfwords, +-4 MB)."""
    off = target - _pc(addr)
    if off % 2 or not -0x400000 <= off < 0x400000:
        raise ValueError(f"bl from {addr:#x} to {target:#x} is out of range")
    return _h(0xF000 | ((off >> 12) & 0x7FF), 0xF800 | ((off >> 1) & 0x7FF))


def b(addr: int, target: int) -> bytes:
    """b target: unconditional branch (+-2 KB)."""
    off = target - _pc(addr)
    if off % 2 or not -2048 <= off < 2048:
        raise ValueError(f"b from {addr:#x} to {target:#x} is out of range")
    return _h(0xE000 | ((off >> 1) & 0x7FF))


def beq(addr: int, target: int) -> bytes:
    """beq target: branch if equal (+-256 bytes)."""
    off = target - _pc(addr)
    if off % 2 or not -256 <= off < 256:
        raise ValueError(f"beq from {addr:#x} to {target:#x} is out of range")
    return _h(0xD000 | ((off >> 1) & 0xFF))


def ldr_pc(addr: int, rd: int, literal: int) -> bytes:
    """ldr rd, [pc, #...]: load the 32-bit word stored at `literal`."""
    off = literal - _pc_aligned(addr)
    if off % 4 or not 0 <= off < 1024:
        raise ValueError(f"literal {literal:#x} unreachable from {addr:#x}")
    return _h(0x4800 | (rd << 8) | (off >> 2))


def adr(addr: int, rd: int, label: int) -> bytes:
    """adr rd, label: rd = address of `label` (which must be 4-byte aligned)."""
    off = label - _pc_aligned(addr)
    if off % 4 or not 0 <= off < 1024:
        raise ValueError(f"label {label:#x} unreachable from {addr:#x}")
    return _h(0xA000 | (rd << 8) | (off >> 2))


def ldr_reg0(rd: int, rn: int) -> bytes:
    """ldr rd, [rn]"""
    return _h(0x6800 | (rn << 3) | rd)


def cmp_imm(rn: int, imm: int) -> bytes:
    return _h(0x2800 | (rn << 8) | imm)


def push_r4_lr() -> bytes:
    return _h(0xB510)


def pop_r4_pc() -> bytes:
    return _h(0xBD10)


# --- more single instructions (low registers r0-r7 only) ---

def movs_imm(rd: int, imm: int) -> bytes:
    return _h(0x2000 | (rd << 8) | imm)


def adds_imm(rd: int, imm: int) -> bytes:
    return _h(0x3000 | (rd << 8) | imm)


def mov_lo(rd: int, rm: int) -> bytes:
    """movs rd, rm (encoded as adds rd, rm, #0)"""
    return _h(0x1C00 | (rm << 3) | rd)


def cmp_reg(rn: int, rm: int) -> bytes:
    return _h(0x4280 | (rm << 3) | rn)


def ldrb(rd: int, rn: int, imm: int = 0) -> bytes:
    return _h(0x7800 | (imm << 6) | (rn << 3) | rd)


def strb(rd: int, rn: int, imm: int = 0) -> bytes:
    return _h(0x7000 | (imm << 6) | (rn << 3) | rd)


def str_sp(rd: int, imm: int) -> bytes:
    return _h(0x9000 | (rd << 8) | (imm >> 2))


def add_sp_rd(rd: int, imm: int) -> bytes:
    """add rd, sp, #imm"""
    return _h(0xA800 | (rd << 8) | (imm >> 2))


def sub_sp(imm: int) -> bytes:
    return _h(0xB080 | (imm >> 2))


def add_sp(imm: int) -> bytes:
    return _h(0xB000 | (imm >> 2))


def push(regs: list[int], lr: bool = False) -> bytes:
    return _h(0xB400 | (0x100 if lr else 0) | sum(1 << r for r in regs))


def pop(regs: list[int], pc: bool = False) -> bytes:
    return _h(0xBC00 | (0x100 if pc else 0) | sum(1 << r for r in regs))


def bx(rm: int) -> bytes:
    return _h(0x4700 | (rm << 3))


_COND = {"eq": 0, "ne": 1, "lt": 0xB, "ge": 0xA}


def bcond(cond: str, addr: int, target: int) -> bytes:
    off = target - _pc(addr)
    if off % 2 or not -256 <= off < 256:
        raise ValueError(f"b{cond} from {addr:#x} to {target:#x} is out of range")
    return _h(0xD000 | (_COND[cond] << 8) | ((off >> 1) & 0xFF))


class Asm:
    """Two-pass assembler, so instructions can refer to labels defined later.

    asm(b"...")             raw bytes (data or a fixed instruction)
    asm("name")             define a label here
    asm("align4")           pad with zeros to a 4-byte boundary
    asm.ref(size, f)        f(addr, labels) -> bytes, built once labels are known
    """

    def __init__(self, base: int):
        self.base = base
        self.items: list = []

    def __call__(self, item) -> "Asm":
        self.items.append(item)
        return self

    def ref(self, size: int, f) -> "Asm":
        self.items.append((size, f))
        return self

    def _layout(self, labels: dict[str, int], final: bool) -> bytes:
        out, addr = b"", self.base
        for it in self.items:
            if it == "align4":
                chunk = bytes((-addr) % 4)
            elif isinstance(it, str):
                labels[it] = addr
                chunk = b""
            elif isinstance(it, tuple):
                size, f = it
                chunk = f(addr, labels) if final else bytes(size)
                if len(chunk) != size:
                    raise ValueError("instruction size mismatch")
            else:
                chunk = it
            out += chunk
            addr += len(chunk)
        return out

    def build(self) -> tuple[bytes, dict[str, int]]:
        labels: dict[str, int] = {}
        self._layout(labels, final=False)   # pass 1: find label addresses
        return self._layout(labels, final=True), labels


def str_imm(rd: int, rn: int, imm: int = 0) -> bytes:
    """str rd, [rn, #imm] (imm a multiple of 4, up to 124)"""
    return _h(0x6000 | ((imm >> 2) << 6) | (rn << 3) | rd)


def lsrs_imm(rd: int, rm: int, imm: int) -> bytes:
    return _h(0x0800 | (imm << 6) | (rm << 3) | rd)


# --- more instructions for the Photos-slot writer (low registers only) ---

def subs_imm(rd: int, imm: int) -> bytes:
    return _h(0x3800 | (rd << 8) | imm)


def adds_reg(rd: int, rn: int, rm: int) -> bytes:
    return _h(0x1800 | (rm << 6) | (rn << 3) | rd)


def subs_reg(rd: int, rn: int, rm: int) -> bytes:
    return _h(0x1A00 | (rm << 6) | (rn << 3) | rd)


def muls(rd: int, rm: int) -> bytes:
    """muls rd, rm  (rd = rd * rm)"""
    return _h(0x4340 | (rm << 3) | rd)


def lsls_imm(rd: int, rm: int, imm: int) -> bytes:
    return _h(0x0000 | (imm << 6) | (rm << 3) | rd)


def asrs_imm(rd: int, rm: int, imm: int) -> bytes:
    return _h(0x1000 | (imm << 6) | (rm << 3) | rd)


def orrs(rd: int, rm: int) -> bytes:
    return _h(0x4300 | (rm << 3) | rd)


def strh_imm(rd: int, rn: int, imm: int = 0) -> bytes:
    return _h(0x8000 | ((imm >> 1) << 6) | (rn << 3) | rd)


def ldr_imm(rd: int, rn: int, imm: int = 0) -> bytes:
    return _h(0x6800 | ((imm >> 2) << 6) | (rn << 3) | rd)


def ldr_sp(rd: int, imm: int) -> bytes:
    return _h(0x9800 | (rd << 8) | (imm >> 2))


def blx_reg(rm: int) -> bytes:
    return _h(0x4780 | (rm << 3))


_COND.update({"gt": 0xC, "le": 0xD, "hs": 0x2, "lo": 0x3, "hi": 0x8, "ls": 0x9})


def ldrh_imm(rd: int, rn: int, imm: int = 0) -> bytes:
    """ldrh rd, [rn, #imm] (imm even, up to 62)"""
    return _h(0x8800 | ((imm >> 1) << 6) | (rn << 3) | rd)


def ldrb_reg(rd: int, rn: int, rm: int) -> bytes:
    """ldrb rd, [rn, rm]"""
    return _h(0x5C00 | (rm << 6) | (rn << 3) | rd)


def ldr_reg(rd: int, rn: int, rm: int) -> bytes:
    """ldr rd, [rn, rm]"""
    return _h(0x5800 | (rm << 6) | (rn << 3) | rd)
