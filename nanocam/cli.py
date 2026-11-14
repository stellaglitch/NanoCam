"""Command-line entry point: `python -m nanocam <command>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .devices import DFU_LOAD_ADDRESS
from .img1 import Img1, Img1Error
from .patch import PatchError, apply, string_patch_at, string_patches
from .resources import ResourceDB
from .strings import find_strings, grep_strings


def cmd_info(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    try:
        img = Img1.parse(data)
    except Img1Error as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    h = img.header
    print(f"file:        {args.file} ({len(data):,} bytes)")
    print(f"format:      {h.format_name}")
    print(f"entrypoint:  {h.entrypoint:#x}")
    print(f"body length: {h.body_length:#x}")
    print(f"epoch:       {h.security_epoch}")
    if h.is_encrypted:
        print("note: body is encrypted. Decrypt it with `wInd3x decrypt` on the Linux machine.")
    return 0


def cmd_wrap(args: argparse.Namespace) -> int:
    body = Path(args.binary).read_bytes()
    img = Img1.make_unsigned(body, entrypoint=args.entrypoint)
    Path(args.output).write_bytes(img.to_bytes())
    print(f"wrote {args.output}: {len(body)} byte payload, loads at {DFU_LOAD_ADDRESS:#x}")
    return 0


def cmd_strings(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    # For an IMG1 file, search the body so offsets match what Ghidra shows.
    try:
        data = Img1.parse(data).body
    except Img1Error:
        pass

    if args.grep:
        results = grep_strings(data, args.grep, args.min_length)
    else:
        results = find_strings(data, args.min_length)
    for offset, text in results:
        print(f"{offset:#09x}  {text}")
    return 0


def cmd_patch(args: argparse.Namespace) -> int:
    try:
        img = Img1.parse(Path(args.input).read_bytes())
        if img.header.is_encrypted:
            raise PatchError("input is encrypted; patch the wInd3x-decrypted file")
        patches = []
        for old, new in args.string:
            patches += string_patches(img.body, old, new)
        for offset, old, new in args.string_at:
            patches.append(string_patch_at(img.body, int(offset, 0), old, new))
        body = apply(img.body, patches)
    except (Img1Error, PatchError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    for p in patches:
        print(f"{p.offset:#09x}  {p.old.rstrip(bytes(1)).decode()!r} -> {p.new.rstrip(bytes(1)).decode()!r}")
    out = Img1.make_unsigned(body, entrypoint=img.header.entrypoint)
    Path(args.output).write_bytes(out.to_bytes())
    print(f"wrote {args.output} ({len(patches)} patches)")
    return 0


def cmd_resources(args: argparse.Namespace) -> int:
    try:
        body = Img1.parse(Path(args.file).read_bytes()).body
    except Img1Error as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    db = ResourceDB(body)

    if args.type is None:
        for name, rs in db.by_type.items():
            print(f"{name}  {len(rs):5d}")
        return 0
    if args.id is None:
        for r in db.by_type.get(args.type, []):
            print(f"{r.id:#010x}  body {r.offset:#09x}  {r.size} bytes")
        return 0

    r = db.get(args.type, int(args.id, 0))
    if r is None:
        print(f"error: no {args.type} resource {args.id}", file=sys.stderr)
        return 1
    print(f"{r.type} {r.id:#x}: body {r.offset:#x}, {r.size} bytes")
    data = r.data(body)
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  +{i:04x}  {chunk.hex(' '):<47}  {text}")
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    try:
        from .usb import find_nano5g
        modes = find_nano5g()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not modes:
        print("no nano 5G found")
        return 1
    for mode in modes:
        print(f"nano 5G connected in {mode.upper()} mode")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nanocam", description="iPod nano 5G camera hacking tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="show the header of an IMG1 firmware file")
    p.add_argument("file")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("wrap", help="wrap a flat ARM binary as an unsigned IMG1 for haxed DFU")
    p.add_argument("binary")
    p.add_argument("output")
    # type=lambda lets the user type 0x100 as well as 256.
    p.add_argument("--entrypoint", type=lambda s: int(s, 0), default=0)
    p.set_defaults(func=cmd_wrap)

    p = sub.add_parser("strings", help="list readable text in a firmware file (body offsets for IMG1)")
    p.add_argument("file")
    p.add_argument("--grep", help="only show strings matching this case-insensitive regex")
    p.add_argument("--min-length", type=int, default=5)
    p.set_defaults(func=cmd_strings)

    p = sub.add_parser("patch", help="write a patched copy of a decrypted IMG1 firmware")
    p.add_argument("input")
    p.add_argument("output")
    # nargs=2 takes two values per flag; action="append" lets the flag repeat.
    p.add_argument("--string", nargs=2, action="append", default=[], metavar=("OLD", "NEW"),
                   help="replace every copy of string OLD with NEW (same length or shorter)")
    p.add_argument("--string-at", nargs=3, action="append", default=[], metavar=("OFFSET", "OLD", "NEW"),
                   help="replace only the copy of OLD at body OFFSET (e.g. 0x627f1c)")
    p.set_defaults(func=cmd_patch)

    p = sub.add_parser("resources", help="browse the UI resource database (types, IDs, raw data)")
    p.add_argument("file")
    p.add_argument("type", nargs="?", help="four-char type, e.g. View or SCRN; omit to list types")
    p.add_argument("id", nargs="?", help="resource ID, e.g. 0x0dad14ed; omit to list IDs")
    p.set_defaults(func=cmd_resources)

    p = sub.add_parser("detect", help="look for a nano 5G on USB")
    p.set_defaults(func=cmd_detect)

    args = parser.parse_args(argv)
    return args.func(args)
