from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# Let's inspect SCST (Screen Stylesheets) and ACST (App Stylesheets)
print("SCST samples:")
for s in db.by_type.get('SCST', [])[:10]:
    d = s.data(body)
    colrs = []
    for off in range(0, len(d) - 3, 4):
        val = struct.unpack_from('<I', d, off)[0]
        if 0x0DAD0012 <= val <= 0x0DAD00A5:
            colrs.append(hex(val))
    if colrs:
        print(f"SCST {hex(s.id)} (len {len(d)}): COLRs = {colrs}")

# Let's inspect VCvs (View Canvas) samples:
print("\nVCvs samples:")
for v in db.by_type.get('VCvs', [])[:10]:
    d = v.data(body)
    colrs = []
    for off in range(0, len(d) - 3, 4):
        val = struct.unpack_from('<I', d, off)[0]
        if 0x0DAD0012 <= val <= 0x0DAD00A5:
            colrs.append(hex(val))
    if colrs:
        print(f"VCvs {hex(v.id)} (len {len(d)}): COLRs = {colrs}")
