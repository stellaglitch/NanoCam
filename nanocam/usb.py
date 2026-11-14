"""Find a connected nano 5G and report which mode it's in.

Uses pyusb, which needs a libusb backend. On Windows, `pip install libusb-package`
bundles one. Detection can work on Windows; the exploit itself only works on
native Linux (see README).
"""

from __future__ import annotations

from .devices import APPLE_VID, NANO5G_PIDS


def find_nano5g() -> list[str]:
    """Return the mode names ("dfu", "wtf", "disk") of every nano 5G plugged in."""
    try:
        import usb.core
    except ImportError as e:
        raise RuntimeError("pyusb isn't installed. Run: pip install -e .[usb]") from e

    backend = None
    try:
        import libusb_package
        backend = libusb_package.get_libusb1_backend()
    except ImportError:
        pass  # Fine on Linux, where the system libusb is used.

    # Reverse the mapping so we can look up a mode from a product ID.
    mode_by_pid = {pid: mode for mode, pid in NANO5G_PIDS.items()}
    found = usb.core.find(find_all=True, idVendor=APPLE_VID, backend=backend)
    return [mode_by_pid[dev.idProduct] for dev in found if dev.idProduct in mode_by_pid]
