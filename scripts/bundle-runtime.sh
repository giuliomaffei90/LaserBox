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
