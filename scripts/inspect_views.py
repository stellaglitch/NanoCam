from nanocam.img1 import Img1
from nanocam.resources import ResourceDB
import struct

body = Img1.parse(open('firmware/n5g-retailos.dec', 'rb').read()).body
db = ResourceDB(body)

# In firmware-notes.md:
# COLR 0x0dad0012 = ffffffff (white)
# COLR 0x0dad0013 = 000000ff (black, used for text!)
# COLR 0x0dad0028 = 000000ff (black)
# COLR 0x0dad0018 = ffffffff (white)

print("Checking primary text and background colors:")
c12 = db.get("COLR", 0x0DAD0012)
c13 = db.get("COLR", 0x0DAD0013)
c18 = db.get("COLR", 0x0DAD0018)
c28 = db.get("COLR", 0x0DAD0028)

for name, r in [("0x0dad0012 (white)", c12), ("0x0dad0013 (black)", c13), ("0x0dad0018 (white)", c18), ("0x0dad0028 (black)", c28)]:
    print(f"  {name}: offset={hex(r.offset)}, val={r.data(body).hex()}")

# Let's inspect Views referencing 0x0dad0012 and 0x0dad0013:
for v in db.by_type.get('View', [])[:10]:
    d = v.data(body)
    has_12 = d.find(struct.pack('<I', 0x0DAD0012)) != -1
    has_13 = d.find(struct.pack('<I', 0x0DAD0013)) != -1
    if has_12 or has_13:
        print(f"View {hex(v.id)}: has_12={has_12}, has_13={has_13}")
