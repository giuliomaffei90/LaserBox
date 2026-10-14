"""Part 7: AllEdges … DiceTower.  Caricatures of the assembled objects, sizes in mm."""
import math

import bpy
from mathutils import Matrix, Vector

from iso import *

DARK = (0.13, 0.13, 0.14, 1)      # screens, mesh, fan grilles
GREY = (0.86, 0.86, 0.83, 1)      # keycaps
PAPER = (0.97, 0.95, 0.90, 1)


def _slab(plane, a, b, offset, width, t=T, side=1, color=WOOD):
    """A plate whose face is the 2D segment a→b (in `plane`), t thick on the left (side=1)
    or right (side=-1) of the segment, extruded along the third axis from offset by width."""
    (u0, v0), (u1, v1) = a, b
    du, dv = u1 - u0, v1 - v0
    k = math.hypot(du, dv) or 1
    nu, nv = -dv / k * t * side, du / k * t * side
    return extrude([(u0, v0), (u1, v1), (u1 + nu, v1 + nv), (u0 + nu, v0 + nv)], plane, offset, width, color)


def _skin(points, plane, offset, width, only=None, colors=None):
    """Plates of thickness T on the inside of every segment of a counter-clockwise polygon,
    shortened by T at both ends so neighbours do not overlap. `only` limits the segments."""
    out = []
    n = len(points)
    for i in range(n):
        if only is not None and i not in only:
            continue
        (u0, v0), (u1, v1) = points[i], points[(i + 1) % n]
        du, dv = u1 - u0, v1 - v0
        k = math.hypot(du, dv)
        su, sv = du / k * T, dv / k * T
        out.append(_slab(plane, (u0 + su, v0 + sv), (u1 - su, v1 - sv), offset, width,
                         color=(colors or {}).get(i, WOOD)))
    return out


def _cone(x, y, z, r0, r1, h, color=WOOD, axis="z"):
    """A truncated cone with its base centre at (x, y, z): radius r0 at the base, r1 at the far end
    (standing on z, or lying along x / y like cylinder())."""
    rot = {"z": (0, 0, 0), "x": (0, math.pi / 2, 0), "y": (-math.pi / 2, 0, 0)}[axis]
    offset = {"z": (0, 0, h / 2), "x": (h / 2, 0, 0), "y": (0, h / 2, 0)}[axis]
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=r0, radius2=r1, depth=h,
                                    location=(x + offset[0], y + offset[1], z + offset[2]), rotation=rot)
    obj = bpy.context.object
    obj.data.materials.append(material(color))
    return obj


def _cut(obj, cutter):
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    return obj


def _spin(objs, deg, px, py):
    """Rotates objects about the vertical axis through (px, py)."""
    rot = Matrix.Rotation(math.radians(deg), 4, "Z")
    piv = Vector((px, py, 0))
    for o in objs:
        o.location = rot @ (o.location - piv) + piv
        o.rotation_euler.z += math.radians(deg)


def _rot2(pts, deg, cu, cv):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cu + (u - cu) * c - (v - cv) * s, cv + (u - cu) * s + (v - cv) * c) for u, v in pts]


def _glass(objs, color=(0.55, 0.80, 0.95, 0.30)):
    mat = bpy.data.materials.get("glass")
    if mat is None:
        mat = bpy.data.materials.new("glass")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Alpha"].default_value = color[3]
        bsdf.inputs["Roughness"].default_value = 0.2
        mat.blend_method = "BLEND"
        mat.shadow_method = "HASHED"
        mat.show_transparent_back = False
        mat.diffuse_color = color
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(mat)
    return objs


