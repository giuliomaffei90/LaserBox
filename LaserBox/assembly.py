"""Assembled 3D preview: every cut part, extruded by the material thickness, placed in space.

boxes.py only knows the flat sheet, so the parts are recorded while the generator draws them
(which primitive drew them, the local coordinate frame, where the flex cuts are) and a small
recipe per generator says where each part goes. Flexed regions are bent by slicing the part into
narrow strips that follow an arc.

Protocol: assemble(name, args) -> {"pieces": [{"rings": [[[u, v], …], …], "origin": [x, y, z],
"u": [..], "v": [..], "side": ±1, "t": thickness}, …]}  — world(u, v, w) = origin + u·U + v·V + w·side·(U×V)
"""
import math

from affine import Affine
from shapely.geometry import LineString, Polygon, box as rect
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

import boxes
import boxes.drawing
import boxes.edges
import boxes.generators

# ---------------------------------------------------------------- recording

RECORDS = {"current": None, "all": [], "pending": {}}
PRIMITIVES = ("rectangularWall", "roundedPlate", "surroundingWall", "flexBoxSide", "trapezoidWall")


class Record:
    def __init__(self, pending):
        self.primitive = pending.get("primitive")
        self.label = pending.get("label")
        self.args = pending.get("args") or ()
        self.kwargs = pending.get("kwargs") or {}
        self.start = None    # ctx matrix right after move(before=True): bbox corner + spacing
        self.matrix = None   # ctx matrix at the first cc(): the start of the first edge
        self.base_v = 0.0    # the edge is drawn startwidth below the part's base line (its inner face)
        self.flex = []       # (matrix at the flex call, length)


def install():
    if getattr(boxes.Boxes, "_laserbox_instrumented", False):
        return
    boxes.Boxes._laserbox_instrumented = True

    orig_move = boxes.Boxes.move

    def move(self, x, y, where, before=False, label=""):
        if before:
            RECORDS["current"] = Record(RECORDS["pending"])
            RECORDS["all"].append(RECORDS["current"])
            RECORDS["pending"] = {}
        result = orig_move(self, x, y, where, before, label)
        if before and RECORDS["current"] is not None:
            RECORDS["current"].start = self.ctx._m
        if not before:
            RECORDS["current"] = None
        return result

    boxes.Boxes.move = move

    orig_cc = boxes.Boxes.cc

    def cc(self, *a, **kw):
        rec = RECORDS["current"]
        if rec is not None and rec.matrix is None:
            rec.matrix = self.ctx._m
            rec.base_v = max(0.0, (kw.get("y") or 0.0) - self.burn)
        return orig_cc(self, *a, **kw)

    boxes.Boxes.cc = cc

    def wrap(orig, name):
        def wrapped(self, *a, **kw):
            RECORDS["pending"] = {"primitive": name, "label": kw.get("label"), "args": a, "kwargs": kw}
            return orig(self, *a, **kw)
        return wrapped

    # Generators may override a primitive (FlexBox2 has its own surroundingWall): wrap every definition.
    classes = [boxes.Boxes] + list(boxes.generators.getAllBoxGenerators().values())
    for cls in classes:
        for name in PRIMITIVES:
            if name in cls.__dict__:
                setattr(cls, name, wrap(cls.__dict__[name], name))

    orig_flex = boxes.edges.FlexEdge.__call__

    def flex(self, x, h, **kw):
        rec = RECORDS["current"]
        if rec is not None:
            rec.flex.append((self.ctx._m, x))
        return orig_flex(self, x, h, **kw)

    boxes.edges.FlexEdge.__call__ = flex

    orig_new_part = boxes.drawing.Surface.new_part

    def new_part(self, *a, **kw):
        part = orig_new_part(self, *a, **kw)
        part.record = RECORDS["current"]
        return part

    boxes.drawing.Surface.new_part = new_part


# ---------------------------------------------------------------- geometry

