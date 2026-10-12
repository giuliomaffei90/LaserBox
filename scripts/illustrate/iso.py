"""Tiny scene kit for the box illustrations, run inside Blender (bpy).

Units are millimetres of the real object. All panels are plywood of thickness T.
Axes: x to the right, y towards the back, z up. The camera looks from the front-left-top.
"""
import math
import bpy
from mathutils import Vector

T = 3.0  # material thickness used by every model

MODELS = {}


def model(fn):
    """Registers a model function under the generator's name (the function name)."""
    MODELS[fn.__name__] = fn
    return fn


WOOD = (0.92, 0.74, 0.47, 1)      # plywood face
WOOD_EDGE = (0.62, 0.45, 0.25, 1)  # darker: the cut edge of the sheet
ACCENT = (0.90, 0.33, 0.20, 1)     # for the odd non-wood part (a rod, a lens…)


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 32
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 12
    scene.eevee.use_soft_shadows = True
    scene.eevee.shadow_cube_size = "2048"
    scene.eevee.shadow_cascade_size = "4096"
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"

    # Ink outlines on silhouettes and creases, thin and dark brown.
    scene.render.use_freestyle = True
    scene.render.line_thickness = 2.2
    view_layer = bpy.context.view_layer
    view_layer.use_freestyle = True
    linesets = view_layer.freestyle_settings.linesets
    for old in list(linesets):  # the empty factory scene keeps a lineset without a style
        linesets.remove(old)
    lineset = linesets.new("ink")
    lineset.select_silhouette = lineset.select_border = lineset.select_crease = True
    linestyle = bpy.data.linestyles.new("ink")
    linestyle.color = (0.22, 0.14, 0.06)
    linestyle.thickness = 2.2
    lineset.linestyle = linestyle
    view_layer.freestyle_settings.crease_angle = math.radians(120)

    # Soft, bright daylight: a sun from the front-left-top plus a grey world for the shadows.
    world = bpy.data.worlds.new("world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.85, 0.85, 0.88, 1)
    bg.inputs[1].default_value = 0.5
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 2.4  # keeps the brightest (upward) plywood faces off pure white
    sun_data.angle = math.radians(6)
    sun = bpy.data.objects.new("sun", sun_data)
    scene.collection.objects.link(sun)
    # Light from above, a little from the front and the left: top faces brightest, right sides darkest.
    towards_light = Vector((0.30, -0.55, 0.85)).normalized()
    sun.rotation_euler = (-towards_light).to_track_quat("-Z", "Y").to_euler()


def material(color, name=None):
    name = name or "mat%s" % ("_".join("%.2f" % c for c in color))
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.85
        bsdf.inputs["Specular"].default_value = 0.15
        mat.diffuse_color = color
    return mat


def _add(obj, color):
    obj.data.materials.append(material(color))
    return obj


def box(x, y, z, w, d, h, color=WOOD):
    """A solid block with its min corner at (x, y, z) and size w×d×h."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x + w / 2, y + d / 2, z + h / 2))
    obj = bpy.context.object
    obj.scale = (w, d, h)
    return _add(obj, color)


def panel(x, y, z, w, d, h, color=WOOD):
    """A plywood panel: one of w, d, h should be T (or close). Same as box, kept for readability."""
    return box(x, y, z, w, d, h, color)


def floor(x, y, z, w, d, t=T):
    return panel(x, y, z, w, d, t)


def extrude(points, plane, offset, thickness, color=WOOD):
    """A 2D polygon [(u, v), …] in the given plane ("xy", "xz" or "yz"), extruded by `thickness`
    along the third axis starting at `offset`."""
    to3 = {"xy": lambda u, v, w: (u, v, w), "xz": lambda u, v, w: (u, w, v), "yz": lambda u, v, w: (w, u, v)}[plane]
    n = len(points)
    verts = [to3(u, v, offset) for u, v in points] + [to3(u, v, offset + thickness) for u, v in points]
    faces = [list(range(n))[::-1], list(range(n, 2 * n))] + [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    mesh = bpy.data.meshes.new("extrude")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("extrude", mesh)
    bpy.context.collection.objects.link(obj)
    # Faces of an extrusion along xz / yz come out inside-out; let Blender fix the winding.
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    return _add(obj, color)


def _outline(u0, u1, v0, v1, notch_start, notch_end, depth, phase):
    """Rectangle (u0..u1 × v0..v1) whose start/end edges (at u0 / u1) carry finger-joint notches."""
    n = max(3, int(round((v1 - v0) / (depth * 2.5))) | 1)  # odd: both ends are fingers
    seg = (v1 - v0) / n
    def edge(u, inward, upwards, phase):
        pts = []
        order = range(n) if upwards else range(n - 1, -1, -1)
        for i in order:
            a, b = v0 + i * seg, v0 + (i + 1) * seg
            if not upwards: a, b = b, a
            uu = u + inward * depth if (i + phase) % 2 else u
            pts += [(uu, a), (uu, b)]
        return pts
    pts = [(u0, v0), (u1, v0)]
    pts += edge(u1, -1, True, phase) if notch_end else [(u1, v1)]
    pts += [(u1, v1), (u0, v1)]
    pts += edge(u0, +1, False, phase) if notch_start else []
    return pts


def wall_x(x, y, z, w, h, t=T, fingers=False, phase=0, color=WOOD):
    """A wall along x (seen from the front), standing on z, thickness along y.
    fingers=True notches both ends so the wall mates with a wall_y of the opposite phase."""
    if not fingers:
        return panel(x, y, z, w, t, h, color)
    return extrude(_outline(x, x + w, z, z + h, True, True, t, phase), "xz", y, t, color)


def wall_y(x, y, z, d, h, t=T, fingers=False, phase=0, color=WOOD):
    """A wall along y (a side), thickness along x."""
    if not fingers:
        return panel(x, y, z, t, d, h, color)
    return extrude(_outline(y, y + d, z, z + h, True, True, t, phase), "yz", x, t, color)


def open_box(x, y, z, w, d, h, bottom=True, front=True, back=True, left=True, right=True, t=T, fingers=True, color=WOOD):
    """Walls (and floor) of a box of outer size w×d×h with its min corner at (x, y, z).
    The vertical corners get finger joints; the walls stand on the floor."""
    parts = []
    zw = z + t if bottom else z
    hw = h - (zw - z)
    if bottom: parts.append(floor(x, y, z, w, d, t))
    f = fingers and front and back and left and right
    if front: parts.append(wall_x(x, y, zw, w, hw, t, f, 0, color))
    if back: parts.append(wall_x(x, y + d - t, zw, w, hw, t, f, 0, color))
    y0, dd = (y, d) if f else (y + (t if front else 0), d - (t if front else 0) - (t if back else 0))
    if left: parts.append(wall_y(x, y0, zw, dd, hw, t, f, 1, color))
    if right: parts.append(wall_y(x + w - t, y0, zw, dd, hw, t, f, 1, color))
    return parts


def closed_box(x, y, z, w, d, h, t=T):
    parts = open_box(x, y, z, w, d, h, t=t)
    parts.append(floor(x, y, z + h - t, w, d, t))
    return parts


def cylinder(x, y, z, radius, h, color=WOOD, axis="z", segments=48):
    """A cylinder standing on z (axis 'z'), or lying along x / y, with its base centre at (x, y, z)."""
    rot = {"z": (0, 0, 0), "x": (0, math.pi / 2, 0), "y": (math.pi / 2, 0, 0)}[axis]
    offset = {"z": (0, 0, h / 2), "x": (h / 2, 0, 0), "y": (0, h / 2, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=segments, radius=radius, depth=h,
                                        location=(x + offset[0], y + offset[1], z + offset[2]), rotation=rot)
    return _add(bpy.context.object, color)


def prism(points, z, h, color=WOOD):
    """A vertical extrusion of a 2D polygon [(x, y), …] from z to z + h."""
    mesh = bpy.data.meshes.new("prism")
    n = len(points)
    verts = [(px, py, z) for px, py in points] + [(px, py, z + h) for px, py in points]
    faces = [list(range(n))[::-1], list(range(n, 2 * n))] + [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("prism", mesh)
    bpy.context.collection.objects.link(obj)
    return _add(obj, color)


def slanted_panel(x, y, z, w, d, h, color=WOOD):
    """A panel whose front face leans back: the top edge sits d further back than the bottom edge."""
    return prism([(x, y), (x + w, y), (x + w, y + T), (x, y + T)], z, T, color) if h == 0 else \
        _slant(x, y, z, w, d, h, color)


def _slant(x, y, z, w, d, h, color):
    mesh = bpy.data.meshes.new("slant")
    verts = [(x, y, z), (x + w, y, z), (x + w, y + T, z), (x, y + T, z),
             (x, y + d, z + h), (x + w, y + d, z + h), (x + w, y + d + T, z + h), (x, y + d + T, z + h)]
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("slant", mesh)
    bpy.context.collection.objects.link(obj)
    return _add(obj, color)


def hole(obj, x, y, z, w, d, h):
    """Cuts a rectangular hole (min corner x, y, z; size w×d×h) out of obj."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x + w / 2, y + d / 2, z + h / 2))
    cutter = bpy.context.object
    cutter.scale = (w, d, h)
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("hole", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "FAST"
    mod.object = cutter
    return obj


def round_hole(obj, x, y, z, radius, axis="z", length=100):
    half = length / 2
    centre = {"z": (x, y, z - half), "x": (x - half, y, z), "y": (x, y - half, z)}[axis]
    cutter = cylinder(*centre, radius, length, axis=axis)
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("hole", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "FAST"
    mod.object = cutter
    return obj


def round_holes(obj, centres, radius, axis="z", length=400):
    """Drills several round holes through obj in one go: centres = [(x, y, z), …]."""
    cutters = []
    for cx, cy, cz in centres:
        half = length / 2
        base = {"z": (cx, cy, cz - half), "x": (cx - half, cy, cz), "y": (cx, cy - half, cz)}[axis]
        cutters.append(cylinder(*base, radius, length, axis=axis, segments=24))
    bpy.ops.object.select_all(action="DESELECT")
    for c in cutters: c.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    bpy.ops.object.join()
    cutter = bpy.context.object
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("holes", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "FAST"
    mod.object = cutter
    return obj


def rounded_rect(x, y, w, d, r, n=10):
    """Corner points of a rounded rectangle, counter-clockwise, for prism()."""
    pts = []
    for cx, cy, a0 in ((x + w - r, y + d - r, 0), (x + r, y + d - r, 90), (x + r, y + r, 180), (x + w - r, y + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def hollow(outer_points, z, h, t=T, color=WOOD):
    """A wall following a closed outline (bent plywood): the outline is the outer face, t thick."""
    cx = sum(p[0] for p in outer_points) / len(outer_points)
    cy = sum(p[1] for p in outer_points) / len(outer_points)
    # Inset every point towards the centroid by t along the normalised radial direction.
    inner = []
    for px, py in outer_points:
        dx, dy = px - cx, py - cy
        k = (dx * dx + dy * dy) ** 0.5 or 1
        inner.append((px - dx / k * t, py - dy / k * t))
    outer = prism(outer_points, z, h, color)
    cutter = prism(inner, z - 1, h + 2)
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = outer.modifiers.new("hollow", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "FAST"
    mod.object = cutter
    return outer


def render(path, elevation=35.264, azimuth=45, margin=1.12):
    """Frames every visible object in an orthographic isometric camera and saves the PNG."""
    scene = bpy.context.scene
    bpy.context.view_layer.update()  # bound boxes of parts placed from Python are stale until now
    objs = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    corners = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    centre = sum(corners, Vector()) / len(corners)

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.clip_start = 1
    cam_data.clip_end = 20000
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    direction = Vector((math.cos(math.radians(elevation)) * -math.sin(math.radians(azimuth)),
                        math.cos(math.radians(elevation)) * -math.cos(math.radians(azimuth)),
                        math.sin(math.radians(elevation))))
    cam.location = centre + direction * 5000
    cam.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    bpy.context.view_layer.update()

    # Fit: project the bounding corners into the camera plane and centre them.
    inv = cam.matrix_world.inverted()
    xs, ys = zip(*[(inv @ c)[:2] for c in corners])
    cam_data.ortho_scale = max(max(xs) - min(xs), max(ys) - min(ys)) * margin
    shift = Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, 0))
    cam.location += cam.matrix_world.to_3x3() @ shift
    bpy.context.view_layer.update()

    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
