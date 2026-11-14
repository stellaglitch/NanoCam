from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# Let's inspect the main menu preview view or a standard table view cell
# Look at COMPOSERS_CELL or view 0x0dad14e8 (camera preview)
view = db.get("View", 0x0DAD14E8)
if view:
    d = view.data(body)
    print("View 0x0dad14e8 length:", len(d))
    for off in range(0, len(d) - 3, 4):
        val = struct.unpack_from('<I', d, off)[0]
        if 0x0DAD0012 <= val <= 0x0DAD00A5:
            colr = db.get('COLR', val)
            print(f"  +{hex(off)}: COLR {hex(val)} = {colr.data(body).hex()}")

# Look at View 0x0dad14bd (badge view from hide_badge_test.py):
v_badge = db.get("View", 0x0DAD14BD)
if v_badge:
    d = v_badge.data(body)
    print("\nBadge View 0x0dad14bd length:", len(d))
    for off in range(0, len(d) - 3, 4):
        val = struct.unpack_from('<I', d, off)[0]
        if 0x0DAD0012 <= val <= 0x0DAD00A5:
            colr = db.get('COLR', val)
            print(f"  +{hex(off)}: COLR {hex(val)} = {colr.data(body).hex()}")
