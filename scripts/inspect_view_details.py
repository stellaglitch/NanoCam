from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# Let's inspect View 0xdad1470 and 0xdad1473
for vid in [0x0DAD1470, 0x0DAD1473]:
    v = db.get("View", vid)
    d = v.data(body)
    print(f"\nView {hex(vid)} (len {len(d)}):")
    # find all strings, fonts, colors
    for off in range(0, len(d) - 3, 4):
        val = struct.unpack_from('<I', d, off)[0]
        if 0x0DAD0012 <= val <= 0x0DAD00A5:
            print(f"  +{hex(off)}: COLR {hex(val)} = {db.get('COLR', val).data(body).hex()}")
        elif val in [r.id for r in db.by_type.get('FONT', [])]:
            print(f"  +{hex(off)}: FONT {hex(val)}")
        elif val in [r.id for r in db.by_type.get('Str ', [])]:
            print(f"  +{hex(off)}: Str {hex(val)} = {repr(db.text('Str ', val))}")
