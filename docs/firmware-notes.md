# RetailOS firmware notes (nano 5G)

Offsets are into the IMG1 **body** of `firmware/n5g-retailos.dec`, as printed by
`python -m nanocam strings`. Body size is 0x6f2640 bytes.

## The file

- `n5g-retailos.bin`: encrypted, format 3 (x509 signed+encrypted).
- `n5g-retailos.dec`: decrypted by wInd3x, format 4 (plaintext).
- Lots of `pG` byte pairs: `0x4770` is Thumb `bx lr`. The code mixes ARM and
  Thumb-1, using two-halfword `bl` calls and no Thumb-2. The CPU has an **MPU,
  not an MMU** (cp15 c6 region registers, set up around body 0x4b00), which
  points to an ARM946-class core. With no address translation, every address in
  the code is a real hardware address.

## Memory layout

The body holds **two images back to back**:

| Body offset | File offset | Loads at | What |
|---|---|---|---|
| 0x0 – 0x2e27b | 0x600 | **0x22000000** | Early boot: vector table, SoC init, MPU setup, idle loop |
| 0x2e27c – end | 0x2e87c | **0x08000000** | Main OS. Starts with a `hibe` header |

How we know:

- **Early boot:** at body 0x7060 the code does `adr r0, .` and compares the
  result with a stored constant 0x22007060, which is its own linked address.
  The stack is 0x2200ffdc.
- **Main OS:** an exact vote over 400 long strings against every pointer-like
  value in 0x08000000–0x0a000000 gave address = body offset + 0x07fd1d84
  for 152 of the 400 strings. The runner-up got 25. So body 0x2e27c is
  0x08000000.
- To convert: `address = body_offset + 0x07fd1d84` (main OS), or
  `address = body_offset + 0x22000000` (early boot).

UI text (e.g. "Video Camera") and `controller.*` names have **no direct
pointers** even at the right base. They're probably looked up by ID or hash
through a string table. The `*Thread` names are loaded with PC-relative `adr`.

Ghidra project: `C:\Users\marsh\ghidra-projects\iPodCamera`, program
`n5g-retailos.dec`. It holds the main OS at 0x08000000 (ARM:LE:32:v5t). The early
boot image isn't imported yet. Scripts are in `ghidra_scripts/`.

## Boot tests

| Image | Result |
|---|---|
| `n5g-retailos.dec`, unmodified, via `wInd3x cfw run` | Boots to the main menu; Video Camera works |
| `n5g-photocam-rename.dfu`: the 3 copies of "Video Camera" → "Photo Camera" | Main menu shows "Photo Camera"; camera still works |
| `n5g-photocam-menu.dfu`: Composers cell → "Photo Camera" opening the camera (`patches/photo_camera_menu.py`) | Works: "Photo Camera" shows in the main menu and opens the camera |
| `n5g-jpeg-test.dfu` v1: capture constants 7/0xd → 0x27/0x2d | Ran normally, no .jpg. The constants were buffer limits, not flags. |
| `n5g-jpeg-test.dfu` v2 (now `n5g-jpeg-stage3.dfu`): JPEG-path checks test 0x1 instead of 0x20 | White screen and reboot on opening Photo Camera: frames reached the encoder without a file path (assert in `FUN_0811ad10`) |
| `n5g-take-photo.dfu`: center button → TakePhoto (`patches/take_photo.py`) | not tested yet |

So RetailOS has **no integrity check** on its own code or data, and the menu
label comes from one of these three strings, not a separate resource file.

### Which "Video Camera" is which (from neighbouring strings)

| Body offset | Neighbours | Role |
|---|---|---|
| **0x627f1c** | iPod, Music, TV Shows, Podcasts, iTunes U, *Video Camera*, Photos, Videos, Extras, Speakers, Radio, Settings, Shuffle Songs, Now Playing, **Test Menu Item (has no ID)**, Cover Flow, ... | **Main-menu item labels** |
| 0x6295c8 | Camera Roll, Camera Videos, All Unsynced Videos, "Delete all camera videos from your iPod?" | Camera app screens |
| 0x62a8a8 | TV UI, then Artists, Albums, Songs, ... Camera Videos | Probably Settings → Main Menu toggles |

Strings in these pools are 4-byte aligned and NUL-padded. **Nothing points at
them directly**, whichever base address you assume. These searches all came up
empty:
- absolute pointers at any delta (a vote over 300 UI strings was pure noise)
- packed or strided u16/u32 offset tables that keep the menu order
- a table of offsets measured from the "iPod" label

"Test Menu Item (has no ID)" suggests labels are looked up by a **menu item
ID**. Most likely there's an ID → string index table in a different order, or
string lookup by index counting through the pool.

## Camera app

The C++ class names (from RTTI) show the camera app's structure:

| Offset | String | Meaning (guess) |
|---|---|---|
| 0x051bb22 | `TCameraApp`, `N10TCameraApp19TCameraStateMachineE` | the camera app and its state machine |
| 0x051bb70 | `TPodCamera` | |
| 0x051c057 | `GKCameraDevice`, `GKCameraDriver` | low-level camera driver |
| 0x012df1c | `CameraDeviceManager` | |
| 0x0156534 | `GKCameraDriver - camera overflow occurred!` | driver log message |
| 0x00561b4 | `TCCamera`, `TCCameraInitial`, ... | screen controllers |
| 0x0056a7c | `TPhotosGLCntlrLcdCamera` | live viewfinder (shares Photos' GL renderer) |
| 0x0627f1c | `Video Camera` | **main-menu label**, plus 0x06295c8 and 0x062a8a8 |
| 0x06295ac | `Camera Roll` | |
| 0x0637ee8 | `controller.CameraSelected` | menu action when "Video Camera" is picked |

## Still-photo code that seems to already exist

The stock firmware can't take photos, but these strings suggest a photo
pipeline was built and then hidden or left unused:

| Offset | String |
|---|---|
| 0x00ea6fc | `GKImageCaptureThread` |
| 0x00e6800 | `JPEGEncodeThread` |
| 0x00ea780 | `JPEGPreprocessThread` |
| 0x051d89e | `TSilverCameraShutterView` (+ `TShutterAnimationStateMsg`) |
| 0x008eb84 | `CameraShutter` |
| 0x0085e98 | `Resources/Sounds/camera.wav` |
| 0x0633404 | `cameraremote.photo.up` (vs. `cameraremote.video.up`) |
| 0x052202c | `TCameraMediaModel::UnSyncedPhotoListProps` |
| 0x0570902 | `MediaLists_Camera_Delete_Photo_Event_Confirmation` |
| 0x00ca03c | `/DCIM` (camera-style photo folder) |

These are only strings so far. Ghidra has to confirm that real code sits behind
them and isn't just leftover names. If it does, adding a Photo Camera mode
may mostly mean switching existing code back on.

## Code that uses the photo strings (main OS at 0x08000000)

From `ghidra_scripts/CameraXrefs.java` after the re-import (27,363 functions):

| String | Address | Used by |
|---|---|---|
| `GKImageCaptureThread` | 0x080bc480 | `FUN_080bc3f8`, probably creates the capture thread |
| `JPEGEncodeThread` | 0x080b8584 | `FUN_080b8520` |
| `JPEGPreprocessThread` | 0x080bc504 | `FUN_080bc4a0` |
| `Resources/Sounds/camera.wav` | 0x08057c1c | `FUN_08057bc4`, the shutter sound |
| `CameraShutter` | 0x08060908 | code at 0x08060872 (not yet a function) |
| `StartRecord` | 0x080bc7cc | `FUN_080bc69c` |

So the photo pipeline isn't just leftover names: code really does start these
threads and load the shutter sound.

## The camera pipeline (decompiled)

`FUN_0809c478` (Thumb) builds the whole camera pipeline and saves it in a global
singleton at `0x086ba368`. Ghidra hadn't found it as a function at first. It:

1. Creates four buffer queues (`FUN_082251e0(…, 0x11)`): q3, q4, q5, q6.
2. Gets the camera device (`func_0x080b5f80`) and configures it through vtable
   +8 with **640 × 480, stride 640**. If that fails, no stages are built.
3. Builds five stages, each with its own thread:

```
camera ─► GKImageCaptureThread ─► q3 ─► GKImagePreprocessStage1Thread ─┬─► q4 ─► FUN_080bb61c (likely video encoder)
          FUN_080bc3f8                  FUN_080c1d30 (splitter)         └─► q5 ─► JPEGPreprocessThread ─► q6 ─► JPEGEncodeThread
                                                                                FUN_080bc4a0                     FUN_080b8520
```

| Stage | Constructor | Thread body | Notes |
|---|---|---|---|
| Capture | `FUN_080bc3f8` | `FUN_080edc00` | Pulls frames from the device (vtable +0x28), tags them 7 or 0xd, pushes to q3. Flag 0x10 = end of stream |
| Splitter | `FUN_080c1d30` | ? | `GKImagePreprocessStage1Thread`. Builds another sub-stage `func_0x080dc704` |
| Video (?) | `FUN_080bb61c` | ? | Reads q4 |
| JPEG preprocess | `FUN_080bc4a0` | `FUN_080edd8c` | Kind 1 = image buffer (converted); kind 2 = a 0–20 level value |
| JPEG encode | `FUN_080b8520` | `FUN_080ea028` | Encodes buffers flagged 0x20 via `FUN_080f533c` |

**`FUN_080f533c` writes a `.jpg` file.** It builds a path (`FUN_0810a2da`) into
a 1 KB buffer, appends `".jpg"` (0x080f5628), checks free space
(`FUN_0826b8ca(0)` against 0x400), and allocates a width × height buffer. So
the stock firmware can already turn camera frames into JPEG files.

**Still unknown:** whether these JPEGs are full photos or only Camera Roll
thumbnails for videos. The full-size buffer suggests photos. To find out:
- what sets flag 0x20 on a frame (the "take this one" signal), and
- what sends kind-2 buffers.

The UI side is what triggers it.

### Ghidra fixes applied to the saved project
- `FUN_0818eb44` (probably `operator new`; called with object sizes) and
  `FUN_0818edaa` were wrongly marked "does not return", which truncated
  decompiles. Cleared with `ghidra_scripts/FixNoReturn.java`.
- Some Thumb code was decoded as ARM. `Decompile.java <addr>t` redoes it as
  Thumb (run with `-readOnly` to try it without saving).

## How the main menu works (traced from CameraSelected)

The UI is **data-driven**: menu items, screens and transitions are compiled
data that refer to named symbols. Code handles events by comparing names
with `strcmp`.

### 1. Per-item event methods
Small Thumb functions around 0x080dcbb4–0x080de494. Each one posts a named
event, with the name stored inline right after the function, loaded by `adr`:

| Method | Posts |
|---|---|
| 0x080dcc34 | `CameraHilited` |
| 0x080dd08c | `CameraSelected` |
| 0x080dd210 | `PhotosSelected` |
| 0x080dd364 | `VideosSelected` |

The body is roughly `this->vtable[0x1c/4+…](this, "CameraSelected")`, i.e.
post event by name. Siblings exist for Music, Videos, Podcasts, NikePlus,
CoverFlow, GeniusMixes, CameraVideos and more.

### 2. Main menu dispatcher: `FUN_080c3188` (Thumb, ~2 KB)
It's called with an event-handler name and chains `strcmp(name, "HandleXxxHilited")`
… checks, each calling the matching method above. The camera branches are:
`HandleCameraHilited` → 0x080dcc34, `HandleCameraSelected` → 0x080dd08c.
The handler name strings are at 0x080c3c18 onward.

### 3. Symbol table (all UI names → IDs)
- Body **0x59ed54–0x5a5480**: 2,201 records of
  `{u32 name_offset, u32 length+1, u32 symbol_id}`.
- Names are at `0x5add8c + name_offset`. The pool is 4-byte aligned, grouped by
  feature.

Camera and photo symbols:

| ID | Symbol |
|---|---|
| 0x2d9 | `HandleCameraSelected` |
| 0x2db | `HandleCameraHilited` |
| 0x32a | `controller.CameraHilited` |
| 0x32b | `controller.CameraSelected` |
| 0x33d | `controller.EmptyCameraHilited` |
| 0x33e | `MainMenus_Main_Screen_NoCamera` |
| 0x3b6 / 0x3b7 | `controller.PhotosHilited` / `controller.PhotosSelected` |
| 0x1be | `controller.EnterCameraScreen` |
| 0x1bf | `TCCameraInitial` |

### 4. Compiled UI records (`CROS`)
6,804 records tagged `CROS` (bytes 43 52 4f 53) in body 0x11bb30–0x670224.
Layout seen at body 0x5b0800:

```
u32 size (0x10 or 0x18)   u32 type hash (0x0dad1cf9 / 0x0dad1cfb / 0x0dad1cfd)
u32 1                     u32 4 (or 0xc)
'CROS'                    u32 symbol_id
```

The run at 0x5b0800 binds the Pedometer and Photos main-menu items:
PedometerInactiveHilited → Pedometer layout, PhotosHilited, PhotosSelected,
Photos_Screen, then `controller.GotoDefaultLayout`. **No `CROS` record carries
the camera symbols**, so the camera item is defined somewhere else. Candidates:
- u16 symbol-ID lists, e.g. body 0x47763e, which has 0x32b, 0x32c, … and 0x32a
  close together
- a `{0x18, symbol_id, offset}` table at body 0x58c738 (one entry per symbol,
  pointing into another blob)

### 5. Label table (UI text → label IDs)
- Records of `{u32 offset, u32 length+1, u32 label_id}` around body **0x5999e4**,
  with strings at `0x5add8c + offset`, the same pool base as the symbol table.
  1,809 labels decoded.
- **CORRECTION:** this table was decoded off by one record. Use the real `Str`
  resources instead (section 10): **"Video Camera" = `Str` 0x0dad0946**, "Photos"
  = 0x0dad0947. Every label named in sections 5 and 6 below belongs to the
  *next* ID, so for example item 0x9d13 is really Photos, not Video Camera.
- Labels from 0x0dad0c00 up sometimes decode to the wrong text (e.g.
  0x0dad0c05 → "Composers"), so there may be a second table or a different
  base for that range.
- A second table at body 0x595a74 has `{label_id, u32, 0x10}` records (in the
  same 0x0dad0942… order), purpose unknown.

### 6. `CROS` records are 24 bytes
`{'CROS', u32 kind, u32 value, 1, 1, 0xc}`:
- kind 0x80: value is a label ID
- kind 0x9d00 / 0xab00 / 0xa180: value is a small item or resource ID in that
  family (0x9d13, 0xab01, …)

**Menu choice list at body 0x5ef900–0x5efe40:** each entry is one kind-0x9d00
record (item ID 0x9d04–0x9d18) followed by its label twice. Item **0x9d13 =
Video Camera**, 0x9d0d = Photos, 0x9d04 = Videos, 0x9d18 = Voice Memos. It
includes Albums, Songs and the like, so it's probably the **Settings → Main
Menu** on/off list rather than the main menu itself.

Body 0x5e70d4–0x5e72fc is a mixed run of label references: Photos, TV Shows, …,
Video Camera, then a kind-0xa180 record, then "Test Menu Item (has no ID)",
Pedometer, Cover Flow, Playlists, Artists, ... Its structure is unclear.

### 7. These are resources registered by four-character type
The `ITEM` tag (`METI` in the bytes) appears as a code constant once, at
0x08023cb0. `FUN_08023ca4` does `func_0x0802c0e8('ITEM')`, which registers a
resource type. So the UI data is probably a **resource database keyed by type
code and numeric ID**, a bit like classic Mac OS resources. The `CROS` tag
never appears as a code constant, so it's probably handled generically.
**Next:** decompile `func_0x0802c0e8` and the registry it fills. The loader
will show the real record layout, and how an ID like 0x9d13 leads to the
screen Video Camera opens.

### 8. The UI resource database (decoded)

Read by `FUN_081ff738` (find first of a type) and `FUN_081ff80a` (find next),
reached via `FUN_0802c0e8(type)`. It's parsed by `nanocam/resources.py`; try
`python -m nanocam resources firmware\n5g-retailos.dec [TYPE [ID]]`.

```
body 0x58200c  header      { u32 3, u32 data_base (0x2bd80), u32 type_count (40) }
body 0x582018  type table  40 x { u32 fourcc, u32 count, u32 ?, u32 entries_offset (from 0x58200c) }
               entries     count x { u32 id, u32 data_offset (from 0x5add8c), u32 size }
body 0x5add8c  data base   (the same base the symbol and label strings use)
```

There are **14,911 resources in 40 types**: AALI ACST AEVT ANIM CEVT CLov COLR
CSov EEEE FONT ITEM LDTm MASt SANI SCRN SCRT SCST SEVT SLst SORC SRVL SStr SUse
Str StrT T10N TEVT TLIP TLOP TMLT TVCL TVCS TrIN TrIO TrOO TrOU VCvs VLyt VSlt
View.

- The `CROS` records from section 6 are **`SORC` resources** (3,940 of them,
  24 bytes each); "CROS" is just "SORC" in byte-reversed order.
- Resource IDs are mostly in the `0x0dadXXXX` range. Different types share one
  ID for the same screen.

### 9. The Video Camera main-menu row

**`View` 0x0dad14ed** (264 bytes, body 0x682154) is the Video Camera row:
- Two child elements: one tagged `imag` (icon or preview) at +0x44 and one tagged
  `text` at +0xc8. Element IDs are 0x0dad1e7e and 0x0dad1e7f.
- `controller.CameraHilited` (symbol 0x32a) at **+0x80** and
  `controller.CameraSelected` (0x32b) at **+0xf0**.
- Siblings `View` 0x0dad14f6 (`controller.EmptyCameraHilited`) and 0x0dad14f7
  (`MainMenus_Main_Screen_NoCamera`) cover the "no camera content" case.

Referenced from:
- **Screen 0x0dad0868**, which has these resources:
  - `SCRN` (16 bytes)
  - `SCRT`: a list of 47 template views, 0x0dad146a … 0x0dad156c, including
    the camera row at +0x40
  - `SLst`, which points to `SUse` 0x0dad0666: five 0x70-byte view slots,
    0x0dad1470, 0x0dad1474, 0x0dad1475, **0x0dad14ed**, 0x0dad146d
  - **`CEVT`: 770 bytes, not a multiple of 4, so probably compiled event
    bytecode.** That's the likely place where `CameraSelected` becomes "enter the
    camera screen".
- `TMLT` 0x0dad14ed (template, same ID).

The Photos row isn't a View with `controller.Photos*` symbols, so items aren't
all built the same way.

### 10. The main menu, end to end (decoded)

```
TVCL 0xd (and 0xe)    main menu cell list: u32 count (41), then 24-byte cells
                      { 0x10, 'TVCL', u32 cell_id, 0x0dad102b, 0x0dad102c, 1 }
                      cell ids 0x0dad1143 … 0x0dad116b; **cell #22 = 0x0dad1159**
  └ CLov <cell_id>    cell properties: u32 n, then n × { 0x10, u32 property, 1, 4, 'SORC', u32 sorc_id }
                      camera: property 0x0dad1cf9 → SORC 0x399, 0x0dad1cfb → SORC 0x39a
      └ SORC <id>     data source: { 1, 0xc, 'SORC', u32 kind, u32 value, 1 }
                      kind 0x80 = string → value is a Str ID
                      SORC 0x399 / 0x39a → Str 0x0dad0946 "Video Camera"
CEVT 0x0dad0868       the main menu screen's event script (format below)
                      table.cid.229445977.chosen → HandleCameraSelected   (229445977 = 0x0dad1159)
                      table.cid.229445977.linger → HandleCameraHilited
C++ FUN_080c3188      strcmp dispatch: "HandleCameraSelected" → 0x080dd08c → posts "CameraSelected"
```

"chosen" means selected, and "linger" means highlighted.

**Str resources** (`Str ` type, 1,898 of them) are plain NUL-terminated
strings keyed by ID. They're the reliable way to look up text by ID.

**CEVT format.** Bytes, little-endian: `u16 count`, `u16 first`, then entries
of `u8 op (0x31)`, `u16 symbol`, `u16 nargs`, and `nargs × {u16 op, u16 n,
n × u16 symbol}`, then the next `u16 symbol`.

Read as a chain, the pairs are `(table.cid.N.chosen|linger) → handler`. The
handler is either a C++ `Handle*` name (dispatched by `FUN_080c3188`) or a
built-in action. Built-in actions seen so far:
- symbol 0x4a with op 0x111 `[a, screen]`: probably "push screen", e.g.
  Clock_Screen, Alarms_Menu_Screen
- op 0x10c `[x]`
- op 0x6d `[x]` (Notes, Lock, Stopwatch)

The parse with the first layout consumes exactly 770/770 bytes. The handler
pairing is solid. The op-argument meanings are guesses.

### 11. Corrections and the in-place Photo Camera patch

- The "symbol table" in section 3 is really the **`StrT` entry list**, and the
  "label table" in section 5 is the **`Str ` entry list**. Both are
  `{id, offset, size}`, so my hand-made decodes were off by one record.
  `ResourceDB.text()` and `symbol_id()` are correct; the symbol IDs in the
  sections 3–9 tables may be off by one.
- **The CEVT format is now exact:** `u16 count`, then `count × {u16 event, u8 op
  (0x31), u16 handler, u16 nargs, nargs × {u16 action, u16 n, n × u16 arg}}`,
  consuming all 770 bytes. The handler is a C++ `Handle*` name or 0x4a (run
  actions, e.g. `navigator.PushScreen(Search_Main_Screen, …)`,
  `navigator.SwitchLayout(…)`). Parsed by `nanocam.resources.cevt_handlers`.
- All 41 main-menu cells (TVCL 0xd) were mapped. #0 Music … #9 Composers …
  #18 Photos … **#22 Video Camera** … #36 Settings.

**Why not add a new cell?** The firmware finds the resource index at runtime
(no literal points at it). Memory right after the image is used (`.bss`,
heap). Growing the index or appending data isn't safe until that's understood.

**`patches/photo_camera_menu.py`** repurposes cell #9 **Composers** (off by
default in the main menu; Music → Composers still works) with 5 checked
in-place patches, 29 bytes in total:

| Body offset | Change |
|---|---|
| 0x627f80 | `Str` 0x0dad094f "Test Menu Item (has no ID)" → "Photo Camera" |
| 0x5e60d4, 0x5e60ec | `SORC` 0x37f / 0x380 value → `Str` 0x0dad094f |
| 0x5af34f | CEVT: `table.cid.229445964.chosen` handler HandleComposersSelected → **HandleCameraSelected** |
| 0x5af356 | CEVT: `…linger` handler HandleComposersHilited → **HandleCameraHilited** |

Still unknown: the Settings → Main Menu toggle probably still says
"Composers".

### 12. Camera screen: what the center button does

**Event script.** The camera screen's events are in `SEVT` 0x0dad061e–0x0dad0622
(five identical copies, same format as CEVT, parsed by `cevt_handlers`):

| Event | Handler |
|---|---|
| `button.select.up` | **HandleSelect** |
| `button.select.pressandhold` | HandleSelectPressAndHold |
| `button.menu.up` / `button.menu.pressandhold` | PopCamera / PopToMainMenu |
| `cameraremote.action.up` | HandleCameraRemoteSelect |
| `mikey.center.up` / `.delayedup` | HandleMikeyCenter / HandleMikeyCenterReleased |
| `wheel` | HandleWheel |
| `controller.GotoActiveLayout`, `GotoEffectsLayout`, `GotoDiskFull`, `GotoNotIntialized` | 0x4a actions (`navigator.SwitchLayout(Camera_Screen_Active / _Effects …)`) |

Other camera-related event scripts:
- `CEVT` 0x0dad092e, a pause menu: ResumeRecord / StopAndDelete / FinishRecord
- `SEVT` 0x0dad0801–0807, the Voice Memos `StartRecord` family. The camera has no
  such data-level StartRecord, so camera recording is started from C++.

**C++ camera controller dispatcher `FUN_080c85c4`** (Thumb). Its name strings are
at 0x080c8680…; part of it was mis-decoded as ARM, so use
`RedoThumb.java 0x080c85da 0x080c867f` first:

```
cam = FUN_082133c8(this->0x50)
if name in {HandleSelect, HandleCameraRemoteSelect, HandleMikeyCenter, HandleMikeyCenterReleased}:
    if *(u8*)(cam + 0x105) == 2:  post(this, 8)      ← center button
    else: FUN_081940f0(-1)                            (error/assert path)
elif name == "PopCamera":       FUN_082128b6(cam, 0); this[0x64] = 1; post(this, 6)
elif name == (next string):     FUN_082128b6(cam, 0); this[0x64] = 2; post(this, 6)
elif name == "HandleSelectPressAndHold": this[0x68] = 0x0dad061f; this[0x6c] = 2; post(this, 9)
else: FUN_082117ec(this, name, …)                     (base class)
```

`post(this, cmd)` is `FUN_081e1a7c`, a generic state-machine event queue (on the
object at this+0x60). **Command 8 = the center press**, which should toggle
recording; 6 = leave; 9 = long press (effects).

**Next:** find `TCameraApp::TCameraStateMachine` (RTTI string
`N10TCameraApp19TCameraStateMachineE` at body 0x521f21) → typeinfo → vtable
→ the state handlers. Then find where command 8 leads to the recorder.
`FUN_080bc69c` (matches the name `"StartRecord"`) is the recorder's end.
For photo mode, command 8 should trigger one JPEG capture instead.

New Ghidra scripts:
- `Refs.java`: lists references to an address
- `RedoThumb.java <start> <end>`: redo a range as Thumb
- `Decompile.java`: now also re-disassembles code skipped after calls

### 13. Frame flags: how a frame becomes a JPEG

**Frames carry a flag word at frame+0x48.** The test is
`FUN_0824e314(frame, bit)` → `FUN_08206892`: `(*(u32*)(frame+0x48) & bit) != 0`.

**Splitter routing (`FUN_08113810`)**, stage vtable at 0x0852bf7c; loop
`FUN_080eedd0`, decide `FUN_08113ae2`:

| Flag | Goes to |
|---|---|
| 0x2, 0x8, 0x40 | video queue |
| **0x20** | **JPEG queue**; the listener gets code 3 (0x2 → 1, 0x8 → 2) |
| 0x10 | end of stream; goes to both |
| 0x1 | handed to the listener (viewfinder?) |

In the JPEG branch:
- JPEG preprocess turns a kind-1 frame with 0x20 into a kind-2 buffer.
- JPEG encode (`FUN_080f533c`) **writes `<path>.jpg`** for kind 2, if there
  are more than 0x400 units of free space.

**CORRECTION: `FUN_0826726c(pool, owner, kind, LIMIT, wait, w, h)` is a buffer
allocator.** Its 4th argument is the most buffers that `owner` may have out at
once, **not** flags. The capture thread's 7 / 0xd (0x080edcf6 / 0x080edcfa) are
in-flight frame limits.

**Flags come from the camera device.** The capture loop takes a filled frame
from the device (vtable +0x28). It passes the frame on to the splitter queue only
if the frame has flag 0x1 or 0x20. So all viewfinder frames carry 0x1, and a
JPEG frame would arrive from the device already tagged 0x20.

Nothing found so far ever sets 0x20. These all came up empty:
- a scan of all `FUN_0826726c` calls (all pass 0, except the capture loop)
- a search for `ldr/orr/str [rN,#0x48]` with 0x20
- the camera driver vtables (0x084fd850, 0x084fd88c), whose methods are
  power/start/stop and double-buffering only

`snapShot*` strings are Nike+ workout XML tags, not camera code.

**Experiment v1 (invalid):** patching 7 → 0x27 and 0xd → 0x2d only raised buffer
limits. The test ran normally (Photo Camera opened, recording worked, giving
`IMG_0004.mp4`), and no .jpg was written, as you'd now expect.

**Experiment v2:** `patches/jpeg_every_frame_test.py` makes the four JPEG-path
checks test 0x1 instead of 0x20:

| Check | Address of `movs r1,#0x20` |
|---|---|
| splitter: push to the JPEG queue | 0x08113972 |
| preprocess: accept the frame | 0x080eddb8 |
| preprocess: convert kind 1 → kind 2 | 0x080eddd8 |
| encode: write .jpg | 0x080ea03e |

What the result would mean:
- **.jpg files appear:** the JPEG stages run, and only the per-press trigger is
  missing.
- **No files:** the JPEG stages aren't started in camera mode.

**Experiment v2 result:** a white screen and a reboot on opening Photo
Camera. Cause, from the decompiled code: the encoder's path helper
`FUN_0811ad10(frame+0x48)` asserts `frame+0x68 != NULL`. A real JPEG frame
carries a **file path** (frame+0x68) and a **callback** (frame+0x4c..0x54),
and viewfinder frames have neither.

### 14. Apple's dormant TakePhoto API (found)

```c
// 0x0809c3e6 (Thumb), a method of the camera pipeline object
void TakePhoto(Pipeline *p, const char *path, const u32 cb[3]) {
    lock(p + 0x3c);
    assert(strlen(path) < 0x400);
    strncpy(p + 0x4d, path, 0x400);      // photo path, without extension
    memcpy(p + 0x850, cb, 12);           // completion callback (zeros = none)
    *(u32 *)(p + 0x34) |= 0x20;          // request: photo on a coming frame
    unlock(p + 0x3c);
}
```

- **The pipeline object** is created by `FUN_0809c478`, the constructor right after
  it. Its pointer is stored in the global **`*(Pipeline **)0x086ba368`**. The
  capture stage keeps it as `capture[9]`.
- **Per-frame request handling:** `FUN_081cb9b4(p, frame)` runs on every frame the
  capture thread allocates. It turns `p+0x34` bits into frame flags, set with
  **`FUN_081cd7be(frame, bit)`**:
  - **0x20 → 0x40:** arm the request, one frame ahead
  - **0x40 → flag 0x20 + `FUN_0810a2e4(frame, p+0x4d, p+0x850)`:** attach the
    path and callback (setter `FUN_0811ad48`, which copies into a 1 KB buffer)
  - **0x2 → flags 0x2 | 0x40 + `FUN_0810a3a0`** (path + 4-word callback): start a
    video file
  - **0x8 → flag 0x8 (+0x80):** stop recording
  - **0x10 → flag 0x10:** end of stream
  - **0x1 → flag 0x1**
- **The only caller of TakePhoto** is the wrapper `FUN_080857cc(?, path, cb,
  &pipeline)`. It's referenced nowhere, while its neighbouring wrappers sit in
  interface vtables at 0x0851007c / 0x085101e8 / 0x08510354. **The feature is
  built but disconnected.**
- **Path format:** `"%s/%03d%s/%s%04d"` (body 0x28a84c) gives
  `/DCIM/000APPLE/IMG_0004`. The encoder (`FUN_080f533c`) appends `".jpg"`
  itself, so pass the path **without** an extension.

**Plan for the real photo patch** (a code patch, the first one):
1. In the camera controller dispatcher `FUN_080c85c4`, the
   `HandleSelect`/`MikeyCenter` branch (0x080c8602–0x080c860e) currently
   posts command 8 (record toggle). Replace it with a branch to a small Thumb stub.
2. The stub runs `TakePhoto(*(Pipeline**)0x086ba368, "/DCIM/000APPLE/IMG_9000",
   zero_cb)` and returns 1. First version: a fixed name that's overwritten on
   each press. Later: a counter, and only in Photo Camera mode.
3. The stub needs a code cave (unused space in the image) for about 40 bytes of
   code plus the path string.

### 15. First code patch: `patches/take_photo.py`

- **Hook** at 0x080c8602 (camera dispatcher, center-button branch):
  `add r5,#0xff; add r5,#5; ldrb r0,[r5,#1]` → `bl stub; b 0x080c866e`. That
  returns "handled" and skips the command-8 recording toggle.
- **Stub** in the code cave at **0x08276b10** (244 zero bytes of padding at
  0x08276b0c–0x08276c00, with no references; preceded by a function ending
  at 0x08276afe). It runs
  `p = *(Pipeline**)0x086ba368; if (p) TakePhoto(p, "/DCIM/000APPLE/IMG_9000", {0,0,0});`