def _bezier(p0, p1, p2, p3, n=8):
    pts = []
    for i in range(1, n + 1):
        s = i / n
        a, b, c, d = (1 - s) ** 3, 3 * s * (1 - s) ** 2, 3 * s * s * (1 - s), s ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def _is_black(rgb):
    if rgb is None:
        return True
    r, g, b = (rgb.red, rgb.green, rgb.blue) if hasattr(rgb, "red") else tuple(rgb)[:3]
    return (r, g, b) == (0, 0, 0)


def loops_of(part, inverse, cuts=None):
    """Closed loops of a drawn part, in the part's local coordinates. Open black polylines (flex
    cuts, slits) are appended to `cuts` when given."""
    loops, cur = [], []

    def flush(path):
        if len(cur) > 2 and math.dist(cur[0], cur[-1]) < 0.05:
            loops.append(cur[:-1] if len(cur) > 3 else cur)
        elif len(cur) > 1 and cuts is not None and _is_black(path.params.get("rgb")):
            cuts.append(list(cur))
        cur.clear()

    for path in part.pathes:
        for c in path.path:
            kind = c[0]
            if kind == "M":
                flush(path)
                cur.append(tuple(inverse * (c[1], c[2])))
            elif kind == "L":
                cur.append(tuple(inverse * (c[1], c[2])))
            elif kind == "C":
                p0 = cur[-1] if cur else tuple(inverse * (c[1], c[2]))
                cur.extend(_bezier(p0, inverse * (c[3], c[4]), inverse * (c[5], c[6]), inverse * (c[1], c[2])))
        flush(path)
    return loops


KERF = 0.3  # width given to zero-width cuts so they show as slits


def polygons_of(loops, cuts=()):
    """Groups loops into polygons with holes (largest loop outside, loops inside it are holes);
    open cuts are subtracted as thin slits."""
    polys = sorted((Polygon(l) for l in loops if len(l) >= 3), key=lambda p: -abs(p.area))
    result = []
    for p in polys:
        if not p.is_valid:
            p = p.buffer(0)
            if p.is_empty:
                continue
        for outer in result:
            if outer["poly"].contains(p.representative_point()):
                outer["holes"].append(p)
                break
        else:
            result.append({"poly": p, "holes": []})
    slits = unary_union([LineString(c).buffer(KERF / 2, cap_style=2) for c in cuts if len(c) > 1]) if cuts else None
    out = []
    for r in result:
        shell = Polygon(r["poly"].exterior.coords, [h.exterior.coords for h in r["holes"]])
        if not shell.is_valid:
            shell = shell.buffer(0)
        if slits is not None and not slits.is_empty:
            shell = shell.difference(slits)
        out += [g for g in getattr(shell, "geoms", [shell]) if g.geom_type == "Polygon" and g.area > 1e-6]
    return out


def rings(poly):
    poly = orient(poly)
    return [[list(map(float, p)) for p in poly.exterior.coords[:-1]]] + \
           [[list(map(float, p)) for p in i.coords[:-1]] for i in poly.interiors]


# ---------------------------------------------------------------- frames and bends

