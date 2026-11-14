from nanocam.img1 import Img1
from nanocam.resources import ResourceDB

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

white = []
black = []
others = []
colrs = db.by_type.get('COLR', [])
for r in colrs:
    data = r.data(body)
    rgba = data.hex()
    if rgba == 'ffffffff':
        white.append((r.id, r.offset))
    elif rgba == '000000ff':
        black.append((r.id, r.offset))
    else:
        others.append((r.id, r.offset, rgba))

print("Total COLR:", len(colrs))
print("White (ffffffff):", len(white))
print("Black (000000ff):", len(black))
print("Others:", len(others))
print("\nWhite IDs:", [hex(i) for i, o in white])
print("\nBlack IDs:", [hex(i) for i, o in black])
print("\nOther samples:")
for r_id, off, rgba in others[:25]:
    print(f"  {hex(r_id)}: {rgba}")
