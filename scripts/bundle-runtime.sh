#!/bin/zsh
# Builds Runtime/: a relocatable Python with boxes.py and its dependencies, plus the gallery pictures,
# copied into the app bundle. Needs network once; the app itself then runs offline.
set -euo pipefail
setopt null_glob
cd "$(dirname "$0")/.."
PY_VERSION=3.13
BOXES_REF=${BOXES_REF:-b82a6c9f84ab4b9ee91f5621b95d80b1b4fadf8d}
src=$(mktemp -d)/boxes

rm -rf Runtime && mkdir -p Runtime/samples
git init -q "$src" && git -C "$src" fetch -q --depth 1 https://github.com/florianfesti/boxes.git "$BOXES_REF"
git -C "$src" checkout -q FETCH_HEAD
# Upstream typo: NotesHolder with opening 0 never sets front_edge.
sed -i '' 's/font_edge = back_edge/front_edge = back_edge/' "$src/boxes/generators/notesholder.py"
# StackableBin: no optional label strip (it has nowhere to go).
sed -i '' '/label="for label (optional)"/d' "$src/boxes/generators/stackablebin.py"
# StorageShelf's x is the depth: the lid is y wide, so its back edge (hinge, slide-in…) meets the back.
sed -i '' 's/self.drawLid(x, y, self.top_edge)/self.drawLid(y, x, self.top_edge)/' "$src/boxes/generators/storageshelf.py"
# SpicesRack: the feet take the bottom row's supports' holes, so that row's supports are not cut.
sed -i '' 's/self.partsMatrix((self.numx-1)\*self.numy,/self.partsMatrix((self.numx-1)*(self.numy-self.feet),/' "$src/boxes/generators/spicesrack.py"
# FatBallDispenser: the roof support's etched polygon is t / tan(roof angle) in, not t / atan(…);
# no hanger hole (diameter 0) divided by zero: the same formula, multiplied out.
sed -i '' 's|self.thickness / math.atan(ar_roof)|self.thickness / math.tan(ar_roof)|' "$src/boxes/generators/fatballdispenser.py"
sed -i '' 's|(l_roof/2-dx_bottom)/(h_roof_tile/r_roof_hole)|(l_roof/2-dx_bottom)*r_roof_hole/h_roof_tile|' "$src/boxes/generators/fatballdispenser.py"
# DiceTower with one ramp divided by zero working out the (unused) spacing of the others.
sed -i '' 's|/ (self.ramps - 1)$|/ max(self.ramps - 1, 1)|' "$src/boxes/generators/dicetower.py"
# Sphere: the cable hook radius only matters with cable hooks.
sed -i '' 's|if self.cable_hook_radius + 1 > 0.8|if self.cable_hook and self.cable_hook_radius + 1 > 0.8|' "$src/boxes/generators/sphere.py"
# Arcade: side() first cut a leftover outline without the rounded corners, r inside the real one,
# which would cut each side into a frame and a panel.
perl -0pi -e 's/\n        with self\.saved_context\(\):\n            self\.moveTo\(0, r\)\n            self\.polyline\(y, 90, h, 45[^\n]*//' "$src/boxes/generators/arcade.py"
# Ramp: y is the depth (it sets the slope with h), h the height; their help texts were swapped.
perl -0pi -e 's/help="height of the ramp in mm"/help="DEPTH"/; s/help="depth of the ramp in mm, will influence the steepness of the ramp"/help="height of the ramp in mm"/; s/help="DEPTH"/help="depth of the ramp in mm, will influence the steepness of the ramp"/' "$src/boxes/generators/ramp.py"
# ZBeam: z is the second flange, not a depth.
sed -i '' 's|help="inner depth in mm")|help="inner width of the second flange in mm")|' "$src/boxes/generators/zbeam.py"
# WineRack, minimal walls, odd rows: the top row has no roofs, 2 per cell fewer walls to cut.
perl -0pi -e 's/(            if self\.walls == "all":\n                tc -= cx\n)/$1            elif self.walls == "minimal":\n                tc -= 2 * cx\n/' "$src/boxes/generators/winerack.py"
# SevenSegmentPattern (and Clock): the second separator as long as its finger holes (was 0.8 mm short).
sed -i '' 's|2\*\*0.5\* x/4 - t,|2**0.5*(.55*x/2 - t) - t/2,|' "$src/boxes/generators/sevensegment.py"
# AirPurifier with one filter: the "top" wall (d high, no frames) had its fan holes centred as on the
# walls with a filter, off its edge; in its middle, as with two filters.
sed -i '' 's/^            if self.filters==2:$/            if self.filters==2 or not fingerHoles:/' "$src/boxes/generators/airpurifier.py"
# FanHole: (ri*sin a)**2 was written ri*sin(a)**2, so the swirl's arms did not close (0.3–0.5 mm).
sed -i '' -e 's|(ri\*math.sin(math.radians(ai))\*\*2 +|((ri*math.sin(math.radians(ai)))**2 +|' -e 's|(ri\*math.sin(math.radians(ai-ao))\*\*2 +|((ri*math.sin(math.radians(ai-ao)))**2 +|' "$src/boxes/generators/fanhole.py"

uv python install "$PY_VERSION"
cp -R "$(dirname "$(dirname "$(uv python find --managed-python "$PY_VERSION")")")" Runtime/python
Runtime/python/bin/python3 -m pip install --quiet --no-compile --target Runtime/site "$src"

# Gallery pictures: the isometric illustrations (Illustrations/, rendered by scripts/illustrate),
# the web site's photos for the info panel, and a drawing for generators that have neither.
cp Illustrations/*.png Runtime/samples/
for f in "$src"/static/samples/*.jpg; do
  [[ $f == *-thumb.jpg ]] || sips -Z 640 -s formatOptions 70 "$f" --out Runtime/samples/ >/dev/null
done
PYTHONPATH=Runtime/site Runtime/python/bin/python3 -s -B - <<'PY'
import os, sys
sys.argv = ["bridge"]
sys.path.insert(0, "LaserBox")
import bridge
for name in bridge.GENERATORS:
    if not any(os.path.exists(f"Runtime/samples/{name}.{ext}") for ext in ("png", "jpg")):
        with open(f"Runtime/samples/{name}.svg", "w") as f:
            f.write(bridge.render(name, {}, "svg"))
PY

# Trim what the app never uses.
rm -rf Runtime/python/lib/python$PY_VERSION/{test,idlelib,tkinter,turtledemo,ensurepip} Runtime/python/lib/{tcl,tk,itcl,thread}* Runtime/python/share
find Runtime -name __pycache__ -prune -exec rm -rf {} +
# The app runs with -B (the bundle is read-only and signed), so ship bytecode that is never revalidated.
Runtime/python/bin/python3 -m compileall -q -j0 --invalidation-mode unchecked-hash Runtime/python/lib Runtime/site || true
du -sh Runtime Runtime/samples
