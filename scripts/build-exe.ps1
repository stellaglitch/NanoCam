# Builds dist\nanocam-patcher.exe (needs Python 3.10+ with: pip install pyinstaller)
Set-Location (Split-Path $PSScriptRoot -Parent)
$jpg = (Resolve-Path placeholders\200\slot_001.jpg).Path
python -m PyInstaller --onefile --name nanocam-patcher --paths . --paths patches `
    --add-data "${jpg};placeholders\200" --distpath dist --workpath build\pyi --specpath build\pyi patches\nanocam_patcher.py