@model
def AllEdges():
    L, hh = 100, 16
    y = 0
    plain = [(0, 0), (L, 0), (L, hh), (0, hh)]
    strips = [plain]
    pts = [(0, 0), (L, 0), (L, hh)]                         # finger joints
    for i in range(8, 0, -1):
        x1, x0 = i * 12.5, (i - 1) * 12.5
        pts += [(x1, hh), (x1, hh - 4), (x0, hh - 4), (x0, hh)] if i % 2 else [(x1, hh), (x0, hh)]
    strips.append(pts)
    pts = [(0, 0), (L, 0), (L, hh)]                         # a round notch
    for i in range(13):
        a = math.radians(180 * i / 12)
        pts.append((65 + 12 * math.cos(a), hh - 12 * math.sin(a)))
    pts.append((0, hh))
    strips.append(pts)
    pts = [(0, 0), (L, 0), (L, hh - 5)]                     # a raised handle
    pts += [(75, hh - 5), (70, hh), (30, hh), (25, hh - 5), (0, hh - 5)]
    strips.append(pts)
    strips.append(plain)                                    # with hanger holes
    for i, pts in enumerate(strips):
        y = i * 24
        obj = extrude([(u, v + y) for u, v in pts], "xy", 0, T)
        if i == 4:
            round_holes(obj, [(25, y + 8, 0), (75, y + 8, 0)], 3, length=20)
            hole(obj, 40, y + 6, -1, 20, 4, T + 2)
    return dict(elevation=50)


@model
def AngledCutJig():
    x, y = 50, 100
    base = 30 + x + 2 * T
    floor(0, 0, 0, base, y)
    # big ramp (45°) rising to the right on two triangles
    tri = [(33, T), (33 + x, T), (33 + x, T + x)]
    extrude(tri, "xz", 12, T)
    extrude(tri, "xz", y - 12 - T, T)
    _slab("xz", (33, T), (33 + x, T + x), T, y - 2 * T)
    # small stop in front leaning the other way
    tri2 = [(30, T), (10, T + 20), (10, T)]
    extrude(tri2, "xz", 12, T)
    extrude(tri2, "xz", y - 12 - T, T)
    _slab("xz", (30, T), (10, T + 20), T, y - 2 * T, side=-1)
    return dict(azimuth=30)


@model
def Arcade():
    W = 450
    prof = [(30, 0), (544, 0), (544, 409), (403, 550), (328, 475), (398, 404), (151, 157), (0, 117)]
    extrude(prof, "yz", 0, T)
    extrude(prof, "yz", W - T, T)
    plates = _skin(prof, "yz", T, W - 2 * T, colors={5: DARK})
    # speaker holes in the overhanging panel
    for x in (W / 4, 3 * W / 4):
        c = cylinder(0, 0, 0, 32, 40)
        c.location = (x, 363, 439.5)
        c.rotation_euler = (math.radians(135), 0, 0)
        _cut(plates[4], c)
    # joysticks and buttons on the sloping control panel
    tilt = math.radians(15)
    n = Vector((0, -math.sin(tilt), math.cos(tilt)))
    def on_panel(x, s, r, h, color):
        p = Vector((x, 151 - 151 * s, 157 - 40 * s))
        c = cylinder(0, 0, 0, r, h, color)
        c.location = p + n * (h / 2 - 0.5)
        c.rotation_euler = (tilt, 0, 0)
    for x0 in (90, 290):
        on_panel(x0, 0.5, 3, 40, GREY)
        on_panel(x0, 0.5, 12, 24, ACCENT)
        for i, s in ((0, 0.65), (1, 0.65), (2, 0.65), (0, 0.35), (1, 0.35), (2, 0.35)):
            on_panel(x0 + 55 + i * 36, s, 11, 5, (ACCENT, (0.95, 0.80, 0.15, 1), (0.25, 0.65, 0.30, 1))[i])
    return dict(elevation=25)


@model
def Atreus21():
    pitch, cw, cd = 19, 126, 99
    offsets = [3, 6, 11, 5, 0]
    def half(x0, mirror):
        objs = [floor(x0, 0, 0, cw, cd)]
        for z, hh in ((T, 6), (T + 6, T)):
            objs += [box(x0, 0, z, cw, 6, hh), box(x0, cd - 6, z, cw, 6, hh),
                     box(x0, 6, z, 6, cd - 12, hh), box(x0 + cw - 6, 6, z, 6, cd - 12, hh)]
        cols = list(enumerate(offsets)) + [(5, 7.8)]
        for i, off in cols:
            ci = cw - 6 - pitch - (i * pitch) if mirror else 6 + i * pitch
            nkeys = 1 if i == 5 else 4
            for j in range(nkeys):
                objs.append(box(x0 + ci + 2, 6 + off + j * pitch + 2, 2 * T + 6, pitch - 4, pitch - 4, 8, GREY))
        return objs
    left = half(0, False)
    right = half(cw + 50, True)
    _spin(left, -12, 0, 0)
    _spin(right, 12, 2 * cw + 50, 0)
    return dict(elevation=45)


