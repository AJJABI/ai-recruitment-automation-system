import sys
from pathlib import Path

paths = list(Path('.').rglob('*.py'))
found = False
for p in paths:
    b = p.read_bytes()
    if b.find(b"\x00") != -1:
        print(f"NULL bytes in: {p} at offset {b.find(b'\x00')}")
        found = True
if not found:
    print('No null bytes found in .py files')