- `nanocam/thumb.py` is a small Thumb assembler (bl, b, beq, ldr pc, adr, …). It's
  checked against real firmware instructions in `tests/test_thumb.py`.
- Limits of v1: it applies in both camera items, so recording is disabled, and
  every press overwrites `IMG_9000.jpg`.

**Camera files on disk.** Videos are `DCIM/000APPLE/IMG_NNNN.mp4`. Each has an
`IMG_NNNN.DAT` of 315,992 bytes: a Camera Roll metadata file whose magic is
"CamFiPod" (stored byte-reversed). It names the video and holds raw thumbnails.
It isn't a JPEG.

### How to add a "Photo Camera" main-menu item (by adding resources)
All of these are additions to the resource database:
1. **`Str`**: a new ID with "Photo Camera".
2. **`SORC` ×2**: `{1, 0xc, 'SORC', 0x80, <new Str id>, 1}`.
3. **`CLov`**: a new cell ID with properties 0x0dad1cf9 / 0x0dad1cfb → the two
   new SORCs.
4. **`TVCL` 0xd and 0xe**: insert a cell record after cell #22, and bump the
   count from 41 to 42.
5. **Symbols**: add `table.cid.<new decimal id>.chosen` / `.linger` to the
   symbol table.
6. **`CEVT` 0x0dad0868**: add entries mapping them to `HandleCameraSelected` /
   `HandleCameraHilited`. That gives a second entry that opens the camera; a
   photo-mode flag comes later.
7. Check whether the Settings → Main Menu on/off list also needs an entry.

That needs nanocam to **rebuild** the resource index and data region: append
resources, grow the per-type entry lists, and fix every offset. In-place
patching can't do it.

### Plan for a new "Photo Camera" item
1. Decode the `CEVT` bytecode for screen 0x0dad0868 to see what
   `CameraSelected` does, and which list decides the main-menu items and their
   order.
2. Clone `View` 0x0dad14ed (+ `TMLT`) under a new ID, with new hilite/select
   symbols or reused camera ones, and a new label "Photo Camera".
3. Add the new view to `SCRT` / `SUse` and the menu list.
4. Teach nanocam to **rebuild** the resource database: append new resources
   and grow the index. In-place patching can't add entries.

## Next questions for Ghidra

1. Where is `controller.CameraSelected` handled, and how is the main menu
   built? The new "Photo Camera" entry goes there.
2. ~~Who calls `GKImageCaptureThread` and `JPEGEncodeThread`?~~ Answered
   above: `FUN_0809c478` builds them all. Next: who calls `FUN_0809c478`,
   and what sets frame flag 0x20?
3. What does `cameraremote.photo.up` trigger? That may be the existing
   "take photo" entry point.
4. Who calls `FUN_08057bc4` (loads `camera.wav`)? It's called from
   `FUN_0804b0d0`, a large UI dispatcher that decompiles badly.

## 16. Photo mode v2: numbered photos, Video Camera untouched

**v1 result (n5g-take-photo.dfu): it worked.** Pressing the center button wrote
`D:\DCIM\000APPLE\IMG_9000.jpg`: 107,911 bytes, starting FF D8 FF E1 (EXIF), ending FF D9,
640×480. The photo is a real desk shot. Apple's dormant TakePhoto path is fully working.

**Telling the two menu items apart.** Both items used to call HandleCameraSelected. v2 leaves
Photo Camera's `chosen` handler as **HandleComposersSelected** (it only changes the label and
hilite). Then, in the main menu dispatcher `FUN_080c3188`:
- 0x080c393a `bl 0x080dd9ec` (Composers) becomes `bl PHOTO_SEL`, which sets flag = 1 and calls 0x080dd08c.
- 0x080c39bc `bl 0x080dd08c` (Camera) becomes `bl VIDEO_SEL`, which sets flag = 0 and calls 0x080dd08c.

**Shutter.** In the camera dispatcher, 0x080c8602 `adds r5,#0xff; adds r5,#5` becomes `bl SHUTTER`.
- flag = 0: SHUTTER redoes both adds and returns, so the original code at 0x080c8606 records.
- flag = 1: SHUTTER calls TAKE_NUMBERED, drops its return address and `bx`es to 0x080c866e (return 1).

**Numbering.** There is no stored counter. Each press tries n = 0, 1, … up to 9999:
`String s; init(s); sprintf(s, "/DCIM/000APPLE/IMG_%04d.jpg", n); if (!exists(s, 0)) break;`
It then runs vsnprintf into a stack buffer, cuts the name at ".jpg", and calls TakePhoto.

**Helpers identified for this:**

| Address | Function | Evidence |
|---|---|---|
| 0x0827f444 | String init | sets the vtable and a NULL buffer |
| 0x0818ebc0 | String destroy | |
| 0x081909a4 | c_str | |
| 0x08196c00 | sprintf into a String | uses 0x08273378 = vsnprintf(buf, n, fmt, va_list*) |
| 0x08196cb8 | **file exists**(String, vol), filesystem vtable +0x50 | 0x08240f00 tries one Notes file, falls back to another if it returns 0, then opens it |
| 0x0827a610 | **delete**(String, vol), vtable +0x5c | 0x0809da18 deletes a file only if exists() is true |
| 0x0825c548 | build "%s/%03d%s/%s%04d" from a packed asset ID | folder = (id & 0xffffff) >> 14, file = id & 0x3fff |

**Risk: the flag byte lives in the code cave (0x08276bc4).** v1 only read from the cave, so v2
is the first test that writes to it. If the MPU makes that region read-only, opening either camera
will fault.

`patches/photo_mode.py` builds `firmware/n5g-photo-mode.dfu` (8 patches, 212 of 240 cave bytes).

| Image | Result |
|---|---|
| n5g-take-photo.dfu | **works**: IMG_9000.jpg, 640×480 |
| n5g-photo-mode.dfu | **works**: IMG_0000–0005.jpg (all 640×480), then Video Camera recorded IMG_0005/0006.mp4. Writing the flag byte in the cave is fine. |

## 17. Shutter sound (photo mode v3)

**Sounds.** The firmware contains `Resources/Sounds/camera.wav` (path string at 0x08057c1c).
It's loaded by `FUN_08057bc4`, a method of `TCameraApp::TCameraStateMachine` (vtable near
0x08536af4); that's probably the record chime. There's also an RTTI name
`TSilverCameraShutterView` / `TShutterAnimationStateMsg`, an unused shutter animation that
hasn't been traced.

**The click-wheel click is `FUN_08032870()`**, which takes no arguments:
```
if (!*(u8*)0x085509d0) *(u8*)0x085509d0 = load(0x086ca1fc, "Resources/Sounds/clicker.wav");  // 0x082682ac
if (!loaded) return;
player = 0x086ca1fc; player[0x42] = 4; *(u32*)(player+0x20) = 0x7fff; play(player, 1) /*0x08196642*/; player[0x40] = 0 (for each linked player)
```
(At 0x08032884 the bytes are `c0b2` = `uxtb r0,r0`, an ARMv6 instruction, so this core is ARMv6-class.
That's why Ghidra's v5t language choked on it.)

**v3 shutter.** After TakePhoto, the code loads camera.wav into the click player, sets the same
fields and plays it. It then clears 0x085509d0 so the next wheel click reloads clicker.wav.

**Fitting it in.** The cave is the only zero run in the code region, so v3 now starts at 0x08276b0c
(244 bytes, all used). To make room:
- the two mode stubs share one tail
- the callback lives on the stack
- the pipeline is kept in r5
- the firmware's own camera.wav string is reused
- the search stops at n = 8192 (`lsrs r0,r4,#13; beq loop`)
- the name is cut in the String's own buffer (c_str 0x081909a4) instead of a second vsnprintf

Image: `firmware/n5g-photo-shutter.dfu`. **Works**: the shutter sound plays on each photo, the wheel click is normal afterwards, and Video Camera still records. The photos do NOT appear in Camera Roll or in the Photos app.

## 18. Camera Roll .DAT format (decoded from the iPod's own files)

Header (0x1c bytes):
```
"doPIFmaC", u16 1, u16 1, u16 0x1c, u16 0x24, u16 8, u16 3, u32 0x1c (info offset), u32 0x4d240 (thumb table offset)
```

Info (0x24 bytes):
```
char name[16] ("IMG_0006.mp4"), u32 1001, u32 duration in ms (0x2bcf = 11.2 s), u32 0,
u16 288, u16 384 (content size), u8 1, 3 bytes padding
```

Thumbnails are RGB565 and start at 0x40. The table at the end is {u32 artwork format, u32 offset} × 3:

| Format | Size | Contents |
|---|---|---|
| 0x437 | 80×80 | square crop |
| 0x42a | 64×64 | square crop |
| 0x43f | 384×384 | the 288×384 portrait frame, centred with black bars |

These format IDs match the 0x437 / 0x42a / 0x43f constants in FUN_08057a70.

`nanocam/camroll.py` parses this format and builds a .DAT from a JPEG. It produces the same size and
offsets as the real files.

**Test 1:** a hand-made `IMG_0008.DAT` (name "IMG_0008.jpg", kind 1001, duration 0) was copied
next to `IMG_0008.jpg`. Result: not tested yet.

**Test 1 result:** not listed. The DAT said kind 1001 (video) but pointed at a .jpg.

**Kinds (FUN_0825a314):** JPG/JPEG → 501, MP4 → 1001, MOV → 1002. FUN_0825061c(k) is "video"
(k is 1001 or 1002); FUN_08250630(k) is "photo" (k == 501).

**Test 2** (IMG_0007.DAT, kind 501): **listed**, with a thumbnail, but it **doesn't open**. The date
shows as "Aug 11, 2879, 3:151 PM" and the length as "0 seconds".

**A camera-photo browser already exists in the Photos app's UI.** Photos screen SEVT 0x0dad06f8
(and 06f9–06fb) contains:
```
controller.PushScreen_BrowseCameraPhotos    -> navigator.PushScreen PhotosGL_Camera_Screen / PhotosGL_Camera_Screen_Thumbs
controller.PushScreen_BrowseCameraPhotosAlt -> navigator.PushScreen PhotosGL_Camera_Screen / PhotosGL_Camera_Alt_Screen_Thumbs
```
Symbol IDs are 0x4dd and 0x4de. The C++ name string is at 0x0809a3f4 (adr at 0x0809a35a).
By contrast, Camera Roll in the Videos menu (`controller.CameraVideosSelected`) opens
`MediaLists_Camera_All_Videos_Screen`, a video list. That probably explains why a 501 item
appears there but won't open.

**The camera-photo browser is compiled out.** `FUN_0809a29c` is the Photos app's album-chosen
handler. For an ordinary row it does:
```
n = FUN_08232e52() ? FUN_0821aebc(lib) : FUN_0824d280(lib, row);
if (n > 0) post("PushScreen_BrowseCameraPhotos" ...);
```
Both `FUN_08232e52` ("camera photos enabled") and `FUN_0821aebc` ("camera photo count") are
`return 0;` stubs. The UI screens (PhotosGL_Camera_Screen) are in the resources, but the code that
would supply camera photos to them was left out of this build. The Photos app with no synced
photos just says "No photos".

Conclusion: on-device photo viewing needs one of these:
- (a) photos in the Photos app's own synced database (iPod_Control/Photos: Photo Database plus
  .ithmb thumbnails), written from the PC
- (b) a new viewer/back end written into the firmware (large)

## 19. Looking for code space for a bigger patch

- The image ends at 0x086c43c4, and the RAM after it is in use (.bss; for example, the click
  player is at 0x086ca1fc). So the image can't simply grow.
- The 244-byte cave at 0x08276b0c is the only zero-filled gap in the code region, and it's full.
- `ghidra_scripts/DeadFuncs.java` lists functions Ghidra sees no references to. It found 57 of at
  least 512 bytes.
- Raw scan of the image:
  - Thumb BL targets and 32-bit pointers rule out 42 of them, leaving 15 "clean" (about 14 KB).
  - All 15 are ARM-mode code (an ARM library around 0x0839f000–0x083fc000). Every one has ARM
    `B`/`BL` instructions jumping to it from outside, for example several from a dispatcher around
    0x083a0a60. Ghidra just hadn't disassembled those callers. **So none is proven dead. Don't reuse them.**
- The remaining option for code space: disconnect a feature we don't need from its only entry
  points and reuse its code. That needs a careful choice.

**Candidate features to give up:**
- **Games:** not worth it. The firmware has only small menu, screen and control classes for games
  (TCGamesMenu, TCGameScreen, TCGameControls, 4 vtable slots each, code around 0x080b3000–0x080b6200).
  There are no Klondike/Maze/Vortex strings; the games themselves live on disk (iPod_Control/Games_RO).
- **Pedometer, Radio:** they run background services (accelerometer, tuner), so they're risky to cut.
- **Voice Memos:** probably shares the audio recording path with the video camera's microphone.
- Next: trace how PhotosGL_Camera_Screen gets its photos. That tells us how much code is needed,
  and therefore how much space to free.

## 20. The camera-photo viewer in Photos: what exists and what's gated

**Present in the firmware:**
- `TPhotosGLCntlrLcdCamera`: vtables at 0x0850f4a8 and 0x0851eafc, 102 slots. It overrides
  0x080bdc97, 0x080bd945, 0x080bdb1d and 0x080bdc95 of `TPhotosGLCntlrLcd`.
- `SArtLibraryDCIM`: vtable 0x084ff83c. Constructor `FUN_082737c4`, destructor `FUN_082665c4`.
  It's created and destroyed around many photo-library calls, including the album count
  `FUN_0824d280`, so it may simply be the general photo library.
- `SArtAlbumDCIM`: vtable 0x084fb530, created at 0x0818c1fe and 0x0830112a.
- `TCameraMediaModel::UnSyncedPhotoListProps`, the "photos not yet synced" list props.
- The UI screens: PhotosGL_Camera_Screen* plus delete and confirm dialogs.

**Gates:**

| Function | Body | Called from |
|---|---|---|
| `FUN_08232e52` ("camera photos on") | `return 0` | 0x0809a31e (album chosen), 0x080d2ffa (row type), 0x080d316a (album row builder) |
| `FUN_0821aebc` ("camera photo count") | `return 0` | 0x0807ca56 (Photos "no content" check: shows "No photos" only if library count == 0 **and** this == 0), 0x0809a328 |

**Assert:** `FUN_080d3140` (album row builder) calls `FUN_08232e52` and **asserts it's 0**
(`if (on) FUN_081940f0(-1)`). The row logic has no case for a camera row. So turning on the
gate alone would trip that assert.

**Cheapest experiment** (3–4 small in-place patches, no cave needed):
1. Make `FUN_0821aebc` return 1. The Photos app should then stop saying "No photos".
2. Make `FUN_08232e52` return 1.
3. Remove the assert in FUN_080d3140.

Then see what the Photos app shows and whether choosing it opens `PhotosGL_Camera_Screen` with
our JPEGs. A crash only means a reboot.

**Gate test image:** `patches/camera_photos_gate_test.py` builds `firmware/n5g-camera-photos-test.dfu`.
It's photo_mode v3 plus three patches:
- 0x0821aebc `0020` → `0120`
- 0x08232e52 `0020` → `0120`
- 0x080d3194 `03d0` → `03e0` (beq becomes b)

Result: **no change**. The Photos app still says "No photos", so that decision is made somewhere else.

**Why v1 changed nothing:** the main menu decides first. At 0x080dd210 (PhotosSelected) it runs
`FUN_0824d280(lib, 0)`; if that's 0 it posts `EmptyPhotosSelected` (→ NoContent_Screen_NoPhotos),
otherwise `PhotosSelected`. **v2** also changes 0x080dd230 `bne` → `b`, so the menu always enters
the Photos app. Image: `firmware/n5g-camera-photos-test2.dfu`. Result: **opening Photos crashes**.

**Narrowing down the crash** (each image is photo_mode v3 plus some of the gate patches):

