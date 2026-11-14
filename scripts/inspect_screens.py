from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# Let's see what resources contain image, background, or window definitions
# Check types: View, VCvs, VLyt, ACST, SCST, etc.
print("Resource counts:")
for t in ['View', 'VCvs', 'VLyt', 'ACST', 'SCST', 'TVCS', 'TVCL']:
    print(f"  {t}: {len(db.by_type.get(t, []))}")

# Check what color references exist in TVCS (stylesheets for tables)
for r in db.by_type.get('TVCS', [])[:5]:
    d = r.data(body)
    print(f"TVCS {hex(r.id)}: len={len(d)}")
    for off in range(0, len(d) - 3, 4):
        val = struct.unpack_from('<I', d, off)[0]
        if 0x0DAD0012 <= val <= 0x0DAD00A5:
            print(f"  has COLR {hex(val)} at +{hex(off)}")

# Check what views are associated with screens (SCRN)
for s in db.by_type.get('SCRN', [])[:5]:
    d = s.data(body)
    print(f"SCRN {hex(s.id)}: len={len(d)}, hex={d.hex()[:40]}")
