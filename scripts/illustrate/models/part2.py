"""Rack boxes, polygon boxes, sliding/hinged boxes, bee-keeping boxes and the flat hole patterns."""
import math

import bpy
from mathutils import Matrix

from iso import *


# ---- local helpers ---------------------------------------------------------------------------

def _cut(obj, cutters):
    """Subtracts several cutter objects (box / cylinder / prism) from obj with a single boolean."""
    bpy.ops.object.select_all(action="DESELECT")
    for c in cutters:
        c.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    bpy.ops.object.join()
    cutter = bpy.context.object
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    mod.solver = "FAST"   # the exact solver bridges hole loops with edges freestyle would ink
    return obj


def _slots(obj, rects):
    """Rectangular holes through obj: rects = [(x, y, z, w, d, h), …] (one boolean)."""
    return _cut(obj, [box(*r) for r in rects])


def _drill(obj, holes, z=0):
    """Round holes of differing radii along z through a panel at height z: holes = [(x, y, r), …]."""
    return _cut(obj, [cylinder(x, y, z - 50, r, 100, segments=24) for x, y, r in holes])


def _hinge_x(objs, y, z, deg):
    """Rotates objects about an axis parallel to x through (y, z); negative deg swings the front up."""
    bpy.context.view_layer.update()
    m = Matrix.Translation((0, y, z)) @ Matrix.Rotation(math.radians(deg), 4, "X") @ Matrix.Translation((0, -y, -z))
    for o in objs:
        o.matrix_world = m @ o.matrix_world


def _hinge_y(objs, x, z, deg):
    """Rotates objects about an axis parallel to y through (x, z); negative deg swings the right side up."""
    bpy.context.view_layer.update()
    m = Matrix.Translation((x, 0, z)) @ Matrix.Rotation(math.radians(deg), 4, "Y") @ Matrix.Translation((-x, 0, -z))
    for o in objs:
        o.matrix_world = m @ o.matrix_world


def _ngon(cx, cy, r, n, start=90):
    return [(cx + r * math.cos(math.radians(start + 360 * i / n)), cy + r * math.sin(math.radians(start + 360 * i / n)))
            for i in range(n)]


def _rack(inner_w, d, h, ear, lift=25):
    """Box with a flanged front panel, corner triangles and a lifted lid. Returns (front, lid)."""
    front = panel(0, 0, 0, inner_w + 2 * ear, T, h)
    open_box(ear, T, 0, inner_w, d, h, front=False)
    x0, x1, y0, y1, s = ear + T, ear + inner_w - T, T, d, 25
    for tri in ([(x0, y0), (x0 + s, y0), (x0, y0 + s)], [(x1, y0), (x1, y0 + s), (x1 - s, y0)],
                [(x0, y1), (x0, y1 - s), (x0 + s, y1)], [(x1, y1), (x1 - s, y1), (x1, y1 - s)]):
        prism(tri, h - 2 * T, T)
    lid = floor(x0, y0, h + lift, inner_w - 2 * T, d - T)
    return front, lid


def _rack_slots(front, w, h):
    """The four rack-mount slots in the ears of a 19"/10" front panel."""
    return _slots(front, [(x - 5, -1, z - 3.25, 10, T + 2, 6.5) for x in (8.5, w - 8.5) for z in (6, h - 6)])


# ---- rack boxes -------------------------------------------------------------------------------

@model
def Rack19Box():
    front, _ = _rack(442, 100, 86, 17)
    _rack_slots(front, 476, 86)


@model
def Rack10Box():
    front, _ = _rack(213, 100, 86, 17)
    _rack_slots(front, 247, 86)


@model
def RackBox():
    front, lid = _rack(100, 100, 100, 14)
    _cut(front, [cylinder(x, -50, z, 2.5, 100, axis="y", segments=24) for x in (7, 121) for z in (7, 93)])
    _drill(lid, [(x, y, 2) for x in (25, 103) for y in (11, 92)])


