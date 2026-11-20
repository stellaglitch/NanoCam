"""NanoCam Patcher: friendly front end for build_full_firmware.py, packaged as an exe.

Takes Apple's decrypted nano 5G firmware (n5g-retailos.dec) and writes nanocam.dfu.

    nanocam-patcher.exe                       (asks for everything)
    nanocam-patcher.exe n5g-retailos.dec      (drag the file onto the exe)
    nanocam-patcher.exe in.dec out.dfu [slots] [next_number]
"""

from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    HERE = Path(sys.executable).resolve().parent
else:
    HERE = Path(__file__).resolve().parent
    sys.path.insert(0, str(HERE.parent))
    sys.path.insert(0, str(HERE))

from nanocam.img1 import Img1  # noqa: E402
from nanocam.patch import apply  # noqa: E402
import build_full_firmware as bf  # noqa: E402
import photos_slot as ps  # noqa: E402


MB_PER_SLOT = 0.61   # full-size picture + thumbnail reserved per placeholder (200 -> 125 MB, 1000 -> 610 MB)
MAX_GB = 15
MAX_SLOTS = min(10000, int(MAX_GB * 1000 / MB_PER_SLOT))  # 4-digit photo numbers cap it at 10000


def space_text(slots: int) -> str:
    mb = slots * MB_PER_SLOT
    return f"{mb / 1000:.2f} GB" if mb >= 1000 else f"{mb:.0f} MB"


def write_placeholders(folder: Path, slots: int) -> None:
    src = (Path(getattr(sys, "_MEIPASS", HERE.parent)) / "placeholders" / "200" / "slot_001.jpg").read_bytes()
    folder.mkdir(parents=True, exist_ok=True)
    width = max(3, len(str(slots)))
    for i in range(1, slots + 1):
        (folder / f"slot_{i:0{width}d}.jpg").write_bytes(src)
    print(f"Created {slots} placeholder images in {folder}")


def ask(prompt: str, default: str) -> str:
    try:
        text = input(f"{prompt} [{default}]: ").strip().strip('"')
    except EOFError:
        text = ""
    return text or default


def ask_int(prompt: str, default: int, lo: int, hi: int) -> int:
    while True:
        try:
            value = int(ask(prompt, str(default)))
        except ValueError:
            print("  Please enter a number.")
            continue
        if lo <= value <= hi:
            return value
        print(f"  Please enter a number from {lo} to {hi}.")


def build(src: Path, dst: Path, slots: int, next_number: int) -> None:
    img = Img1.parse(src.read_bytes())
    offset = ps.default_offset(slots, next_number)
    patches = bf.build_all_patches(img.body, slots, offset)
    body = apply(img.body, patches)
    out = Img1.make_unsigned(body, entrypoint=img.header.entrypoint)
    dst.write_bytes(out.to_bytes())
    print(f"Applied {len(patches)} patches ({slots} photo slots, next photo number {next_number}).")
    print(f"Wrote {dst}")


def main() -> int:
    args = sys.argv[1:]
    print("NanoCam Patcher - camera, Photos slots and Dark Mode for the iPod nano 5G\n")

    if len(args) >= 2:
        src, dst = Path(args[0]), Path(args[1])
        slots = int(args[2]) if len(args) > 2 else 200
        next_number = int(args[3]) if len(args) > 3 else 0
        placeholder_dir = None
        if not 1 <= slots <= MAX_SLOTS:
            print(f"Slots must be 1 to {MAX_SLOTS}")
            return 1
    else:
        default_src = args[0] if args else str(HERE / "n5g-retailos.dec")
        src = Path(ask("Decrypted firmware (n5g-retailos.dec)", default_src))
        while True:
            slots = ask_int(f"Number of photo placeholders (1 to {MAX_SLOTS})", 200, 1, MAX_SLOTS)
            print(f"  Space on the iPod: about {space_text(slots)} of the {MAX_GB} GB limit")
            if 10000 % slots:
                print("  Note: a count that divides 10000 (200, 250, 500, 1000...) keeps the photo order\n"
                      "  correct if numbering ever wraps after PIC_9999.")
            if ask("Use this number? (y/n)", "y").lower().startswith("y"):
                break
        placeholder_dir = Path(ask("Folder to create the placeholder images in (blank to skip)", "")) \
            if ask("Also create the placeholder images to sync with iTunes? (y/n)", "y").lower().startswith("y") else None
        next_number = ask_int("Next photo number (0 unless the iPod already has PIC_ files)", 0, 0, 9999)
        dst = Path(ask("Output file", str(src.with_name("nanocam.dfu"))))

    if not src.is_file():
        print(f"\nCan't find {src}")
        return 1
    try:
        build(src, dst, slots, next_number)
        if placeholder_dir and str(placeholder_dir) not in ("", "."):
            write_placeholders(placeholder_dir, slots)
    except Exception as e:  # patch mismatch, wrong firmware, bad file
        print(f"\nFailed: {e}")
        print("Make sure this is the decrypted iPod nano 5G firmware, version 1.0.2 (34A20020).")
        return 1
    print("\nDone. Copy it to your Linux machine and run:  wInd3x cfw run nanocam.dfu")
    return 0


if __name__ == "__main__":
    code = main()
    if getattr(sys, "frozen", False) and len(sys.argv) < 3:
        try:
            input("\nPress Enter to close...")
        except EOFError:
            pass
    sys.exit(code)
