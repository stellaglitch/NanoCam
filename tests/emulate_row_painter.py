"""Runs the real row painter FUN_0808d718 (with the STRIPE and ROWDRAW hooks) in Unicorn, callees stubbed.\nChecks colours, highlight calls, balanced stack, preserved registers and 8-byte sp alignment at every call.\n\n    python tests/emulate_row_painter.py\n"""
import struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "patches"))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from nanocam.img1 import Img1
from nanocam.patch import apply
import dark_mode_toggle as d
import build_full_firmware as bf

B = d.BASE
IMAGE = 0x07FD1000
FAKE = 0x20000000
STACK = 0x22000000
LIST, CELL, VT, PREFS, PVT = FAKE + 0x1000, FAKE + 0x2000, FAKE + 0x2400, FAKE + 0x400, FAKE + 0x500
DRAW, PGET, STOP = FAKE + 0x800, FAKE + 0x900, FAKE + 0xA00
PAINT, PEND = 0x0808D718, 0x0808D9A4
HL = 0x0820B6A0

stock = Img1.parse((ROOT / "firmware" / "n5g-retailos.dec").read_bytes()).body
body = bytearray(apply(stock, bf.build_all_patches(stock, 200, 0)))
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
# stub bl targets of the painter
targets = set()
for i in md.disasm(bytes(body[PAINT - B:PEND - B]), PAINT):
    if i.mnemonic == "bl":
        t = int(i.op_str.lstrip("#"), 16)
        if not (0x08180000 <= t < 0x08181000):
            targets.add(t)
for t in targets:
    body[t - B:t - B + 4] = bytes.fromhex("00207047")  # movs r0,#0; bx lr


def run(dark, striped=True, even=True, selected=False):
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    mu.mem_map(IMAGE, (len(body) + (B - IMAGE) + 0xFFF) & ~0xFFF)
    mu.mem_write(B, bytes(body))
    mu.mem_map(FAKE, 0x4000)
    mu.mem_map(STACK - 0x10000, 0x10000)
    mu.mem_write(d.PREFS_SLOT, struct.pack("<I", PREFS))
    mu.mem_write(PREFS, struct.pack("<I", PVT))
    mu.mem_write(PVT + d.PREFS_GET_BOOL, struct.pack("<I", PGET | 1))
    mu.mem_write(CELL, struct.pack("<I", VT))
    mu.mem_write(VT + 0x84, struct.pack("<I", DRAW | 1))
    for a in (DRAW, PGET, STOP):
        mu.mem_write(a, bytes.fromhex("7047"))
    mu.mem_write(LIST + 0x114, struct.pack("<II", CELL, CELL))
    mu.mem_write(LIST + 0x14C, struct.pack("<I", (1 << 18) if striped else 0))
    log = []

    def on_get(mu, a, s, u):
        mu.mem_write(mu.reg_read(UC_ARM_REG_R2), bytes([1 if dark else 0]))
        for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3):
            mu.reg_write(r, 0xDEADBEEF)

    def on_draw(mu, a, s, u):
        sp = mu.reg_read(UC_ARM_REG_SP)
        log.append(("draw", mu.reg_read(UC_ARM_REG_R0) == CELL, hex(mu.reg_read(UC_ARM_REG_R1)),
                    mu.reg_read(UC_ARM_REG_R2) - (entry_sp - 0xB0 + 0x50 + 0x0), sp % 8, mu.reg_read(UC_ARM_REG_R3) == (DRAW & ~1) or hex(mu.reg_read(UC_ARM_REG_R3))))

    def on_hl(mu, a, s, u):
        log.append(("hl", mu.reg_read(UC_ARM_REG_R0) == CELL, mu.reg_read(UC_ARM_REG_R1), mu.reg_read(UC_ARM_REG_SP) % 8))

    def on_fill(mu, a, s, u):   # bl 0x81b2110 area: record the colour written at sp+8 by the stripe code
        pass
    mu.hook_add(UC_HOOK_CODE, on_get, begin=PGET, end=PGET)
    mu.hook_add(UC_HOOK_CODE, on_draw, begin=DRAW, end=DRAW)
    mu.hook_add(UC_HOOK_CODE, on_hl, begin=HL, end=HL)
    # capture the stripe colour: the call at 0x0808d7aa uses [sp+8..]
    def on_stripe_call(mu, a, s, u):
        sp = mu.reg_read(UC_ARM_REG_R1)
        log.append(("stripe", bytes(mu.mem_read(sp, 4)).hex()))
    fill_target = 0x081B2110
    mu.hook_add(UC_HOOK_CODE, on_stripe_call, begin=fill_target, end=fill_target)

    trace=[]
    mu.hook_add(UC_HOOK_CODE, lambda mu,a,s,u: trace.append(a))
    entry_sp = STACK - 0x100
    # stack args: [S+0] = r? , [S+4] = selected(r7) , [S+8] = r5 arg
    mu.mem_write(entry_sp, struct.pack("<IIIIII", 0, 1 if selected else 0, 0, 0, 0, 0))
    mu.reg_write(UC_ARM_REG_SP, entry_sp)
    mu.reg_write(UC_ARM_REG_R0, LIST)
    mu.reg_write(UC_ARM_REG_R1, 0x1111)
    mu.reg_write(UC_ARM_REG_R2, 0x2222)
    mu.reg_write(UC_ARM_REG_R3, 0 if even else 1)
    for r, v in zip((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7), (0x44, 0x55, 0x66, 0x77)):
        mu.reg_write(r, v)
    mu.reg_write(UC_ARM_REG_LR, STOP | 1)
    try:
        mu.emu_start(PAINT | 1, STOP, count=20000)
    except Exception as e:
        print("  EXCEPTION", e, hex(mu.reg_read(UC_ARM_REG_PC)), [hex(x) for x in trace[-8:]], hex(mu.reg_read(UC_ARM_REG_R0)), hex(mu.reg_read(UC_ARM_REG_LR)))
        return log
    ok = mu.reg_read(UC_ARM_REG_PC) == STOP and mu.reg_read(UC_ARM_REG_SP) == entry_sp
    regs = [mu.reg_read(r) for r in (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)]
    log.append(("end", "ok" if ok else f"BAD pc={mu.reg_read(UC_ARM_REG_PC):#x} sp={mu.reg_read(UC_ARM_REG_SP):#x}",
                [hex(x) for x in regs]))
    return log


for dark in (False, True):
    for striped in (True, False):
        for even, selected in ((True, False), (False, False), (True, True)):
            print(f"dark={dark} striped={striped} even={even} selected={selected}")
            for l in run(dark, striped, even, selected):
                print("   ", l)




