import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nanocam.img1 import Img1
from nanocam.resources import ResourceDB

img = Img1.parse(Path("firmware/n5g-retailos.dec").read_bytes())
body = img.body
db = ResourceDB(body)

spares = [
    "Test Menu Item (has no ID)",
    "World Wide (TEST)",
]

for s in spares:
    found = [r for r in db.by_type.get("Str ", []) if db.text("Str ", r.id) == s]
    if found:
        r = found[0]
        print(f"'{s}': Str ID = {hex(r.id)}, offset = {hex(r.offset)}, size = {r.size}")
    else:
        print(f"'{s}': NOT FOUND in Str")

# Let's check which string "Test Menu Item (has no ID)" is in photo_camera_menu.py
spare_photo = next(r for r in db.by_type["Str "] if db.text("Str ", r.id) == "Test Menu Item (has no ID)")
print(f"\nPhoto Camera uses spare string ID: {hex(spare_photo.id)}, text: {repr(db.text('Str ', spare_photo.id))}")
