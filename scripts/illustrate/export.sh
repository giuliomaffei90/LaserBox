#!/bin/zsh
# Renders every model and writes the palettised 800 px PNGs the app ships into Illustrations/.
set -euo pipefail
cd "$(dirname "$0")/../.."
tmp=$(mktemp -d)
/Applications/Blender.app/Contents/MacOS/Blender -b -P scripts/illustrate/render.py -- --size 800 "$tmp" "$@" | grep -E "^(rendered|FAILED)" || true
mkdir -p Illustrations
PYTHONPATH=Runtime/site Runtime/python/bin/python3 -s -B - "$tmp" <<'PY'
import os, sys
from PIL import Image
src = sys.argv[1]
for f in sorted(os.listdir(src)):
    im = Image.open(os.path.join(src, f)).convert("RGBA")
    # Trim the empty margin, keep the picture square, then 256 colours with alpha.
    box = im.getbbox()
    im = im.crop(box) if box else im
    side = max(im.size) + 24
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(im, ((side - im.width) // 2, (side - im.height) // 2))
    square.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(os.path.join("Illustrations", f), optimize=True)
print(len(os.listdir(src)), "illustrations")
PY
du -sh Illustrations
