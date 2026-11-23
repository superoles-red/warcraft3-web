#!/usr/bin/env python3
"""Apply the skirmish lobby fix to the pinned upstream browser engine."""
import hashlib
from pathlib import Path
import sys

# Static linking merges the game HUD and menu FDF frame registries in this
# build. G_InitGame's early UI_ResetHud() then clears the active lobby.
# G_LoadMap already performs that reset before constructing each map's HUD.
# Source equivalent: remove UI_ResetHud() between G_RegisterGlobalSounds()
# and the "Game initialized" message in games/warcraft-3/game/g_main.c.
upstream_sha256 = '5deaf6ae927e5b75eabdf3b2a3baf0187001bb056ed8e386b3fbe514028a755a'
offset = 0x1b5ca8
original = bytes.fromhex('10 e6 aa 80 80 00')  # call UI_ResetHud (5478)
replacement = b'\x01' * len(original)  # equal-length WASM nop instructions

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'engine/openwarcraft3.wasm'
    data = bytearray(path.read_bytes())
    # Verify even a previously patched input against the entire upstream build.
    current = data[offset:offset + len(original)]
    if current not in (original, replacement):
        sys.exit('Unexpected G_InitGame instruction')
    data[offset:offset + len(original)] = original
    if hashlib.sha256(data).hexdigest() != upstream_sha256:
        sys.exit('Expected the pinned Warcraft III WebAssembly build')
    if current == original:
        data[offset:offset + len(original)] = replacement
        path.write_bytes(data)

if __name__ == '__main__':
    main()
