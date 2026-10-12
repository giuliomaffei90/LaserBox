"""Blender -b -P render.py -- [--size 512] OUT_DIR [Name …]   (no names = every model)"""
import importlib
import os
import sys
import traceback

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso
import models

args = sys.argv[sys.argv.index("--") + 1:]
size = 1024
if args[0] == "--size":
    size, args = int(args[1]), args[2:]
out, names = args[0], args[1:] or sorted(iso.MODELS)
os.makedirs(out, exist_ok=True)
for name in names:
    iso.clear()
    bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = size
    try:
        view = iso.MODELS[name]() or {}
        iso.render(os.path.join(out, name + ".png"), **view)
        print("rendered", name)
    except Exception:
        print("FAILED", name)
        traceback.print_exc()
