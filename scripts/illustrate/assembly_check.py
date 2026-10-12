"""Blender -b -P assembly_check.py -- OUT_DIR file.json …  : renders assemblies dumped by bridge.py."""
import json
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iso

args = sys.argv[sys.argv.index("--") + 1:]
out, files = args[0], args[1:]
os.makedirs(out, exist_ok=True)
for f in files:
    data = json.load(open(f))
    iso.clear()
    for piece in data["pieces"]:
        bm = bmesh.new()
        edges = []
        for ring in piece["rings"]:
            verts = [bm.verts.new((u, v, 0)) for u, v in ring]
            edges += [bm.edges.new((verts[i], verts[(i + 1) % len(verts)])) for i in range(len(verts))]
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        geom = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
        top = [v for v in geom["geom"] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=top, vec=(0, 0, piece["t"]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        mesh = bpy.data.meshes.new("piece")
        bm.to_mesh(mesh)
        obj = bpy.data.objects.new("piece", mesh)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(iso.material(iso.WOOD))
        U, V = Vector(piece["u"]), Vector(piece["v"])
        N = U.cross(V) * piece["side"]
        obj.matrix_world = Matrix(((U.x, V.x, N.x, piece["origin"][0]),
                                   (U.y, V.y, N.y, piece["origin"][1]),
                                   (U.z, V.z, N.z, piece["origin"][2]),
                                   (0, 0, 0, 1)))
    name = os.path.splitext(os.path.basename(f))[0]
    iso.render(os.path.join(out, name + ".png"))
    print("rendered", name)