@model
def Rack19HalfWidth():
    w, ear, h, deep, shallow = 217, 17, 38, 124, 20
    front = panel(0, 0, 0, w + ear, T, h)
    plate = [(0, T), (w, T), (w, T + shallow), (0, T + deep)]
    prism(plate, 0, T)
    prism(plate, h - T, T)
    wall_y(0, T, T, deep, h - 2 * T)
    wall_y(w - T, T, T, shallow, h - 2 * T)
    # XLR, XLR, MIDI, 9V, wire, XLR on the front; two rack slots in the ear.
    _cut(front, [cylinder(x, -50, h / 2, r, 100, axis="y", segments=24)
                 for x, r in ((28, 11), (62, 11), (96, 8), (124, 4), (146, 3), (185, 11))])
    _slots(front, [(w + ear - 9, -1, z - 5, 6.5, T + 2, 10) for z in (9, h - 9)])


# ---- polygon boxes ----------------------------------------------------------------------------

@model
def RegularBox():
    pts = _ngon(0, 0, 50, 5)
    prism(pts, 0, T)
    hollow(pts, T, 57)


@model
def RegularStarBox():
    r, h = 50, 50
    lower, upper = _ngon(0, 0, r, 5, 90), _ngon(0, 0, r, 5, 90 + 36)
    prism(lower, 0, T)          # bottom half: floor + walls
    hollow(lower, T, h - 2 * T)
    hollow(upper, 0, h - T)     # top half, rotated 36°: walls + lid; the two cross into a star
    prism(upper, h - T, T)


# ---- housings with doors / hinges -------------------------------------------------------------

@model
def SideDoorHousing():
    s = 100
    for x in (0, s - T):                     # sides, stackable feet cut into the bottom edge
        hole(wall_y(x, 0, 0, s, s - T), x - 1, 12, -1, T + 2, s - 24, 6)
    floor(T, T, 8, s - 2 * T, s - 2 * T)
    wall_x(T, s - T, 8 + T, s - 2 * T, s - 2 * T - 8)   # back (second hatch, closed)
    wall_x(T, 0, 8 + T, s - 2 * T, 10)                  # low strip the front hatch sits on
    floor(0, 0, s - T, s, s)                            # top
    # The front hatch lying in front: panel, two lips, two latches.
    dy, dh = -118, s - 8 - 10 - 2 * T
    panel(0, dy, 0, s, dh, T)
    for x in (3, s - T - 3):
        panel(x, dy, T, T, dh, 6)
    box(0, dy + 4, T, 16, 6, 6)
    box(s - 16, dy + dh - 10, T, 16, 6, 6)


@model
def SideHingeBox():
    # Two half boxes sharing a hinge on one long edge; the upper half swung open like a book.
    w, d, h = 100, 150, 45
    open_box(0, 0, 0, w, d, h)                                          # lower half
    lid = open_box(0, 0, h, w, d, h - T, bottom=False) + [floor(0, 0, 2 * h - T, w, d)]
    _hinge_y(lid, 0, h, -120)                                           # swung open on the x=0 edge
    return dict(azimuth=-45)


# ---- sliding boxes ----------------------------------------------------------------------------

@model
def SlidingDrawer():
    w, d, h, out = 90, 140, 40, 55
    floor(0, 0, 0, w, d)
    floor(0, 0, h - T, w, d)
    wall_y(0, 0, T, d, h - 2 * T)
    wall_y(w - T, 0, T, d, h - 2 * T)
    wall_x(T, d - T, T, w - 2 * T, h - 2 * T)
    iw, ih = w - 2 * T - 2, h - 2 * T - 2
    parts = open_box(T + 1, -out, T + 1, iw, d - T - 2, ih)
    round_hole(parts[1], T + 1 + iw / 2, -out, T + 1 + ih, 11, axis="y", length=20)


