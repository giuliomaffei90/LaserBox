"""Flex (living hinge) boxes and a few odd generators: bent walls follow a 2D profile."""
import math

import bpy
import mathutils

from iso import *

GROOVE = (0.30, 0.18, 0.08, 1)   # a flex-cut slit, hinted as a thin dark strip
RUBBER = (0.12, 0.12, 0.12, 1)
METAL = (0.72, 0.74, 0.76, 1)


# ---------------------------------------------------------------- 2D helpers

def arc(cx, cy, r, a0, a1, n=12):
    """Points on a circle from angle a0 to a1 (degrees), both ends included."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def turtle(cmds, start=(0, 0), heading=0):
    """boxes.py-style polyline: a number moves straight, (angle, r) turns left by angle (an arc if r)."""
    x, y = start
    a = heading
    pts = [start]
    for c in cmds:
        if isinstance(c, tuple):
            ang, r = c
            if r:
                s = 1 if ang > 0 else -1
                cx, cy = x - s * r * math.sin(math.radians(a)), y + s * r * math.cos(math.radians(a))
                n = max(2, int(abs(ang) / 8))
                for i in range(1, n + 1):
                    b = math.radians(a - s * 90 + ang * i / n)
                    pts.append((cx + r * math.cos(b), cy + r * math.sin(b)))
                x, y = pts[-1]
            a += ang
        elif c:
            x, y = x + c * math.cos(math.radians(a)), y + c * math.sin(math.radians(a))
            pts.append((x, y))
    if math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) < 1e-3:
        pts.pop()
    return pts


def ccw(pts):
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return pts if area > 0 else pts[::-1]


def offset(pts, t, closed=True):
    """Every point moved by t to the left of the path (inwards for a counter-clockwise outline)."""
    n = len(pts)

    def normal(i, j):
        dx, dy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
        k = math.hypot(dx, dy) or 1
        return (-dy / k, dx / k)

    out = []
    for i in range(n):
        ns = []
        if closed or i > 0: ns.append(normal((i - 1) % n, i))
        if closed or i < n - 1: ns.append(normal(i, (i + 1) % n))
        if len(ns) == 2:
            bx, by = ns[0][0] + ns[1][0], ns[0][1] + ns[1][1]
            k = t / (1 + ns[0][0] * ns[1][0] + ns[0][1] * ns[1][1])
        else:
            (bx, by), k = ns[0], t
        out.append((pts[i][0] + bx * k, pts[i][1] + by * k))
    return out


def rounded(u0, v0, w, h, radii):
    """Rectangle outline with per-corner radii, counter-clockwise from (u0, v0): (br, tr, tl, bl)."""
    br, tr, tl, bl = radii
    return turtle([w - bl - br, (90, br), h - br - tr, (90, tr), w - tr - tl, (90, tl), h - tl - bl, (90, bl)],
                  start=(u0 + bl, v0))


# ---------------------------------------------------------------- 3D helpers

def bent(pts, plane, offset_, length, t=T, color=WOOD):
    """A bent wall (closed outline, t thick, outline = outer face) in any plane; like hollow()."""
    pts = ccw(pts)
    outer = extrude(pts, plane, offset_, length, color)
    cutter = extrude(offset(pts, t), plane, offset_ - 1, length + 2)
    cutter.hide_render = True
    cutter.display_type = "WIRE"
    mod = outer.modifiers.new("hollow", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    return outer


def band(path, plane, offset_, length, t=T, color=WOOD):
    """A sheet of thickness t following an open path (the path is its left-hand face when t > 0)."""
    return extrude(path + offset(path, t, closed=False)[::-1], plane, offset_, length, color)


def grooves(plane, points, offset_, length, s=1.2):
    """Thin dark strips along the third axis, one at every 2D point: a hint of the flex slits."""
    for u, v in points:
        extrude([(u - s / 2, v - s / 2), (u + s / 2, v - s / 2), (u + s / 2, v + s / 2), (u - s / 2, v + s / 2)],
                plane, offset_, length, GROOVE)


def solid(verts, faces, color=WOOD):
    mesh = bpy.data.meshes.new("solid")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("solid", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.data.materials.append(material(color))
    return obj


def battlement(u0, w, h, n, m=10):
    """Wall outline (u, v) with n merlons on top."""
    seg = w / (2 * n - 1)
    pts = [(u0, 0), (u0 + w, 0)]
    for j in reversed(range(2 * n - 1)):
        top = h if j % 2 == 0 else h - m
        pts += [(u0 + (j + 1) * seg, top), (u0 + j * seg, top)]
    return pts


# ---------------------------------------------------------------- sliding doors

@model
def BreadBox():
    w, d, h, r = 150, 100, 100, 40
    side = rounded(0, 0, d, h, (0, 0, r, 0))        # (y, z): front-top corner rounded
    extrude(side, "yz", 0, T)
    extrude(side, "yz", w - T, T)
    floor(T, T, 0, w - 2 * T, d - T)
    wall_x(T, d - T, T, w - 2 * T, h - T)           # back
    floor(T, d / 2, h - T, w - 2 * T, d / 2 - T)    # fixed half of the top
    door = [(d / 2, h)] + arc(r, h - r, r, 90, 180) + [(0, T)]
    band(door, "yz", T, w - 2 * T)                  # the gliding door, closed
    grooves("yz", arc(r, h - r, r, 97, 173, 5) + [(0, h - r - 20), (0, h - r - 40)], T, w - 2 * T)


@model
def ShutterBox():
    w, d, h, r = 100, 150, 100, 40
    side = rounded(0, 0, d, h, (0, 0, r, 0))
    extrude(side, "yz", 0, T)
    extrude(side, "yz", w - T, T)
    floor(T, 0, 0, w - 2 * T, d)
    wall_x(T, d - T, T, w - 2 * T, h - T)           # back
    wall_x(T, 0, T, w - 2 * T, h - r - T)           # low fixed front
    door = [(0.55 * d, h)] + arc(r, h - r, r, 90, 180) + [(0, h - r)]
    band(door, "yz", T, w - 2 * T)                  # shutter, half open
    grooves("yz", [(0.5 * d, h), (0.5 * d - 11, h), (0.5 * d - 22, h)] + arc(r, h - r, r, 97, 173, 5), T, w - 2 * T)


# ---------------------------------------------------------------- flex boxes

@model
def UBox():
    w, d, h, r = 120, 90, 80, 30
    u = rounded(0, 0, d, h, (r, 0, 0, r))           # (y, z): bottom corners rounded
    extrude(u, "yz", 0, T)
    extrude(u, "yz", w - T, T)
    path = [(0, h)] + arc(r, r, r, 180, 270) + arc(d - r, r, r, 270, 360) + [(d, h)]
    band(path, "yz", T, w - 2 * T)
    grooves("yz", arc(r, r, r, 195, 255, 3) + arc(d - r, r, r, 285, 345, 3), T, w - 2 * T)


@model
def FlexBox():
    # A stadium-shaped box (pill from above): flex walls on the two fully rounded ends, flat lid.
    L, W, h = 100, 60, 45
    r = W / 2
    pts = rounded_rect(0, 0, L, W, r - 1)            # r = W/2 exactly repeats a point, breaking the boolean
    prism(pts, 0, T)                                 # bottom
    bent(pts, "xy", T, h - T)                        # the wall
    prism(pts, h + 20, T)                            # lid, lifted off
    grooves("xy", arc(r, r, r, 95, 265, 10) + arc(L - r, r, r, -85, 85, 10), T, h - T)   # flex on the ends
    box(L / 2 - 8, -2, h - 14, 16, 2, 10)            # latch tab


@model
def FlexBox2():
    w, d, h, r = 70, 70, 110, 15
    p = rounded(0, 0, d, h, (0, r, r, 0))           # top corners rounded
    extrude(p, "yz", 0, T)
    extrude(p, "yz", w - T, T)
    bent(p, "yz", T, w - 2 * T)
    grooves("yz", [(0, h - r - 24)] + arc(r, h - r, r, 100, 170, 3), T, w - 2 * T)
    box(w / 2 - 8, -2, h - r - 38, 16, 2, 12)


@model
def FlexBox3():
    w, d, h, r, lh = 100, 90, 80, 10, 10
    p = rounded(0, 0, d, h, (0, r, 0, 0))           # (y, z): hinge corner at the back top
    extrude(p, "yz", 0, T)
    extrude(p, "yz", w - T, T)
    path = [(0, h), (0, 0), (d, 0), (d, h - r)] + arc(d - r, h - r, r, 0, 90)
    band(path, "yz", T, w - 2 * T)
    # Lid: a shallow tray hinged at the back-top corner, shown open.
    a = math.radians(35)
    py, pz = d - r, h

    def L(u, v):
        return (py - u * math.cos(a) + v * math.sin(a), pz + u * math.sin(a) + v * math.cos(a))

    def rect(u0, u1, v0, v1):
        return [L(u0, v0), L(u1, v0), L(u1, v1), L(u0, v1)]

    lp = d - r + T
    extrude(rect(0, lp, 0, T), "yz", -T, w + 2 * T)             # lid top
    extrude(rect(lp - T, lp, -lh, 0), "yz", -T, w + 2 * T)      # front lip
    extrude(rect(0, lp, -lh, 0), "yz", -T, T)                   # side lips
    extrude(rect(0, lp, -lh, 0), "yz", w, T)


@model
def FlexBox4():
    w, d, h, r = 120, 60, 50, 15
    p = rounded(0, 0, w, h, (r, r, 0, 0))           # (x, z): right end rounded = the hinge
    extrude(p, "xz", 0, T)
    extrude(p, "xz", d - T, T)
    bent(p, "xz", T, d - 2 * T)
    grooves("xz", [(22, h)] + arc(w - r, h - r, r, 10, 80, 3), T, d - 2 * T)   # lid seam + flex
    box(6, d / 2 - 8, h, 14, 16, 2)                 # latch tab


@model
def FlexBox5():
    w, d, h = 70, 100, 60
    r = h / 2
    p = rounded(0, 0, d, h, (r, r, r, r))           # (y, z): stadium
    extrude(p, "yz", 0, T)
    extrude(p, "yz", w - T, T)
    bent(p, "yz", T, w - 2 * T)
    grooves("yz", [(d - r - 8, h)] + arc(r, r, r, 100, 260, 7), T, w - 2 * T)
    box(w / 2 - 8, d - r - 24, h, 16, 14, 2)


@model
def DoubleFlexDoorBox():
    w, d, h, r = 200, 45, 55, 15
    p = rounded(0, 0, w, h, (r, r, r, r))           # (x, z)
    extrude(p, "xz", 0, T)
    extrude(p, "xz", d - T, T)
    bent(p, "xz", T, d - 2 * T)
    grooves("xz", [(w / 2, h)] + arc(w - r, h - r, r, 15, 75, 3) + arc(r, h - r, r, 105, 165, 3), T, d - 2 * T)
    box(w / 2 - 12, d / 2 - 7, h, 24, 14, 2)        # latch across the seam


@model
def FlexBook():
    w, d, h = 75, 125, 35
    r = h / 2
    p = rounded(0, 0, w, h, (0, 0, r, r))           # (x, z): spine on the left
    extrude(p, "xz", 0, T)                          # the "pages"
    extrude(p, "xz", d - T, T)
    bent(p, "xz", T, d - 2 * T)
    grooves("xz", arc(r, r, r, 110, 250, 6), T, d - 2 * T)
    prism(rounded_rect(w - 24, d / 2 - 6, 18, 12, 5, 4), h, 2)   # latch


@model
def HeartBox():
    x, h = 150, 50
    l = 2 / 3 * x
    r = l / 2 - T / 2
    p = turtle([l, (180, r), T, (-90, 0), T, (180, r), l])
    c, s = math.cos(math.radians(45)), math.sin(math.radians(45))
    p = [(u * c - v * s, u * s + v * c) for u, v in p]   # tip to the front, lobes at the back
    prism(p, 0, T)
    bent(p, "xy", T, h - T)
    prism(p, h + 24, T)


# ---------------------------------------------------------------- polygon boxes

@model
def RoundedRegularBox():
    n, ap, h, r = 5, 75, 90, 15
    side = 2 * ap * math.tan(math.pi / n)
    s = side - 2 * r * math.tan(math.pi / n)
    p = turtle([s, (360 / n, r)] * n, start=(-s / 2, -ap))
    prism(p, 0, T)
    bent(p, "xy", T, h - 2 * T)
    bent(p, "xy", h - T, T, t=8)                    # top with a hole
    return dict(azimuth=30)


@model
def RoundedTrapezoidBox():
    xf, xb, y, h, r = 130, 80, 100, 60, 20
    a = math.degrees(math.atan((xf - xb) / (2 * y)))
    yl = y / math.cos(math.radians(a))
    df = math.tan(math.radians((90 + a) / 2)) * r
    db = math.tan(math.radians((90 - a) / 2)) * r
    p = turtle([xf - 2 * df, (90 + a, r), yl - df - db, (90 - a, r), xb - 2 * db, (90 - a, r), yl - db - df, (90 + a, r)],
               start=(df, 0))
    prism(p, 0, T)
    bent(p, "xy", T, h - 2 * T)
    bent(p, "xy", h - T, T, t=8)
    return dict(elevation=45)


# ---------------------------------------------------------------- the rest

@model
def Castle():
    s, th = 60, 200
    extrude(battlement(0, s, th, 4), "xz", 0, T)
    extrude(battlement(0, s, th, 4), "xz", s - T, T)
    extrude(battlement(T, s - 2 * T, th, 4), "yz", 0, T)
    extrude(battlement(T, s - 2 * T, th, 4), "yz", s - T, T)
    extrude(battlement(s, 200, 100, 10), "xz", s / 2 - T / 2, T)     # long wall to the right
    extrude(battlement(-90, 90, 100, 5), "yz", s / 2 - T / 2, T)     # short wall to the front


@model
def OrganPipe():
    w, d, h = 60, 50, 240
    parts = open_box(0, 0, 0, w, d, h)
    hole(parts[1], T, -1, 50, w - 2 * T, T + 2, 30)       # the mouth
    floor(T, T, 48, w - 2 * T, d - 2 * T)                  # languid, seen through the mouth
    box(w / 2 - 12, d / 2 - 10, -30, 24, 20, 30)           # foot
    return dict(elevation=25)


@model
def Planetary2():
    s = 90
    box(s / 2 - 21, s / 2 - 21, -42, 42, 42, 42, RUBBER)    # NEMA motor under the base
    floor(0, 0, 0, s, s)
    ring = floor(0, 0, 20, s, s)
    round_hole(ring, s / 2, s / 2, 20, 32)                   # ring gear
    cylinder(s / 2, s / 2, 20, 10, T, segments=10)           # sun
    for a in (90, 210, 330):
        cylinder(s / 2 + 20 * math.cos(math.radians(a)), s / 2 + 20 * math.sin(math.radians(a)), 20, 10, T, segments=10)
    pulley = cylinder(s / 2, s / 2, 85, 45, T, segments=40)   # secondary ring gear / belt pulley, lifted
    round_hole(pulley, s / 2, s / 2, 85, 30)
    return dict(elevation=50)


@model
def Platonic():
    p = (1 + 5 ** 0.5) / 2
    V = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    N = []
    for a in (-1, 1):
        for b in (-1, 1):
            V += [(0, a / p, b * p), (a / p, b * p, 0), (a * p, 0, b / p)]
            N += [(0, a, b * p), (a, b * p, 0), (a * p, 0, b)]
    faces = []
    for n in N:
        n = mathutils.Vector(n).normalized()
        idx = sorted(range(20), key=lambda i: -mathutils.Vector(V[i]).dot(n))[:5]
        u = n.orthogonal().normalized()
        v = n.cross(u)
        idx.sort(key=lambda i: math.atan2(mathutils.Vector(V[i]).dot(v), mathutils.Vector(V[i]).dot(u)))
        faces.append(idx)
    rot = mathutils.Vector((0, -1, -p)).normalized().rotation_difference(mathutils.Vector((0, 0, -1)))
    verts = [rot @ (mathutils.Vector(x) * (60 / (2 / p))) for x in V]
    zmin = min(x.z for x in verts)
    solid([(x.x, x.y, x.z - zmin) for x in verts], faces)   # a dodecahedron, edge 60


@model
def Rotary():
    box(0, 19, 0, 420, 32, 7, METAL)                 # aluminium beam
    d, hh, L = 70, 42, 110
    for x0, motor in ((40, False), (270, True)):
        floor(x0, 0, 7, L, d)
        wall_x(x0, 0, 10, L, hh)
        wall_x(x0, d - T, 10, L, hh)
        wall_y(x0, T, 10, d - 2 * T, hh)
        wall_y(x0 + L - T, T, 10, d - 2 * T, hh)
        for wx in (x0 + 25, x0 + L - 25):
            cylinder(wx, d / 2 - 4, 48, 36, 8, RUBBER, axis="y")   # wheel with O ring
            cylinder(wx, -4, 48, 3, d + 8, METAL, axis="y")        # axle
        if motor:
            box(x0 + L / 2 - 21, d, 15, 42, 42, 42, RUBBER)


@model
def Silverware():
    w, d, h, r = 250, 154, 120, 30
    p = rounded_rect(0, 0, w, d, r)
    prism(p, 0, T)
    bent(p, "xy", T, h - T)
    hw, hh = 150, 150
    side = (w - 2 * T - hw) / 2
    handle = turtle([w - 2 * T, (90, 0), h - T, (90, 0), side, (-90, 0), hh - 20, (90, 20), hw - 40, (90, 20),
                     hh - 20, (-90, 0), side, (90, 0), h - T], start=(T, T))
    centre = extrude(handle, "xz", d / 2 - T / 2, T)
    hole(centre, w / 2 - 60, d / 2 - T / 2 - 1, h + 30, 120, T + 2, hh - 55)
    for x in (w / 3, 2 * w / 3):
        wall_y(x - T / 2, T, T, d / 2 - 1.5 * T, h - 10 - T)
        wall_y(x - T / 2, d / 2 + T / 2, T, d / 2 - 1.5 * T, h - 10 - T)