@model
def BirdHouse():
    x, y, h = 200, 200, 200
    floor(0, 0, 0, x, y)
    gable = [(0, T), (y, T), (y, h + T), (y / 2, h + T + y / 2), (0, h + T)]
    for xx in (0, x - T):
        g = extrude(gable, "yz", xx, T)
        hole(g, xx - 1, y / 8, T + h / 8, T + 2, 0.75 * y, 0.75 * h)
    for yy in (0, y - T):
        s = wall_x(T, yy, T, x - 2 * T, h)
        hole(s, x / 8, yy - 1, T + h / 8, 0.75 * x, T + 2, 0.75 * h)
    # roof: two slabs at 45° meeting at the ridge, overhanging on every side
    ridge = (y / 2, h + T + y / 2)
    ov = 40
    for sign in (-1, 1):
        a = (ridge[0] + sign * 1.0, ridge[1] - 1.0)
        b = (ridge[0] + sign * (y / 2 + ov), ridge[1] - (y / 2 + ov))
        _slab("yz", a, b, -ov, x + 2 * ov, side=1 if sign > 0 else -1)


@model
def BookHolder():
    W = 297
    prof = [(0, 0), (100, 0), (100, 226), (46, 23), (8, 33), (0, 33)]
    extrude(prof, "yz", 0, T)
    extrude(prof, "yz", W - T, T)
    _skin(prof, "yz", T, W - 2 * T, only=(2, 3))
    # a book leaning on the stand
    u = (54 / 210, 203 / 210)
    a = (47.3 + 2 * u[0], 27.8 + 2 * u[1])
    b = (a[0] + 180 * u[0], a[1] + 180 * u[1])
    _slab("yz", a, b, 80, 150, t=25, side=1, color=(0.85, 0.45, 0.12, 1))


@model
def BottleStack():
    # Three beer bottles lying side by side in a low cradle: two scalloped rails (along x) tied by cross bars.
    r, n, pitch = 30, 3, 80
    H, rc, dip = 22, 31, 12                                  # rail height, scallop radius and depth
    L = n * pitch + 12
    pts = [(0, 0), (L, 0), (L, H)]
    for i in range(n - 1, -1, -1):
        cx, cz = 6 + pitch / 2 + i * pitch, H + rc - dip
        a0 = math.asin((H - cz) / rc)                        # right intersection with the top edge
        for k in range(13):
            ang = a0 - (math.pi + 2 * a0) * k / 12            # right -> bottom -> left
            pts.append((cx + rc * math.cos(ang), cz + rc * math.sin(ang)))
    pts.append((0, H))
    rails = (60, 150)
    for yy in rails:
        extrude(pts, "xz", yy, T)
    for xx in (6, L - 6 - T, 6 + pitch - T / 2, 6 + 2 * pitch - T / 2):
        panel(xx, rails[0] + T, 0, T, rails[1] - rails[0] - T, H - 8)   # cross bars
    colours = ((0.28, 0.13, 0.05, 1), (0.10, 0.24, 0.11, 1), (0.33, 0.16, 0.06, 1))
    for i, (col, dy) in enumerate(zip(colours, (0, 16, -8))):
        cx, cz = 6 + pitch / 2 + i * pitch, H + rc - dip + (rc - r)
        cylinder(cx, 35 + dy, cz, r, 150, col, axis="y")     # body
        _cone(cx, 19 + dy, cz, 12, r, 16, col, axis="y")     # shoulder, widening towards the body
        cylinder(cx, -7 + dy, cz, 12, 26, col, axis="y")     # neck
        cylinder(cx, -14 + dy, cz, 13.5, 7, (0.85, 0.75, 0.35, 1), axis="y")   # cap
    return dict(elevation=58)