@model
def SlidingLidBox():
    w, d, h, out, rail = 76, 186, 50, 60, 4.5
    floor(0, 0, 0, w, d)
    wall_y(0, 0, T, d, h + 2 * T)
    wall_y(w - T, 0, T, d, h + 2 * T)
    wall_x(T, d - T, T, w - 2 * T, h + 2 * T)       # back, full height
    wall_x(T, 0, T, w - 2 * T, h - T)               # front, lower: the lid slides over it
    for x in (T, w - T - rail):                     # lower and upper rails on both sides
        box(x, T, h - T, rail, d - 2 * T, T)
        box(x, T, h + T, rail, d - 2 * T, T)
    lid = panel(T + 1, -out, h, w - 2 * T - 2, d - T, T)
    hole(lid, w / 2 - 20, -out + 8, h - 1, 40, 20, T + 2)
    round_holes(lid, [(w / 2 - 20, -out + 18, h), (w / 2 + 20, -out + 18, h)], 10)


# ---- other boxes --------------------------------------------------------------------------------

@model
def StevensonScreenBox():
    w, d, h = 100, 100, 100
    h1 = h + 10                                     # front is higher: roof slopes to the back
    for x in (0, w - T):
        extrude([(0, 0), (d, 0), (d, h), (0, h1)], "yz", x, T)
    floor(T, (d - 50) / 2, 5, w - 2 * T, 50)
    for i in range(7):                              # front louvers, 45°, overlapping
        slanted_panel(T, 0, 5 + i * 13, w - 2 * T, 15, 15)
    panel(T, T, 98, w - 2 * T, T, h1 - 2 - 98)
    for i in range(6):                              # back louvers
        slanted_panel(T, d - T, 5 + i * 13, w - 2 * T, -15, 15)
    panel(T, d - 2 * T, 85, w - 2 * T, T, h - 2 - 85)
    extrude([(-T, h1 + 1), (d + T, h + 1), (d + T, h + T + 1), (-T, h1 + T + 1)], "yz", -T, w + 2 * T)   # roof


@model
def TwoPiece():
    s, h, lift = 80, 50, 25
    open_box(0, 0, 0, s, s, h)
    o = T + 1
    open_box(-o, -o, h + lift, s + 2 * o, s + 2 * o, h - T, bottom=False)
    floor(-o, -o, 2 * h + lift - T, s + 2 * o, s + 2 * o)


@model
def UnevenHeightBox():
    # A closed cuboid cut by a diagonal into a lower and an upper wedge; the upper one barely lifted.
    s, lo, hi, lift = 100, 55, 100, 4
    floor(0, 0, 0, s, s)
    wall_x(T, 0, T, s - 2 * T, lo - T)
    wall_x(T, s - T, T, s - 2 * T, hi - T)
    for x in (0, s - T):
        extrude([(0, T), (s, T), (s, hi), (0, lo)], "yz", x, T)
    floor(0, 0, hi - T + lift, s, s)
    wall_x(T, 0, lo + lift, s - 2 * T, hi - lo - T)
    for x in (0, s - T):
        extrude([(0, lo + lift), (s, hi - T + lift), (0, hi - T + lift)], "yz", x, T)
    return dict(azimuth=-45)                      # the diagonal on the right face, as in the photo


# ---- bee keeping ------------------------------------------------------------------------------

@model
def BeeQueenCage():
    # A small elongated cage lying flat: slit rows on the long faces, a round plug hole at one end.
    L, w = 90, 30
    parts = closed_box(0, 0, 0, L, w, w)
    round_hole(parts[3], 0, w / 2, w / 2, 8.5, axis="x")
    xs = [8 + i * 6 for i in range(13)]
    _slots(parts[1], [(x, -1, z, 2, T + 2, 9) for x in xs for z in (5, 16)])     # front slits
    _slots(parts[5], [(x, y, w - T - 1, 2, 9, T + 2) for x in xs for y in (5, 16)])   # top slits
    plug = (0.90, 0.86, 0.72, 1)
    cylinder(-18, w / 2, w / 2, 10, 3, plug, axis="x")                   # the plug, pulled out
    cylinder(-15, w / 2, w / 2, 7.5, 7, plug, axis="x")


