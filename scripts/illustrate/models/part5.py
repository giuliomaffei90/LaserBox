"""Shelf-group racks and the "Part" generators: flat test panels, gears, knobs, beams, mechanisms."""
import math
import bpy
from mathutils import Euler, Matrix, Vector
from iso import *

FLAT = dict(elevation=50)          # flat parts lie on the table
METAL = (0.45, 0.47, 0.50, 1)      # bolts, shafts, pins
TIN = (0.25, 0.25, 0.27, 1)        # spice cans
GLASS = (0.12, 0.28, 0.14, 1)      # wine bottles


# ----------------------------------------------------------------------------- helpers

def _ccw(pts):
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return pts if area > 0 else pts[::-1]


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-6 and abs(out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def _prism(pts, z, h, color=WOOD):
    return prism(_ccw(_dedupe(pts)), z, h, color)


def _arc(cx, cy, r, a0, a1, n=12):
    """Points on a circle from angle a0 to a1 (degrees), both included."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _notched(p, q, inward, depth=T, n=None, phase=0):
    """Points from p to q (p excluded) along a straight edge with finger-joint notches cut inward."""
    L = math.hypot(q[0] - p[0], q[1] - p[1])
    n = n or max(3, int(round(L / (depth * 3.5))) | 1)
    pts = []
    for i in range(n):
        a = (p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n)
        b = (p[0] + (q[0] - p[0]) * (i + 1) / n, p[1] + (q[1] - p[1]) * (i + 1) / n)
        k = depth if (i + phase) % 2 else 0
        pts += [(a[0] + inward[0] * k, a[1] + inward[1] * k), (b[0] + inward[0] * k, b[1] + inward[1] * k)]
    return pts


def _finger_rect(x, y, w, d, depth=T):
    pts = [(x, y)]
    pts += _notched((x, y), (x + w, y), (0, 1), depth)
    pts += _notched((x + w, y), (x + w, y + d), (-1, 0), depth)
    pts += _notched((x + w, y + d), (x, y + d), (0, -1), depth)
    pts += _notched((x, y + d), (x, y), (1, 0), depth)
    return pts


def _fillet(P, V, Q, r, n=8):
    """Replaces the corner V of the path P-V-Q by an arc of radius r: points from the first tangent to the second."""
    u1 = Vector((P[0] - V[0], P[1] - V[1])).normalized()
    u2 = Vector((Q[0] - V[0], Q[1] - V[1])).normalized()
    theta = u1.angle(u2)
    d = r / math.tan(theta / 2)
    t1, t2 = Vector(V) + u1 * d, Vector(V) + u2 * d
    c = Vector(V) + (u1 + u2).normalized() * (r / math.sin(theta / 2))
    a1 = math.degrees(math.atan2(t1.y - c.y, t1.x - c.x))
    a2 = math.degrees(math.atan2(t2.y - c.y, t2.x - c.x))
    while a2 - a1 > 180: a2 -= 360
    while a2 - a1 < -180: a2 += 360
    return _arc(c.x, c.y, r, a1, a2, n)


def _gear(n, m, cx=0, cy=0, phase=0, tip=None, root=None):
    """Polygon of a spur gear: n teeth of modulus m, one tooth centred on angle `phase` (degrees)."""
    tip = tip if tip is not None else m * (n + 2) / 2
    root = root if root is not None else m * (n - 2.5) / 2
    p = 360 / n
    pts = []
    for k in range(n):
        c = phase + k * p
        for r, da in ((root, -0.34), (tip, -0.16), (tip, 0.16), (root, 0.34)):
            a = math.radians(c + da * p)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _rot2(pts, deg, cx=0, cy=0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def _pip(x, y, poly):
    inside = False
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def _cut(obj, cutters):
    """Subtracts the given objects (joined into one cutter) from obj."""
    bpy.ops.object.select_all(action="DESELECT")
    for c in cutters: c.select_set(True)
    bpy.context.view_layer.objects.active = cutters[0]
    bpy.ops.object.join()
    cutter = bpy.context.object
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    return obj


def _cut_boxes(obj, rects):
    """One boolean cutting many rectangular slots: rects = [(x, y, z, w, d, h), …]."""
    verts, faces = [], []
    for x, y, z, w, d, h in rects:
        b = len(verts)
        verts += [(x, y, z), (x + w, y, z), (x + w, y + d, z), (x, y + d, z),
                  (x, y, z + h), (x + w, y, z + h), (x + w, y + d, z + h), (x, y + d, z + h)]
        faces += [[b + i for i in f] for f in ([0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7])]
    mesh = bpy.data.meshes.new("slots")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    cutter = bpy.data.objects.new("slots", mesh)
    bpy.context.collection.objects.link(cutter)
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = obj.modifiers.new("slots", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    return obj


def _model(fn):
    """Like iso.model, but refreshes the depsgraph first so render() sees up-to-date bounding boxes
    (objects whose transform was set from Python without a following operator keep stale bounds)."""
    def run():
        view = fn()
        bpy.context.view_layer.update()
        return view
    run.__name__ = fn.__name__
    return model(run)


def _xform(objs, rot, origin):
    """Rotates objects (Euler rot, degrees, XYZ) about the world origin, then moves them to `origin`."""
    R = Euler([math.radians(a) for a in rot], "XYZ").to_matrix()
    for o in objs:
        o.location = Vector(origin) + R @ o.location
        o.rotation_euler = (R @ o.rotation_euler.to_matrix()).to_euler()
    bpy.context.view_layer.update()


# ----------------------------------------------------------------------------- shelves

@_model
def SpicesRack():
    # Wall rack with stepped rows: each row a shelf whose front edge is scalloped, the jars lying in
    # the scallops with their lids to the front; the rows climb back like stairs.
    cans, rows, pitch, r = 5, 3, 65, 27
    step, row_h, depth = 45, 70, 60
    W, D = cans * pitch + 2 * T, (rows - 1) * step + depth + T
    zs = [12 + i * row_h for i in range(rows)]
    H = zs[-1] + T
    wall_x(0, D - T, 0, W, H)                                   # back
    side = [(0, 0), (D, 0), (D, H)]                             # side wall: a stair profile in (y, z)
    for i in range(rows - 1, 0, -1):
        side += [(i * step, zs[i] + T), (i * step, zs[i - 1] + T)]
    side.append((0, zs[0] + T))
    extrude(side, "yz", 0, T)
    extrude(side, "yz", W - T, T)
    filled = {(0, 0), (0, 1), (0, 2), (0, 4), (1, 1), (1, 3), (2, 2)}
    for i in range(rows):
        y0, z = i * step, zs[i]
        shelf = floor(T, y0, z, W - 2 * T, D - T - y0)
        cutters = []
        for j in range(cans):
            cx = T + j * pitch + pitch / 2
            cutters.append(cylinder(cx, y0 - 40, z + 15, r + 1.5, 80, axis="y"))
            if (i, j) in filled:
                cylinder(cx, y0 - 28, z + 15, r, 60, TIN, axis="y")                 # the jar
                cylinder(cx, y0 - 30, z + 15, r + 0.8, 8, (0.42, 0.42, 0.44, 1), axis="y")   # its lid
        _cut(shelf, cutters)


@_model
def StackableBin():
    W, D, h = 76, 103, 50

    def bin_():
        side = [(20, 0), (0, 20), (20, h + T), (D, h + T), (D, 0)]   # profile in (y, z): lip at the front
        k = T / 2 ** 0.5
        return [extrude(side, "yz", 0, T), extrude(side, "yz", W - T, T),
                floor(T, 22.3, 0, W - 2 * T, D - 22.3 - T),
                wall_x(T, D - T, T, W - 2 * T, h),                                  # back
                extrude([(20, 0), (0, 20), (k, 20 + k), (20 + k, k)], "yz", T, W - 2 * T)]   # retainer lip

    bin_()
    _xform(bin_(), (0, 0, 0), (0, 0, h + T + 5))                # second bin stacked on top
    for x in (0, W - T):                                        # feet of the upper bin
        for y in (25, 85):
            box(x, y, h + T, T, 10, 5)


@_model
def StorageRack():
    x, d, levels = 100, 200, 3
    H = levels * 50 + (levels + 1) * T
    wall_y(0, 0, 0, d, H)
    wall_y(x + T, 0, 0, d, H)
    floor(T, 0, 0, x, d)
    floor(T, 0, H - T, x, d)
    wall_x(T, d - T, T, x, H - 2 * T)
    for i in range(1, levels):
        z = i * (50 + T)
        floor(T, 0, z, 30, d)                                   # rails
        floor(x + T - 30, 0, z, 30, d)
    for i, pull in enumerate((60, 40, 20)):                     # the drawers, pulled out a little
        z = i * (50 + T) + T + 0.5
        open_box(T + 1, -pull, z, x - 2, d, 47)


@_model
def StorageShelf():
    # A two-compartment shelf box; the lower compartment holds a storage box with an oval hand hole.
    w, d, h = 156, 103, 159
    floor(0, 0, 0, w, d)
    floor(0, 0, h - T, w, d)
    wall_y(0, 0, T, d, h - 2 * T)
    wall_y(w - T, 0, T, d, h - 2 * T)
    wall_x(T, d - T, T, w - 2 * T, h - 2 * T)
    zm = h / 2
    floor(T, 0, zm, w - 2 * T, d - T)                           # middle shelf
    bw, bh = w - 2 * T - 4, zm - T - 6
    parts = open_box(T + 2, -12, T + 0.5, bw, d - 2, bh)
    front = parts[1]
    cutter = extrude(rounded_rect(T + 2 + bw / 2 - 24, T + 0.5 + bh / 2 - 8, 48, 16, 8), "xz", -14, T + 4)
    _cut(front, [cutter])


@_model
def WineRack():
    W, H, depth, R = 400, 300, 210, 46
    r = 2 * (R + T) * math.tan(math.pi / 6)
    dx, dy = r * math.cos(math.pi / 6), r * math.sin(math.pi / 6)
    ox, oz = (W - 8 * dx) / 2, (H - (2 * dy + 2 * r + 2 * dy + r)) / 2
    cells = [(ox + j * 2 * dx + dx, oz + i * (2 * r + 2 * dy) + r) for i in range(2) for j in range(4)]
    cells += [(ox + j * 2 * dx, oz + 2 * r + dy) for j in range(1, 4)]
    front = wall_x(0, 0, 0, W, H)
    round_holes(front, [(cx, 0, cz) for cx, cz in cells], R, axis="y")
    wall_x(0, T + depth, 0, W, H)                               # solid back
    edges = {}
    for cx, cz in cells:
        hexa = _arc(cx, cz, r, 30, 390, 6)[:6]
        for k in range(6):
            a, b = hexa[k], hexa[(k + 1) % 6]
            key = tuple(sorted(((round(a[0]), round(a[1])), (round(b[0]), round(b[1])))))
            edges[key] = (a, b)
    for a, b in edges.values():
        d = Vector((b[0] - a[0], b[1] - a[1])).normalized()
        n = Vector((-d.y, d.x)) * T / 2
        a, b = Vector(a) + d * 2, Vector(b) - d * 2
        extrude([tuple(a + n), tuple(b + n), tuple(b - n), tuple(a - n)], "xz", T, depth)
    for k in (0, 5, 10):                                        # a few bottles
        cx, cz = cells[k]
        cylinder(cx, -60, cz, 36, 190, GLASS, axis="y")
        cylinder(cx, -100, cz, 14, 40, GLASS, axis="y")


# ----------------------------------------------------------------------------- flat test parts

@_model
def BurnTest():
    for i, (x, y) in enumerate(((0, 0), (118, 6), (4, 120), (122, 124))):
        _prism(_finger_rect(x, y, 100, 100), 0, T)
    return FLAT


@_model
def FillTest():
    X, Y = 320, 220
    border = [(5, 10), (245, 10), (225, 150), (235, 150), (255, 10), (290, 10), (270, 190), (45, 190),
              (45, 50), (35, 50), (35, 190), (5, 190)]
    plate = floor(0, 0, 0, X, Y)
    centres, s, rad = [], 24, 7.5
    for row in range(12):
        y = 12 + row * s * 0.866
        for col in range(14):
            x = 10 + col * s + (s / 2 if row % 2 else 0)
            if all(_pip(x + (rad + 3) * math.cos(a), y + (rad + 3) * math.sin(a), border)
                   for a in (math.radians(60 * k) for k in range(6))):
                centres.append((x, y, 0))
    round_holes(plate, centres, rad)
    return FLAT


@_model
def FlexTest():
    X, Y = 120, 100
    plate = floor(0, 0, 0, X, Y)
    rects = []
    for k in range(25):
        x = 11.5 + k * 4
        ys = (0, 25, 50, 75, 100) if k % 2 == 0 else (12.5, 37.5, 62.5, 87.5)
        for yc in ys:
            y0, y1 = max(-1, yc - 11), min(Y + 1, yc + 11)
            rects.append((x, y0, -1, 1, y1 - y0, T + 2))
    _cut_boxes(plate, rects)
    return FLAT


@_model
def FlexTest2():
    X, n, w = 100, 5, 0.8
    c = X / n
    plate = floor(0, 0, 0, X, X)
    rects = []

    def arm(x, y, heading, lengths):
        for i, L in enumerate(lengths):
            dx, dy = math.cos(math.radians(heading)), math.sin(math.radians(heading))
            s = w / 2 + 0.2                                   # cutter boxes must not touch each other
            x0, y0 = x + dx * s, y + dy * s
            x1, y1 = x + dx * L, y + dy * L
            rects.append((min(x0, x1) - w / 2 * abs(dy), min(y0, y1) - w / 2 * abs(dx), -1,
                          abs(x1 - x0) + w * abs(dy), abs(y1 - y0) + w * abs(dx), T + 2))
            x, y, heading = x1, y1, heading + 90

    u = c / 5
    for i in range(n):
        for j in range(n):
            if (i + j) % 2:
                arm(i * c, j * c, 0, (4 * u, 4 * u, 2 * u, 2 * u))
                arm((i + 1) * c, (j + 1) * c, 180, (4 * u, 4 * u, 2 * u, 2 * u))
            else:
                arm((i + 1) * c, j * c, 90, (4 * u, 4 * u, 2 * u, 2 * u))
                arm(i * c, (j + 1) * c, -90, (4 * u, 4 * u, 2 * u, 2 * u))
    _cut_boxes(plate, rects)
    return FLAT


@_model
def RectangularWall():
    s = 100
    pts = [(0, 0), (s, 0)]
    pts += _notched((s, 0), (s, s), (-1, 0), 1.5, 25)                # fine teeth on the right
    pts += [(s, s), (90, s), (90, 96), (80, 96), (80, s), (20, s), (20, 96), (10, 96), (10, s), (0, s)]
    pts += _notched((0, s), (0, 0), (1, 0))                          # finger joint on the left
    _prism(pts, 0, T)
    return FLAT


@_model
def TriangularWall():
    s, r = 100, 12
    A, B, C = (0, 0), (s, 0), (s, s)
    arc_c = _fillet(B, C, A, r)
    arc_a = _fillet(C, A, B, r)
    pts = [arc_a[-1]]
    pts += _notched(arc_a[-1], B, (0, 1))
    pts += _notched(B, arc_c[0], (-1, 0))
    pts += arc_c + arc_a
    _prism(pts, 0, T)
    return FLAT


@_model
def LaserHoldfast():
    # Holdfasts in use: a sheet on the honeycomb bed, pinned at its corners by four hooks. Each hook is
    # an L: a shaft that goes down into a honeycomb cell and a short leg, a flat 30-degree arch standing
    # on its edge, that presses the sheet. A loose one lies flat on the sheet.
    h, hh, sw, a, x = 40, 5, 5, 30, 25
    r = x / math.radians(a)
    cx, cv = sw / 2 + r * math.sin(math.radians(a / 2)), -r * math.cos(math.radians(a / 2))
    hook = [(-sw / 2, -h), (sw / 2, -h)] + _arc(cx, cv, r, 90 + a / 2, 90 - a / 2, 10) \
        + _arc(cx, cv, r + hh, 90 - a / 2, 90 + a / 2, 10) + [(-sw / 2, hh)]
    Wp, Dp, bed = 80, 64, 12
    base = box(-30, -30, -bed, Wp + 60, Dp + 60, bed, (0.20, 0.20, 0.22, 1))
    floor(0, 0, 0, Wp, Dp)
    slots = []
    for y in (10, Dp - 10 - T):
        for x0, flip in ((-sw / 2 - 1, 1), (Wp + sw / 2 + 1, -1)):
            extrude([(x0 + flip * u, T + 0.3 + v) for u, v in hook], "xz", y, T)
            slots.append((x0 - sw / 2 - 1, y - 1, -bed - 1, sw + 2, T + 2, bed + 2))
    _cut_boxes(base, slots)
    loose = _prism([(Wp / 2 - 6 + v, Dp / 2 - 20 + u) for u, v in hook], T, T)
    hole(loose, Wp / 2 - 6 - 14, Dp / 2 - 20 - 0.5, T - 1, 16, 1, T + 2)    # the slit in the shaft
    return FLAT


# ----------------------------------------------------------------------------- gears, knobs, mechanisms

@_model
def Gears():
    big = _prism(_gear(32, 2, 0, 0, 0), 0, T)
    cutters = []
    for k in range(3):
        a0, a1 = 90 + k * 120, 210 + k * 120
        do, di = math.degrees(math.asin(3.5 / 25)), math.degrees(math.asin(3.5 / 9))
        cutters.append(prism(_arc(0, 0, 25, a0 + do, a1 - do, 12) + _arc(0, 0, 9, a1 - di, a0 + di, 6), -1, T + 2))
    _cut(big, cutters)
    round_hole(big, 0, 0, 0, 3)
    small = _prism(_gear(12, 2, 44, 0, 195), 0, T)
    round_hole(small, 44, 0, 0, 3)
    return FLAT


@_model
def GearBox():
    # An open tray with the gear train lying inside: two big gears, each with a small pinion stacked
    # on its axle, the pinion of one driving the big gear of the other.
    W, D, h, m = 116, 74, 20, 3
    open_box(0, 0, 0, W, D, h)
    ax, bx, y = 38, 38 + m * (8 + 16) / 2, D / 2
    big_a = _prism(_gear(20, m, ax, y, 0), T, T)
    _prism(_gear(8, m, ax, y, 0), 2 * T, T)                     # pinion on A, meshing with B
    big_b = _prism(_gear(16, m, bx, y, 180 + 360 / 32), 2 * T, T)
    _prism(_gear(8, m, bx, y, 0), 3 * T, T)
    for g, cx, ro in ((big_a, ax, 20), (big_b, bx, 14)):        # spoked cut-outs
        cutters = []
        for k in range(3):
            a0, a1 = 90 + k * 120, 210 + k * 120
            cutters.append(prism(_arc(cx, y, ro, a0 + 10, a1 - 10, 8) + _arc(cx, y, 7, a1 - 28, a0 + 28, 4), 0, 3 * T))
        _cut(g, cutters)
    cylinder(ax, y, 3 * T, 2.8, 38 - 3 * T, METAL)              # axle pins sticking up
    cylinder(bx, y, 4 * T, 2.8, 38 - 4 * T, METAL)
    return dict(elevation=52)


@_model
def Planetary():
    m, sun_t, planet_t = 3, 8, 20
    ring_t = sun_t + 2 * planet_t
    orbit = m * (sun_t + planet_t) / 2
    R_out = m * (ring_t + 2.5) / 2 + 18
    cylinder(0, 0, 0, R_out, T)                                 # back plate
    ring = cylinder(0, 0, T, R_out, T)
    _cut(ring, [prism(_gear(ring_t, m, 0, 0, 0, tip=m * (ring_t - 2) / 2, root=m * (ring_t + 2.5) / 2), T - 1, T + 2)])
    _prism(_gear(sun_t, m, 0, 0, 0), T, T)
    angles = (0, 135, 225)
    carrier = []
    for a in angles:
        px, py = orbit * math.cos(math.radians(a)), orbit * math.sin(math.radians(a))
        _prism(_gear(planet_t, m, px, py, a + 180 + 9), T, T)
        cylinder(px, py, 2 * T, 3, 42, METAL)                   # planet pins, up to the carrier
        carrier += _arc(px, py, 14, a - 90, a + 90, 10)
    spider = _prism(carrier, 2 * T + 34, T)
    round_holes(spider, [(orbit * math.cos(math.radians(a)), orbit * math.sin(math.radians(a)), 0) for a in angles] + [(0, 0, 0)], 3.3)
    cylinder(0, 0, 2 * T, 2.8, 55, METAL)                       # sun shaft
    return dict(elevation=45)


@_model
def Pulley():
    pts = _gear(20, 0.9, 0, 0, 0, tip=6.35, root=5.3)
    p = _prism(pts, 0, 2 * T)
    round_hole(p, 0, 0, 0, 2.5)
    return dict(elevation=45)


def _knob(pts):
    cylinder(0, 0, 0, 3, 28, METAL)                             # the bolt the knob sits on
    _prism(pts, 28, 3 * T)


@_model
def ConcaveKnob():
    R, n, rm = 25, 3, 11
    pts = []
    for i in range(n):
        base = i * 360 / n
        pts += _arc(0, 0, R, base - 12, base + 12, 6)
        # the dent: a circular arc through the two rim points and a point at radius rm on the dent axis
        ax, ay = math.cos(math.radians(48)) * R, math.sin(math.radians(48)) * R
        c = (ax * ax + ay * ay - rm * rm) / (2 * (ax - rm))
        rr = c - rm
        a = math.degrees(math.atan2(ay, ax - c))
        dent = _arc(c, 0, rr, 360 - a, a, 14)
        pts += _rot2(dent, base + 60)
    _knob(pts)


@_model
def WavyKnob():
    pts = [((23.4 + 1.8 * math.cos(20 * a)) * math.cos(a), (23.4 + 1.8 * math.cos(20 * a)) * math.sin(a))
           for a in (2 * math.pi * k / 240 for k in range(240))]
    _knob(pts)


@_model
def Linkage():
    plate = floor(0, 0, 0, 100, 100)
    holes = [(5 + 5 * i, y, 0) for y in (5, 50, 95) for i in range(19)]
    holes += [(x, 5 + 5 * i, 0) for x in (5, 50, 95) for i in range(1, 18) if i != 9]
    round_holes(plate, holes, 1.65)

    def link(x, y, L, deg, z):
        pts = _rot2(rounded_rect(x - 7.5, y - 7.5, L + 15, 15, 7.5), deg, x, y)
        bar = _prism(pts, z, T)
        round_holes(bar, [(cx, cy, z) for cx, cy in _rot2([(x + 5 * i, y) for i in range(int(L / 5) + 1)], deg, x, y)], 1.65)
        return (x + L * math.cos(math.radians(deg)), y + L * math.sin(math.radians(deg)))

    p1 = link(30, 50, 40, 60, T)
    p2 = link(p1[0], p1[1], 75, 0, 2 * T)
    link(95, 50, 45, 50, T)
    for px, py, hz in ((30, 50, 2 * T), (p1[0], p1[1], 3 * T), (p2[0], p2[1], 3 * T), (95, 50, 2 * T)):
        cylinder(px, py, 0, 1.5, hz + 3, METAL)
    return FLAT


@_model
def NemaMount():
    s = 26.3
    base = floor(0, 0, 0, s, s)
    round_hole(base, s / 2, s / 2, 0, 8)
    round_holes(base, [(s / 2 + dx, s / 2 + dy, 0) for dx in (-7.7, 7.7) for dy in (-7.7, 7.7)], 1.5)
    back = wall_x(0, s - T, T, s, s)
    for x in (5.45, s - 5.45):
        hole(back, x - 1.5, s - T - 1, T + 5, 3, T + 2, 15)
    for x in (0, s - T):
        extrude([(0, T), (s - T, T), (s - T, s + T)], "yz", x, T)


@_model
def LBeam():
    L, x, y = 150, 50, 40
    floor(0, 0, 0, L, x)
    wall_x(0, x - T, T, L, y - T)


@_model
def ZBeam():
    L, x, y, z = 150, 40, 40, 40
    floor(0, 0, 0, L, x)
    wall_x(0, x - T, T, L, y - T)
    floor(0, x - T, y - T, L, z)


@_model
def RobotArm():
    r = 12

    def segment(l, w):
        stad = rounded_rect(-r, -r, l + 2 * r, 2 * r, r)
        parts = [extrude(stad, "xz", 0, T), extrude(stad, "xz", w - T, T),
                 box(r, T, -r, l - 2 * r, w - 2 * T, T), box(r, T, r - T, l - 2 * r, w - 2 * T, T),
                 cylinder(l, -1.5, 0, 3.5, 1.5, METAL, axis="y"), cylinder(l, w, 0, 3.5, 1.5, METAL, axis="y")]
        return parts

    w1 = 40
    floor(-35, -T - 1, 0, 85, w1 + 2 * T + 2)                  # base plate and its two ears
    for y in (-T - 1, w1 + 1):
        extrude(rounded_rect(-20, T, 40, 49, 12), "xz", y, T)
    cylinder(0, -T - 2.5, 40, 3.5, 1.5, METAL, axis="y")
    cylinder(0, w1 + 1 + T, 40, 3.5, 1.5, METAL, axis="y")

    pivot, angle, y = Vector((0, 0, 40)), 0, 0
    for l, w, da in ((60, w1, -70), (55, w1 - 8, 55), (45, w1 - 16, 60)):
        angle += da
        parts = segment(l, w)
        _xform(parts, (0, angle, 0), pivot + Vector((0, y, 0)))
        pivot = pivot + Matrix.Rotation(math.radians(angle), 3, "Y") @ Vector((l, 0, 0))
        y += T + 1
