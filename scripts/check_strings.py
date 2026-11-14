import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanocam.img1 import Img1
from nanocam.resources import ResourceDB

img = Img1.parse(Path("firmware/n5g-retailos.dec").read_bytes())
body = img.body
db = ResourceDB(body)

str_spare = db.get("Str ", 0x0DAD0DA9)
print(f"Str 0x0dad0da9 offset: {hex(str_spare.offset)}, size: {str_spare.size}")
print("Bytes around 0x0dad0da9 (-16 to +32):")
print(body[str_spare.offset - 16 : str_spare.offset + 32])

# Also let's check Str 0x0dad0e31 (Rotate):
str_rot = db.get("Str ", 0x0DAD0E31)
print(f"\nStr 0x0dad0e31 (Rotate) offset: {hex(str_rot.offset)}, size: {str_rot.size}")
print("Bytes around 0x0dad0e31 (-16 to +32):")
print(body[str_rot.offset - 16 : str_rot.offset + 32])

# Check all strings in the resource table between 0x0dad0da0 and 0x0dad0db0
print("\nNeighbouring Str resources:")
for r in db.by_type.get("Str ", []):
    if 0x0DAD0DA0 <= r.id <= 0x0DAD0DB5:
        print(f"  {hex(r.id)}: offset={hex(r.offset)}, size={r.size}, text={repr(db.text('Str ', r.id))}")
