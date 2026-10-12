"""Models for ABox … PirateChest (part 1). Sizes are mm, walls use iso.T."""
import math
import bpy
from mathutils import Matrix, Vector
from iso import *

GLASS = (0.80, 0.92, 0.96, 1)
KEYCAP = (0.93, 0.93, 0.90, 1)
PAPER = (0.98, 0.92, 0.45, 1)
DICE = (0.15, 0.22, 0.62, 1)
DARK_WOOD = (0.52, 0.36, 0.20, 1)


def _names():
    return {o.name for o in bpy.data.objects}


def _since(before):
    return [o for o in bpy.data.objects if o.name not in before]


def _rotate(objs, pivot, axis, degrees):
    """Rotates objs (cutters included) about the axis through pivot."""
    bpy.context.view_layer.update()
    m = Matrix.Translation(Vector(pivot)) @ Matrix.Rotation(math.radians(degrees), 4, axis) @ Matrix.Translation(-Vector(pivot))
    for o in objs:
        o.matrix_world = m @ o.matrix_world


def _cut(obj, cutters):
    """One boolean subtracting all cutters (joined into one object) from obj."""
    bpy.ops.object.select_all(action="DESELECT")
    for c in cutters:
        c.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    if len(cutters) > 1:
        bpy.ops.object.join()
    cutter = bpy.context.view_layer.objects.active
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    return obj


def _hex(cx, cy, r):
    return [(cx + r * math.cos(math.radians(60 * i)), cy + r * math.sin(math.radians(60 * i))) for i in range(6)]


def _hex_plate(x, y, z, w, d, centres, apothem):
    """A floor plate with flat-top hexagonal holes of the given apothem."""
    plate = floor(x, y, z, w, d)
    r = apothem / math.cos(math.radians(30))
    return _cut(plate, [prism(_hex(cx, cy, r), z - 1, T + 2) for cx, cy in centres])


def _honeycomb(cx, cy, pitch):
    return [(cx, cy)] + [(cx + pitch * math.cos(math.radians(30 + 60 * i)), cy + pitch * math.sin(math.radians(30 + 60 * i))) for i in range(6)]


def _lid(w, d, hb, lh, angle, build=None):
    """A lid of height lh built behind the box (open side up) and swung onto the back top edge
    (y=d, z=hb): angle 180 closes it, 90 stands it upright, 80 leans it back."""
    before = _names()
    open_box(0, d, hb - lh, w, d, lh)
    if build:
        build()
    _rotate(_since(before), (0, d, hb), "X", angle)


def _feet(wall, x, y, z, w, d):
    """Cuts the middle (x..x+w, y..y+d) out of a wall's bottom edge so the corners stand like feet."""
    return hole(wall, x - 1, y - 1, z - 1, w + 2, d + 2, 7)


@model
def ABox():
    open_box(0, 0, 0, 100, 100, 100)


@model
def AngledBox():
    x, y, h = 130, 80, 50
    a = y / 2                                   # a 12-gon of apothem y/2, cut in two and stretched to x
    r = a / math.cos(math.radians(15))
    lx = x - 2 * a
    pts = [(x / 2 + lx / 2 + r * math.cos(math.radians(k)), y / 2 + r * math.sin(math.radians(k))) for k in range(-75, 76, 30)]
    pts += [(x / 2 - lx / 2 + r * math.cos(math.radians(k)), y / 2 + r * math.sin(math.radians(k))) for k in range(105, 256, 30)]
    prism(pts, 0, T)
    hollow(pts, T, h - T)
    prism(pts, h + 24, T)


@model
def BasedBox():
    floor(-12, -12, 0, 104, 104)
    closed_box(0, 0, T, 80, 80, 80)


@model
def BayonetBox():
    r, n, lh = 30, 5, 4                          # outer radius, number of stacked layers, layer height
    cylinder(0, 0, 0, r, T)
    for i in range(n):                           # outside rings, glued to the bottom
        round_hole(cylinder(0, 0, T + i * lh, r, lh), 0, 0, T + i * lh + lh / 2, r - 5)
    lift = T + n * lh + 30
    for i in range(2):                           # inside rings, glued to the lid
        round_hole(cylinder(0, 0, lift - (i + 1) * lh, r - 5.5, lh), 0, 0, lift - (i + 1) * lh + lh / 2, r - 10)
    cylinder(0, 0, lift, r, T)
    for k in range(0, 360, 120):                 # the locking lugs
        a = math.radians(k + 90)
        box(-3 + (r - 5.5) * math.cos(a), -3 + (r - 5.5) * math.sin(a), lift - 2 * lh, 6, 6, lh)


@model
def BrickSorter():
    def sieve(x, y, z, w, d, h, n):
        """Open box whose floor is a lattice of n×n holes (bars in two layers: no booleans)."""
        open_box(x, y, z, w, d, h, bottom=False)
        cell = (w - 2 * T - (n + 1) * T) / n
        for i in range(n + 1):
            panel(x + T, y + T + i * (cell + T), z, w - 2 * T, T, T)
            panel(x + T + i * (cell + T), y + T, z + T, T, d - 2 * T, T)
    sieve(0, 0, 0, 170, 170, 60, 4)
    sieve(10, 10, 95, 150, 150, 55, 6)      # the next, finer level lifted off (they nest for storage)


