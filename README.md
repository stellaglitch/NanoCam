# NanoCam

A proper photo camera mode for the iPod nano 5th generation, added to Apple's stock
firmware. With the ability to view photos taken on the pod through the native Photos app!
I've also been developing a nano 5g dark mode which is included in this build. 

## How This Works

The nano 5G only boots Apple-signed code. The
[wInd3x](https://github.com/freemyipod/wInd3x) exploit (freemyipod project)
uses a bug in the bootrom's DFU mode to run unsigned code. This allows us to
boot a modified copy of Apple's own firmware (RetailOS) with extra features added.

RetailOS already contains a working camera driver and a video recorder. 
It was much easier to patch in a "save this frame" feature than
to write a new camera driver from scratch. Because of this, the camera
viewfinder looks identical to the video mode, despite it functioning differently. 

When I started this project I always envisioned being able to view your photos directly
on the iPod after taking them. I consider this to be an essential feature of any good
digital camera and wanted to be sure it got added. My first hurdle was figuring out how to 
add photos to the native "Photos" app already included on the iPod. The only way to add 
photos to the iPod is through syncing with iTunes, which isn't practical. 

After some tinkering I figured out a duct-taped together solution of using placeholder 
images. The concept behind it is to sync a batch of hundreds to thousands of empty 
placeholder images onto the iPod, which the camera app then overwrites one by one as you 
take photos, allowing you to view your pictures instantly within the device, and bypassing 
the photos app iTunes sync limitation. 

After capturing an image using the center clickwheel button the Pictures are saved 
as JPEG to the internal storage as separately numbered files, just like the video app. 
The photos are saved at a blistering 0.3mp at 480x640 resolution which comes out to around 
~100-150kb per photo. 

## Linux is Required

wInd3x's nano 4G/5G exploit only works on native Linux. Your options are:

- A Raspberry Pi (the wInd3x authors' suggestion, and what I used), or
- booting a Linux live USB (e.g. Ubuntu) on your PC.

Everything except actually sending code to the iPod can be done on Windows.

### Raspberry Pi setup

1. Flash **Raspberry Pi OS** with Raspberry Pi Imager. In its settings, turn on
   SSH and set a username and Wi-Fi.
2. Copy this project to the Pi from Windows (Or transfer via USB Drive):

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
anyway, and don't write anything to NOR flash until you understand it. I've tested
this on multiple of my nano 5gs and haven't had any issues, but proceed with caution.

## Resources

- wInd3x/freemyipod wiki: https://freemyipod.org/wiki/
- [Ghidra by the NSA](https://github.com/nationalsecurityagency/ghidra) 
