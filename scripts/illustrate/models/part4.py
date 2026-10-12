"""Trays with dividers and slopes, drill / pen / paint holders, gridfinity, racks."""
import math
from iso import *

GREY = (0.78, 0.80, 0.83, 1)     # metal discs
GREEN = (0.20, 0.50, 0.32, 1)    # circuit boards
PAPER = (0.96, 0.95, 0.90, 1)    # a pile of cards


def side(x, pts, t=T, color=WOOD):
    """A panel in the yz plane (profile pts = [(y, z), …]), t thick, starting at x."""
    return extrude(pts, "yz", x, t, color)


def grid_walls(x, y, z, w, d, h, xs, ys):
    """Inner dividers of a cavity x..x+w × y..y+d; xs / ys are the wall centre lines."""
    for cx in xs: wall_y(cx - T / 2, y, z, d, h)
    for cy in ys: wall_x(x, cy - T / 2, z, w, h)


def feet(nx, ny, z=-T):
    """Gridfinity pads under a box: one square per 42 mm cell."""
    for i in range(nx):
        for j in range(ny):
            box(3 + 42 * i, 3 + 42 * j, z, 36, 36, T)


@model
def CompartmentBox():
    w, d, h = 150, 130, 40
    open_box(0, 0, 0, w, d, h, front=False, fingers=False)
    wall_x(T, 0, T, w - 2 * T, h - 2 * T)               # low front wall: the lid slides over it
    wall_y(75 - T / 2, T, T, d - 2 * T, h - 2 * T)      # inner walls one T lower: the lid rests on them
    wall_x(T, 65 - T / 2, T, w - 2 * T, h - 2 * T)
    panel(0, 0, h, 10, d, T)                            # lips on the side walls hold the lid down
    panel(w - 10, 0, h, 10, d, T)
    floor(T + 1, T - 50, h - T, w - 2 * T - 2, d - 2 * T)   # the lid, pulled half out to the front


@model
def DividerTray():
    w, d, h = 100, 160, 60
    open_box(0, 0, 0, w, d, h, bottom=False)
    wall_y(50 - T / 2, T, 0, d - 2 * T, h)
    for x0, x1 in ((T, 50 - T / 2), (50 + T / 2, w - T)):
        for y in (40, 80, 120):   # dividers: tabs at the top corners sit in the wall slots
            pts = [(x0, 0), (x1, 0), (x1, h + 6), (x1 - 8, h + 6), (x1 - 8, h - 12),
                   (x0 + 8, h - 12), (x0 + 8, h + 6), (x0, h + 6)]
            extrude(pts, "xz", y - T / 2, T)


@model
def DrillBox():
    w, d, h = 81, 246, 46
    open_box(0, 0, 0, w, d, h)
    top = floor(T, T, h - T, w - 2 * T, d - 2 * T)
    for j in range(4):   # rows of ever bigger drills
        round_holes(top, [(T + 12.5 + 25 * i, T + 60 * j + 20 * (k + 0.5), h) for i in range(3) for k in range(3)],
                    1.8 + 0.7 * j)


@model
def GridfinityBase():
    parts = open_box(0, 0, 0, 126, 84, 21)
    for i in range(3):
        for j in range(2):
            hole(parts[0], 3 + 42 * i, 3 + 42 * j, -1, 36, 36, T + 2)


@model
def GridfinityDrillBox():
    w, d, h = 125, 83, 46
    open_box(0, 0, 0, w, d, h)
    top = floor(T, T, h - T, w - 2 * T, d - 2 * T)
    round_holes(top, [(21 + 42 * i + dx, 21 + 42 * j + dy, h) for i in range(3) for j in range(2)
                      for dx, dy in ((-10, -10), (10, -10), (-10, 10), (10, 10))], 4)
    feet(3, 2)


@model
def GridfinityTrayLayout():
    w, d, h = 125, 83, 50
    open_box(0, 0, 0, w, d, h)
    grid_walls(T, T, T, w - 2 * T, d - 2 * T, h - T, [w / 5 * i for i in range(1, 5)], [d / 3 * j for j in (1, 2)])
    feet(3, 2)


@model
def HobbyCase():
    cw, d, h = 215, 128, 300
    w = 3 * cw + 4 * T
    floor(0, 0, 0, w, d)
    floor(0, 0, h - T, w, d)
    wall_x(0, d - T, T, w, h - 2 * T)
    for x in (0, T + cw, 2 * T + 2 * cw, w - T):
        wall_y(x, 0, T, d - T, h - 2 * T)
    for col, zs in enumerate(((100, 200), (75, 150, 225), (100, 200))):
        x = T + col * (cw + T)
        for z in zs:
            floor(x, 8, z, cw, d - T - 8)   # shelves, inset from the front edge


