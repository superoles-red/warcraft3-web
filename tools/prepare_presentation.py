#!/usr/bin/env python3
"""Convert original 1.31 artwork for the installer. Requires Pillow."""
import argparse
import struct
import shutil
from pathlib import Path
from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--local', type=Path, default=Path(__file__).resolve().parents[1] / 'local')
args = parser.parse_args()
data = args.local / 'gamedata'
dest = args.local / 'compact/presentation'
dest.mkdir(parents=True, exist_ok=True)

def texture(path):
    raw = path.read_bytes()
    magic, compression, alpha, width, height = struct.unpack_from('<4s4I', raw)
    if magic != b'BLP1' or compression != 1 or alpha != 8:
        return Image.open(path).convert('RGBA')
    # BLP1 stores the 8-bit alpha plane AFTER mip indices, outside the palette.
    offset, = struct.unpack_from('<I', raw, 28)
    pixels = width * height
    im = Image.open(path).convert('RGB')
    im.putalpha(Image.frombytes('L', (width, height), raw[offset+pixels:offset+2*pixels]))
    return im

glues = data / 'ui/glues'
screen = Image.new('RGB', (1024, 768))
for corner, pos in [('topleft',(0,0)),('topright',(512,0)),('botleft',(0,512)),('botright',(512,512))]:
    tile = texture(glues / f'loading/load-generic/generic-loading-{corner}.blp')
    screen.paste(tile.convert('RGB'), pos)
screen.save(dest/'background.webp', quality=91, method=5)
for role, name in [('border','loading-barborder'),('fill','loading-barfill')]:
    texture(glues / f'loading/loadbar/{name}.blp').save(dest/f'{role}.png', optimize=True)
for edition, name in [('roc','warcraftiiilogo/warcraftiii-logo-alpha'),('tft','warcraftiiilogo_exp/war3xlogo')]:
    image = texture(glues / f'mainmenu/{name}.blp')
    image.save(dest/f'{edition}.webp', lossless=True, method=5)
button = texture(data / 'ui/widgets/glues/gluescreen-button1-bordersingle.blp')
button.crop(button.getchannel('A').getbbox()).save(dest/'button.webp', lossless=True)
icon = texture(data/'replaceabletextures/commandbuttons/btnarthas.blp')
for size in (192,512):
    icon.resize((size,size), Image.Resampling.LANCZOS).save(dest/f'icon-{size}.png',optimize=True)
shutil.copyfile(data/'fonts/frizqt__.ttf',dest/'font.ttf')
print(dest)
