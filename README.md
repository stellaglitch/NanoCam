# NanoCam

A proper photo camera mode for the iPod nano 5th generation, added to Apple's stock
firmware. With the ability to view photos taken on the pod through the native Photos app!

## How this works

The nano 5G only boots Apple-signed code. The
[wInd3x](https://github.com/freemyipod/wInd3x) exploit (freemyipod project)
uses a bug in the bootrom's DFU mode to run unsigned code. Its `cfw run`
command can boot a **modified copy of Apple's own firmware (RetailOS)**.

That shapes the plan. RetailOS already contains a working camera driver and a
video recorder. It's much easier to patch in a "save this frame" feature than
to write a camera driver from scratch. Writing our own driver stays a later
goal, once disassembling RetailOS has shown us how the sensor is driven.

| Piece | Language | Runs on |
|---|---|---|
| `nanocam` toolkit (firmware parsing, patching, USB) | Python | Windows or Linux |
| Exploit and boot (`wInd3x`) | Go (existing tool) | **Native Linux only** |
| On-device code (patches, payloads) | ARM assembly / C | the iPod |
| Disassembly | [Ghidra](https://ghidra-sre.org/) | Windows |

## The Linux requirement

wInd3x's nano 4G/5G exploit **only works on native Linux. It fails in a VM,
which includes WSL2.** Options:

- A Raspberry Pi (the wInd3x authors' suggestion), or
- booting a Linux live USB (e.g. Ubuntu) on this PC.

Everything except actually sending code to the iPod can be done on Windows.

### Raspberry Pi setup

1. Flash **Raspberry Pi OS** with Raspberry Pi Imager. In its settings, turn on
   SSH and set a username and Wi-Fi.
2. Copy this project to the Pi from Windows:

   ```bash
   scp -r C:\Users\marsh\Dropbox\VSCode\NanoCam pi@raspberrypi.local:~/NanoCam
   ```

3. SSH in and run the setup script. It installs Go 1.23, builds wInd3x, adds a
   udev rule so iPods don't need `sudo`, and installs nanocam:

   ```bash
   ssh pi@raspberrypi.local
   ```

   ```bash
   cd ~/NanoCam && bash scripts/pi-setup.sh
   ```

4. Plug the nano into one of the Pi's USB ports (not through a hub if you can
   avoid it), then check that it shows up:

   ```bash
   source .venv/bin/activate && python -m nanocam detect
   ```

Replace `pi` with the username you chose in step 1.

## Roadmap

1. **Setup.** Install Python, Ghidra, and a Linux box with wInd3x built
   (`go build ./cmd/wInd3x`).
2. **First contact.** Put a spare nano in DFU mode (hold Menu+Select through
   two reboots until it appears as "USB DFU Device"), run `nanocam detect`,
   then `wInd3x haxdfu`.
3. **Get the firmware.** On Linux: `wInd3x download retailos n5g-retailos.bin`,
   then `wInd3x decrypt n5g-retailos.bin n5g-retailos.dec`.
   Check it here with `nanocam info`.
4. **Prove the boot path.** Run the *unmodified* decrypted RetailOS with
   `wInd3x cfw run n5g-retailos.dec`. The iPod should boot normally.
   *Done: it boots, and Video Camera works.*
5. **Find the camera code.** Load the firmware into Ghidra (ARM little-endian).
   Look for camera UI strings, the video encoder, and I2C writes to the
   sensor. Write down addresses in `docs/`.
6. **First patch.** Make a visible, harmless change (such as a UI string) with a
   Python patch script, then boot it. This proves the patch-and-boot loop works:

   ```bash
   python -m nanocam patch firmware\n5g-retailos.dec firmware\n5g-photocam-rename.dfu --string "Video Camera" "Photo Camera"
   ```

   *Done: the menu shows "Photo Camera", and the camera still works.*
7. **Add a "Photo Camera" menu item** next to "Video Camera" in the main menu.
   At first it can just open the existing video camera screen.
   *Done: `patches/photo_camera_menu.py` repurposes the hidden Composers item.
   Enable it in Settings → Main Menu.*
8. **Still capture.** In Photo Camera mode, make the center button grab the
   current viewfinder frame instead of starting a recording. Encode it to JPEG
   or BMP and save it where the stock Photos app can show it.
9. **Make it permanent.** `cfw run` is tethered: the patched OS only runs
   when booted from the Pi, and a normal reboot brings back stock firmware.
   Freemyipod lists no untethered method for the nano 5G yet. So this step is
   research into whether a patched OS can be made to survive a reboot.
10. **Stretch goals:** filters, a self-timer, and our own camera driver.

## Setup (Windows)

```bash
winget install Python.Python.3.12
```

Then, in this folder:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -e .[usb,dev]
```

```bash
pytest
```

## Commands

```bash
python -m nanocam info firmware.bin
```

```bash
python -m nanocam strings firmware\n5g-retailos.dec --grep camera
```

```bash
python -m nanocam detect
```

What's been learned about the firmware so far is in
[docs/firmware-notes.md](docs/firmware-notes.md).

```bash
python -m nanocam wrap payload.bin payload.dfu
```

## Safety

Haxed DFU only lasts until the next reboot, and `cfw run` doesn't write to
flash, so experiments are tethered and mostly reversible. Work on spare units
anyway, and don't write anything to NOR flash until you understand it.

## Resources

- freemyipod wiki: https://freemyipod.org/wiki/ (IMG1 format, nano 5G status)
- `#freemyipod` on libera.chat IRC