@model
def PenHolderBox():
    s = 100
    open_box(0, 0, 0, s, s, s)
    top = floor(T, T, s - T - 3, s - 2 * T, s - 2 * T)
    round_holes(top, [(17 + 22 * i, 17 + 22 * j, s) for i in range(4) for j in range(4)], 6)
    for i, j in ((1, 2), (2, 1)):
        cylinder(17 + 22 * i, 17 + 22 * j, 12, 5, 125, ACCENT)


@model
def SlantedTray():
    w, d, h, hf = 126, 46, 40, 12
    floor(0, 0, 0, w, d)
    wall_x(T, d - T, T, w - 2 * T, h - T)
    wall_x(T, 0, T, w - 2 * T, hf - T)
    side(0, [(0, T), (d, T), (d, h), (0, hf)])
    side(w - T, [(0, T), (d, T), (d, h), (0, hf)])
    for x in (40 + T / 2, 80 + 1.5 * T):
        side(x, [(T, T), (d - T, T), (d - T, h), (T, hf)])


@model
def SmallPartsTray():
    w, d, h, r = 150, 100, 30, 15
    open_box(0, 0, 0, w, d, h)
    grid_walls(T, T, T, w - 2 * T, d - 2 * T, h - T, [50, 100], [])
    k = T * 2 ** 0.5
    for x0, x1 in ((T, 50 - T / 2), (50 + T / 2, 100 - T / 2), (100 + T / 2, w - T)):
        y1 = d - T   # a 45° ramp against the front and the back wall of every compartment
        extrude([(T, T + r), (T + r, T), (T + r + k, T), (T, T + r + k)], "yz", x0, x1 - x0)
        extrude([(y1, T + r), (y1 - r, T), (y1 - r - k, T), (y1, T + r + k)], "yz", x0, x1 - x0)


@model
def SmallPartsTray2():
    w, d, h = 150, 100, 30
    open_box(0, 0, 0, w, d, h)
    grid_walls(T, T, T, w - 2 * T, d - 2 * T, h - T, [50, 100], [50])
    for x0, x1 in ((T, 50 - T / 2), (50 + T / 2, 100 - T / 2), (100 + T / 2, w - T)):
        for y0, y1 in ((T, 50 - T / 2), (50 + T / 2, d - T)):
            slanted_panel(x0, y0, T, x1 - x0, y1 - y0 - T, 20)   # the slope, high at the back


@model
def TrayInsert():
    w, d, h = 150, 150, 50
    for x in (50, 100): wall_y(x - T / 2, 0, 0, d, h)
    for y in (50, 100): wall_x(0, y - T / 2, 0, w, h)


@model
def TrayLayout():
    w, d, h = 150, 120, 50
    open_box(0, 0, 0, w, d, h)
    wall_x(T, 60 - T / 2, T, w - 2 * T, h - T)
    wall_y(75 - T / 2, 60 + T / 2, T, d - T - 60 - T / 2, h - T)   # only the back half is split


@model
def BinTray():
    cw, ch, d, n = 50, 50, 60, 2                   # 2 bins wide, 2 rows: a cube with sloped fronts
    lip = 0.4 * ch
    w = n * cw + (n + 1) * T
    rows = [T + i * (ch + T) for i in range(n)]    # z of every cell floor
    h = rows[-1] + ch + T
    k = T * 2 ** 0.5
    for z in [0] + [zb + ch for zb in rows]:
        floor(T, lip, z, w - 2 * T, d - lip - T)
    wall_x(T, d - T, T, w - 2 * T, h - 2 * T)
    pts = [(d, 0), (lip, 0)]
    for zb in rows:
        pts += [(lip, zb), (0, zb + lip), (lip, zb + ch)]
    pts += [(lip, h), (d, h)]
    side(0, pts)
    side(w - T, pts)
    cols = [(T + i * (cw + T), T + i * (cw + T) + cw) for i in range(n)]
    for zb in rows:
        for x0, x1 in cols:   # the sloped front lip of every bin
            extrude([(lip, zb), (lip + k, zb), (k, zb + lip), (0, zb + lip)], "yz", x0, x1 - x0)
        for x0, x1 in cols[:-1]:
            side(x1, [(d - T, zb), (lip + k, zb), (k, zb + lip), (lip, zb + ch), (d - T, zb + ch)])
    return dict(elevation=30)


