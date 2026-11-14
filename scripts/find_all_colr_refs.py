from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# Let's search across ALL resource types for where COLR resources are referenced
refs_by_type = {}
for code, res_list in db.by_type.items():
    cnt = 0
    for r in res_list:
        data = r.data(body)
        for off in range(0, len(data) - 3, 4):
            val = struct.unpack_from('<I', data, off)[0]
            if 0x0DAD0012 <= val <= 0x0DAD00A5:
                cnt += 1
    if cnt > 0:
        refs_by_type[code] = cnt

print("COLR references by resource type:")
for t, c in sorted(refs_by_type.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c} references")
