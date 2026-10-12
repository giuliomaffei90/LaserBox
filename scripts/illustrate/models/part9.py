"""Part 9: OttoLegs … TriangleLamp."""
import math

import bpy
from iso import *

PAPER = (0.80, 0.20, 0.18, 1)
FOAM = (0.85, 0.22, 0.20, 1)
WHITE = (0.95, 0.95, 0.92, 1)
SCREEN = (0.60, 0.64, 0.66, 1)  # top faces render near white, so the screen is a mid grey
GREY = (0.78, 0.80, 0.76, 1)
DARK = (0.18, 0.18, 0.20, 1)
GREEN = (0.30, 0.85, 0.40, 1)


# ---- local helpers -------------------------------------------------------------------------

def arc(cx, cy, r, a0, a1, n=12):
    """Points of an arc from a0 to a1 degrees (either direction), n segments."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def circle(cx, cy, r, n=48):
    return arc(cx, cy, r, 0, 360 - 360 / n, n - 1)


def frame(o, angle):
    """Maps local (s, k) to plane coordinates: s along a direction at `angle` degrees from the
    first plane axis, k along its left normal."""
    a = math.radians(angle)
    return lambda s, k: (o[0] + s * math.cos(a) - k * math.sin(a), o[1] + s * math.sin(a) + k * math.cos(a))


def rect(f, s0, s1, k0, k1):
    return [f(s0, k0), f(s1, k0), f(s1, k1), f(s0, k1)]


def dedupe(pts):
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def poly(pts, z, h, color=WOOD):
    """prism() with the outline cleaned and forced counter-clockwise."""
    pts = dedupe(pts)
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return prism(pts if area > 0 else pts[::-1], z, h, color)


def sheet(pts, plane, offset, thickness, color=WOOD):
    return extrude(dedupe(pts), plane, offset, thickness, color)


def strip(pts, t):
    """A polyline thickened by t towards its right-hand side (normal (-dv, du)) → polygon."""
    normals = []
    for i in range(len(pts) - 1):
        du, dv = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
        k = math.hypot(du, dv)
        normals.append((-dv / k, du / k))
    inner = []
    for i, (u, v) in enumerate(pts):
        ns = normals[max(0, i - 1):i + 1]
        nu, nv = sum(n[0] for n in ns) / len(ns), sum(n[1] for n in ns) / len(ns)
        inner.append((u + t * nu, v + t * nv))
    return pts + inner[::-1]


def rect_holes(obj, boxes):
    """Cuts several rectangular holes [(x, y, z, w, d, h), …] out of obj with one boolean."""
    cutters = []
    for x, y, z, w, d, h in boxes:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x + w / 2, y + d / 2, z + h / 2))
        c = bpy.context.object
        c.scale = (w, d, h)
        cutters.append(c)
    bpy.ops.object.select_all(action="DESELECT")
    for c in cutters: c.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    bpy.ops.object.join()
    cutter = bpy.context.object
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("holes", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    return obj


def mesh(verts, faces, color=WOOD, solidify=0):
    m = bpy.data.meshes.new("mesh")
    m.from_pydata(verts, [], faces)
    m.update()
    obj = bpy.data.objects.new("mesh", m)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material(color))
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if solidify:
        mod = obj.modifiers.new("solid", "SOLIDIFY")
        mod.thickness = solidify
    return obj


def tube(pts, plane, offset, length, t=T, color=WOOD):
    """hollow() along another axis: outline `pts` in `plane`, walls t thick."""
    cu = sum(p[0] for p in pts) / len(pts)
    cv = sum(p[1] for p in pts) / len(pts)
    inner = []
    for pu, pv in pts:
        du, dv = pu - cu, pv - cv
        k = math.hypot(du, dv) or 1
        inner.append((pu - du / k * t, pv - dv / k * t))
    outer = extrude(pts, plane, offset, length, color)
    cutter = extrude(inner, plane, offset - 1, length + 2)
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = outer.modifiers.new("hollow", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    return outer


# ---- models -----------------------------------------------------------------------------

@model
def OttoLegs():
    # The two legs of the Otto robot: a small box each, standing at the back of a foot plate that sticks forward.
    for fx in (0, 56):
        c = 5
        poly([(fx + c, 0), (fx + 46 - c, 0), (fx + 46, c), (fx + 46, 55 - c), (fx + 46 - c, 55),
              (fx + c, 55), (fx, 55 - c), (fx, c)], 0, T)
        closed_box(fx + 8, 20, T, 30, 30, 36)


@model
def OttoSoles():
    for y in (0, 48):
        c = 5
        sole = poly([(c, y), (58 - c, y), (58, y + c), (58, y + 38 - c), (58 - c, y + 38),
                      (c, y + 38), (0, y + 38 - c), (0, y + c)], 0, 4, FOAM)
        hole(sole, 4, y + 4, -1, 50, 30, 6)


@model
def PaperBox():
    w, d, h, t = 100, 80, 50, 1
    parts = open_box(0, 0, 0, w, d, h, t=t, fingers=False, color=PAPER)
    round_hole(parts[1], w / 2, 0, h, 7.5, axis="y")                # finger notch in the front
    # lid hinged on the back top edge, opened 110°: its inside faces the camera
    f = frame((d, h), 70)
    extrude(rect(f, 0, d, 0, t), "yz", 0, w, PAPER)               # lid
    for x in (0, w - t):                                           # side flaps
        extrude(rect(f, 2, d - 2, t, 21), "yz", x, t, PAPER)
    extrude(rect(f, d, d + t, t, 16), "yz", 0, w, PAPER)           # front tuck flap


@model
def PhoneHolder():
    w, a = 73, 25
    f = frame((0, 0), 90 - a)                                      # s up the plate, k towards the front
    extrude(rect(f, 0, 172, -T, 0), "yz", 0, w, WOOD)              # leaning front plate
    yb = 172 * math.sin(math.radians(a)) + 3
    panel(0, yb, 0, w, T, 154)                                     # vertical back plate
    for x in (0, w - T):                                           # side tabs holding the phone
        extrude(rect(f, 30, 106, 0, 11), "yz", x, T)
    for x in (27, 46):                                             # bottom supports with their ledge
        extrude([(45, 0), f(106, -T), f(1.4, -T)], "yz", x, T)
        extrude(rect(f, 30, 35, 0, 14), "yz", x, T)
    extrude(rect(f, 35, 165, 1, 9), "yz", 3.5, w - 7, DARK)         # the phone
    return dict(azimuth=25, elevation=25)


@model
def PhotoFrame():
    W, H = 205, 255
    front = extrude([(0, 0), (W, 0), (W, H), (0, H)], "xz", 0, T)
    hole(front, 25, -1, 25, W - 50, T + 2, H - 50)                  # window
    for x, z, w, h in ((0, 0, 20, H), (W - 20, 0, 20, H), (20, 0, W - 40, 20)):  # guide layer: U-shaped pocket
        panel(x, T, z, w, T, h)
    mat = panel(20, T + 0.3, 20, W - 40, 1, H - 40, GREY)
    hole(mat, 52, T - 1, 52, W - 104, 4, H - 104)
    panel(22, T + 1.5, 22, W - 44, 1, H - 44, ACCENT)               # the photo
    panel(0, 2 * T, 0, W, T, H)                                     # back layer
    return dict(elevation=22, azimuth=35)


@model
def PizzaShovel():
    w, d = 382, 400
    floor(0, 0, 0, w, d)
    # pusher at the front: side wedges, back wall and top, with the grip sticking out forwards
    wedge = [(0, T), (0, 36), (70, 36), (240, T)]
    for x in (0, w - T):
        extrude(wedge, "yz", x, T)
    wall_x(T, 0, T, w - 2 * T, 33)
    floor(T, T, 33, w - 2 * T, 69)
    f = frame((70, 36), math.degrees(math.atan2(-36 + T, 170)))
    extrude(rect(f, 60, 63, 0, 40), "yz", T, w - 2 * T)             # pusher bar across the slope
    grip = [(0, 5), (-240, 5)] + arc(-240, 20, 15, -90, -270, 10) + [(0, 35)]
    sheet(grip, "yz", w / 2 - 4.5, 9)
    return dict(azimuth=35)


@model
def PoleHook():
    d, ww = 50, 12
    full = ([(0, 0), (d + 2 * ww, 0), (d + 2 * ww, 2 * d)] + arc(d + 1.5 * ww, 2 * d, ww / 2, 0, 180, 6)
            + [(d + ww, 2 * d), (d + ww, d)] + arc(d / 2 + ww, d, d / 2, 0, -180, 12)
            + [(ww, d), (ww, 1.5 * d)] + arc(ww / 2, 1.5 * d, ww / 2, 0, 180, 6) + [(0, 1.5 * d)])
    half = ([(0, 0), (d + 2 * ww, 0), (d + 2 * ww, d), (d + ww, d)] + arc(d / 2 + ww, d, d / 2, 0, -180, 12)
            + [(ww, d), (ww, 1.5 * d)] + arc(ww / 2, 1.5 * d, ww / 2, 0, 180, 6) + [(0, 1.5 * d)])
    for y, pts in ((-7.5, full), (-4.5, half), (-1.5, full), (1.5, half), (4.5, full)):
        sheet(pts, "xz", y, T)
    for y in (-4.5, 1.5):                                            # the locks swung shut over the pole
        f = frame((d + 1.5 * ww, 2 * d), math.degrees(math.atan2(-20, -56)))
        extrude(rect(f, -6, 48, -6, 6), "xz", y, T)
    cx = d / 2 + ww
    cylinder(cx, -40, d, d / 2 - 1, 80, ACCENT, axis="y")            # the hooked pole
    for z in (-T, -2 * T):                                            # discs clamped to the other pole
        cylinder(cx, 0, z, cx, T)
    knob = [(cx + (22 + 3 * math.cos(10 * a)) * math.cos(a), (22 + 3 * math.cos(10 * a)) * math.sin(a))
            for a in (math.radians(i * 7.5) for i in range(48))]
    poly(knob, -3 * T, T)
    return dict(elevation=25)


@model
def Ramp():
    w, d, h = 160, 120, 60
    for x in (0, w - T):
        extrude([(0, 0), (d, 0), (d, h)], "yz", x, T)
    floor(T, 0, 0, w - 2 * T, d)
    wall_x(T, d - T, T, w - 2 * T, 52)
    f = frame((0, 0), math.degrees(math.atan2(h, d)))
    extrude(rect(f, 0, math.hypot(d, h), 0, T), "yz", 0, w)


@model
def RoyalGame():
    s = 25
    closed_box(0, 0, 0, 200, 75, 22)
    for x in range(8):
        for y in range(3):
            if x in (2, 3) and y != 1:
                continue
            box((x + 0.05) * s, (y + 0.05) * s, 22, 0.9 * s, 0.9 * s, 0.4, WOOD_EDGE)
    for x in (30, 55, 80):
        cylinder(x, -25, 0, 10, T)
    for x in (130, 160):
        r = s / 3 ** 0.5
        mesh([(x + r, -30, 0), (x - r / 2, -30 + s / 2, 0), (x - r / 2, -30 - s / 2, 0), (x, -30, s * (2 / 3) ** 0.5)],
             [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])


@model
def SevenSegmentClock():
    w, d, h = 254, 20, 100
    parts = open_box(0, 0, 0, w, d, h)
    floor(0, 0, h - T, w, d)
    panel(T, T + 1, T, w - 2 * T, 1.5, h - 2 * T, GREEN)             # the LED strip glow behind the digits
    cuts = []
    W, H, sw, g = 44, 80, 6, 1.5
    for dx in (10, 70, 140, 200):
        for z in (10, 10 + H / 2 - sw / 2, 10 + H - sw):
            cuts.append((dx + sw + g, -1, z, W - 2 * sw - 2 * g, T + 2, sw))
        for x in (dx, dx + W - sw):
            cuts.append((x, -1, 10 + sw + g, sw, T + 2, H / 2 - 1.5 * sw - 2 * g))
            cuts.append((x, -1, 10 + H / 2 + sw / 2 + g, sw, T + 2, H / 2 - 1.5 * sw - 2 * g))
    rect_holes(parts[1], cuts)
    round_holes(parts[1], [(127, 0, 40), (127, 0, 60)], 4, axis="y")
    return dict(elevation=18, azimuth=30)


@model
def Shadowbox():
    w, d, h, fw = 200, 41, 260, 13
    front = extrude([(0, 0), (w, 0), (w, h), (0, h)], "xz", 0, T)
    hole(front, fw, -1, fw, w - 2 * fw, T + 2, h - 2 * fw)
    for x in (0, w - T):
        panel(x, T, 0, T, d - T, h)
    floor(T, T, 0, w - 2 * T, d - T)
    floor(T, T, h - T, w - 2 * T, d - T)
    panel(T, d - T, T, w - 2 * T, T, h - 2 * T)                    # back
    # paper layers: cut-out scenery, each one a little further back
    scenes = [
        [(fw, fw), (w - fw, fw), (w - fw, 60), (150, 90), (120, 70), (90, 110), (60, 80), (fw, 100)],
        [(fw, fw), (w - fw, fw), (w - fw, 120), (160, 150), (130, 125), (100, 170), (70, 140), (fw, 160)],
        [(fw, fw), (w - fw, fw), (w - fw, 180), (140, 215), (100, 195), (fw, 220)],
    ]
    for i, pts in enumerate(scenes):
        extrude(pts, "xz", 7 + i * 9, 0.8, WHITE)
    return dict(elevation=22, azimuth=35)


@model
def Shoe():
    # Side profile (y, z): toe at y=0 with a low lip, a concave quarter pipe up to the vertical front of
    # the tall open-top box at the back. A bent sheet follows the profile between the two side walls.
    L, W, H, hf, ft, R = 140, 65, 90, 15, 25, 40
    curve = [(0, hf), (ft, hf)] + arc(ft, hf + R, R, -90, 0, 10)[1:] + [(ft + R, H)]
    side = [(0, 0), (L, 0), (L, H)] + curve[::-1]
    for x in (0, W - T):
        extrude(side, "yz", x, T)
    floor(T, 0, 0, W - 2 * T, L)
    panel(T, L - T, T, W - 2 * T, T, H - T)                         # back
    panel(T, 0, T, W - 2 * T, T, hf - 2 * T)                        # toe lip
    extrude(strip(curve, -T), "yz", T, W - 2 * T)                   # the bent sheet
    return dict(azimuth=35)


@model
def Sphere():
    R, gores = 100, 6
    t0, t1 = math.asin(30 / R), math.pi - math.asin(80 / R)
    N = 14
    for g in range(gores):
        verts, faces = [], []
        for i in range(N + 1):
            th = t0 + (t1 - t0) * i / N
            for lam in (g * 2 * math.pi / gores, (g + 1) * 2 * math.pi / gores):
                verts.append((R * math.sin(th) * math.cos(lam), R * math.sin(th) * math.sin(lam), R * math.cos(th)))
            if i:
                faces.append([2 * i - 2, 2 * i - 1, 2 * i + 1, 2 * i])
        mesh(verts, faces, WOOD, solidify=1.5)
    return dict(elevation=25)


@model
def Spool():
    h, ro, ri, ra = 100, 100, 40, 20
    for x in (0, h - T):
        disc = cylinder(0, x, 0, ro, T, axis="y")
        round_hole(disc, 0, x, 0, ra, axis="y")
    oct_ = [((ri + T) * math.cos(math.radians(22.5 + 45 * i)), (ri + T) * math.sin(math.radians(22.5 + 45 * i))) for i in range(8)]
    tube(oct_, "xz", T, h - 2 * T)


@model
def Stachel():
    ri, ro, rp, rpo, cx = 57.5, 64.5, 12.5, 20.5, 105
    a1 = math.degrees(math.asin(20 / ro))
    a2 = math.degrees(math.asin(20 / rpo))
    outline = (arc(0, 0, ro, -90 + a1, -a1, 6) + [(cx + rpo * math.cos(math.radians(-a2)), -20)]
               + arc(cx, 0, rpo, -a2, a2, 10) + [(cx + rpo * math.cos(math.radians(a2)), 20)]
               + arc(0, 0, ro, a1, 270 - a1, 40) + [(-20, -ro - 25), (20, -ro - 25)])
    for z, hgt, r in ((0, T, ri - 20), (T, 2 * T, ri)):
        layer = poly(outline, z, hgt)
        round_hole(layer, 0, 0, z, r)
        round_hole(layer, cx, 0, z, rp)
        rect_holes(layer, [(-1, -ro - 26, z - 1, 2, 30, hgt + 2), (cx + rp - 2, -1, z - 1, 12, 2, hgt + 2)])


@model
def Tetris():
    s = 40
    extrude([(0, 0), (2 * s, 0), (2 * s, s), (s, s), (s, 3 * s), (0, 3 * s)], "xz", 0, s)
    # etched lines marking the blocks
    for x, z, w, h in ((0, s, 2 * s, 1), (0, 2 * s, s, 1), (s, 0, 1, s)):
        box(x, -0.3, z, w, 0.3, h, WOOD_EDGE)
    for z in (s, 2 * s):
        box(-0.3, 0, z, 0.3, s, 1, WOOD_EDGE)


@model
def TrafficLight():
    h, d, s, n = 100, 100, 50, 3
    H = n * (h + T) - T + 2 * T
    parts = open_box(0, 0, 0, h, d, H)
    floor(0, 0, H - T, h, d)
    round_holes(parts[1], [(h / 2, 0, T + i * (h + T) + h / 2) for i in range(n)], h / 2 - T, axis="y")
    for i, color in enumerate(((0.85, 0.15, 0.10, 1), (0.95, 0.65, 0.10, 1), (0.20, 0.70, 0.30, 1))):
        z0 = T + i * (h + T)
        cylinder(h / 2, T + 1, z0 + h / 2, h / 2 - T - 4, 1.5, color, axis="y")
        for x in (0, h - T):                                        # the shade: two triangles and a top
            extrude([(0, z0), (0, z0 + h - T), (-s, z0 + h - T)], "yz", x, T)
        box(0, -s, z0 + h - T, h, s, T)


@model
def TriangleLamp():
    # A triangular prism: equilateral front / back faces, three side panels, standing on one side.
    e, D = 120, 60
    H = e * 3 ** 0.5 / 2
    tri = [(0, 0), (e, 0), (e / 2, H)]
    cx, cy = e / 2, H / 3
    inner = [(x + (cx - x) * 2 * T / (e / 3 ** 0.5), y + (cy - y) * 2 * T / (e / 3 ** 0.5)) for x, y in tri]
    for y in (0, D - T):
        wall = sheet(tri, "xz", y, T)
        cut = sheet([(x + (cx - x) * 0.55, z + (cy - z) * 0.55) for x, z in tri], "xz", y - 1, T + 2)
        cut.hide_render = True
        cut.display_type = "WIRE"
        mod = wall.modifiers.new("hole", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "FAST"
        mod.object = cut
    for i, (dx, dz) in enumerate(((0, 0), (0, 0), (-16, 9))):      # bottom, right, left (lifted off)
        a, b = tri[i], tri[(i + 1) % 3]
        a2, b2 = inner[i], inner[(i + 1) % 3]
        sheet([(a[0] + dx, a[1] + dz), (b[0] + dx, b[1] + dz), (b2[0] + dx, b2[1] + dz), (a2[0] + dx, a2[1] + dz)],
              "xz", T, D - 2 * T)
    return dict(azimuth=35, elevation=25)