@model
def CardBox():
    w, d, h = 200, 90, 35
    open_box(0, 0, 0, w, d, h - T - 1)
    for i in (1, 2):
        wall = wall_y(i * (w / 3) - T / 2, T, T, d - 2 * T, h - 2 * T - 1)
        hole(wall, i * (w / 3) - T / 2 - 1, d / 2 - 15, h - 25, T + 2, 30, 30)
    floor(0, -0.4 * d, h - T, w, d)             # the sliding lid, pulled forward


@model
def Console2():
    w, d, h, fh, angle = 100, 100, 100, 30, 50
    pd = (h - fh) / math.tan(math.radians(angle))   # depth taken by the sloping panel
    top = d - pd
    z0 = 6                                           # the walls carry feet below the floor
    floor(T, T, z0, w - 2 * T, d - 2 * T)
    _feet(wall_x(T, d - T, 0, w - 2 * T, h), T + 18, d - T, 0, w - 2 * T - 36, T)
    _feet(wall_x(T, 0, 0, w - 2 * T, fh), T + 18, 0, 0, w - 2 * T - 36, T)
    slanted_panel(T, 0, fh, w - 2 * T, pd - T, h - fh - T)
    floor(T, d - top - T, h - T, w - 2 * T, top)
    side = [(0, 0), (d, 0), (d, h), (d - top, h), (0, fh)]
    for x in (0, w - T):
        _feet(extrude(side, "yz", x, T), x, 18, 0, T, d - 36)


@model
def Crate():
    w, d, h = 150, 200, 100
    floor(T, T, 6, w - 2 * T, d - 2 * T)
    for y in (0, d - T):
        wall = _feet(wall_x(0, y, 0, w, h, fingers=True), 20, y, 0, w - 40, T)
        hole(wall, w / 2 - 50, y - 1, h - 10 - 25, 100, T + 2, 25)   # the handle
    for x in (0, w - T):
        _feet(wall_y(x, 0, 0, d, h, fingers=True, phase=1), x, 24, 0, T, d - 48)


@model
def DiceBox():
    w, d, hb, lh = 100, 100, 18, 18
    open_box(0, 0, 0, w, d, hb)
    cells = _honeycomb(w / 2, d / 2, 25)
    _hex_plate(T, T, 6, w - 2 * T, d - 2 * T, cells, 11)
    for cx, cy in cells:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=7.5, location=(cx, cy, T + 7.5))
        bpy.context.object.data.materials.append(material(DICE))
    _lid(w, d, hb, lh, 80, lambda: _hex_plate(T, d + T, hb - lh + 6, w - 2 * T, d - 2 * T,
                                             _honeycomb(w / 2, d + d / 2, 25), 11))


@model
def DisplayCase():
    w, d, h = 160, 70, 90
    floor(0, 0, 0, w, d)
    parts = open_box(0, 0, T, w, d, h - 2 * T, bottom=False, fingers=False, color=GLASS)
    parts.append(panel(0, 0, h - T, w, d, T, GLASS))
    mat = material(GLASS)
    mat.blend_method = "BLEND"
    mat.shadow_method = "NONE"
    mat.show_transparent_back = False
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Alpha"].default_value = 0.3
    bsdf.inputs["Roughness"].default_value = 0.2


@model
def ElectronicsBox():
    w, d, h, tri = 100, 100, 40, 25
    base = prism(rounded_rect(-16, 0, w + 32, d, 8), 0, T)
    round_holes(base, [(-8, 14, 0), (-8, d - 14, 0), (w + 8, 14, 0), (w + 8, d - 14, 0)], 2.5)
    open_box(0, 0, T, w, d, h, bottom=False)
    for (cx, cy, sx, sy) in ((T, T, 1, 1), (w - T, T, -1, 1), (T, d - T, 1, -1), (w - T, d - T, -1, -1)):
        prism([(cx, cy), (cx + sx * tri, cy), (cx, cy + sy * tri)], T + h - 2 * T, T)
    lid = floor(0, 0, T + h + 26, w, d)
    round_holes(lid, [(7, 7, 0), (w - 7, 7, 0), (7, d - 7, 0), (w - 7, d - 7, 0)], 2)


@model
def EngravingFrame():
    s, fw = 140, 20                               # outer size, frame width
    before = _names()
    frame = extrude(rounded_rect(0, 0, s, s, 6), "xz", 0, 2 * T)
    hole(frame, fw, -1, fw, s - 2 * fw, 2 * T + 2, s - 2 * fw)
    panel(fw + 0.5, 2 * T - T - 0.3, fw + 0.5, s - 2 * fw - 1, T, s - 2 * fw - 1, DARK_WOOD)   # the engraving, recessed
    _rotate(_since(before), (0, 0, 0), "X", -10)
    sy, sz = 2 * T * math.cos(math.radians(10)) + s * math.sin(math.radians(10)), s * math.cos(math.radians(10)) - 2 * T * math.sin(math.radians(10))
    extrude([(2 * T + 0.3, 0), (48, 0), (sy + 0.3, sz)], "yz", s / 2 - T / 2, T)   # the back support
    for x in (15, s - 15 - 25):
        box(x, -12, 0, 25, 12, T)                 # feet