def _norm(v):
    k = math.sqrt(sum(c * c for c in v)) or 1
    return tuple(c / k for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _add(a, b, k=1.0):
    return tuple(x + k * y for x, y in zip(a, b))


def _rot(a, axis, phi):
    """Rodrigues: rotate a about the unit axis by phi."""
    c, s = math.cos(phi), math.sin(phi)
    d = sum(x * y for x, y in zip(axis, a))
    ax = _cross(axis, a)
    return tuple(a[i] * c + ax[i] * s + axis[i] * d * (1 - c) for i in range(3))


class Placement:
    """Where a part goes. origin is the world position of local (0, 0); U and V the local axes in
    world; side = +1 when the thickness goes along U×V, -1 the other way. bends = [(u0, u1, angle°, r)]
    turn the part about V, towards V×U, with inner radius r (the flat part before u0 keeps U)."""

    def __init__(self, origin, U, V, side=1, bends=(), offset=(0, 0)):
        self.origin, self.U, self.V, self.side, self.bends, self.offset = origin, _norm(U), _norm(V), side, list(bends), offset

    def frame_at(self, u):
        """(position of local (u, 0), tangent) walking the bends."""
        pos, T, u_cur = self.origin, self.U, 0.0
        for u0, u1, angle, r in self.bends:
            if u <= u0:
                break
            pos = _add(pos, T, u0 - u_cur)
            L = _cross(self.V, T)
            centre = _add(pos, L, r)
            total = math.radians(angle)
            phi = total * min(1.0, (u - u0) / (u1 - u0))
            radial = tuple(-r * l for l in L)
            pos = _add(centre, _rot(radial, self.V, phi))
            T = _rot(T, self.V, phi)
            u_cur = u0 + (u1 - u0) * min(1.0, (u - u0) / (u1 - u0))
            if u <= u1:
                return pos, T
        return _add(pos, T, u - u_cur), T

    def pieces(self, polys, t):
        if not self.bends:
            return [self._piece(p, t, 0.0, self.origin, self.U) for p in polys]
        cuts = []
        for u0, u1, angle, r in self.bends:
            n = max(2, int(round(angle / 5)))
            cuts += [u0 + (u1 - u0) * i / n for i in range(n + 1)]
        cuts = sorted(set(cuts))
        out = []
        for p in polys:
            minu, minv, maxu, maxv = p.bounds
            edges = [minu - 1] + [c for c in cuts if minu < c < maxu] + [maxu + 1]
            for a, b in zip(edges, edges[1:]):
                strip = p.intersection(rect(a, minv - 1, b, maxv + 1))
                for g in getattr(strip, "geoms", [strip]):
                    if g.geom_type == "Polygon" and g.area > 1e-6:
                        uc = (max(a, minu) + min(b, maxu)) / 2
                        pos, T = self.frame_at(uc)
                        out.append(self._piece(g, t, uc, pos, T))
        return out

    def _piece(self, poly, t, uc, pos, T):
        origin = _add(pos, T, -uc)
        return {"rings": rings(poly), "origin": list(origin), "u": list(T), "v": list(self.V), "side": self.side, "t": t}


def local_matrix(record):
    """World→local: local (0, 0) is the start of the part's base line (the inner face)."""
    m = record.matrix or record.start
    return ~(m * Affine.translation(0, record.base_v))


# ---------------------------------------------------------------- recipes

RECIPES = {}


def recipe(fn):
    RECIPES[fn.__name__] = fn
    return fn


X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)


def inner(box):
    """Inner x, y, h as the generator uses them."""
    x, y, h = box.x, box.y, box.h
    if box.outside:
        x, y, h = box.adjustSize(x), box.adjustSize(y), box.adjustSize(h)
    return x, y, h


@recipe
def ClosedBox(box, parts):
    x, y, h = inner(box)
    return {
        "Wall 1": Placement((0, 0, 0), X, Z, 1),
        "Wall 2": Placement((0, 0, 0), Y, Z, -1),
        "Wall 4": Placement((x, 0, 0), Y, Z, 1),
        "Wall 3": Placement((0, y, 0), X, Z, -1),
        "Top": Placement((0, 0, h), X, Y, 1),
        "Bottom": Placement((0, 0, 0), X, Y, -1),
    }


@recipe
def OpenBox(box, parts):
    x, y, h = box.x, box.y, box.h
    if box.outside:
        x, y, h = box.adjustSize(x), box.adjustSize(y, False), box.adjustSize(h, False)
    return [  # by drawing order: back, left, right, bottom
        Placement((0, y, 0), X, Z, -1),
        Placement((0, 0, 0), Y, Z, -1),
        Placement((x, 0, 0), Y, Z, 1),
        Placement((0, 0, 0), X, Y, -1),
    ]


@recipe
def TypeTray(box, parts):
    t = box.thickness
    sx, sy = box.sx, box.sy
    x = sum(sx) + t * (len(sx) - 1)
    y = sum(sy) + t * (len(sy) - 1)
    place = {
        "bottom": Placement((0, 0, 0), X, Y, -1),
        "front": Placement((0, 0, 0), X, Z, 1),
        "back": Placement((0, y, 0), X, Z, -1),
        "left side": Placement((0, 0, 0), Y, Z, -1),
        "right side": Placement((x, y, 0), (0, -1, 0), Z, -1),
        "top": Placement((0, 0, box.h), X, Y, 1),
    }
    pos = 0
    for i, s in enumerate(sy[:-1]):
        pos += s
        place[f"inner x {i + 1}"] = Placement((0, pos, 0), X, Z, -1)
        pos += t
    pos = 0
    for i, s in enumerate(sx[:-1]):
        pos += s
        place[f"inner y {i + 1}"] = Placement((pos, 0, 0), Y, Z, 1)
        pos += t
    return place