@model
def CardHolder():
    cw, d, hf, hb, z0, a = 60, 70, 22, 45, 12, math.radians(7.5)
    w = 3 * cw + 4 * T
    rise = (d - 2 * T) * math.tan(a)
    prof = [(0, 0), (d, 0), (d, hb), (d - 10, hb), (d - 26, hf), (0, hf)]      # low in front, high at the back
    side(0, prof)
    side(w - T, prof)
    extrude([(T, 0), (w - T, 0), (w - T, hb - 8), (w - 22, hb - 8), (w - 32, hb), (32, hb), (22, hb - 8), (T, hb - 8)],
            "xz", d - T, T)                                                   # back wall, raised in the middle
    wall_x(T, 0, z0, w - 2 * T, hf - z0)                                      # low front wall
    extrude([(T, z0), (d - T, z0 + rise), (d - T, z0 + rise + T), (T, z0 + T)], "yz", T, w - 2 * T)  # tilted floor
    for i in (1, 2):
        side(i * (cw + T), [(T, z0 + T), (d - T, z0 + rise + T), (d - T, hb - 2), (d - 10, hb - 2), (d - 26, hf), (T, hf)])
    th, ph = math.radians(20), 30                                             # a pack of cards leaning back in every slot
    yb = d - T - ph * math.sin(th) - 6
    zb = z0 + T + rise * (yb - T) / (d - 2 * T) + 3
    for i in range(3):
        bpy.ops.mesh.primitive_cube_add(size=1, rotation=(-th, 0, 0),
                                        location=(T + i * (cw + T) + cw / 2, yb + ph / 2 * math.sin(th), zb + ph / 2 * math.cos(th)))
        pack = bpy.context.object
        pack.scale = (cw - 16, 6, ph)
        pack.data.materials.append(material(PAPER))


@model
def DiscRack():
    o, R, n, pitch, slot = 156, 75, 10, 20, 5
    a = math.radians(18)
    u = (math.sin(a), math.cos(a))      # up along the rear plate (leaning back)
    v = (-math.cos(a), math.sin(a))     # forward along the lower plate
    f = 0.75 * R
    k = (o / 2 - f * (u[0] + v[0]), o / 2 - f * (u[1] + v[1]))   # corner where the plates meet
    w = n * pitch + 2 * T
    side(0, [(0, 0), (o, 0), (o, o), (0, o)])
    side(w - T, [(0, 0), (o, 0), (o, o), (0, o)])

    def plate(p0, along, nrm, length):
        """A slotted plate: full-width strips at both ends, teeth between the slots."""
        def strip(s0, s1, x0, x1):
            a0 = (p0[0] + s0 * along[0], p0[1] + s0 * along[1])
            a1 = (p0[0] + s1 * along[0], p0[1] + s1 * along[1])
            extrude([a0, a1, (a1[0] + T * nrm[0], a1[1] + T * nrm[1]), (a0[0] + T * nrm[0], a0[1] + T * nrm[1])],
                    "yz", x0, x1 - x0)
        strip(0, 5, T, w - T)
        strip(length - 8, length, T, w - T)
        edges = [T] + [T + pitch * i + (pitch - slot) / 2 + e for i in range(n) for e in (0, slot)] + [w - T]
        for i in range(0, len(edges), 2):
            strip(5, length - 8, edges[i], edges[i + 1])

    plate(k, v, u, k[0] / math.cos(a))
    plate((k[0] + T * u[0], k[1] + T * u[1]), u, v, min((o - k[0]) / math.sin(a), (o - k[1]) / math.cos(a)) - T)
    for i in (4, 6, 8):
        cylinder(T + pitch * i + pitch / 2 - 2.5, o / 2, o / 2, R, 5, GREY, axis="x")


@model
def PaintStorage():
    w, d, h, zp = 300, 100, 48, 32

    def unit(z):
        wall_y(0, 0, z, d, h)
        wall_y(w - T, 0, z, d, h)
        floor(T, 0, z, w - 2 * T, d)
        top = floor(T, 0, z + zp, w - 2 * T, d)
        round_holes(top, [(21.5 + 43 * i, 25 + 50 * j, z + zp) for i in range(7) for j in range(2)], 15)

    unit(0)
    for x in (0, w - T):   # stacking feet
        box(x, 8, h, T, 16, 4)
        box(x, d - 24, h, T, 16, 4)
    unit(h + 4)
    for i, j in ((1, 1), (3, 0), (5, 1)):
        cylinder(21.5 + 43 * i, 25 + 50 * j, h + 4 + T, 14, 50, ACCENT)


@model
def SBCMicroRack():
    bw, bd, n, pitch = 92, 63, 5, 31
    hs = n * pitch + pitch / 2
    wall_y(0, 0, 0, bd, hs)
    right = wall_y(bw + T, 0, 0, bd, hs)
    for i in range(n + 1):
        floor(T, 0, i * pitch, bw, bd)
    for i in range(n):
        z = i * pitch + T
        box(T + 3.5, 3.5, z, 85, 56, 1.6, GREEN)                 # the single-board computer
        hole(right, bw, 5, z + 4, T + 2, bd - 10, 18)              # port cut-outs in the right wall