@model
def BottleTag():
    w, h = 72, 98
    tag = prism(rounded_rect(0, 0, w, h, 15), 22, 1.2, PAPER)
    round_hole(tag, w / 2, h - 30, 22, 12.5)
    glass = (0.55, 0.30, 0.12, 1)
    cx, cy = w / 2, h - 30
    cylinder(cx, cy, -80, 30, 70, glass)                     # body
    cylinder(cx, cy, -10, 20, 10, glass)                     # shoulder
    cylinder(cx, cy, 0, 12, 36, glass)                       # neck through the tag
    cylinder(cx, cy, 36, 14, 10, (0.75, 0.75, 0.78, 1))      # cap
    return dict(elevation=40)


@model
def CanStorage():
    w, d, h = 460, 116, 210
    floor(0, 0, 0, w, d)
    wall_x(0, d - T, T, w, h - T)                            # back
    front = wall_x(0, 0, T, w, h - T)
    for i in range(5):
        hole(front, 25, -1, 30 + i * 35, w - 50, T + 2, 9)
    wall_y(w - T, T, T, d - 2 * T, h - T)                    # right end
    wall_y(0, T, 95, d - 2 * T, h - 95)                      # left end: open below for the cans
    wall_y(0, T, T, d - 2 * T, 16)                           # barrier lip
    up = ((T, 128), (375, 95))                               # upper chute slopes to the right
    low = ((w - T, 32), (T, 5))                              # lower chute slopes to the exit
    _slab("xz", up[0], up[1], T, d - 2 * T, side=-1)
    _slab("xz", low[0], low[1], T, d - 2 * T, side=1)
    def zat(seg, x):
        (x0, z0), (x1, z1) = seg
        return z0 + (z1 - z0) * (x - x0) / (x1 - x0)
    can = (0.80, 0.25, 0.20, 1)
    for x in (45, 125, 205, 285):
        cylinder(x, 4, zat(up, x) + 39, 37, 108, can, axis="y")
    for x in (300, 380):
        cylinder(x, 4, zat(low, x) + 39, 37, 108, can, axis="y")
    cylinder(42, 4, zat(low, 42) + 39, 37, 108, can, axis="y")


@model
def CarbonFilter():
    # The V-shaped filter pockets between their end plates: shown as the app assembles them.
    assembled("CarbonFilter")


@model
def Clock():
    R, cx = 100, 100
    disc = cylinder(cx, 0, R + 10, R, T, axis="y")
    for s in (-1, 1):
        fx = cx + s * 43
        hole(disc, fx - 1.8, -1, 9, 3.6, T + 2, 30)
        panel(fx - 1.5, -18, 0, T, 18 + T + 18, 32)
        extrude([(T, 72), (T, 58), (45, 0), (58, 0)], "yz", cx + s * 74.5 - 1.5, T)
    ink = (0.08, 0.08, 0.08, 1)
    cylinder(cx, -3.5, R + 10, 5, 2, ink, axis="y")
    extrude(_rot2([(cx - 3, R + 10 - 8), (cx + 3, R + 10 - 8), (cx + 1.5, R + 80), (cx - 1.5, R + 80)], -60, cx, R + 10), "xz", -1.5, 1.5, ink)
    extrude(_rot2([(cx - 3.5, R + 10 - 8), (cx + 3.5, R + 10 - 8), (cx + 2, R + 55), (cx - 2, R + 55)], 60, cx, R + 10), "xz", -1.5, 1.5, ink)
    extrude(_rot2([(cx - 1, R + 10 - 15), (cx + 1, R + 10 - 15), (cx + 1, R + 75), (cx - 1, R + 75)], 150, cx, R + 10), "xz", -3.2, 1.2, ACCENT)
    cylinder(cx, 0, R + 10 + R - 2, 10, T, axis="y")         # the little ear on top
    return dict(azimuth=30, elevation=20)


@model
def CoffeeCapsuleHolder():
    # A plate screwed under a shelf; three keyhole slots, the capsules hang by their rims in columns.
    W, D, cols, pitch = 120, 200, 3, 38
    plate = floor(0, 0, 0, W, D)
    xs = [20 + c * 40 for c in range(cols)]
    for x in xs:
        hole(plate, x - 15.5, 10, -1, 31, 165, T + 2)        # the slot
    round_holes(plate, [(x, 175, 0) for x in xs], 19.5)      # its round end, where a capsule goes in
    box(-12, D - 24, T + 4, W + 24, 36, 16)                  # the shelf strip the plate hangs from
    colours = ((0.15, 0.25, 0.30, 1), (0.75, 0.40, 0.18, 1), (0.90, 0.90, 0.86, 1))
    for x, col, count in zip(xs, colours, (5, 4, 5)):
        for k in range(count):
            y = 175 - (k + 1) * pitch
            cylinder(x, y, T, 18.5, 1.5, col)                # rim resting on the plate
            _cone(x, y, T - 24, 10, 15, 24, col)             # the body hanging below
    return dict(elevation=20)