@recipe
def RoundedBox(box, parts):
    x, y, r = box.x, box.y, box.radius
    sh = box.sh
    t = box.thickness
    h = sum(sh) + t * (len(sh) - 1)
    out = []
    plates = [p for p in parts if p.record.primitive == "roundedPlate"]
    levels = [0] + [sum(sh[:i + 1]) + t * i for i in range(len(sh))]
    # A rounded plate's local origin is r along its bottom edge (where the first straight edge starts).
    for i, p in enumerate(plates):
        if i < len(levels):
            z, side = levels[i], (-1 if i == 0 else 1)
            out.append((p, Placement((r, 0, z), X, Y, side)))
        else:  # the loose lid, lifted off
            out.append((p, Placement((r, 0, h + t + 20), X, Y, 1)))
    wall = [p for p in parts if p.record.primitive == "surroundingWall"]
    for p in wall:
        c4 = math.pi * r / 2
        bends = []
        for m, length in p.record.flex:
            u0 = (local_matrix(p.record) * (m * (0, 0)))[0]
            bends.append((u0, u0 + length, 90 * max(1, round(length / c4)), r))
        out.append((p, Placement((x / 2, 0, 0), X, Z, 1, bends)))
    return out


@recipe
def FlexBox2(box, parts):
    x, y, h, r, t = box.x, box.y, box.h, box.radius, box.thickness
    c4 = math.pi * r / 2
    out = []
    sides = 0
    for p in parts:
        rec = p.record
        if rec.primitive == "surroundingWall":
            local = ~(rec.start * Affine.translation(t, 0.25 * t))
            bends = []
            for m, length in rec.flex:
                u0 = (local * (m * (0, 0)))[0]
                bends.append((u0, u0 + length, 90 * max(1, round(length / c4)), r))
            out.append((p, Placement((x + t, 0, 0), Z, (-1, 0, 0), 1, bends), local))
        elif rec.primitive == "flexBoxSide":
            # The side's u runs from the latch end (back) to the full-height end (front).
            out.append((p, Placement((0, y, 0), (0, -1, 0), Z, 1) if sides == 0 else Placement((x, y, 0), (0, -1, 0), Z, -1)))
            sides += 1
        elif rec.primitive == "rectangularWall" and rec.kwargs.get("edges") == "FFFF":
            out.append((p, Placement((0, 0, 0), Y, X, 1)))      # bottom (y × x)
        elif rec.primitive == "rectangularWall":
            out.append((p, Placement((0, y, 0), X, Z, -1)))     # back wall below the latch
    return out


# ---------------------------------------------------------------- driver

def assemble(box):
    """Runs the generator with the recording hooks and returns the placed pieces."""
    install()
    RECORDS["all"], RECORDS["current"], RECORDS["pending"] = [], None, {}
    box.open()
    box.render()
    parts = [p for p in box.ctx._dwg.parts if p.pathes and getattr(p, "record", None) is not None]
    recipe_fn = RECIPES.get(type(box).__name__)
    if recipe_fn is None:
        raise ValueError(f"No 3D assembly for {type(box).__name__} yet")
    placed = recipe_fn(box, parts)
    pieces = []
    if isinstance(placed, dict):
        items = [(p, placed.get(p.record.label)) for p in parts]
    elif placed and isinstance(placed[0], tuple):
        items = placed
    else:
        items = list(zip(parts, placed))
    for item in items:
        part, placement = item[0], item[1]
        if placement is None:
            continue
        local = item[2] if len(item) > 2 else None
        matrix = local if local is not None else local_matrix(part.record)
        cuts = []
        polys = polygons_of(loops_of(part, matrix, cuts), cuts)
        pieces += placement.pieces(polys, box.thickness)
    return {"pieces": pieces, "count": len(parts)}
