from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# Let's inspect where 0xdad0074, 0xdad0012, 0xdad0084, 0xdad0013 are used in Views
target_colrs = [0x0DAD0074, 0x0DAD0012, 0x0DAD0084, 0x0DAD0013, 0x0DAD004E]

for tc in target_colrs:
    colr = db.get('COLR', tc)
    views = []
    for v in db.by_type.get('View', []):
        d = v.data(body)
        idx = d.find(struct.pack('<I', tc))
        if idx != -1:
            views.append((v.id, idx))
    print(f"COLR {hex(tc)} ({colr.data(body).hex()}): {len(views)} views. First 5: {[hex(vid) for vid, _ in views[:5]]}")