@model
def CoinBankSafe():
    s = 100
    parts = closed_box(0, 0, 0, s, s, s)
    hole(parts[-1], 35, 48, s - T - 1, 30, 4, T + 2)         # coin slot
    front = parts[1]
    hole(front, 72, -1, 5, 1, T + 2, 90)                     # door seams
    hole(front, 5, -1, 94, 68, T + 2, 1)
    hole(front, 5, -1, 5, 68, T + 2, 1)
    for z in (25, 50, 75):                                   # the three dials
        cylinder(86, -4, z, 7, 4, axis="y")
        cylinder(86, -7, z, 4, 3, axis="y")
    box(36, -6, 45, 4, 6, 12)                                # handle


@model
def CoinDisplay():
    s = 106
    walls = open_box(0, 0, 0, s, s, s, fingers=False)
    walls.append(floor(0, 0, s - T, s, s))
    _glass(walls[1:])
    # the coin holder inside: two sloped sides, a back and a tilted plate with the coin
    x0, y0, cp = (s - 50) / 2, (s - 43) / 2, 50
    floor(x0 - T, y0, T, cp + 2 * T, 43)
    side = [(y0, 2 * T), (y0 + 43, 2 * T), (y0 + 43, 2 * T + 50), (y0, 2 * T + 25)]
    extrude(side, "yz", x0 - T, T)
    extrude(side, "yz", x0 + cp, T)
    panel(x0, y0 + 43 - T, 2 * T, cp, T, 50 - T)
    plate = _slab("yz", (y0, 2 * T + 25), (y0 + 43, 2 * T + 50), x0, cp)
    tilt = math.radians(30)
    cx, cy, cz = x0 + cp / 2, y0 + 21.5, 2 * T + 37.5
    nx = Vector((0, -math.sin(tilt), math.cos(tilt))) * (T / 2)
    cut = cylinder(0, 0, 0, 11, 20)
    cut.location = Vector((cx, cy, cz)) + nx
    cut.rotation_euler = (tilt, 0, 0)
    _cut(plate, cut)
    coin = cylinder(0, 0, 0, 10, 2, (0.85, 0.70, 0.30, 1))
    coin.location = Vector((cx, cy, cz)) + nx
    coin.rotation_euler = (tilt, 0, 0)


@model
def Desksign():
    w, hgt, ang = 150, 80, 60
    base, hh = hgt * math.cos(math.radians(ang)), hgt * math.sin(math.radians(ang))
    _slab("yz", (0, 0), (base, hh), 0, w)
    tri = [(0, 0), (base, 0), (base, hh)]
    extrude(tri, "yz", 12, T)
    extrude(tri, "yz", w - 12 - T, T)
    return dict(azimuth=55, elevation=25)


@model
def DiceTower():
    w, d, h = 80, 80, 170
    tray = open_box(-T, -90, 0, w + 2 * T, d + 90 + T, 12)
    floor(0, 0, T, w, d)
    wall_x(0, d - T, 2 * T, w, h - T)                        # back
    wall_y(0, T, 2 * T, d - 2 * T, h - T)
    wall_y(w - T, T, 2 * T, d - 2 * T, h - T)
    gap = d * math.tan(math.radians(30))
    wall_x(0, 0, 2 * T + gap, w, h - T - gap)                # front, open at the bottom
    z0 = 2 * T
    _slab("yz", (d - T, z0 + gap), (T, z0 + 1), T, w - 2 * T, side=1)
    _slab("yz", (T, z0 + 102), (d / 2, z0 + 79), T, w - 2 * T, side=-1)
    _slab("yz", (d - T, z0 + 158), (d / 2, z0 + 135), T, w - 2 * T, side=1)
    for x, y in ((15, -50), (45, -30)):
        box(x, y, T, 10, 10, 10, ACCENT)
    return dict(elevation=30)
