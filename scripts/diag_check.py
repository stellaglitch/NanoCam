"""Diagnostic test script to check the three patches on stock retailos.dec.

Run via:
    .\\.venv\\Scripts\\python.exe scripts\\diag_check.py
"""
import sys
from pathlib import Path
import struct

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanocam.img1 import Img1
from nanocam.resources import ResourceDB

firmware_path = Path("firmware/n5g-retailos.dec")
if not firmware_path.exists():
    print("Firmware file not found at", firmware_path)
    sys.exit(1)

img = Img1.parse(firmware_path.read_bytes())
body = img.body
db = ResourceDB(body)

print("Checking Str 0x0dad0da9:")
r_spare = db.get("Str ", 0x0DAD0DA9)
if r_spare:
    print(f"  Offset: {hex(r_spare.offset)}, Size: {r_spare.size}, Content: {repr(db.text('Str ', 0x0DAD0DA9))}")
else:
    print("  NOT FOUND")

print("\nChecking SORC 0x985 & 0x986:")
s_985 = db.get("SORC", 0x985)
s_986 = db.get("SORC", 0x986)
if s_985 and s_986:
    k_985 = struct.unpack_from("<I", body, s_985.offset + 12)[0]
    v_985 = struct.unpack_from("<I", body, s_985.offset + 16)[0]
    print(f"  SORC 0x985: offset={hex(s_985.offset)}, kind={hex(k_985)}, val={hex(v_985)} ({db.text('Str ', v_985)})")
    k_986 = struct.unpack_from("<I", body, s_986.offset + 12)[0]
    v_986 = struct.unpack_from("<I", body, s_986.offset + 16)[0]
    print(f"  SORC 0x986: offset={hex(s_986.offset)}, kind={hex(k_986)}, val={hex(v_986)} ({db.text('Str ', v_986)})")

# Check which resources reference Str 0x0dad0da9
refs_to_spare = []
for sorc in db.by_type.get("SORC", []):
    v = struct.unpack_from("<I", body, sorc.offset + 16)[0]
    if v == 0x0DAD0DA9:
        refs_to_spare.append(sorc.id)
print(f"\nExisting SORC references to Str 0x0dad0da9: {refs_to_spare}")

# Check which resources reference "Rotate" string (Str 0xdad0e31)
s_rot = db.get("Str ", 0x0DAD0E31)
print(f"\nRotate string Str 0x0dad0e31: {repr(db.text('Str ', 0x0DAD0E31))}")
refs_to_rot = []
for sorc in db.by_type.get("SORC", []):
    v = struct.unpack_from("<I", body, sorc.offset + 16)[0]
    if v == 0x0DAD0E31:
        refs_to_rot.append(hex(sorc.id))
print(f"SORC references to Rotate string: {refs_to_rot}")