@model
def BeeQueenTransportBox():
    w, d, h, lift = 151, 91, 92, 25
    parts = open_box(0, 0, 0, w, d, h)
    tray = floor(T, T, 15, w - 2 * T, d - 2 * T)                    # the cage holder layer
    _drill(tray, [(T + 5 + 22.5 + i * 45, T + 5 + 12.5 + j * 25, 9) for i in range(3) for j in range(3)], 15)
    rows = (25, 45, 65)
    _slots(parts[1], [(x, -1, z, 35, T + 2, 3) for x in (15, 58, 101) for z in rows])   # front air slots
    _slots(parts[3], [(-1, 18, z, T + 2, 55, 3) for z in rows])                          # side air slots
    o = T + 0.5
    open_box(-o, -o, h + lift, w + 2 * o, d + 2 * o, 4, bottom=False, fingers=False)     # over-the-top lid
    lid = floor(-o, -o, h + lift + 4, w + 2 * o, d + 2 * o)
    hexes = [(0, 0)] + [(7 * math.cos(math.radians(60 * k)), 7 * math.sin(math.radians(60 * k))) for k in range(6)]
    _drill(lid, [(cx + dx, cy + dy, 2.5) for cx in (18, w - 18) for cy in (16, d - 16) for dx, dy in hexes], h + lift + 4)


# ---- flat hole patterns -----------------------------------------------------------------------

@model
def FanHole():
    p = panel(0, 0, 0, 100, 100, T)
    round_hole(p, 50, 50, 0, 40)
    round_holes(p, [(x, y, 0) for x in (15, 85) for y in (15, 85)], 2)
    cylinder(50, 50, 0, 8, T)                                        # inner disc
    for i in range(10):                                              # ten swept arms
        a1, a2 = math.radians(36 * i), math.radians(36 * i + 55)
        p_in = (50 + 8 * math.cos(a1), 50 + 8 * math.sin(a1))
        p_out = (50 + 40 * math.cos(a2), 50 + 40 * math.sin(a2))
        dx, dy = p_out[0] - p_in[0], p_out[1] - p_in[1]
        k = 2.5 / math.hypot(dx, dy)
        nx, ny = dy * k, -dx * k
        prism([(p_in[0] + nx, p_in[1] + ny), (p_out[0] + nx, p_out[1] + ny),
               (p_out[0] - nx, p_out[1] - ny), (p_in[0] - nx, p_in[1] - ny)], 0, T)
    return dict(elevation=50)


@model
def FrontPanel():
    p = panel(0, 0, 0, 120, 80, T)
    hole(p, 15, 40, -1, 90, 28, T + 2)                               # display cut-out
    _drill(p, [(20 + i * 20, 20, 5) for i in range(5)] + [(8, 72, 2.5), (112, 72, 2.5)])
    return dict(elevation=50)


@model
def HolePattern():
    p = panel(0, 0, 0, 100, 70, T)
    centres = []
    for i, n in enumerate((4, 5, 6, 5, 4)):                          # a hexagonal field of holes
        centres += [(50 + (j - (n - 1) / 2) * 11, 35 + (i - 2) * 9.5, 0) for j in range(n)]
    _drill(p, [(x, y, 3.5) for x, y, _ in centres])
    return dict(elevation=50)


@model
def NemaPattern():
    p = panel(0, 0, 0, 60, 60, T)
    _drill(p, [(30, 30, 13)] + [(x, y, 1.8) for x in (17, 43) for y in (17, 43)])
    return dict(elevation=50)


@model
def SevenSegmentPattern():
    p = panel(0, 0, 0, 65, 110, T)
    l, w = 40, 5

    def segment(cx, cy, vertical):
        pts = [(-l / 2, 0), (-l / 2 + w, -w), (l / 2 - w, -w), (l / 2, 0), (l / 2 - w, w), (-l / 2 + w, w)]
        if vertical:
            pts = [(-v, u) for u, v in pts]
        return prism([(cx + u, cy + v) for u, v in pts], -1, T + 2)

    ox, oy = 5, 5
    cutters = [segment(ox + x, oy + y, True) for x in (5, 50) for y in (27.5, 72.5)]
    cutters += [segment(ox + 27.5, oy + y, False) for y in (5, 50, 95)]
    _cut(p, cutters)
    return dict(elevation=50)
