"""Blender -b -P assembly_check.py -- OUT_DIR file.json …  : renders assemblies dumped by bridge.py."""
import json
import os
import sys


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso

args = sys.argv[sys.argv.index("--") + 1:]
out, files = args[0], args[1:]
os.makedirs(out, exist_ok=True)
for f in files:
    data = json.load(open(f))
    iso.clear()
    iso.pieces(data["pieces"])
    name = os.path.splitext(os.path.basename(f))[0]
    iso.render(os.path.join(out, name + ".png"))
    print("rendered", name)
