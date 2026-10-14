"""Models, part 8: Dispenser … NightLightBox."""
import math
import bpy
from iso import *

GREY = (0.72, 0.72, 0.75, 1)
DARK = (0.16, 0.16, 0.18, 1)


def arc(cx, cy, r, a0, a1, n=8):
    """Points on a circle from angle a0 to a1 (degrees), inclusive."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def cut(obj, points, z, h):
    """Subtracts the vertical extrusion of an xy polygon from obj."""
    cutter = prism(points, z, h)
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    return obj


def pyramid(points, z, h, color=WOOD):
    """A solid pyramid over an xy polygon base, apex h above the base centroid."""
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    verts = [(px, py, z) for px, py in points] + [(cx, cy, z + h)]
    faces = [list(range(n))[::-1]] + [[i, (i + 1) % n, n] for i in range(n)]
    mesh = bpy.data.meshes.new("pyramid")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("pyramid", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material(color))
    return obj


def sphere(x, y, z, r, color):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(x, y, z), segments=32, ring_count=16)
    obj = bpy.context.object
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(material(color))
    return obj


def hexagon(r, cx=0, cy=0):
    return [(cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30))) for i in range(6)]


@model
def Dispenser():
    x, y, h, hs = 100, 100, 100, 10
    # Floor with the deep finger cut-out at the front.
    prism([(0, 0), (x / 4, 0), (x / 4, y * 2 / 3), (3 * x / 4, y * 2 / 3), (3 * x / 4, 0), (x, 0),
           (x, y), (0, y)], 0, T)
    wall_x(0, y - T, T, x, h - T)                 # back
    wall_y(0, T, T, y - 2 * T, h - T)             # sides
    wall_y(x - T, T, T, y - 2 * T, h - T)
    w = x / 3                                     # two front panels leave a viewing slot in the middle
    wall_x(0, 0, hs, w, h - hs)                   # and the dispensing slot underneath
    wall_x(x - w, 0, hs, w, h - hs)
    floor(T, T, h - T, x - 2 * T, y - 2 * T)      # two-layer lid
    floor(0, 0, h, x, y)


@model
def Display():
    x, H, a, b = 150, 240, 20, 25           # panel leans back a°, the foot tilts up b°
    sa, ca = math.sin(math.radians(a)), math.cos(math.radians(a))
    sb, cb = math.sin(math.radians(b)), math.cos(math.radians(b))
    # Panel coordinates: v along the panel from its bottom edge, w into the thickness.
    P = lambda v, w: (v * sa + w * ca, v * ca - w * sa)
    def slab(v0, v1, x0, w):
        extrude([P(v0, 0), P(v1, 0), P(v1, T), P(v0, T)], "yz", x0, w)
    vs = 40                                 # the slot the foot passes through
    slab(0, vs - 2.5, 0, x)
    slab(vs + 2.5, H, 0, x)
    slab(vs - 2.5, vs + 2.5, 0, 22)
    slab(vs - 2.5, vs + 2.5, x - 22, 22)
    # The foot: a plate through the slot, its rear end on the ground, its front end a raised lip.
    py, pz = vs * sa + T / 2 * ca, vs * ca - T / 2 * sa
    rear = pz / sb
    f, nrm = (-cb, sb), (sb, cb)
    def F(s, k):
        return (py + s * f[0] + k * nrm[0], pz + s * f[1] + k * nrm[1])
    extrude([F(-rear, -T / 2), F(60, -T / 2), F(60, T / 2), F(-rear, T / 2)], "yz", 23, x - 46)


@model
def DrillStand():
    x, rows, dh = 165, ((0, 13), (16, 36), (39, 69)), 15   # row y-ranges (10/20/30 deep)
    y, sh = 72, (25, 40, 60)
    floor(0, 0, 0, x, y)
    # Walls along x: tops rise from left to right by dh.
    ys = [0, 13, 36, 69]
    for yy, hh in zip(ys, (sh[0], sh[1], sh[2], sh[2])):
        extrude([(0, T), (x, T), (x, T + hh + dh), (0, T + hh)], "xz", yy, T)
    # Side and divider walls: stepped, each step at the height of its row at that x.
    for xx in (0, 28, 56, 84, 112, 140, x - T):
        k = dh * (xx + T / 2) / x
        h1, h2, h3 = (s + k + T for s in sh)
        extrude([(0, T), (y, T), (y, h3), (37.5, h3), (37.5, h2), (14.5, h2), (14.5, h1), (0, h1)], "yz", xx, T)


@model
def FatBallDispenser():
    r, rr, hb, L = 62, 84, 20, 185
    base = hexagon(r)
    prism(base, 0, T)                      # floor
    hollow(base, T, hb)                    # balcony walls
    for px, py in hexagon(r - 14):         # the six poles
        cylinder(px, py, T, 4, L, WOOD_EDGE, segments=16)
    prism(hexagon(r), T + L, T)            # ceiling
    prism(hexagon(36), 2 * T + L, 6)       # bracket / spacer stack
    prism(hexagon(rr), 2 * T + L + 6, T)   # roof bottom plate
    pyramid(hexagon(rr), 3 * T + L + 6, 50)
    cylinder(0, 0, 3 * T + L + 56, 1.5, 14, GREY, segments=12)   # the hook
    for i in range(2):                     # fat balls
        sphere(0, 0, T + 34 + i * 68, 34, (0.62, 0.52, 0.34, 1))


@model
def FilamentSpool():
    R, ri, ra, h = 100, 50, 25, 48
    zc = R
    a = cylinder(0, 0, zc, R, T, axis="y", segments=64)
    b = cylinder(0, h - T, zc, R, T, axis="y", segments=64)
    hub = cylinder(0, T, zc, ri, h - 2 * T, axis="y", segments=8)
    for o in (a, b, hub):
        round_hole(o, 0, 0, zc, ra, axis="y")
    return dict(azimuth=35)


@model
def FrameLoom():
    L, W, b = 235, 165, 14
    floor(0, 0, 0, b, L, T)                    # side rails
    floor(W - b, 0, 0, b, L, T)
    floor(b, 0, 0, W - 2 * b, b, T)            # end rails
    floor(b, L - b, 0, W - 2 * b, b, T)
    for i in range(19):                        # the warp teeth
        xx = b + 6 + i * (W - 2 * b - 12) / 18
        box(xx - 0.8, -7, 0, 1.6, 7, T)
        box(xx - 0.8, L, 0, 1.6, 7, T)
    # Heddle bar standing across the frame near the top.
    box(b, L - 60, T, W - 2 * b, T, 28)
    for i in range(18):
        xx = b + 6 + i * (W - 2 * b - 12) / 17
        box(xx - 0.8, L - 60 - 0.5, T + 28, 1.6, T + 1, 6)
    # Two shuttles and a needle beside the loom.
    for xx in (W + 20, W + 48):
        prism([(xx, 10), (xx + 18, 10), (xx + 18, 24), (xx + 9, 30), (xx + 9, 110), (xx + 18, 116), (xx + 18, 130),
               (xx, 130), (xx, 116), (xx + 9, 110), (xx + 9, 30), (xx, 24)], 0, T)
    prism([(W + 78, 10), (W + 83, 10), (W + 81, 140), (W + 80, 140)], 0, T)


@model
def Hook():
    w, d, hh, s = 46, 40, 40, 20                  # back plate width, depth, mouth height, strength
    D = d + s                                      # how far the hook sticks out of the wall
    panel(0, D, 0, w, T, s + hh + d)               # back plate on the wall
    # Side profile in (distance from wall, z), mapped to y = D - distance.
    prof = [(0, 0), (s, 0), (D, d), (D, d + hh + s), (d + T, d + hh + s), (d + T, d + s), (0, d + s)]
    for xx in (3, w - 3 - T):
        extrude([(D - u, v) for u, v in prof], "yz", xx, T)
    panel(3 + T, D - d, d + s, w - 6 - 2 * T, d, T)            # shelf (bottom of the mouth)
    front = panel(3 + T, D - d - T, d + s + T, w - 6 - 2 * T, T, hh - T)   # front wall
    round_hole(front, w / 2, D - d, d + s + hh / 2 + 1, 8.5, axis="y")
    panel(3 + T, D - d - s, d + hh + s - T, w - 6 - 2 * T, s - T, T)      # top strip
    return dict(azimuth=35)


@model
def JointPanel():
    pw, ph, g, dd = 200, 133, 14, 12
    pieces = {}
    for c in range(2):
        for r in range(3):
            x0, y0 = c * (pw + g), r * (ph + g)
            pieces[c, r] = box(x0, y0, 0, pw, ph, T)
    for r in range(3):                              # dovetails across the vertical joint
        x1, y0 = pw, r * (ph + g)
        for yc in (y0 + ph / 3, y0 + 2 * ph / 3):
            prism([(x1, yc - 12), (x1 + dd, yc - 18), (x1 + dd, yc + 18), (x1, yc + 12)], 0, T)
            x2 = x1 + g
            cut(pieces[1, r], [(x2 - 1, yc - 13), (x2 + dd + 1, yc - 19), (x2 + dd + 1, yc + 19), (x2 - 1, yc + 13)], -1, T + 2)
    for c in range(2):                              # and across the two horizontal joints
        x0 = c * (pw + g)
        for r in range(2):
            y1 = r * (ph + g) + ph
            for xc in (x0 + pw / 3, x0 + 2 * pw / 3):
                prism([(xc - 12, y1), (xc + 12, y1), (xc + 18, y1 + dd), (xc - 18, y1 + dd)], 0, T)
                y2 = y1 + g
                cut(pieces[c, r + 1], [(xc - 13, y2 - 1), (xc + 13, y2 - 1), (xc + 19, y2 + dd + 1), (xc - 19, y2 + dd + 1)], -1, T + 2)


@model
def Kamishibai():
    w, d, h, sw, sh = 340, 60, 250, 297, 210
    open_box(0, 0, 0, w, d, h, front=False, fingers=False)
    floor(0, 0, h - T, w, d)
    front = wall_x(0, 0, T, w, h - T)
    hole(front, (w - sw) / 2, -1, (h - sh) / 2, sw, T + 2, sh)
    box((w - sw) / 2, 22, (h - sh) / 2, sw, 2, sh, (0.45, 0.72, 0.74, 1))   # the picture sheet
    # Doors swung open to the sides, hinged at the front corners.
    L = 170
    for hx, sgn, a in ((0, -1, math.radians(55)), (w, 1, math.radians(30))):
        f, n = (sgn * math.cos(a), -math.sin(a)), (math.sin(a), sgn * math.cos(a))
        pts = [(hx, 0), (hx + L * f[0], L * f[1]), (hx + L * f[0] + T * n[0], L * f[1] + T * n[1]), (hx + T * n[0], T * n[1])]
        prism(pts, T, h - T)
    # Carry handle on top.
    handle = box(w / 2 - 60, d / 2 - T, h, 120, 2 * T, 40)
    hole(handle, w / 2 - 35, d / 2 - T - 1, h + 14, 70, 2 * T + 2, 16)
    return dict(elevation=25)


@model
def LaptopStand():
    L, H, off = 340, 65, 10
    prof = [(0, 0), (L, 0), (L, H + off), (12, 12.5), (12, 22), (0, 22)]
    a = extrude(prof, "xz", L / 2 - T / 2, T)
    round_hole(a, L - 30, L / 2, 50, 10, axis="y")
    b = extrude(prof, "yz", L / 2 - T / 2, T)
    round_hole(b, L / 2, L - 30, 50, 10, axis="x")
    return dict(azimuth=20, elevation=25)


@model
def LaserClamp():
    t = T
    # Bottom part: foot with a peg for the knife-table slot, an upright and a spring hook.
    base = [(0, 0), (8 * t, 0), (8 * t, -2 * t), (12 * t, -2 * t), (12 * t, 0), (14 * t, 0), (14 * t, 2 * t),
            (8 * t, 2 * t), (8 * t, 11 * t), (4 * t, 11 * t), (4 * t, 9 * t), (6 * t, 9 * t), (6 * t, 2 * t), (0, 2 * t)]
    extrude(base, "xz", 0, t)
    # Top part: a slider riding on the upright, with the clamping arm and its round eye.
    arm = [(8 * t, 2 * t), (10 * t, 2 * t), (10 * t, 17 * t)] + arc(-2 * t, 17 * t, 4 * t, 0, 180) + \
          [(-6 * t, 17 * t), (-6 * t, 15 * t), (-1 * t, 15 * t), (-1 * t, 13 * t), (8 * t, 13 * t)]
    top = extrude(arm, "xz", t, t)
    round_hole(top, -2 * t, t, 17 * t, 1.5 * t, axis="y")
    # The tension spring between the two hooks.
    cylinder(5 * t, t, 10 * t, 1.2, 5 * t, ACCENT, segments=12)
    return dict(azimuth=30, elevation=20)


@model
def MagazineFile():
    x, y, h, hi = 100, 200, 300, 150
    floor(0, 0, 0, x, y)
    wall_x(0, y - T, T, x, h - T)                         # tall back
    wall_x(0, 0, T, x, hi - T)                            # low front
    side = [(0, T), (y, T), (y, h), (y * 0.6, h), (y * 0.4, hi), (0, hi)]
    extrude(side, "yz", 0, T)
    extrude(side, "yz", x - T, T)


@model
def Matrix():
    w, d = 200, 30
    front = panel(0, 0, 0, w, T, w)
    hole(front, 20, -1, 20, 160, T + 2, 160)
    box(20, T + 1.5, 20, 160, 1, 160, (0.98, 0.45, 0.10, 1))   # the lit matrix
    for i in range(9):                                      # the grid separating the pixels
        box(20 + i * 20 - 0.75, T, 20, 1.5, 1.5, 160, DARK)
        box(20, T, 20 + i * 20 - 0.75, 160, 1.5, 1.5, DARK)
    panel(0, d - T, 0, w, T, w)                             # back
    panel(0, T, 0, w, d - 2 * T, T)                         # bottom / top / sides
    panel(0, T, w - T, w, d - 2 * T, T)
    panel(0, T, T, T, d - 2 * T, w - 2 * T)
    panel(w - T, T, T, T, d - 2 * T, w - 2 * T)
    return dict(azimuth=30, elevation=25)


@model
def NightLightBox():
    w, d, h = 175, 100, 100
    parts = open_box(0, 0, 0, w, d, h)
    hole(parts[1], 12.5, -1, 12.5, 150, T + 2, 75)         # the window in the front
    floor(0, 0, h - T, w, d)
    # Three decorative plates: hills, trees and a mountain, one behind the other.
    hills = [(8, T), (167, T), (167, 30), (150, 40), (120, 34), (95, 44), (60, 36), (30, 46), (8, 38)]
    trees = [(8, T), (167, T), (167, 42), (140, 42), (135, 62), (128, 50), (120, 68), (112, 52), (105, 42),
             (70, 42), (62, 58), (56, 48), (50, 66), (44, 50), (38, 42), (8, 42)]
    mount = [(8, T), (167, T), (167, 50), (130, 56), (100, 84), (75, 62), (45, 76), (8, 60)]
    for yy, pts in ((12, hills), (27, trees), (42, mount)):
        extrude(pts, "xz", yy, 5)
    box(8, 57, T, 159, 5, 90, (1.0, 0.95, 0.72, 1))          # the diffuser lit from behind
