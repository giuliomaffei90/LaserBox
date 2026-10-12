"""Wall-mounted holders. The wall is the plane y = 0; every holder hangs in front of it (y <= 0).

Profiles of side pieces are (y, z) polygons extruded along x with `side()`.
"""
import math

from iso import *

PALE = (0.93, 0.90, 0.84, 1)     # the pegboard hint behind the holder
SLOT = (0.35, 0.28, 0.20, 1)
STEEL = (0.72, 0.73, 0.76, 1)
PAPER = (0.96, 0.96, 0.94, 1)
PEG = (0.25, 0.55, 0.32, 1)      # the green pegs of the pin row


def side(points, x, t=T, color=WOOD):
    """A plywood piece standing perpendicular to the wall: (y, z) outline, t thick, at x."""
    return extrude(points, "yz", x, t, color)


def arc(cy, cz, r, a0, a1, n=8):
    """Points on a circle in the (y, z) plane from angle a0 to a1 (degrees)."""
    return [(cy + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def wall_hint(x0, x1, z0, z1, pitch=40):
    """A small pale pegboard panel at y = 0..2 with a few Skadis-style slots."""
    panel(x0, 0, z0, x1 - x0, 2, z1 - z0, PALE)
    row = 0
    z = z0 + 12
    while z < z1 - 14:
        x = x0 + 10 + (pitch / 2 if row % 2 else 0)
        while x < x1 - 10:
            box(x, -0.6, z, 5, 0.6, 14, SLOT)
            x += pitch
        z += pitch / 2
        row += 1


def slots_on(x0, z0, w, h, y=-0.6, pitch=40):
    """Skadis slot pattern drawn as dark strips on the front face at y of a board."""
    row = 0
    z = z0 + 12
    while z < z0 + h - 14:
        x = x0 + 10 + (pitch / 2 if row % 2 else 0)
        while x < x0 + w - 10:
            box(x, y, z, 5, 0.6, 14, SLOT)
            x += pitch
        z += pitch / 2
        row += 1


@model
def DinRailBox():
    w, d, h = 70, 60, 90                       # x, h (depth from the rail), y (height along the rail)
    closed_box(0, -d, 0, w, d - 4, h)          # the box, lid at the front
    panel(0, -d - T, 0, w, T, h)               # lid, a plain plate on the front
    # DIN rail (top hat, 35 mm) running behind the box.
    rail = [(0, 0), (-7.5, 0), (-7.5, 8), (-1.5, 8), (-1.5, 27), (-7.5, 27), (-7.5, 35), (0, 35),
            (0, 33.5), (-6, 33.5), (-6, 28.5), (0, 28.5), (0, 6.5), (-6, 6.5), (-6, 1.5), (0, 1.5)]
    rail = [(y, z + h / 2 - 17.5) for y, z in rail]   # centred on the box height
    side(rail, -40, 150, STEEL)


@model
def KeyHolder():
    n, pitch = 7, 20
    w, h = 10 + n * pitch, 60
    panel(0, -T, 0, w, T, h)
    # J-shaped hooks slotted into the plate, 5 mm thick, with a little lip at the tip.
    hook = [(-T, 20), (-T, 40), (-6, 40), (-6, 25), (-16, 25), (-16, 32), (-21, 32), (-21, 20)]
    for i in range(n):
        side(hook, 10 + i * pitch, 5)
    wall_hint(-20, w + 20, -15, h + 15)


@model
def RollHolder():
    w, dia, h, r = 275, 120, 80, 12
    wall_hint(-20, w + 40, -20, h + 30)
    panel(0, -T, 0, w + 20, T, h)
    bracket = [(-T, 0), (-T, h), (-dia / 2 - 12, h), (-dia / 2 - 12, h - 26), (-dia / 2 + 10, h - 26)]
    for x in (12, w + 5):
        side(bracket, x)
    cylinder(-30, -dia / 2, h - 13, r, w + 60, ACCENT, "x")
    cylinder(10, -dia / 2, h - 13, dia / 2 - 10, w - 20, PAPER, "x")


@model
def SkadisBoard():
    w, h = 280, 360
    extrude(rounded_rect(0, 0, w, h, 12), "xz", -5, 5)
    slots_on(0, 0, w, h, -5.6)


@model
def SkadisStand():
    # Mirrored in y (the slotted board looks the same from both sides): the board leans towards
    # the camera and the feet are in front of it, so both are lit and visible.
    w, h, a = 240, 200, math.radians(70)
    k = 1 / math.tan(a)                      # horizontal run per unit height of the leaning board
    yb = 40                                   # the board's lower face at the floor
    slanted_panel(0, yb, 0, w, -h * k, h)
    foot = [(yb, 0), (yb - 100, 0), (yb - 100, 10), (yb - 10 - 10 * k, 10),
            (yb - 10 - 150 * k, 150), (yb - 150 * k, 150)]
    for x in (40, w - 50):
        side(foot, x, 10)
    for i in range(6):                        # slots on the leaning board
        for j in range(4):
            z = 30 + i * 30
            xo = 30 + j * 60 + (30 if i % 2 else 0)
            bpy.ops.mesh.primitive_cube_add(size=1, location=(xo + 2.5, yb - (z + 7) * k - 0.3, z + 7))
            o = bpy.context.object
            o.scale = (5, 0.6, 14)
            o.rotation_euler = (math.pi / 2 - a, 0, 0)
            o.data.materials.append(material(SLOT))


@model
def WallCaliper():
    h, hc = 100, 6
    w = 18 + 4 * T
    wall_hint(-25, w + 25, -20, h + 20)
    panel(0, -T, 0, w, T, h)
    prof = [(-T, 0), (-24, 0), (-24, 48), (-20, 48), (-20, 24), (-15 + hc - 6, 24), (-9, h), (-T, h)]
    # the caliper beam drops into the channel between the two fingers
    side(prof, 0)
    side(prof, w - T)


@model
def WallChiselHolder():
    n, pitch, d, h = 6, 32, 42, 120
    w = n * pitch + 6
    wall_hint(-20, w + 20, -30, h + 20)
    panel(0, -T, 0, w, T, h)
    # Top plate with a round hole per tool and a slot from the front edge.
    pts = [(0, -T), (0, -d)]
    for i in range(n):
        cx = 3 + pitch * (i + 0.5)
        pts += [(cx - 2.5, -d), (cx - 2.5, -d / 2), (cx + 2.5, -d / 2), (cx + 2.5, -d)]
    pts += [(w, -d), (w, -T)]
    top = prism(pts, h - T, T)
    round_holes(top, [(3 + pitch * (i + 0.5), -d / 2, h) for i in range(n)], 12)
    for x in (0, w - T):
        side([(-T, 0), (-T, h - T), (-d, h - T), (-d, h - 60)], x)


@model
def WallConsole():
    w, h, td, bd = 100, 100, 50, 35
    wall_hint(-25, w + 25, -20, h + 20)
    panel(0, -T, 0, w, T, h)
    prof = [(-T, 0), (-bd, 0), (-td, h), (-T, h)]
    side(prof, 0)
    side(prof, w - T)
    slanted_panel(T, -bd, 0, w - 2 * T, -(td - bd), h)


@model
def WallDrillBox():
    sx, sy, sh, eh = [25] * 6, [10, 20, 30], [25, 40, 60], 15
    w = sum(sx) + 5 * T
    d = sum(sy)
    wall_hint(-20, w + 40, -20, max(sh) + eh + 20)
    # side walls and dividers: stepped profile, taller towards the right
    x = 0
    for i in range(7):
        e = eh * x / w
        prof = [(0, 0), (-d, 0), (-d, sh[0] + e), (-d + sy[0], sh[0] + e), (-d + sy[0], sh[1] + e),
                (-d + sy[0] + sy[1], sh[1] + e), (-d + sy[0] + sy[1], sh[2] + e), (0, sh[2] + e)]
        side(prof, x)
        x += (sx[i] + T) if i < 6 else 0
    floor(T, -d, 0, w - 2 * T, d)
    # row walls, each with the sloped top edge
    y = -d
    for i, (depth, hh) in enumerate(zip(sy, sh)):
        extrude([(T, 0), (w - T, 0), (w - T, hh + eh), (T, hh)], "xz", y, T)
        y += depth
    extrude([(T, 0), (w - T, 0), (w - T, sh[2] + eh), (T, sh[2])], "xz", -T, T)


@model
def WallEdges():
    h = 120
    wall_hint(-15, 4 * 50 + 5, -25, h + 35)
    for i in range(4):
        x = i * 50
        panel(x, -8, 0, 40, T, h)
        if i < 3:  # hooks at the top reaching into the wall
            for xo in (4, 26):
                box(x + xo, -8, h - 2, 10, 8, 14)
        if i in (1, 3):  # and at the bottom
            box(x + 15, -8, -6, 10, 8, 12)
        if i == 2:
            for z in range(12, h - 14, 20):
                box(x + 17.5, -8.6, z, 5, 0.6, 14, SLOT)


@model
def WallHook():
    h, hid, ht, w = 100, 40, 20, 10
    wall_hint(-45, w + 50, -20, h + 20)
    cy, cz = -37, 40
    prof = [(0, 0), (-37, 0)] + arc(cy, cz, 40, 270, 180) + \
        arc(-67, cz, 10, 180, 0) + arc(cy, cz, 20, 180, 360) + [(-17, 80)] + arc(0, 80, 17, 180, 90)
    side(prof, 0)
    side(prof, w + T)
    panel(T, -T, 0, w, T, h - 4)
    panel(T, -40, 10, w, 37, T)       # cross piece in the bottom arm
    panel(T, -68.5, 22, w, T, 20)     # cross piece in the front tip


@model
def WallHopper():
    w, h, hd, dd, dh = 80, 150, 50, 45, 50
    d = hd + dd
    wall_hint(-25, w + 25, -20, h + 20)
    prof = [(0, 0), (-d + 18, 0), (-d, 10), (-d, dh), (-hd, dh), (-hd, h), (0, h)]
    side(prof, 0)
    side(prof, w - T)
    panel(T, -T, 0, w - 2 * T, T, h)                      # back
    floor(T, -d + 18, 0, w - 2 * T, d - 18 - T)           # flat bottom
    extrude([(-d + 18, 0), (-d, 10), (-d, 13), (-d + 18, 3)], "yz", T, w - 2 * T)  # sloped bit
    panel(T, -d, 10, w - 2 * T, T, dh - 15)               # front lip with the label area
    panel(T, -hd, 45, w - 2 * T, T, h - 45)               # hopper front, gap at the bottom


@model
def WallPinRow():
    n, pitch, h, a = 8, 35, 50, math.radians(20)
    w = n * pitch
    wall_hint(-20, w + 20, -20, h + 25)
    yb, yt = -30, -13                                    # front plate leans back by 20 degrees
    extrude([(yb, 4), (yb + T, 4), (yt + T, h + 2), (yt, h + 2)], "yz", 0, w)
    panel(0, -T, 0, w, T, h / 2)                          # back plate, half height
    prof = [(0, 0), (yb - 2, 0), (yb - 2, 4), (yt, h + 2), (0, h + 2)]
    for x in (0, w / 2 - T / 2, w - T):
        side(prof, x)
    L, r = 40, 3.5                                        # round pegs, square to the plate: out and 20 degrees up
    y0 = yb + (h / 2 - 4) / (h - 2) * (yt - yb) + 1       # the plate's front face at mid height
    for i in range(n):
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=L + 2, rotation=(math.pi / 2 - a, 0, 0),
                                            location=(pitch * (i + 0.5), y0 - L / 2 * math.cos(a), h / 2 + L / 2 * math.sin(a)))
        bpy.context.object.data.materials.append(material(PEG))


@model
def WallPlaneHolder():
    w, l, hl, h = 80, 250, 30, 80
    sd, sl = h + 4 * T, l + 2 * T
    wall_hint(-25, w + 30, -20, sl + 20)
    for x in (0, w + T):
        side([(0, 0), (-sd, 0), (-sd, sl), (0, sl)], x)
    floor(T, -sd + T, 2 * T, w, sd - 2 * T)               # the plane stands on this shelf
    panel(T, -2 * T, 2 * T, w, T, l / 4)                   # back plates, bottom and top quarter
    panel(T, -2 * T, 2 * T + 0.75 * l, w, T, l / 4)
    panel(T, -sd + T, sl - T - hl, w, T, hl)               # front strip holding the plane
    return dict(azimuth=40)


@model
def WallPliersHolder():
    w, d, h = 300, 50, 50
    wall_hint(-20, w + 20, -20, 2 * h + 20)
    panel(0, -d, h, w, T, h)
    prof = [(0, 0), (-d + T, h), (-d + T, 2 * h), (0, 2 * h)]
    for x in (0, 100, 200, w - T):
        side(prof, x)


@model
def WallRack():
    w, d, fh, bh = 200, 50, 20, 30
    panel(0, -T, 0, w + 2 * T, T, 300)
    for i in range(3):
        z = i * 100
        floor(T, -d - T, z, w, d)
        panel(T, -d - T, z + T, w, T, fh - T)
        for x in (0, w + T):
            side([(-T, z + T), (-d - T, z + T), (-d - T, z + fh), (-T, z + bh)], x)


@model
def WallRollHolder():
    w, dia, h, r = 275, 120, 80, 12
    pw = w + h / 2 + 2 * T
    wall_hint(-20, pw + 20, -20, h + 30)
    panel(0, -T, 0, pw, T, h)
    for x in (pw - 30, pw - 20):
        side([(-T, h - 20), (-dia / 2 - 12, h - 20), (-dia / 2 - 12, h - 14), (-T, h)], x)
    cylinder(5, -dia / 2, h - 23, r, pw - 20, ACCENT, "x")
    cylinder(pw - 34, -dia / 2, h - 23, 20, T, WOOD, "x")   # ring
    cylinder(10, -dia / 2, h - 23, dia / 2 - 10, w - 55, PAPER, "x")


@model
def WallSlottedHolder():
    # Three prongs sticking out of the wall, sloping down 25 degrees, joined by a slotted top plate.
    n, gap, L, H, tw, a = 3, 35, 90, 100, 14, math.radians(25)
    w = n * T + (n - 1) * gap
    ca, sa = math.cos(a), math.sin(a)
    wall_hint(-20, w + 20, -30, H + 25)
    panel(0, -T, 0, w, T, H)                                       # strip on the wall
    tip = (-L * ca + tw / 2 * sa, H - 0.3 - L * sa - tw / 2 * ca)  # centre of the rounded tip
    prof = [(-T, 0), (-T, H - 0.3 - T * sa / ca)] + arc(*tip, tw / 2, 115, 295)
    for i in range(n):
        side(prof, i * (gap + T))
    pts = [(0, -T / ca), (0, -L)]                                  # top plate, slots between the prongs
    for i in range(n - 1):
        gx = T + gap / 2 + i * (gap + T)
        pts += [(gx - 3, -L), (gx - 3, -30)] + arc(gx, -30, 3, 180, 0) + [(gx + 3, -L)]
    pts += [(w, -L), (w, -T / ca)]
    top = prism(pts, 0, T)
    top.rotation_euler = (a, 0, 0)
    top.location = (0, 0, H)
    return dict(elevation=12, azimuth=25)                         # low and frontal: the gaps between the prongs show


@model
def WallStackableBin():
    w, d, h = 90, 150, 130
    wall_hint(-25, w + 25, -20, h + 20)
    prof = [(0, 0), (-110, 0), (-d, 23), (-d, 62), (-100, h), (0, h)]
    side(prof, 0)
    side(prof, w - T)
    panel(T, -T, 0, w - 2 * T, T, h)
    floor(T, -110, 0, w - 2 * T, 110 - T)
    extrude([(-110, 0), (-d + 2, 23 - 1), (-d + 2, 26 - 1), (-110, 3)], "yz", T, w - 2 * T)
    panel(T, -d, 23, w - 2 * T, T, 62 - 23)


@model
def WallStairs():
    sx, sy, sh = [250 / 3] * 3, [40] * 3, [30, 100, 180]
    w = sum(sx) + 2 * T
    d = sum(sy)
    wall_hint(-20, w + 20, -20, max(sh) + 20)
    prof = [(0, 0), (-d, 0), (-d, sh[0]), (-d + sy[0], sh[0]), (-d + sy[0], sh[1]),
            (-d + sy[0] + sy[1], sh[1]), (-d + sy[0] + sy[1], sh[2]), (0, sh[2])]
    x = 0
    for i in range(4):
        side(prof, x)
        x += sx[0] + T if i < 3 else 0
    y = -d
    for depth, hh in zip(sy, sh):
        floor(T, y, hh - T, w - 2 * T, depth)
        y += depth
    panel(T, -T, 0, w - 2 * T, T, 30)                        # brace at the bottom back


@model
def WallTypeTray():
    w, d, h = 150, 100, 60
    open_box(0, -d, 0, w, d, h, back=False)
    wall_x(0, -T, T, w, h - T)
    wall_hint(-25, w + 25, -20, h + 30)
    for x in (50, 100):
        wall_y(x - T / 2, -d + T, T, d - 2 * T, h - T)
    wall_x(T, -d / 2 - T / 2, T, w - 2 * T, h - T)


@model
def WallWrenchHolder():
    # Two slotted cheeks on a back plate; the wrenches lie across them, in slots sloping to the wall.
    w, d, h, n, pitch, sw, sl, a = 100, 40, 150, 11, 12.5, 6, 18, math.radians(30)
    ca, sa = math.cos(a), math.sin(a)
    wall_hint(-25, w + 25, -20, h + 20)
    panel(T, -T, 0, w - 2 * T, T, h)
    prof = [(0, 0), (-d, 0)]
    for i in range(n):
        z = 12 + i * pitch
        prof += [(-d, z), (-d + sl * ca, z - sl * sa), (-d + sl * ca, z + sw - sl * sa), (-d, z + sw)]
    prof += [(-d, h), (0, h)]
    side(prof, 0)
    side(prof, w - T)
    for i, k in enumerate((1, 4, 7, 10)):                 # wrenches: a flat shank and two ring heads
        y, z = -d + sl * ca, 12 + k * pitch + sw / 2 - sl * sa
        c = (y - 6 * ca, z + 6 * sa)                          # shank centre, 6 mm out of the slot bottom
        bpy.ops.mesh.primitive_cube_add(size=1, location=(w / 2, *c), rotation=(math.pi / 2 - a, 0, 0))
        bar = bpy.context.object
        bar.scale = (w + 40, 4, 10)
        bar.data.materials.append(material(STEEL))
        r = 9 + 1.2 * i
        for x in (-20 - r + 3, w + 20 + r - 3):
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=4, location=(x, *c), rotation=(-a, 0, 0))
            bpy.context.object.data.materials.append(material(STEEL))