@model
def EuroRackSkiff():
    w, d, h = 320, 128, 100
    open_box(0, 0, 0, w, d, h)
    for y in (T, d - T - 8):
        rail = panel(T, y, h - 2 * T, w - 2 * T, 8, T)
        round_holes(rail, [(T + 10 + i * 20, y + 4, h - 2 * T) for i in range(int((w - 2 * T - 20) / 20) + 1)], 2)


@model
def HalfBox():
    x, h, d = 100, 100, 103
    floor(T, 0, 0, d - 2 * T, x)
    wall_x(T, x - T, T, d - 2 * T, h - T)
    tri = [(0, 0), (x, 0), (x, h)]
    for px in (0, d - T):
        extrude(tri, "yz", px, T)
    extrude([(0, T), (x - T, T), (x - T, h)], "yz", d / 2 - T / 2, T)


@model
def HingeBox():
    w, d, hb, lh = 100, 100, 80, 20
    open_box(0, 0, 0, w, d, hb)
    for x in (22, w - 32):
        box(x, d, hb - 16, 10, T, 16)                               # hinge leaf on the box
        cylinder(x - 1, d, hb, 2.2, 12, ACCENT, axis="x")            # the pin
    _lid(w, d, hb, lh, 80, lambda: [box(x, d - T, hb - 16, 10, T, 16) for x in (22, w - 32)])


@model
def IntegratedHingeBox():
    w, d, hb, lh, r = 100, 100, 80, 20, 10
    parts = open_box(0, 0, 0, w, d, hb)
    for wall in parts[3:]:                                            # notch for the hinge disc
        hole(wall, -1, d - r - 1, hb - r - 1, w + 2, r + 2, r + 2)
    arc = [(d + r * math.cos(math.radians(k)), hb + r * math.sin(math.radians(k))) for k in range(0, 271, 15)]
    side = [(d, hb - lh), (2 * d, hb - lh), (2 * d, hb), (d + r, hb)] + arc[1:]

    def build():
        for x in (0, w - T):
            extrude(side, "yz", x, T)
        cylinder(-1.5, d, hb, 3, w + 3, WOOD_EDGE, axis="x")          # the pin

    before = _names()
    floor(T, d, hb - lh, w - 2 * T, d)
    wall_x(T, d, hb - lh + T, w - 2 * T, lh - T)
    wall_x(T, 2 * d - T, hb - lh + T, w - 2 * T, lh - T)
    build()
    _rotate(_since(before), (0, d, hb), "X", 80)


@model
def Keypad():
    cols, rows, key, pitch, pad, h = 4, 3, 15.6, 19.6, 10, 30
    w, d = cols * pitch - (pitch - key) + 2 * pad, rows * pitch - (pitch - key) + 2 * pad
    closed_box(0, 0, 0, w, d, h)
    for i in range(cols):
        for j in range(rows):
            box(pad + i * pitch, pad + j * pitch, h + 0.4, key, key, 7, KEYCAP)


@model
def NotesHolder():
    w, d, h, z0 = 78, 78, 35, 6
    floor(T, T, z0, w - 2 * T, d - 2 * T)
    _feet(wall_x(0, d - T, 0, w, h), 12, d - T, 0, w - 24, T)
    for x in (0, w - 0.3 * w):
        _feet(wall_x(x, 0, 0, 0.3 * w, h), x + 5, 0, 0, 0.3 * w - 10, T)
    for x in (0, w - T):
        wall_y(x, T, z0, d - 2 * T, h - z0)
    box(T + 3, T + 3, z0 + T, w - 2 * T - 6, d - 2 * T - 6, 20, PAPER)


@model
def OpenBox():
    open_box(0, 0, 0, 120, 90, 80, front=False)


@model
def PirateChest():
    w, d, hb = 100, 100, 70
    open_box(0, 0, 0, w, d, hb)
    a = d / 2
    r = a / math.cos(math.radians(22.5))
    k = r * math.sin(math.radians(22.5))
    prof = [(0, 0), (0, k), (a - k, a), (a + k, a), (d, k), (d, 0)]    # half an octagon, standing on the box
    side = [(y, hb + z) for y, z in prof]
    for x in (0, w - T):
        extrude(side, "yz", x, T)
    for (y0, z0), (y1, z1) in zip(side, side[1:]):                    # the facets, T thick, inward
        nx, nz = z1 - z0, -(y1 - y0)
        n = math.hypot(nx, nz)
        nx, nz = nx / n * T, nz / n * T
        extrude([(y0, z0), (y1, z1), (y1 + nx, z1 + nz), (y0 + nx, z0 + nz)], "yz", T, w - 2 * T)
    for x in (-T, w):                                                  # the hinge discs
        cylinder(x, d - 10, hb, 10, T, axis="x")
        cylinder(x - 0.3 if x < 0 else x + T, d - 10, hb, 4, 0.3, WOOD_EDGE, axis="x")
