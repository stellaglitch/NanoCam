#!/usr/bin/env bash
# Set up a Raspberry Pi (Raspberry Pi OS / Debian) to run wInd3x and nanocam.
# Run from the NanoCam folder on the Pi:  bash scripts/pi-setup.sh
# Or copy just this file and run it anywhere: it then installs only wInd3x.
set -euo pipefail

GO_VERSION=1.23.3   # wInd3x's go.mod requires Go 1.23; Debian's packaged Go is older.
WIND3X_DIR="$HOME/wInd3x"

echo "== Installing system packages"
sudo apt-get update
sudo apt-get install -y git build-essential pkg-config libusb-1.0-0-dev python3-venv curl

echo "== Installing Go $GO_VERSION"
case "$(uname -m)" in
  aarch64) GO_ARCH=arm64 ;;
  armv6l|armv7l) GO_ARCH=armv6l ;;
  x86_64) GO_ARCH=amd64 ;;
  *) echo "unsupported CPU: $(uname -m)"; exit 1 ;;
esac
if ! /usr/local/go/bin/go version 2>/dev/null | grep -q "go$GO_VERSION"; then
  curl -fsSL "https://go.dev/dl/go$GO_VERSION.linux-$GO_ARCH.tar.gz" -o /tmp/go.tgz
  sudo rm -rf /usr/local/go
  sudo tar -C /usr/local -xzf /tmp/go.tgz
  rm /tmp/go.tgz
fi
export PATH="/usr/local/go/bin:$PATH"
grep -q /usr/local/go/bin "$HOME/.profile" || echo 'export PATH="/usr/local/go/bin:$PATH"' >> "$HOME/.profile"

echo "== Building wInd3x"
if [ -d "$WIND3X_DIR" ]; then
  git -C "$WIND3X_DIR" pull --ff-only
else
  git clone https://github.com/freemyipod/wInd3x "$WIND3X_DIR"
fi
(cd "$WIND3X_DIR" && go build ./cmd/wInd3x)
sudo install -m 755 "$WIND3X_DIR/wInd3x" /usr/local/bin/wInd3x

echo "== Allowing USB access to Apple devices without sudo"
# 05ac is Apple's vendor ID. TAG+="uaccess" grants access to the logged-in user;
# MODE 0666 also covers SSH sessions, which aren't "logged in" at the seat.
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="05ac", MODE="0666", TAG+="uaccess"' \
  | sudo tee /etc/udev/rules.d/60-ipod.rules > /dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger

if [ -f pyproject.toml ]; then
  echo "== Installing nanocam"
  python3 -m venv .venv
  .venv/bin/pip install -q -e ".[usb,dev]"
  echo "Activate nanocam with:  source .venv/bin/activate"
else
  echo "== Skipping nanocam (no pyproject.toml here; only wInd3x was installed)"
fi

echo
echo "Done. wInd3x: $(command -v wInd3x)"
echo "Unplug and replug the iPod so the new USB permissions apply."
