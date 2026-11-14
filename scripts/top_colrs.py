from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# Count how many times each COLR ID is referenced across View, VLyt, SORC, TMLT
colr_counts = {}
for code in ['View', 'VLyt', 'SORC', 'TMLT', 'ITEM']:
    for r in db.by_type.get(code, []):
        data = r.data(body)
        for off in range(0, len(data) - 3, 4):
            val = struct.unpack_from('<I', data, off)[0]
            if 0x0DAD0012 <= val <= 0x0DAD00A5:
                colr_counts[val] = colr_counts.get(val, 0) + 1

print("Top 30 most referenced COLR IDs:")
for cid, cnt in sorted(colr_counts.items(), key=lambda x: -x[1])[:30]:
    r = db.get('COLR', cid)
    rgba = r.data(body).hex()
    print(f"  {hex(cid)}: {cnt:3d} refs, rgba={rgba}")
