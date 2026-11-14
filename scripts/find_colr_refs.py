from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# Let's inspect where COLR resources are referenced across View, TVCS, etc.
colr_refs = {}
for code in ['View', 'TVCS', 'TVCL', 'VCvs', 'VLyt', 'ITEM']:
    for r in db.by_type.get(code, []):
        data = r.data(body)
        for off in range(0, len(data) - 3, 4):
            val = struct.unpack_from('<I', data, off)[0]
            if 0x0DAD0012 <= val <= 0x0DAD00A5:
                colr_refs.setdefault(val, []).append((code, hex(r.id), hex(off)))

print(f"Total referenced COLR IDs: {len(colr_refs)} of 148")
for cid in sorted(colr_refs.keys())[:25]:
    refs = colr_refs[cid]
    types = set(t for t, rid, o in refs)
    colr = db.get('COLR', cid)
    print(f"COLR {hex(cid)} ({colr.data(body).hex()}): {len(refs)} refs in {types}")
