"""Hardware constants for the iPod nano 5th generation.

Values cross-checked against wInd3x (github.com/freemyipod/wInd3x, pkg/devices).
"""

# Apple's USB vendor ID. Every iPod reports this.
APPLE_VID = 0x05AC

# USB product IDs the nano 5G reports in each mode.
# - DFU:  the bootrom's recovery mode (hold Menu+Select until it reboots, keep holding).
#         This is the mode that has the wInd3x vulnerability.
# - WTF:  the second-stage USB loader that the bootrom hands off to.
# - DISK: normal operation, mounted as a USB mass storage device.
NANO5G_PIDS = {
    "dfu": 0x1231,
    "wtf": 0x1246,
    "disk": 0x1265,
}

# The SoC is a Samsung S5L8730. Its firmware images begin with this ASCII magic.
NANO5G_SOC_CODE = b"8730"

# IMG1 header area size for this SoC. The body starts at this offset.
NANO5G_IMG1_HEADER_SIZE = 0x600

# Where the bootrom loads a flat binary sent over haxed DFU.
DFU_LOAD_ADDRESS = 0x22000000