| Image | Patches | Result |
|---|---|---|
| n5g-photos-A-menu-only.dfu | menu bypass only | **Photos doesn't open** (no crash; selecting it does nothing) |
| n5g-photos-B-menu-count.dfu | menu bypass + count = 1 | **crash** on opening Photos |
| n5g-camera-photos-test2.dfu | all 4 | crash on opening Photos |

If A crashes, the Photos app can't cope with an empty synced library, and the camera gates aren't the cause.

**Conclusion of the narrowing down:** the camera-photo-count gate gets Photos past its empty
check (A doesn't open, B gets in), and then it crashes with an empty synced library. Entering via
the Photos main screen looks like a dead end.

## 21. A better entry point: Camera Roll → EnterPhotosScreen

The Camera Roll list screens (SEVT 0x0dad0623 / 0x0dad0624, used by SLst 0x0dad084b / 084c,
`TCCameraLocalMediaList`) contain:
```
controller.EnterPhotosScreen -> navigator.PushScreen PhotosGL_Camera_Screen / PhotosGL_Camera_Screen_Thumbs
```
They also have Delete-Photo-Event confirmations. So Apple meant selecting a photo in Camera Roll to
open it in the camera photo viewer.

**The poster is dormant:** `FUN_0809c8c0(this, flag)` has no callers and no pointers:
```
SArtLibrary lib; FUN_0819938c(&lib, 0);              // generic photo library query object (0x54 bytes)
album = flag ? FUN_08246466(&lib) : FUN_081991ee(&lib);
FUN_08245afc(photosModel = FUN_081b071c(), album);   // set the Photos model's current album
FUN_082513ca(photosModel, 0, 0); photosModel[0x55c] = !flag;
(optional notify through FUN_081b115c)
post(this, "EnterPhotosScreen")                       // FUN_0819d8bc
```
`SArtLibraryDCIM`'s constructor `FUN_082737c4(obj, …)` calls `FUN_0819938c(obj, 0)` and then sets
the DCIM vtable, so it's a drop-in replacement for the first line.

**Plan:**
1. In FUN_0809c8c0, change `bl 0x0819938c` (0x0809c8cc) to `bl 0x082737c4`, so it builds a DCIM library.
2. In Camera Roll's select handler (TCCameraLocalMediaList `HandleSelect`), when the chosen item is
   kind 501, call FUN_0809c8c0(this, 0) instead of starting playback.

That's only a few bytes plus a small hook.

## 22. Camera Roll's select handler

`FUN_080847d4` (Thumb) is the select handler. It gets the item and reads its type byte `[item+4]`,
then branches through a switch8 table at 0x08084804 (`blx 0x0818f268`). Items are
`TCameraMediaModel::CameraItemProps` (typeinfo 0x084ece84), cast with `FUN_081908fc` (dynamic_cast):

| Type | Branch | Class | Action |
|---|---|---|---|
| 2 | 0x08084832 | `UnSyncedPhotoListProps` (0x084ecea4) | `FUN_081d1294(this, item)`, then `FUN_0809c95c(this, 0)` |
| 3, 4 | 0x080848aa / 0x0808485e | `UnSyncedVideoFileProps` (0x084eceb0) | play (0x0824b554, GotoNowPlaying) |
| 5 | 0x08084910 | synced content | library query |
| 6 | 0x0808480e | `UnSyncedAllContentProps` (0x084ecec8) | `FUN_081d1188(this, item)`, then `FUN_0809c95c(this, 0)` |
| 0, 1, other | 0x08084958 | | return 1 |

`FUN_0809c95c` sets the Photos album but shows nothing, which fits "listed but doesn't open".
Its dormant twin `FUN_0809c8c0` posts `EnterPhotosScreen`.

**Test:** 0x08084858 `bl 0x0809c95c` → `bl 0x0809c8c0`
(`patches/camera_roll_photos_test.py` → `firmware/n5g-camera-roll-photos-test.dfu`). Not tested yet.

## 23. ⚠ The DCIM scanner deletes whole items

**Observed:**
- Test 2's IMG_0007.jpg plus .DAT were listed, then later disappeared.
- A second IMG_0007.jpg (taken 2026-11-06 4:43) plus a fresh kind-501 .DAT also disappeared,
  after booting n5g-camera-roll-photos-test.dfu. Camera Roll showed nothing.
- The user did not delete them.
- JPEGs **without** a .DAT (IMG_0000–0005 on 2026-11-04) survived several boots.

**Mechanism** (the scanner around 0x0809b408–0x0809b7b0):
- It recognises `%s/%s  is a DCIM formated entity`, looks it up in the camera DB
  (`FUN_0824c854`), and calls the importer (vtable +0xd8, probably `FUN_08156444`).
- The importer returns **3** if the .DAT can't be read, or if the DAT's kind doesn't match the
  kind from the file extension (`FUN_0825a314`).
- On failure the scanner formats `"%s%04d"` + `".*"` (strings at 0x0809b70c / 0x0809b714), loops
  over the matches with `FUN_0827bd38`, logs `--- Deleting %s ---`, and calls
  `FUN_0827a610` (delete) at 0x0809b684.
- **So it deletes IMG_NNNN.\* (the JPEG too).**

Why the kind-501 item was accepted once and then deleted on a later boot is still unknown. The
already-in-DB path probably checks more (the bogus date "2879" suggests a field we fill wrongly).

**Rule until this is understood:** don't put photo .DATs on the iPod. Copy any photo you want to keep
off first. Backups are in firmware/dcim-backup.

### 23a. Decoding what the scan checks

**The DAT reader, `FUN_08250478(dat, &id, dir, folder, prefix)`**, called from the importer
`FUN_08156444` at 0x08156476:
1. Path = `FUN_0825c548(id, …)` + ".DAT". If `exists()` is false, it fails.
2. Reads 0x1c header bytes and requires all of:
   - `doPI` `FmaC`
   - u32 at 0x08 == 0x00010001
   - header size ≤ 0x1c, info size ≤ 0x24, entry size ≤ 8
3. Seeks to the info offset and reads the info block; it must read the full size.
4. If count > 0, it reads count × 8-byte table entries from the table offset (it doesn't read the pixels).

Our photo DATs pass all of these. The importer then needs `info.kind == kind(extension)` (501
for .jpg), which also passes. **It returns 3 only on those two failures.**

**The purge loop**, in `FUN_0809b27c` (the scan routine that contains the 0x0809b408 code, called
from 0x0807f758):
```
set purge(8, 10000, 8)                       // FUN_08278178, IDs 0..9999
... scan fills sets (see FUN_0809b408 part) ...
for id in purge:
    dir = FUN_0823bc3c(id, …)                // "/DCIM/NNNAPPLE"
    pattern = sprintf("%s%04d", "IMG_", id) + ".*"
    for each name in dir (FUN_0827bd60 / FUN_0827bd38):
        if wildmatch(name, pattern) (FUN_081d4666):
            log("--- Deleting %s ---"); delete(path) (FUN_0827a610)   // or rmdir for directories
    purge.erase(id)
```
Later in the same routine, IDs found on disk get added to the DB set at `scanner+0xac`.

**Still open:** exactly which condition puts an ID into `purge`. The relevant code is the 0x0809b408
part, which Ghidra still treats as a separate function. Static decoding has stalled here.

Ghidra project change: no-return was cleared on FUN_08252590 (set-iterator deref, wrongly flagged)
and on FUN_081940f0 (the panic/assert, which genuinely doesn't return). Decompiles now show code
falling through after asserts.

### 23b. Purge experiment 1 (2026-11-06)

Throwaway files in D:\DCIM\000APPLE. Originals are in firmware/dcim-backup.

| File | What it is | Tests |
|---|---|---|
| IMG_0050.jpg + .DAT | copy of backup IMG_0003.jpg, kind-501 DAT from camroll.py | does a photo item get purged? |
| IMG_0051.jpg | same JPEG, no DAT | control: a JPEG alone |
| IMG_0052.mp4 + .DAT | backup IMG_0001.mp4 + its real DAT, name field changed to IMG_0052.mp4 | control: does any item copied in from a PC get purged? |
| IMG_0000.jpg | the user's real photo (backed up) | — |

Procedure: stock boot → Camera Roll (note what's listed) → reboot → Camera Roll → plug in and compare.
Result: **every file was gone**: IMG_0000.jpg (the user's photo), IMG_0050.jpg/.DAT, IMG_0051.jpg
(no DAT!) and IMG_0052.mp4/.DAT. A new IMG_0000.mp4 + .DAT from 2026-11-06 7:14:18 is present.
The user **recorded a video** during the test.

### 23c. What sets off the purge, and a safe naming rule

- **Trigger:** `FUN_0807f648` mounts the camera's DCIM database on a volume. It makes sure the folders
  exist, then calls the scan `FUN_0809b27c`, which runs the purge. That happens when the camera starts
  or records, not at boot.
- **How the scan routine is built:**
  1. `FUN_08256bf8` walks the folder (0x0809b310).
  2. A loop over the known-item set at `scanner+0xac` runs the "is a DCIM formated entity" / lookup /
     import code (0x0809b352–0x0809b5a0, including the 0x0809b408 part). That loop fills set
     `sp+0xb0`, which is copied to the purge set `sp+0xa0` (0x0809b5b6).
  3. The purge loop deletes `IMG_NNNN.*` for every ID in the purge set (0x0809b5c0–0x0809b6c2).
  Ghidra doesn't reach loop 2's body, so the exact rule for what gets purged is still unknown.
- **Observed:**
  - 2026-11-04: JPEGs the camera wrote with no DAT survived many camera sessions, and IMG_0005.jpg
    coexisted with IMG_0005.mp4.
  - 2026-11-06: after files were copied in from a PC, a video was recorded at 7:14 (it became
    IMG_0000.mp4, since the DB was empty). Every IMG_* file was deleted, including a JPEG with no DAT,
    a real video + DAT, and the camera's own IMG_0000.jpg from 5:09.
- **The purge only ever matches names built from `"IMG_"` + 4 digits.** So photos saved under
  another prefix (for example `PIC_NNNN.jpg`) can never be matched or deleted.
  That's a one-string change to photo_mode.py's FMT (same length, so EXT_AT is unchanged).

**v4: `firmware/n5g-photo-pic.dfu`.** photo_mode.py's FMT is now `/DCIM/000APPLE/PIC_%04d.jpg`,
the same length, so the cave layout is identical (fmt at 0x08276be4, 244/244 bytes). Everything else
is the same as v3: numbered photos, shutter sound, and Video Camera untouched.
Result (2026-11-06): **works**. PIC_0000–0004.jpg (7:31:12–22), all 640×480 and valid, plus
videos IMG_0001–0003.mp4 (7:30:50–7:31:00), and IMG_0000.mp4 (7:14) survived. The videos were
recorded *before* the photos, though, so "photos survive a later recording" is **not yet shown**.
**Follow-up:** after PIC_0005/0006 (7:33:06/16), IMG_0004.mp4 was recorded at 7:33:30, and all seven
PIC_ photos survived. **PIC_ naming is safe from the purge.**

### 23d. The purge rule, decoded with Capstone (loop at 0x0809b352–0x0809b5a0)

Capstone is now in the venv. Ghidra won't decode this block.

```
for folder in folders:                                   // uxth id from set sp+0xe4, "%03d%s" -> "000APPLE"
  for entry in listdir(folder):                          // FUN_0827bd60 / FUN_0827bd38
    log("%s/%s dir = %s", yes/no)
    if !match(entry, entity_pattern): continue           // FUN_081d4666
    log("%s/%s is a DCIM formated entity")
    id = FUN_080c9664(folder, entry); if id == -1: continue
    if known.contains(id): continue                      // FUN_0824c854(scanner+0x54, id, 0)
    ok = FUN_0827a2cc(path)                              // also yields a volume index at sp+4
    if ok:
      res = volume[idx].importer->vfunc[+0xd8](id, entry, 0)   // FUN_08156444
      if res == 0:
        purge.insert(id)                                 // FUN_081d8518
        if known.add(id) == 0 /*newly added*/: notify; return 10
        else: FUN_08218f34(id); continue                 // already known: refresh the .mp4/.DAT
      assert(res == 3)
    if purge.add(id) == 0 /*newly added*/: notify; return 10
    // otherwise it stays in purge
purge_copy = purge -> purge loop deletes IMG_%04d.* for each id   (0x0809b5c0)
```

`FUN_082628d0(set, id)` is just `FUN_082410c4(set, id)`: it returns 1 if the id is already in the set.

**What this explains:**
- The import fails (res 3) whenever the .DAT is missing or wrong. So **a JPEG with no .DAT whose
  number isn't already a known item is a purge candidate.**
- On 2026-11-04 the camera's IMG_0000–0007.jpg shared their numbers with videos already in the known
  set, so they were skipped. That's why they survived.
- On 2026-11-06 the known set was empty or different, so IMG_0051.jpg (no DAT), IMG_0050 and so on
  were new, and they were purged.

**Still open:**
- The exact meaning of `return 10`. FUN_0807f648 treats a nonzero result as "not mounted", so a later
  pass presumably finishes the scan.
- Why the kind-501 IMG_0007 item (whose import should succeed) was later purged.

**Safe rule for photos in Camera Roll:** an IMG_ photo needs a valid kind-501 .DAT *before* any
camera start. Never leave an IMG_NNNN.jpg without a .DAT on the iPod.

### 23e. Camera Roll viewing test (2026-11-06)

IMG_0060.jpg (a copy of PIC_0003.jpg) plus a kind-501 .DAT from camroll.py. The whole folder was
backed up first to firmware/dcim-backup/2026-11-06_*.
Procedure: boot n5g-camera-roll-photos-test.dfu → Camera Roll → select IMG_0060 **without starting
the camera first**. **Not possible:** Camera Roll is only reachable from inside the camera app,
so starting the camera (and its scan) always comes first. Result: Camera Roll listed **only videos**;
IMG_0060 wasn't shown, and **both of its files were purged**.

### 23f. Where static analysis stalls, and a pragmatic fix

- File attributes don't differ: the iPod's own files and copied ones are all just Archive.
  The iPod's DATs have creation time 1980-01-01.
- `FUN_08256bf8` only registers observers. `FUN_080bafa8` only makes sure the folders exist
  (`--- prepping collection %d ---`, `--- %s is not a directory, deleting ---`).
- So far I can't tell which "known" set survives reboots, or whether the importer's own photo set
  (+0x54) is the same set the scan checks. If it is, a successful photo import would itself land the
  ID in the purge list, which would explain why photo items always get deleted. That's unconfirmed.
- **Pragmatic fix:** disable the deletion itself. At 0x0809b684, `bl 0x0827a610` (delete) becomes
  `movs r0,#0; nop`. The purge loop then still runs but deletes nothing, and orphaned files just stay
  on disk. Then the Camera Roll photo test can run without anything being removed.

**No-purge test image:** `patches/no_purge.py` builds `firmware/n5g-no-purge-test.dfu`. It's the PIC_
photo firmware, plus the Camera Roll select → 0x0809c8c0 patch, plus 0x0809b684 `def1c4ff` →
`0020c046`. IMG_0060.jpg + .DAT were put back on the iPod. Result: **not listed**, and later both files were
gone again. The only code that uses the `.*` wildcard is the purge (0x0809b748, used at 0x0809b640),
so the deletion probably happened **after a reboot into stock firmware** (cfw run only lasts until the
next reboot; the stock firmware mounts DCIM and scans at boot). So "not listed" (the import or listing
fails in the patched firmware) and "deleted" (stock purge later) are separate issues.
Retest: put IMG_0060 back, boot the no-purge image, check Camera Roll, then plug in **without rebooting**.

**No-purge v1 retest** (checked without rebooting): **not listed**, and **files gone even in the
patched firmware**. So there's a second deleter: the camera DB's RemoveItem method
`FUN_0812d454(db, id, delete_files)`. It adjusts the photo/video byte totals, then, if
`delete_files` is set, calls `FUN_0809da18`, which deletes the item's .DAT (0x0809daa6) and its media
file (0x0809dab0). It's called through a vtable. Likely story: the photo is imported, then removed
again with its files, which is why it's never listed.
**v2** (`firmware/n5g-no-purge-test2.dfu`) also changes 0x0812d50e `bl 0x0809da18` → `movs r0,#0; nop`.
IMG_0060 was put back. Not tested yet.

**No-purge v2 result:** IMG_0060 was still deleted.
**v3** (`firmware/n5g-no-purge-test3.dfu`) also changes the purge's other branch, 0x0809b67e
`bl 0x08234698` → `movs r0,#0; nop`. The listing flag `[sp+0x5c]` may mean "is a file" rather than
"is a folder"; FUN_08234698 contains its own delete call (0x0823472a). IMG_0060 was put back.
Not tested yet.

**No-purge v3 result:** IMG_0060 was still deleted, even with all three delete calls switched off.
**Probable real cause:** the files were always copied in while the iPod ran **stock** firmware in disk
mode. Ejecting returns to stock RetailOS, which remounts DCIM and runs the scan and purge (FUN_0807f648)
**before** the user ever enters DFU to boot the test image. So none of the no-purge images ever got a
chance to protect the files.
**Correct procedure:** cfw run the test image first → plug in (disk mode under the patched firmware) →
copy the files → eject (back into the patched firmware) → Camera Roll → plug in again without rebooting.

**No-purge v3 result:** **crashed after eject**. Cause: after every deletion, the purge loop
closes and re-opens the folder listing (0x0809b688–0x0809b6a6) to restart. With deletion NOP'd, the
same file matched forever, allocating 0x44 bytes per pass, until it crashed.
**v4** (`firmware/n5g-no-purge-test4.dfu`) leaves the delete calls alone and instead skips the
whole purge loop: 0x0809b788 `beq 0x0809b78c` → `b 0x0809b78c`. It keeps the RemoveItem change at
0x0812d50e. Not tested yet.

**No-purge v4 result:** no crash, and **IMG_0060's files survived**, so skipping the purge loop works.
Still **not listed** in Camera Roll. Next idea: test 2's photo, the only one ever listed, was numbered
right after the existing videos. Renamed the test item to IMG_0005 (next after IMG_0004.mp4) under the
still-running test4.
**IMG_0005 result:** still **not listed**, so the number isn't the reason.

**Camera Roll listing, first look:**
- The camera-photo gates (FUN_08232e52, FUN_0821aebc) are called only from Photos app code
  (0x0809a31e, 0x080d2ffa, 0x080d316a, 0x0807ca56, 0x0809a328), not from Camera Roll.
- `FUN_0807e84c` is the **TCameraMediaModel constructor**. It embeds one fixed props object for each
  row type: 3 VideoFile, 2 PhotoList, 4, 1, 5, 6 AllContent (vtables of PhotoList: 0x080847b4 /
  0x080849f0 / 0x08536de0). So rows aren't created per item. Camera Roll shows a single "photo list"
  row (type 2) under some condition, presumably a non-zero photo count from the DCIM DB's photo set.
- Next: find the model's row-count / row-type method (it uses these props) and see what count it
  reads for the photo row.

### 23g. How Camera Roll builds its rows

- `FUN_081d7944(model, row, &item)` returns the item at a row. Fixed rows sit at model `+0x1d0`,
  `+0x1d4` (synced, uses `+0x108`) and `+0x1d8` (all content, only if `+0x1e4`). Item rows are the
  range `[+0x1dc, +0x1dc + +0x1e0)`.
- For an item row, `FUN_0821f510(model, row, &count, &group)` gives an entry with `id` at +0xc.
  `kind = FUN_0821e274(id) = id >> 24`:
  - **kind 0 → photo-list row** (props +0x138)
  - otherwise a single video (count < 2, props +0x10c, opens via FUN_08244364) or a video group (+0x150)
- `FUN_0821fe5c(model, row)` builds each row's title and date text.
- **Item IDs:** `FUN_0822be44(folder, file) = (folder & 0x3ff) << 14 | (file & 0x3fff)`. That's the
  ID the scan makes, with top byte 0. The top byte is a collection number (see
  `--- prepping collection %d ---` in FUN_080bafa8), so video items must carry a non-zero
  collection byte from somewhere else.
- `FUN_0827a2cc(scanner, path, &collection_index)` picks the collection for a file, by matching the path
  against each collection's folder string (scanner `+0x2c`). The decompile stops at 0x0827a30c on a
  **`uxtb` (ARMv6) instruction**.

**Tooling problem:** this core is ARMv6-class (uxtb at 0x08032884 and 0x0827a30c), but the Ghidra
project was imported as ARM:LE:32:v5t. So any function that uses v6 instructions decompiles truncated.
Re-importing or setting the language to an ARMv6 variant should unblock this and the remaining
listing logic.

**FUN_0827a2cc (collection picker), via Capstone:**
```
lock(scanner+4)
if !scanner[0xdc]: result = 2
else for i = 0 .. while collections[i].importer (scanner+0x2c, 12-byte entries {String path; importer*}):
    if FUN_08193d0c(entry->path_cstr (arg1+4), collections[i].path) == 0: *out = i; result = 0; break
    i = uxtb(i + 1)                       // the ARMv6 instruction at 0x0827a30c
(otherwise result = 0xd)
unlock; return result
```
A file is imported only if its path matches one collection's path string. If it matches none, the
result is 0xd, the scan treats that as a failure, and the item goes to the purge list.
Next: read the collection table (what paths are registered, and by whom).
An ARMv6 copy is being imported into the Ghidra project as `n5g-retailos-v6.dec` (ARM:LE:32:v6,
base 0x08000000, file offset 0x2e87c, length 0x6c43c4).

### 23h. ARMv6 re-analysis

- Imported `n5g-retailos-v6.dec` (ARM:LE:32:v6) into the same Ghidra project; auto-analysis took 404 s.
  **Use this program from now on** (run scripts with `-process n5g-retailos-v6.dec`). It decodes
  `uxtb` and friends, and it finds callers the v5t program missed (FUN_0827a2cc ← 0x0809b446).
  The v5t program is kept for reference, but its RedoThumb, FixNoReturn and RemoveFunc edits were not
  carried over.
- Classes:
  - the mount `FUN_0807f648` is **TCameraMediaModel vtable slot 43 (+0xac)**
  - the importer `FUN_08156444` is **TCameraMediaDatabaseInterface slot 54 (+0xd8)**
  So the camera model registers its database interface as a collection, and the same importer
  handles both photos and videos. A .jpg in /DCIM/000APPLE probably matches that same collection.
- **Current hypothesis for "not listed":** a new item found by the scan makes it `return 10`, and
  FUN_0807f648 treats a nonzero result as a failed mount (`[0x37] = 0`). The caller may then roll
  back newly found items through RemoveItem, which deletes their files (the second deleter) and
  never lists them. Next: find the caller of vtable +0xac and what it does when the result is 10.
- The 12 `ldr …,#0xac]; blx` call sites are on other classes (for example the volume loop in
  FUN_080b3108), so the mount's caller wasn't found that way.
- **v5 test** (`firmware/n5g-no-purge-test5.dfu`) = v4 plus 0x0809b4e4 `b 0x0809b53a` → `b 0x0809b56e`.
  After a new item is added, the scan continues to the next entry instead of returning 10. If photos
  then appear in Camera Roll, the early 10 was what blocked them. Not tested yet.
- **v5 result:** still **not listed**. The early `return 10` isn't (or isn't the only) blocker.

### 23i. Where this stands (2026-11-06)

Working and safe: `n5g-photo-pic.dfu` (numbered PIC_NNNN.jpg photos, shutter sound, Video Camera untouched).

Camera Roll photo viewing is still blocked. What's been ruled out:
- the DAT format (the reader's checks all pass)
- the file number
- the purge deleting the files (fixed in the test images)
- the RemoveItem delete
- the scan's early return 10

Static analysis can't show what actually happens to the item at run time. The next realistic
steps need run-time visibility, which means redirecting the firmware's debug log (FUN_0821df80; the
scan logs every entry) to a file. That needs far more code space than the 244-byte cave, so it
means reclaiming space first (section 19). Alternatively, the Photos-library-from-PC route needs no
firmware changes.

**Baseline retest (photo-pic firmware, no Camera Roll patches):** IMG_0005 (copy of PIC_0003) plus a
kind-501 DAT, copied in under n5g-photo-pic.dfu, then eject → Camera Roll: **not listed**. So test 2's
success (IMG_0007 listed with the bogus date "Aug 11 2879") **can't be reproduced** with the same DAT
generator. Differences from test 2 that remain:
- in test 2, the DAT was added under **stock** firmware and the iPod was **rebooted**, so the item
  was seen by a boot-time scan rather than an eject-time scan
- in test 2, videos IMG_0000/0001 (2014) were the only other items
- test 2 was the first photo item ever introduced (any persistent camera DB state is unknown)

**Exact test-2 repeat (stock firmware, file added in disk mode, normal reboot, then Camera Roll):**
**not listed.** So test 2 can't be reproduced even under the same procedure. The remaining
differences are persistent state (test 2 was the first photo item ever, and the camera DB's
persistent storage hasn't been found) and the specific item (ID 7, alongside only two 2014 videos).
**Camera Roll photo viewing is parked here.**
**Disk-mode repeat** (hardware disk mode via Select+Play, IMG_0007 = copy of PIC_0003 plus a kind-501
DAT, eject → automatic restart → Camera Roll): **not listed** either. Every procedural variant of
test 2 now fails, so the difference must be persistent state or something about the original item.

## 24. The TakePhoto completion callback

- The wrapper `0x080857cc(?, path, cb, &pipeline)` just forwards the caller's `cb` to TakePhoto, and
  nothing references the wrapper. So the code that was meant to supply the callback (presumably to
  register photos) isn't in this build.
- The JPEG encoder `FUN_080f533c(frame)`:
  ```
  FUN_0810a2da(frame, path_buf, &cb, 1)           // path_buf = frame path (+0x48 area), cb = {fn, ctx, byte}
  append ".jpg"; if free space ≤ 0x400 or frame[9] != 2: cb.fn(path_buf, 1 /*failed*/, 0, cb.ctx)
  … encode, write EXIF (date "%04d:%02d:%02d %02d:%02d:%02d", "FW %s Sens R2.1"), write file …
  if (*(u8*)0x08550950) FUN_08106838(path_buf, raw, w, h)   // DEBUG: byte-swaps the raw frame and writes <name>.yuv
  cb.fn(path_buf, 0 /*ok*/, 0, cb.ctx)
  ```
- **So a completion callback is called as `fn(const char *jpeg_path, int failed, 0, void *ctx)`**,
  after the file is closed. That's the natural hook for registering a photo.
- `FUN_08106838` is not a thumbnailer. It's a debug raw-frame (.yuv) dump, off by default (flag byte = 0).
- **What a registration callback would need:**
  1. Make the three RGB565 thumbnails (80², 64², 384² letterboxed). The raw frame isn't available in
     the callback, so it would have to decode the JPEG, or the hook would have to sit in the encoder.
  2. Write the .DAT.
  3. Add the item to the camera DB (importer / known set).
  Realistically that's 0.5–1 KB of new code, more than the 244-byte cave. And step 3 runs into the
  same unknown "not listed" blocker as the hand-made DATs (section 23i).

## 25. Code space, round 2 (using the ARMv6 analysis)

**Option 1, unused code** (raw scan for Thumb BL / ARM B / 32-bit pointers):

| Code | Bytes | Status |
|---|---|---|
| 0x0809c8c0 EnterPhotosScreen poster | 156 | **not free**: called from 0x080846e6 (Camera Roll code) |
| 0x08106838 .yuv debug dump | 144 | free once its debug-gated call at 0x080f55da is removed |
| 0x080857cc TakePhoto wrapper | 22 | free (its only "ref" is a stray ARM decode) |

DeadFuncs on the v6 program lists 243 unreferenced functions of at least 128 bytes. None of the Thumb
ones in 0x08000000–0x08300000 passes the raw scan (every one has some call-like hit), so none is
proven dead. **Total usable: about 166 bytes.**

**Option 2, other languages' text:** **not in the firmware.** No French, German or Spanish UI words
appear anywhere in the image (UTF-8 or UTF-16), so localisations must come from disk. The resource
database (960,841 bytes) is English plus layout and logic: SUse 183 KB, View 175 KB, SEVT 117 KB,
SORC 98 KB, StrT 64 KB, Str 43 KB, and so on.

## 26. Voice Memos as a code-space donor

- 17 Voice Memos classes (TVoiceMemosApp, TVoiceMemosModel(+_Import), TCVoiceMemos, …Idle,
  …Loading, …MainMenu, …ContextMenu, …TimedStatus, …LabelSelectMenu, plus their
  TSilverCntlrTransitionAddon<> wrappers). Their vtables hold 271 method pointers, of which **182
  appear only in Voice Memos vtables**.
- `ghidra_scripts/FuncSizes.java` (v6 program): 84 of those are recognised functions, totalling
  5,434 bytes; **5,232 bytes have no callers outside the set**. Another 98 aren't yet recognised as
  functions, so the real total is larger.
- The largest are **screen-controller methods**, which only run when a Voice Memos screen is pushed:
  - `TCVoiceMemosMainMenu[85]` 0x080bc69c (302 bytes)
  - the TransitionAddon slot [68] for each controller, about 184 bytes each: 0x080a41a0 (TCVoiceMemos),
    0x080a5834 (Idle), 0x080a887c (TimedStatus), 0x08069304 (Loading), 0x080a9224 (LabelSelectMenu),
    0x080a8548 (ContextMenu), 0x080a753c (MainMenu)
  - `TCVoiceMemosIdle[68]` 0x080b8ad8 (116 bytes)
  - Avoid TVoiceMemosModel methods (for example 0x0803de08, 160 bytes): models may be created at boot.
- So **about 1.6 KB** is available just from controller methods that run only inside the Voice Memos
  screens. That's enough for photo registration (est. 0.5–1 KB). To make it safe, the way into Voice
  Memos (its menu item's handler) should be cut so those screens can never open.

## 27. Photo + clip: getting photos into Camera Roll through the recorder

**The key fact:** Camera Roll lists only items the iPod's own recorder registered. Anything copied in
is purged, even a genuine recorded video with its real DAT (experiment 1, IMG_0052). So photos get
into Camera Roll by making the recorder produce an item for each one.

**Stopping from the JPEG callback is unsafe:** `FUN_081e1a7c` (the dispatcher's `post(this, 8)`)
isn't a queued message. It starts a state-machine transition directly and asserts if one is pending
(`this+0x54` non-zero, or `this+0x5c` set). Calling it from the encoder thread would race the UI.

**Design (two presses):** the mode flag at 0x08276be0 gets a third value.

| Value | Meaning |
|---|---|
| 0 | Video Camera |
| 1 | Photo Camera |
| 2 | Photo Camera, clip running |

```
SHUTTER2 (0x08106838, 40 bytes):
  flag == 0 -> original path (record as usual)
  flag == 1 -> TAKE_NUMBERED (PIC_NNNN.jpg + shutter sound); flag = 2; original path (= start clip)
  flag == 2 -> flag = 1; original path (= stop clip)
original path = adds r5,#0xff; adds r5,#5; return to 0x080c8606 (state == 2 check, then post(8))
```
- Space: SHUTTER2 lives in the debug .yuv dump `FUN_08106838` (144 bytes). Its only call,
  0x080f55da (behind the zero debug flag), becomes `nop; nop`.
- The hook at 0x080c8602 now calls SHUTTER2. The old SHUTTER in the cave is left unused.
- `patches/photo_clip.py` builds `firmware/n5g-photo-clip.dfu` (10 patches). Not tested yet.
- Open question: whether the camera's state byte is still 2 while recording. Apple's own stop goes
  through the same path, so it should be.

## 28. The stock Photos library (placeholder-slot idea)

After an iTunes sync of the 10 `placeholders/slot_NN.jpg` files, the library is at **`D:\Photos`**
(not iPod_Control). It's backed up in `firmware/photos-db/`.

- `Photo Database` (mhfd, 11,708 bytes). Each photo is an `mhii` (ids 100–109) with 4 `mhni` children
  `{format, offset, size, geometry}` plus an mhod type 3 file name (`:Thumbs:F####_1.ithmb`).

| File | Format | Contents | Slot stride |
|---|---|---|---|
| F1087_1.ithmb | 0x43f | 384×384 RGB565, letterboxed (geom 0,48,384,336) | 0x48000 (294,912 bytes) |
| F1081_1.ithmb | 0x439 | **a baseline JPEG, 640×480**, letterboxed; variable size (21–26 KB) in a fixed 0x4b000 (307,200-byte) slot | 0x4b000 |
| F1079_1.ithmb | 0x437 | 80×80 RGB565 | 0x3200 |
| F1066_1.ithmb | 0x42a | 64×64 RGB565 | 0x2000 |

- F1087, F1079 and F1066 are the same formats as the Camera Roll DAT thumbnails (camroll.py makes them).
- **F1081 is just a JPEG.** The camera's own 640×480 JPEGs (45–190 KB) fit the 300 KB slot. The
  DB's size field would need raising (from the PC tool) so larger JPEGs aren't truncated.
- **Format-use test:** slot 01 (id 100) was relabelled on the iPod: F1087 = "87" on blue, F1081 = "81"
  JPEG on red, F1079 = "79" on green, F1066 = "66" on purple. Viewing it shows which file feeds the
  grid and the full-screen view. Not checked yet.

**Format-use result:** grid thumbnail = **F1066 (64×64)**; full screen = **F1087 (384×384)**.
F1081 (the JPEG) and F1079 weren't seen; they're probably TV out or other views.
So the on-device writer needs F1087 and F1066 only.

**Plan:** the encoder's debug-dump call `FUN_08106838(path, raw, w, h)` at 0x080f55da is the hook.
It gets the raw frame before JPEG compression. Point it at a new writer that converts and downscales
into slot = the PIC number, at offsets n×0x48000 (F1087) and n×0x2000 (F1066). Code is about
300–450 bytes, so it needs the Voice Memos donor space (section 26).

**Step 1, raw format:** `patches/yuv_dump_test.py` → `firmware/n5g-yuv-dump-test.dfu`. That's the
photo firmware plus the debug flag 0x08550950 set to 1, so each photo also writes PIC_NNNN.yuv
(the frame, byte-swapped in 16-bit pairs). Not tested yet.
**v1 result:** no .yuv was written (PIC_0015–0018.jpg only). The flag byte is read only by the encoder
(literal 0x080f5690) and nothing writes it, so it's probably zeroed at boot (bss-like).
**v2** (`firmware/n5g-yuv-dump-test2.dfu`) was meant to NOP the `beq` at 0x080f55d0, but a failed script
edit meant it was **built as v1 again** (no .yuv; PIC_0019–0022). The photos' EXIF ("Yuiop", "FW 1.0.2
(34A20020) Sens R2.1") confirms FUN_080f533c is the encoder. **v3** (`firmware/n5g-yuv-dump-test3.dfu`)
really has the NOP (checked by disassembly). Not tested yet.

**v3 result: it works.** PIC_0023–0028 each got a 614,400-byte .yuv (backed up in `firmware/yuv/`).
- The .yuv file decodes as **UYVY** (mean squared error 4 against the JPEG, which is compression
  noise; every other order is >1400). The dump swaps 16-bit pairs before writing, so **in memory the
  frame is YUYV** (Y0 U Y1 V), 640×480, row-major, landscape (the same orientation as the stored JPEG).
- Displaying it upright needs a 90° rotation (the JPEG uses EXIF orientation for this).
- So the slot writer (hooked at 0x080f55da with r0 = path, r1 = frame, r2 = 640, r3 = 480) must:
  read YUYV, convert to RGB565, rotate 90°, and downscale to 288×384 inside 384×384 (F1087) and to
  64×64 (F1066). Note the dump modified the live buffer in place, but only after the JPEG was encoded.

## 29. The Photos-slot writer

`patches/photos_slot.py` builds `firmware/n5g-photos-slot.dfu` (14 patches: photo_mode v4 plus 5).

| Address | Change |
|---|---|
| 0x082003dc | Voice Memos entry (the only callee of both HandleVoiceMemosSelected branches): `push {r4,lr}` → `bx lr`. Voice Memos can no longer open. |
| 0x080f55d0 | Debug-dump flag check → NOP |
| 0x080f55da | Debug-dump call → `bl WRITE_SLOTS` (r0 = path, r1 = YUYV frame) |
| 0x080bc69c | **WRITE_SLOTS**, 260/302 bytes (TCVoiceMemosMainMenu[85]). slot = PIC number mod SLOTS (10). Writes F1087 (384 rows: frame rotated 90° CW, 288×384 at x = 48, black bars) and F1066 (64 rows from the centre 480² square) through a 768-byte row buffer on the stack (frame 796 bytes, sp kept 8-aligned). |
| 0x080a9224 | **PIX**, 182/184 bytes (TCVoiceMemosLabelSelectMenu[68]): YUYV → RGB565 (R = Y + 359v/256, G = Y − (88u + 183v)/256, B = Y + 454u/256, clamped), plus the two path strings. |
| 0x080a8548 | **OPEN_SEEK / WRITE_ROW / CLOSE**, 100/184 bytes (TCVoiceMemosContextMenu[68]). Open with `FUN_0827f35c(new(0x54), path, 0, 0, [0x400, 1, 0])`; seek with `FUN_0827ddec(f, _, slot × stride, 0, [0])`, closing and skipping if that fails; write with `FUN_0823b61a(f, len, row, &written)`; close with `f->vtable[1](f)`. |

**Verified in emulation:** `tests/emulate_photos_slot.py` runs the three blocks in Unicorn, with
Python stubs for new/open/seek/write/close, on firmware/yuv/PIC_0027.yuv. Both outputs match a numpy
reference bit for bit, at the right offsets (slot 7: 0x1f8000 / 0xe000), with balanced stack. The
pictures are upright, letterboxed and correctly coloured. (It takes about 100 s, so it isn't in pytest.)

**Unknowns that only the device can answer:** whether opening for writing truncates the .ithmb
(backups are in firmware/photos-db/; a truncated file makes the seek fail, so the writer skips it);
whether the Photos app caches thumbnails; and timing (the write happens on the encoder thread).

**🎉 Device result (2026-11-06): it works.** PIC_0029 (20:38) showed up as placeholder #10 (slot 9) in the
stock Photos app, both as the grid thumbnail and full screen. All four .ithmb files kept their sizes,
so opening for writing does **not** truncate. Slot 9 of F1087 read back from the iPod is the upright
photo, letterboxed. No caching problem: it appeared without a reboot. The library after the test is
backed up in firmware/photos-db-after/.

**200-slot version:**
- `placeholders/` now holds slot_001…slot_200.jpg: blank black 30×40 (still 3:4 portrait, so iTunes
  uses the same letterbox geometry), 651 bytes each. Each slot still costs about 610 KB on the iPod.
- The writer now computes `slot = (PIC number + offset) mod slots`, with
  `offset = default_offset(slots, next_number)` so the next photo lands in slot 0 (top of the grid).
- Emulated PIC_0031 with 200 slots and next = 30: lands in slot 1 (0x48000 / 0x2000), bit-exact.
- `firmware/n5g-photos-slot200.dfu` = `photos_slot.py … 200 0` (rebuilt after the user deleted the
  old PIC_ photos, so numbering restarts at PIC_0000): **PIC_0000 → slot 0**, offset 0.

**Shrinking the library:** `nanocam/photodb.py` (`image_refs`, `compact`). It packs one format's
pictures tightly, at 512-byte alignment, and rewrites the mhni offsets (test: `tests/test_photodb.py`).
Applied to the 200-slot library: **F1081 went from 61,440,000 to 1,740,800 bytes**, and all 200
JPEGs still decode. The library is now about 64.9 MB (was about 124.6 MB). The pre-change copy is in
`firmware/photos-db-200/`. iTunes rebuilds everything at full size on the next photo sync, so rerun
`compact(Path('D:/Photos'), 1081)` afterwards.

### 29a. Hiding unused placeholders (album-count test)

Photo Database structure (200-slot library):
- mhfd → mhsd(1) → **mhli** (image list; its third word = 200 images)
- mhsd(2) → **mhla** (1 album) → **mhba** at 0x308fc: +12 = 1 data object, **+16 = item count (200)**,
  +20 = album id 0x13b, then 200 `mhia` entries

**Test:** set the mhba item count at **0x3090c** from 200 to 3 (the compacted DB was backed up first as
`firmware/photos-db-200/Photo Database.compacted`). If the grid then shows 3 pictures, the camera can
write `slot + 1` there to reveal photos as they're taken. Result: **Photos showed 0 pictures**, not 3.
The app seems to reject an album whose count disagrees with its mhia children, rather than trusting
the count. So hiding by count alone doesn't work. Restoring the count to 200.

## 30. Hiding the recording overlay in Photo Camera

- The camera screen is SUse 0x0dad0618. It uses VCvs 0x0dad1648 (layout override → SORC 0x1a8,
  Camera_Screen_Active), View/TMLT 0x0dad1470 (752 bytes, the main screen) and **View/TMLT 0x0dad14bd**
  (396 bytes) = a 3-element overlay:

| Offset | Element | Details |
|---|---|---|
| 0x044 | `imag` 0x0dad1dbf | COLR 0x0dad0012 |
| 0x0c8 | `imag` 0x0dad1dc0 | COLR 0x0dad0028 |
| 0x14c | `text` 0x0dad1dc1 | COLR 0x0dad0013, FONT/Str 0x0dad00a6 "Helvetica" |

  This is probably the record dot and the timer. Each tag is followed by a word 0x00010000 (offsets
  0x048, 0x0cc, 0x150), probably flags.
- The timer text is formatted by `FUN_081b15f8` ("%02d:%02d:%02d…"), reached via the wrapper
  FUN_0804dc14 in camera app code.
- **Test:** `patches/hide_rec_overlay_test.py` → `firmware/n5g-hide-overlay-test.dfu` is photos_slot200
  plus those three words set to 0, in **both** modes (body offsets 0x67c140 / 0x67c1c4 / 0x67c248).
  **Result: the timer and dot were still there** (the labels worked). Either it's the wrong view or
  the wrong field.

## 31. Labels: "Camera"

- The photo item's main-menu label (the spare Str 0x0dad094f) is now **"Camera"** (it was "Photo Camera").
- The home screen's split-screen camera preview text is **Str 0x0dad0bff** "Video Camera". It's used
  through SORC 0x322 in preview View 0x0dad14e8 (the 264-byte main-menu preview panes are
  0x0dad14e6–0x0dad14f8). It's now **"Camera"**, which shows for both camera items.
- Unchanged: Str 0x0dad0946 "Video Camera" (the Video Camera item, CLov 0x0dad1159, plus
  CLov 0x0dad11d4, probably the Settings → Main Menu list). Str 0x0dad0a67 "Video Camera" has no
  resource reference that I've found.
- photo_mode.py now expects 5 menu patches. Rebuilt n5g-photos-slot200.dfu (15 patches) and
  n5g-hide-overlay-test.dfu (18 patches) with the new labels.
- **v2 test:** the timer is most likely text **0x0dad1c88** in the main View 0x0dad1470 (at +0x2b0).
  It's the element whose data source the camera's VCvs 0x0dad1648 binds to SORC 0x1a8 (a dynamic
  source: kind 0xa480, value 0xa488). The dot is probably imag 0x0dad1c87 (+0x22c). Their post-tag
  words are 0x00010000 / 0x00010100. v2 (`firmware/n5g-hide-overlay-test2.dfu`) clears bit 0x00010000
  in both. **Result: still there.** So bit 0x00010000 isn't visibility (or it's the wrong element).
- **v3 test (positive identification):** `patches/timer_binding_test.py` → `firmware/n5g-timer-binding-test.dfu`
  rebinds VCvs 0x0dad1648 +0x18 from SORC 0x1a8 (live) to SORC 0x399 ("Video Camera" text).
  **Result: no change.** Text 0x0dad1c88 isn't the timer (or that binding isn't what feeds it). The
  timer and dot are probably drawn by another view (status bar?) or by code. Next: get a photo of the
  screen to see exactly what is drawn and where.

- **Photo of the screen (2026-11-06):** the indicator is a small dark rounded **badge** at the top right
  holding a red dot and the text "0:00:00". That's 3 elements, which matches **View 0x0dad14bd**
  (imag 1dbf, imag 1dc0, text 1dc1), the v1 target. So v1 had the right view, and the post-tag word
  isn't visibility.
- COLR resources are 4-byte RGBA (148 of them). The badge's colours are 0x0dad0012 = ffffffff (white,
  probably an image tint), 0x0dad0028 = 000000ff and 0x0dad0013 = 000000ff. **0x0dad001a = 00000000
  (transparent).**
- **v4 test:** `patches/hide_badge_test.py` → `firmware/n5g-hide-badge-test.dfu` repoints the badge
  view's three colour refs (+0x5c, +0xe0, +0x168) to 0x0dad001a, in both modes. **Result: still there.**
  So View 0x0dad14bd probably isn't what's drawn (another orientation or layout copy?).
- Only one view in the database has the badge pattern (2 imag + text, Helvetica): 0x0dad14bd, used
  only by SUse 0x0dad0618. Yet neither its flags nor its colours made a visible difference.
- `getRecordedDurationMs` (0x084679a0) belongs to an accessory remote-UI method table
  (0x081408d4), not the badge.
- **Open question:** whether edits to `View` resources take effect at all. Str/SORC/CEVT edits did
  (labels, menu), but **no View edit has ever produced a visible change**. A sanity test (changing an
  obvious colour in a view that's always on screen) would settle that. Parked for now.

## 32. Upside-down photos

- Test photos (PIC_0003 normal, PIC_0004 upside down) both had EXIF orientation 6: **the camera ignores
  the accelerometer for stills.**
- Screen rotation: `*(u32*)(FUN_081ab630() + 0x290)` = 0 / 90 / 180 / 270 degrees. The camera's
  rotation handler (HandleScreenRotation in FUN_082117ec) copies it via FUN_080e5d66 into cam+0x13c
  (90→4, 180→2, 270→3, else 1).
- The camera's JPEGs always keep EXIF orientation as a big-endian u16 at **byte 54** (checked on 8 photos).
- Writer changes (photos_slot.py):
  - **SETUP** (region D) stores the path and `flip = (rotation == 180)` in the writer's frame (FLIP at sp+792, PATH at sp+796; frame 804 bytes)
  - **PIXF** (region C) mirrors sampling coordinates (x → 639 − x, y → 479 − y) when flipped, so the slot gets a 90° anticlockwise rotation
  - **FINISH / FIX_EXIF** (region D, TCVoiceMemosTimedStatus[68] 0x080a887c, 152/184 bytes) writes 0x08 at byte 55 of the JPEG
  - Sizes: WRITE_SLOTS 272/302, PIX 182/184, helpers 132/184.
- Emulated with the UI angle at 0 and at 180: both match the reference; EXIF is untouched or set to 8 as expected.
- Assumption to verify: 180 is "upside down" when holding the iPod with the wheel at the top. Landscape
  (90/270) photos are still saved as portrait.

## 33. Landscape photos (90 and 270 degrees)

Portrait upright and upside down were confirmed on the iPod (section 32). This adds sideways shots.

| UI angle | Photos-app slot (F1087 / F1066) | JPEG EXIF orientation |
|---|---|---|
| 0 | frame turned 90 CW, 288x384 centred | 6 (untouched) |
| 180 | turned 90 CCW (frame mirrored through its centre) | 8 |
| 90 | frame as-is, **landscape**: 288x216 at rows 84..299 of the 384x384 slot, black above and below | 1 |
| 270 | the same, turned 180 | 3 |

- The slot is portrait (the Photo Database letterboxes every picture to 288x384), so a landscape shot is
  letterboxed inside that area. F1066 takes the centre 480x480 square either way.
- **Which of 90 and 270 is which is a guess** (90 = frame as-is). If a landscape photo comes out upside
  down, swap the two angles (`EXIF_FOR_ANGLE` and SETUP's checks).
- Code layout in `patches/photos_slot.py`, now five Voice Memos donor methods:

| Region | Donor | Used |
|---|---|---|
| A 0x080bc69c | TCVoiceMemosMainMenu[85] | WRITE_SLOTS 224/302 |
| B 0x080a9224 | TCVoiceMemosLabelSelectMenu[68] | PIX 182/184 |
| C 0x080a8548 | TCVoiceMemosContextMenu[68] | OPEN_SEEK, WRITE_ROW, CLOSE, PIXF 128/184 |
| D 0x080a887c | TCVoiceMemosTimedStatus[68] | FINISH, FIX_EXIF 132/184 |
| E 0x080a5834 | TCVoiceMemosIdle[68] | SETUP, SAMPLE87, SAMPLE66 176/184 |

  The per-pixel coordinate maths moved out of the writer into SAMPLE87 and SAMPLE66 (their own routines
  in region E); PIXF now takes the flip flag in r3; the writer frame is 804 bytes (LAND at sp+800).
- Verified in Unicorn (`tests/emulate_photos_slot.py <yuv> <n> <outdir> 200 0 <angle>`, about 100 s per
  angle) at 0, 90, 180 and 270: F1087 and F1066 match the numpy reference bit for bit at the right offsets,
  and the EXIF byte at offset 55 is untouched / 8 / 1 / 3. Landscape output is letterboxed correctly.
  The test frame was shot portrait, so it shows the scene on its side. The check is the mapping, not
  the "real" upright.
- Built `firmware/n5g-photos-slot200.dfu` (17 patches, `photos_slot.py ... 200 0`), 29 tests pass.
  Not tested on the iPod yet.
- Tooling note: the project moved to `C:\Users\marsh\Dropbox\Coding_Projects\iPodCamera`.

## 34. Dark Mode toggle (replaces Settings > General > Rotate)

- **The setting.** The Rotate row's handler `ToggleSetting_Rotate` is FUN_08089cb8 (strcmp dispatch at
  0x0808980a). It flips a bool preference: `prefs = FUN_0827f4e4()` (= FUN_0818ed5c, singleton stored at
  **0x0855115c**, created on first use), `prefs->vtable[0x4c](prefs, key, u8 *out)` reads,
  `vtable[0x3c](prefs, key, &value, 0)` writes. The key is `*(char **)0x08550bbc` = "General.Rotate"
  (the key-pointer table for all settings is around 0x08550b60).
- **Who reads it:** only three places, each `...; ldrb r0,[r3]; cmp r0,#0; beq skip`:
  0x08088308, 0x080b7b60, 0x080bd344 (rotate-to-Cover-Flow logic).
- **Colours.** Code fetches a resource with `FUN_081a3f86(manager, type, id)` → pointer to its data
  (`manager = FUN_081a3f7c()`; it walks a manager chain calling vtable[0x74](mgr, type, id, &out)).
  Colour users then read the RGBA word straight from that pointer (0x08040f86, 0x0802e17a, 0x0809dd54, …).
  254 call sites in total, all types.
- **`patches/dark_mode_toggle.py`** → `firmware/n5g-dark-toggle.dfu` (10 patches; also part of
  `build_full_firmware.py`):
  - the getter's tail (0x081a3faa) becomes `bl HOOK`; for type 'COLR', when General.Rotate is on, HOOK
    returns a pointer into a table of dark colours (`dark_theme_palette.COLOR_MAP`, 20 colours) instead
  - the three readers above get `movs r0,#1`, so rotation always behaves as "On"
  - the row is labelled "Dark Mode" (dark_mode_setting.py)
  - space: TCVoiceMemos[68] 0x080a41a0 (HOOK, 112/184 bytes) and TCVoiceMemosIdle[68] 0x080a5834
    (tables, 101/184 bytes)
- **Verified in emulation only** (`tests/emulate_dark_mode.py`, Unicorn, real image): off → all 148
  colours stock; on → exactly the 20 mapped colours change; no preferences object → stock; other
  resource types untouched; stack and r4–r7 preserved. **Not yet run on the iPod.**
- **To check on the device:** whether the palette itself looks right (the COLOR_MAP choices are untested;
  backgrounds drawn from bitmaps won't change), and whether screens already open keep their old colours
  until they're rebuilt (toggling may need leaving Settings, or a restart, to show everywhere).

### 34a. Backgrounds are bitmaps (first on-device result)

- **Result of the first build on the iPod:** text turned white (so the COLR hook works on the device),
  but **the background stayed white**. Backgrounds aren't COLR fills.
- Bitmaps are in `Resources/UI/SilverImagesDB.LE.bin` on the iPod (not in the OS image). The image DB
  object (size about 0xcc300) keeps one 0x18-byte cache entry per id: `{data, file offset, size,
  refcount, next, prev}`. `FUN_08270104(db, id)` loads and returns the bitmap, `FUN_08155d2c` /
  `FUN_0815d8c8` retain / release by id, and `FUN_0831faec` evicts entries whose refcount is 0.
- Screens get a bitmap through the **same getter as colours**: `FUN_081a3f86(mgr, 'BMap', id)`
  (0x0802a94a; the manager's finder 0x0827f1c2 forwards 'BMap' to FUN_08270104). The returned object
  carries its own id at +0x18, which is what retain (FUN_081b15d8) and release (FUN_08198f34) use.
- Static bitmap references are `SORC` records of kind 0x80 whose value is the bitmap id
  (0x0dad01de ← SORC 0x116, 0x2b7, 0x2c5, 0x2c8; 0x0dad02e5 ← 11 SORCs; 0x0dad0572 ← 9 SORCs).
- **Fix in dark_mode_toggle.py:** for type 'BMap', when Dark Mode is on and the id is in LIGHT_BITMAPS
  (01de, 02e5, 053e–0540, 0553–0555, 0544, 055a), HOOK looks up **0x0dad0572** (stock dark gradient,
  240×376) instead. Because the swap returns the dark bitmap's own object, refcounts stay right even
  if the setting changes while a screen holds it. HOOK 152/184 bytes, tables + DARK() 168/184 bytes.
- Emulated (off / on / dark bitmap missing / no preferences). **Not yet run on the iPod.**
- Unknowns: LIGHT_BITMAPS was chosen from the few extracted previews (`firmware/slice_*.png`), so other
  light bitmaps may remain; and 0x0dad0572 is taller than the 205/176/91/99 px panels it replaces, so
  it may be clipped, squashed or overlap. A copy of SilverImagesDB.LE.bin would settle both.

### 34b. The menu's white background is the table element's fallback colour

- **Second on-device result:** with the bitmap swap, the background was **still white**.
- View element factories are registered by tag (FUN_081aaf6c): `list` → 0x0802b8e4, `tabl` → 0x0802c210,
  `grad` → 0x0802efd0, `text` → 0x0802bd7c.
- Nearly every menu screen uses **View 0x0dad1474** (imag 1c96, imag 1c97, `tabl` 1c98; in about 140 SUse
  lists). Its rows are separate cell views chosen by `TVCS` records `{id, View, VLyt normal, VLyt hilite}`
  (0x0dad1492 etc.: two `text` + one `imag`; text colour COLR 0x13 normally, **0x12 when highlighted**).
  Neither the menu view nor the cells have a background element.
- **The white:** FUN_0802c210 does `c = GET_RESOURCE(mgr, 'COLR', element[+0x50])` at 0x0802c2a8 and
  starts from `ff ff ff ff`, replacing it only if the lookup succeeds; the 4 bytes go to table object
  +0x170. View 0x0dad1474's table has COLR id 0, so the lookup fails and the table is opaque white.
- `list` elements differ: they carry inline ARGB values (tag +0x34 = ffffffff, then the blue highlight
  gradient ff4289f6 / ff184d99 …) and only look up a COLR if element +0x50 is non-zero. 16 views; **not
  handled yet**.
- **COLOR_MAP was wrong about whites.** Every white COLR referenced by views is a text colour or image
  tint (0x12 highlighted menu text; 0x18, 0x74, 0x84, 0x89, 0xa1 white text on dark screens). Those six
  entries are removed; four more black text colours (3f, 46, 5d, 6e) are added. 18 colours now.
- **Fix:** HOOK's failed-lookup path (NOT_FOUND, in TCVoiceMemosLoading[68] 0x08069304, 52/184 bytes)
  returns `121212ff` for a failed `COLR 0` lookup whose return address is 0x0802c2ad, when Dark Mode is
  on. Emulated; **not yet run on the iPod.**

### 34c. Status bar, lighter background, and a donor-region clash (third on-device result)

- On the iPod the table-fallback fix works: menus are dark. The status bar was still silver.
- `firmware/SilverImagesDB.LE.bin` is now in the repo. Format: header `{3, data_start, 1, 'BMap', count, 1, 0x1c}`,
  then `count` × `{id, offset, size}`; each image is `{u16 fmt, u16 ?, u16 stride, u16 bpp, …, u32 height @0x10,
  u32 width @0x14, u32 id @0x18, u32 data_size @0x1c}`, then for fmt 0x64/0x65 a palette (`u32 n`, n × BGRA) and
  8/16-bit indices; fmt 0x1888 is raw BGRA.
- The status bar is View 0x0dad1470 (silver; ~255 screens reference it through SUse) or View 0x0dad1471 (dark; Now
  Playing etc.). The two views are byte-identical except element ids, the image SORCs (0x4c–0x50 vs 0x51–0x55), one
  `stsp` flag and the title colour (COLR 0x13 vs 0x54). The views can't simply be swapped: VCvs/VLyt resources bind
  to the element ids (title text 0x0dad1c88 vs 0x0dad1c8e).
- SORC 0x4c = constant bitmap 0x0dad0129 (320×20 silver gradient); SORC 0x51 = 0x0dad030c (1×20, 5e5e5e → 171717).
  SORCs 0x4d–0x4f / 0x52–0x54 are dynamic sources (0xa100/0x9a00/0x9f80 with a light/dark selector); SORCs are not
  fetched through FUN_081a3f86 (they go through the resource-handle path FUN_081b23a4 → FUN_0830125c), so the hook
  can't swap them. Their bitmaps do come through the hook.
- Battery bitmaps: 0x0dad0143–0x159 (green, for the silver bar) + 0x15a/0x15b (charging glyphs); the dark bar's
  white set is the same 25 images at +0x19 (0x15c–0x174). The +0x19 pairing is inferred from the layout of the ids
  and the look of the images, not traced through code.
- Hook change: the bitmap table is now ranges `{first, last, dark, step}` (dark id = dark + step × (id − first)),
  stored in the NOT_FOUND region. Added 0x129 → 0x30c and 0x143..0x15b → 0x15c... Other status icons (play state,
  lock, pedometer shoe) keep their silver-bar versions.
- `DARK_BACKGROUND` 121212 → 363636 (closer to the iPod classic's dark grey).
- Region clash: `photos_slot.py` (landscape photos, section 33, written on another machine) took
  TCVoiceMemosIdle[68] 0x080a5834 as its region E, which was this patch's table region. The tables moved to
  TCVoiceMemosMainMenu[68] 0x080a753c..0x080a75f4. All seven controller [68] slots are now used.
- Built `firmware/n5g-full-build-dark-toggle.dfu`; emulation and 29 tests pass. Not tested on the iPod yet.

- Row value text: the Rotate row's On value is Str 0x0dad0e32 "Cover Flow" (next to the label 0x0dad0e31, referenced only by the string tables). `dark_mode_setting.py` now rewrites it in place to "On". Not tested on the iPod yet.

### 34d. Now Playing must stay stock (fourth on-device result)

- Now Playing is Views 0x0dad1515/1516/1518 + status bar 0x0dad1519 (dark, bitmap 0x30b) + one overlay of 0x1522..0x1527
  (0x1512..0x1514 is a sibling set). With Dark Mode on it looked broken.
- Cause: COLR 0x0dad0057 (black) is the tint of the backdrop `imag` in Views 0x1512/0x1515; the palette turned it f0f0f0.
  Removed 0x57 from COLOR_MAP, and 0x58 (text in Views 0x151c/0x151e, which sit under the dark status bar 0x151b).
- Still mapped but used on screens with a native dark status bar (0x151b), unchecked on the iPod: 0x28, 0x46, 0x70,
  0x87, 0x88, 0xa5. If another stock-dark screen looks wrong, these are the suspects.
- Not tested on the iPod yet.

### 34e. Menu background decided at draw time (fifth on-device result)

- With Dark Mode switched off again, text and status bar went back to light but menus stayed dark: the table factory
  copies the background colour into the table object once (4 bytes B,G,R,A at +0x170; object size 0x3fc, constructor
  FUN_08037028, vtable 0x084f604c), and existing menus (main menu) are never rebuilt.
- The only vtable method that touches obj+0x170 is slot 34, FUN_08058090: `mov r1,r7; adds r1,#0xff; adds r1,#0x71;
  add r0,sp,#0x20; bl 0x08278fe2` at 0x08058102. Assumed to be the table's background draw; not confirmed on the iPod.
- The two adds (0x08058104) are now `bl TABLE_BG` (in the NOT_FOUND region): same adds, then if the colour is opaque
  white and Dark Mode is on, r1 -> DARK_BACKGROUND (stored B,G,R,A). The factory is stock again (NOT_FOUND just
  returns 0), so nothing is baked in.
- If menus are white with Dark Mode on in this build, slot 34 is not the draw path. Not tested on the iPod yet.

### 34f. White line under menus; value text (sixth on-device result)

- White line at the bottom of menus with Dark Mode on: COLR 0x0dad0028 (black) is only ever the tint of an `imag`\n  showing bitmap 0x0dad01a4 (1x15 black alpha gradient, a drop shadow) in ~23 menu views. Mapped to white it drew a
  white line. Removed from COLOR_MAP (now 15 colours).
- The photo also suggests text colours and the status bar are cached per screen: right after toggling, the table
  background (decided per draw, 34e) had changed but the text was still black and the bar silver.
- The row still read "Cover Flow" in that photo. Unknown whether that build had the 0x0dad0e32 patch. Also patched
  Str 0x0dad0d71 (the only other "Cover Flow" with no SORC reference) to "On". If some other label now reads
  "On", revert that one. Not tested on the iPod yet.
- Correction: that photo was an old build, so the 0x0dad0d71 change was unnecessary and has been reverted (it reads "Cover Flow" again). Only 0x0dad0e32 is "On". The note above about text/status bar being cached came from the same old-build photo and is unconfirmed.

### 34g. Cover Flow (seventh on-device result)

- With Dark Mode on, Cover Flow kept its white background but its title text went white (unreadable) and its status
  bar went dark. So the bitmap swap does work on the iPod (the landscape bar is View 0x0dad1517, bitmap 0x129).
- Cover Flow's screen is Views 0x0dad14cb (one `spok` element, SORC 0x249: hosts the app surface; factory 0x08028c80),
  0x14cc (title/artist text, COLR 0x3f black and 0x44), 0x1517 (status bar), 0x14cd/0x14ce (flip-side track list).
- The covers and the white behind them are drawn by TCoverFlowApp (a TGLESApplication; vtable 0x084fc570, methods
  0x0803ab14..0x0803b7xx and 0x08043048..), i.e. OpenGL ES. No COLR id appears as a code literal anywhere, and I did
  not find the clear colour: no glClearColor-like call with four equal 1.0/0x10000 args, no 0x4100 clear mask, no
  white constants in those methods. TCoverFlowApp loads bitmap 0x0dad029e (45x45 ARGB) via FUN_081af6bc. Next step
  would be decompiling TCoverFlowApp's draw path in Ghidra (GL calls go through `blx` on an import table).
- `covw` (View 0x1597) is NOT Cover Flow: it and 0x1598 (`sbgh`) sit on the blue-gradient View 0x1578 (fitness).
- For now COLR 0x3f is removed from COLOR_MAP (14 colours), so Cover Flow's text is black on white as in stock.
  Not tested on the iPod yet.

### 34h. Applying the toggle at once

- On the iPod the toggle only showed after leaving and re-entering the page (text colours / status bar are looked up when a screen is built).
- ToggleSetting_FontSize = FUN_08089e80: flips General.FontSize (key slot 0x08550b9c) between "standard" (0x08550ba0) and "large" (0x08550ba4) with prefs vtable[0x50] get-string / vtable[0x40] set-string. Open menus rebuild on that preference change (stock behaviour of the Font Size row).
- ToggleSetting_Rotate's tail (0x08089ce4) now `bl REFRESH` (NOT_FOUND region): calls FUN_08089e80 twice, then returns 1 as before. Font size ends unchanged. Unknown on the iPod: whether the double rebuild is visible as a flicker, and whether the status bar refreshes too. Not tested on the iPod yet.

### 34h. Applying the toggle at once

- On the iPod the toggle only showed after leaving and re-entering the page (text colours / status bar are looked up when a screen is built).
- ToggleSetting_FontSize = FUN_08089e80: flips General.FontSize (key slot 0x08550b9c) between "standard" (0x08550ba0) and "large" (0x08550ba4) with prefs vtable[0x50] get-string / vtable[0x40] set-string. Open menus rebuild on that preference change (stock behaviour of the Font Size row).
- ToggleSetting_Rotate's tail (0x08089ce4) now `bl REFRESH` (NOT_FOUND region): calls FUN_08089e80 twice, then returns 1 as before. Font size ends unchanged. Unknown on the iPod: whether the double rebuild is visible as a flicker, and whether the status bar refreshes too. Not tested on the iPod yet.

### 35. Selector colour presets (in progress)

- Goal: a Settings row that cycles the menu selector's colour through presets (user chose presets before a colour wheel).
- Not yet known: what draws the menu selector. Ruled out: the cell view 0x0dad1492 / its hilite VLyt (only the text colour changes, COLR 0x13 -> 0x12); the tabl element's SORC 0x5e (dynamic 0xa180/0xa181 = "font is large" flag, notified from FUN_08185490 on General.FontSize); bitmaps 0x187..0x195 (rounded 8x29 caps loaded by FUN_08082fxx from base literal 0x0dad018a: a pill/slider, three styles); 0x181..0x183 (5/1 x22 blue 3-slice, SORCs 0xc5..0xc7, Views 0x1490/0x154b).
- Candidate: bitmap 0x0dad01a7 (240x30, fmt 0x65, 259-colour palette, blue gradient bar 88ace7 -> 3e83dd). No SORC or literal references it. PROBE in the current build: with Dark Mode on it is swapped for the silver bar 0x0dad0435; if the selector turns silver on the iPod, 0x1a7 is it.
- Recolour idea if confirmed: the returned bitmap object is the image blob (id at +0x18, palette count at +0x20, BGRA entries from +0x24), so permuting the palette's colour channels in RAM gives six hues while keeping the gradient.
- Code space: HOOK 176/184, NOT_FOUND region ~170/184, tables 112/184. All seven Voice Memos [68] slots are used; more dead Voice Memos methods exist (section 26) and must be located before adding the preset code.

## 36. Donor space moved to the Nike+ heart-rate-monitor screens; Voice Memos restored

- The user asked for Voice Memos back and agreed to give up the Nike+ heart-rate-monitor screens. (Translations are not in the OS image - only the language names are - so removing languages frees nothing.)
- Classes: TTrainer_Cntlr_HeartMonitorLinking, ...Unlinking, ...LinkingInstructions, TTrainer_Cntlr_Settings_HeartMonitor and their TSilverCntlrTransitionAddon<> wrappers. 62 methods appear only in these eight vtables and have no bl callers: 4,404 bytes (sizes = distance to the next known function start).
- Largest: 0x080a096c 604 (LinkingInstructions[98]); addon[89]/[94] 336 each at 0x08181902, 0x081815ce, 0x08180c2a (start at +2 for word alignment: 334 usable); addon[68] 184 each at 0x08181834, 0x08181500, 0x081811cc, 0x08180b5c; then 142, 136, 132, 3x100, 4x98, 4x72 ... still free.
- New map: photos_slot A 0x08181904..0x08181a52, B 0x08181834, C 0x08181500, D 0x081811cc, E 0x08180b5c (184 each); dark mode HOOK 0x081815d0..0x0818171e, tables 0x08180c2c..0x08180d7a, NOT_FOUND/TABLE_BG/REFRESH/bitmap table 0x080a096c..0x080a0bc8 (158 of 604 used: room for the selector presets).
- The Voice Memos entry cut (0x082003dc) is removed from photos_slot.py; dark_mode_toggle's cut_voice_memos now defaults to False. A diff of the built image against stock shows no change left in any Voice Memos method.
- NOT done: the heart-monitor screens' entry points are not cut. They only open with a Nike+ receiver and heart-rate monitor attached; opening one would now run patch code as a controller method and crash. Not tested on the iPod yet (neither the relocation nor Voice Memos).

- Section 35 update: the 0x1a7 probe was negative on the iPod (selector stayed blue), so 0x1a7 is not the selector; probe removed. No code constants match the list-element gradient colours (4289f6 / 184d99) either.
- New candidate: FUN_08082fc0 (one caller, 0x0805eba6, in the table-code neighbourhood) loads six bitmaps into obj+0x1e4.. by style byte obj+0x145: style 1 = 0x18a,0x18b,0x18c (blue gradient 69bee7 -> 3199d4 -> 267bc0, 8/1/8 x 29, raw ARGB fmt 0x1888) + 0x187..0x189 (grey); style 0 = 0x190..0x192 (blue, 6/1/6 x 26) + 0x18d..0x18f (dark); style 2 = 0x196..0x198 + 0x193..0x195.
- PROBE now in the build: with Dark Mode on, 0x18a..0x18c -> 0x187..0x189 and 0x190..0x192 -> 0x18d..0x18f. If the selector goes grey/dark, these are it. These are raw ARGB (no palette): recolouring means permuting channels in the pixel data (from +0x20, size at +0x1c).
- Pedometer shoe: status-bar bitmap 0x0dad03a0 (18x20, grey 6e6e6e) -> 0x0dad03a1 (white d2d2d2) while Dark Mode is on. Not tested on the iPod yet.

### 34i. Instant apply, second attempt

- On the iPod the double ToggleSetting_FontSize call (34h) only refreshed some text; the rest updated after changing pages. Removed.
- FUN_08185490(obj, event): preference-changed handler (event[4] == 0x16, id at event[0xc]). For id 0x9d2c (General.FontSize) it recomputes the "large font" flag, and if it differs from the cached byte obj+0x78 stores it and calls obj->vtable[0x64](obj, 'VMax', 0xa181); menu tables bind their row style to source 0xa181 (the tabl element's SORC 0x5e), so they rebuild. With 34h the font was back to its old value before this ran, so no flag change, no rebuild.
- Now 0x0818549e (ldr r1,=0x9d2c; cmp r0,r1) is `bl VMAX_HOOK`: for id 0x9d2a (assumed to be General.Rotate's change id: it is the selector of the Rotate row's value SORC 0x987) it flips obj+0x78 and notifies, twice, then redoes the original compare. Emulated: two notifications with the flag flipped then restored; font-size and other ids behave as stock.
- Unknown on the iPod: whether 0x9d2a really is the Rotate change id, and whether the tables rebuild synchronously (one flash of large-font rows) or just once at the end. Not tested on the iPod yet.

- Section 35 update 2: the second probe was also negative on the iPod (selector stayed blue with 0x18a..0x18c and 0x190..0x192 swapped), so FUN_08082fc0's bitmaps are not the menu selector either; probe removed. Still unknown what draws the selector. Likewise Cover Flow's white background (34g). Both need the table / TCoverFlowApp draw paths decompiled; pattern-searching the binary has not found them. This machine has no Ghidra (only a Java 17 JRE).
- Row divider (reported white in Music/Videos lists with Dark Mode on): bitmap 0x0dad01a5 (1x2 raw ARGB: black a=0x1a over white a=0x66), used by cell View 0x0dad1491 and View 0x1522. Swapped for 0x0dad054b (1x2: black a=0x23, white a=0x13) while Dark Mode is on. Other 1x2 dividers exist: 0x1a6, 0x4fd. Not tested on the iPod yet. Later changed to 0x0dad0399 (240x1 palette, black a=0xc9) for a 1px near-black line; untested. (0x01a6, 1x2 black a=0x33 + white a=0x1a, was the previous try.) (0x04d7, a 1x5 all-black strip, was tried but is 5px tall.)

### 35a. Selector hunt with Ghidra (still not found)

- Ghidra 12.2 + JDK 25 are installed at C:\Users\fernf\ghidra-nanocam (gh.ps1 runs ghidra_scripts/Decompile.java headless on body.bin).
- Table draw FUN_08058090 (vtable 0x084f604c slot 34): fills the background when flag obj+0x3f9 is set; if flag obj+0x3f0 is set it purges all cached cells (FUN_082176cc) and relayouts; then draws each dirty row and the selected row (obj+0x230) last through FUN_0827dfec(table,row) -> cell, FUN_081bfab4(cell) -> cell[5]->vtable[8]().
- FUN_0827c12c(table) = invalidate the whole table (FUN_0826acb0(table, table+0x6c)). FUN_08075f64(table,row,..) = change selection: calls cell[5]->vtable[0x14](obj, 0/1) on the old/new cell. FUN_081d46d8 creates a cell; the cell object comes from FUN_0821c300 (a provider lookup, FUN_0827ef4c), so its class is not visible statically.
- Cell style: TVCS {id, View, VLyt normal, VLyt hilite}; menu rows are View 0x0dad1492 (TMLT: 240 x 29). The hilite VLyt differs from the normal one in three words: root element 0x1cf8 entry (1, SORC 0x473, 0 -> 3), text colour COLR 0x13 -> 0x12, and the last element's final word 0 -> 1. The selector bar is therefore whatever "3" means for the root element; not found yet. SORCs 0x44a/0x473/0x475 are dynamic sources 0x9985/0x998f/0x998c (0x99xx = media-list data sources; FUN_082c6068 is their big provider switch).
- Ruled out as the selector: every blue bitmap 28..40 px high in the image DB that goes through the hook (0x18a-c, 0x190-2 are a segmented control drawn by code near 0x0805eb60); COLR ids and the list-element gradient colours do not occur as code constants.
- Note: 11 code sites fetch 'BMap' through a vtable call instead of FUN_081a3f86 (e.g. 0x0826ea8a), so a bitmap could bypass the hook.

### 35b. Selector found; colour presets built

- Applying a VLyt: FUN_08082f60(view, vlytId) -> for each entry element->vtable[0x134](element, entry); base impl FUN_08168850 switches on the property's SORC *id* (0x44a = text colour via COLR, 0x473 -> FUN_081a905e(element, n) = put the element on compositor layer n). The hilite layout moves the row to layer 3.
- The selector is a sprite the table creates behind the selected row: FUN_082171c8(table,row) makes a layer (table+0x1f8) the size of the cell and has the painter at table+0x1f0 (or +0x1f4 when table+0x394 != 0) draw into it.
- FUN_08093f60(table) installs the painters (called from FUN_081d384a, i.e. whenever the table rebuilds): it asks the table's provider (table+0x158) through FUN_081a3f86; if that returns 0 it builds FUN_081c46d0(new(0x14), &c1, &c2, &c3) from R,G,B,A bytes on its stack: active = 09a4e1 / 0063d3 / 96c5da, inactive = bdcdf1 / a1bcdf / aaaaaa.
- Presets: 0x08093fd6 (add r1,sp,#0x10; add r3,sp,#8) -> `bl SEL_HOOK`: permutes the R,G,B bytes of the three active colours by preset 0..5 (blue, orange e1a409, green a4e109, pink e109a4, teal 09e1a4, purple a409e1), then does the two adds.
- The preset is stored in General.SortContacts (key slot 0x08550bc0) as "c0".."c5". ToggleSetting_SortContacts FUN_08089cec is now push; bl CYCLE; movs r0,#1; pop: CYCLE stores the next preset with prefs vtable[0x40]. The row label Str 0x0dad0d6f "Sort Contacts" -> "Highlight". The row's value text (SORC 0x994, source 0x9d2d) will probably be blank for these values; contact sort order falls back to the firmware default.
- VMAX_HOOK (34i) now also fires for event id 0x9d2d so open menus rebuild (and so re-run FUN_08093f60). That mechanism is still unconfirmed on the iPod; without it the new colour shows after the menu is rebuilt (e.g. changing pages).
- Later: the row is "Highlight Color" and its value shows the colour name; a seventh preset "Red" was added (perm (2,0,0): 09a4e1 -> e10909, 0063d3 -> d30000, 96c5da -> da9696). The value text ("First"/"Last", Str 0x0dad0d8c/d8d) and the label (Str 0x0dad0d6f) are replaced in HOOK's new 'Str ' branch, which returns pointers to NUL-terminated names in the extra region (names by preset, 8-byte slots). This assumes the row's text comes through GET_RESOURCE('Str ', id); untested on the iPod. The old in-place label patch was dropped (the new label is longer than "Sort Contacts").
- All new code is in the 604-byte region (442 used). Emulated: six colour sets, cycling, register/stack preservation. Not tested on the iPod yet.

### 34k. Cover Flow floor / reflection: what does NOT work (tested on the iPod, 2026-11-11)

- The white floor (reflections fading to white) and the text outline are still unsolved in Dark Mode.
- Tinting the GL colour (FUN_08273a1c = glColor4f wrapper `push {r3-r7,lr}; mov r5,r0; mov r6,r1`) changed nothing in Cover Flow: not at the two cover-draw sites in FUN_0814b70e / FUN_0814ba88, not at 17 other call sites (three colour-coded groups), not at the byte-colour wrapper at 0x0827cb7a, and not by hooking SET_COLOUR's entry (so every colour set was tinted magenta). Cover Flow's covers/reflections therefore never set a GL colour, and no code sets a colour array (FUN_0827d4fc is only called with array 0 and 1). The reflection fade is most likely baked into the cover textures, or done through texture-environment state.
- FUN_0814b70e / FUN_0814ba88 (vtables 0x85058b4 / 0x8505a84, draw = slot 0x10, per-cover via FUN_080ebbd8) and FUN_080dfbb4 (the TGLView tree drawer, lighting) are probably Photos GL, not Cover Flow. FUN_081aa1e8 (render frame, with CF_HOOK) is shared by several GL apps. FUN_080fab54 is a random animation. The Cover Flow cover renderer is the object at TCoverFlowApp+0x960 (vtable +0x68), not located yet.
- The text outline is not in View 0x14cc (colours/fonts only).
- Note: earlier ad-hoc scripts used 0x08000000 as the image base; the right one is 0x07FD1D84 (BASE), so addresses they printed are off.

### 34j. Cover Flow background found (replaces the dead ends in 34g)

- The renderer is not classic GL names but a GL-like API whose calls take the context first: FUN_0827c6e2/0827c6ba(ctx, 0x1700) push/pop matrix, FUN_08277cb8 translate, FUN_0827cc20 bind texture, FUN_0827c518(ctx, 5, 0, 4) draw strip, FUN_0827ca94 set state, FUN_08273a1c(r,g,b,a) colour, and **FUN_08252d7c(ctx, flags, 0xRRGGBBAA, depth, stencil) = clear**. Drawing code clusters at 0x080f6e3c..0x080ff904 and 0x0811xxxx.
- FUN_081aa1e8(app) renders a Cover Flow frame (callers 0x080232f6, 0x08023354, 0x0804d0b6, 0x080cf36c, 0x0824514c): grey = (int)(brightness * 255.0), brightness read from app+0x93c via FUN_0827c662; clear(ctx, 3, grey<<24|grey<<16|grey<<8|0xff, 1.0, 0) at 0x081aa238.
- Patch: 0x081aa220 (movs r2,#0; str r2,[sp]) -> `bl CF_HOOK`: while Dark Mode is on, grey = grey * 0x24 >> 8 (255 -> 0x23). Emulated: ffffffff -> 232323ff, 808080 -> 121212, stock when off.
- COLOR_MAP: 0x3f (title/artist) is light again and 0x44 (3b3b3b secondary text) -> b0b0b0, both only used by View 0x0dad14cc.
- Unknown on the iPod: how the cover reflections look on dark (they may fade through a white overlay), and whether the same clear is used by other 3D screens. Not tested on the iPod yet.
