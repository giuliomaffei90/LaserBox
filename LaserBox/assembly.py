"""Assembled 3D preview: every cut part, extruded by the material thickness, placed in space.

boxes.py only knows the flat sheet, so the parts are recorded while the generator draws them
(which primitive drew them, the local coordinate frame, where the flex cuts are) and a small
recipe per generator says where each part goes. Flexed regions are bent by slicing the part into
narrow strips that follow an arc.

Protocol: assemble(name, args) -> {"pieces": [{"rings": [[[u, v], …], …], "origin": [x, y, z],
"u": [..], "v": [..], "side": ±1, "t": thickness[, "decoration": kind]}, …], "turn": degrees}  — world(u, v, w) = origin + u·U + v·V + w·side·(U×V)
"""
import math
from types import SimpleNamespace

from affine import Affine
from shapely import set_precision
from shapely.geometry import LineString, Point, Polygon, box as rect
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

import boxes
import boxes.drawing
import boxes.edges
import boxes.generators

# ---------------------------------------------------------------- recording

RECORDS = {"current": None, "all": [], "pending": {}, "walls": None, "stack": []}
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

    # Parts can nest (a stackable edge draws its stabilizer strip in the middle of the wall): the
    # records form a stack, and move() opens a new drawing part on entering and on leaving a part,
    # so the wall's drawing goes on in a part of its own, recorded to the wall again.
    def move(self, x, y, where, before=False, label=""):
        stack = RECORDS["stack"]
        if before:
            stack.append(Record(RECORDS["pending"]))
            RECORDS["current"] = stack[-1]
            RECORDS["all"].append(stack[-1])
            RECORDS["pending"] = {}
        else:
            stack.pop()
            RECORDS["current"] = stack[-1] if stack else None
        result = orig_move(self, x, y, where, before, label)
        if before:
            stack[-1].start = self.ctx._m
            if result:  # "only": nothing drawn, no move after it
                stack.pop()
                RECORDS["current"] = stack[-1] if stack else None
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

    orig_walls = boxes.Boxes.polygonWalls

    def polygonWalls(self, borders, h, bottom="F", *a, **kw):
        """The walls round a polygon are all drawn in one part: record where each one's bottom edge
        starts (and the polygon) so a recipe can tell them apart."""
        edge = self.edges.get(bottom, bottom)
        starts = RECORDS["walls"] = {"borders": list(borders), "starts": []}

        class Recorded(type(edge)):
            def __call__(rec, length, **kw):
                # like rectangularWall's base line: the inner face is startWidth in from the edge
                starts["starts"].append((rec.ctx._m * Affine.translation(0, rec.startWidth()), length))
                return super().__call__(length, **kw)

        recorded = object.__new__(Recorded)  # copy.copy trips on the edges' __getattr__ forwarding
        recorded.__dict__.update(edge.__dict__)
        return orig_walls(self, borders, h, recorded, *a, **kw)

    boxes.Boxes.polygonWalls = polygonWalls

    orig_new_part = boxes.drawing.Surface.new_part

    def new_part(self, *a, **kw):
        part = orig_new_part(self, *a, **kw)
        part.record = RECORDS["current"]
        if part.record is None:  # drawn outside any part (polygonWalls): a part of its own
            part.record = Record({})
            part.record.start = Affine.identity()
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
        if len(cur) > 2 and math.dist(cur[0], cur[-1]) < 0.2:  # a corner's kerf offset can leave 0.14
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
    """Groups loops into polygons with holes by nesting depth (even-odd: a loop filling most of a
    hole is a separate piece, like the inner ring cut out of a disc; a small one is scrap); open cuts
    are subtracted as thin slits."""
    polys = sorted((Polygon(l) for l in loops if len(l) >= 3), key=lambda p: -abs(p.area))
    seen, result = [], []
    for p in polys:
        if not p.is_valid:
            p = p.buffer(0)
            if p.is_empty:
                continue
        inside = [n for n in seen if n["poly"].contains(p.representative_point())]
        node = {"poly": p, "holes": []}
        if len(inside) % 2:
            inside[-1]["holes"].append(p)  # the smallest loop around it, a piece
        elif inside and p.area < 0.5 * inside[-1]["poly"].area:
            continue  # a cut inside a hole (a pin's key in its bearing) falls out with it
        else:
            result.append(node)
        seen.append(node)
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


def snapped(poly):
    """The polygon, simplified within 10 µm and on a 1 µm grid, as clean polygons. SceneKit drops a
    whole piece over µm-short edges (the burn's tiny corner arcs), near-duplicate points (where
    angled finger joints meet), float noise, and slivers left where a flex cut meets a strip's edge;
    snapping with topology repair removes them (and may split a piece)."""
    g = set_precision(poly.simplify(0.01), 0.001)
    return [q for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon" and q.area > 1e-6]


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
    turn the part about V, towards V×U, with inner radius r (the flat part before u0 keeps U).
    keep(polygon) picks which of the part's pieces go here, when one cut part is several pieces.
    decoration marks the pieces as one the 3D view can hide (a lid), with that kind."""

    def __init__(self, origin, U, V, side=1, bends=(), offset=(0, 0), keep=None, decoration=None):
        self.origin, self.U, self.V, self.side, self.bends, self.offset = origin, _norm(U), _norm(V), side, list(bends), offset
        self.keep, self.decoration = keep, decoration

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
        if self.keep:
            polys = [p for p in polys if self.keep(p)]
        if not self.bends:
            return [self._piece(q, t, 0.0, self.origin, self.U) for p in polys for q in snapped(p)]
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
                        out += [self._piece(q, t, uc, pos, T) for q in snapped(g)]
        return out

    def _piece(self, poly, t, uc, pos, T):
        origin = _add(pos, T, -uc)
        piece = {"rings": rings(poly), "origin": list(origin), "u": list(T), "v": list(self.V), "side": self.side, "t": t}
        if self.decoration:
            piece["decoration"] = self.decoration
        return piece


def local_matrix(record):
    """World→local: local (0, 0) is the start of the part's base line (the inner face)."""
    m = record.matrix or record.start
    return ~(m * Affine.translation(0, record.base_v))


# ---------------------------------------------------------------- recipes

RECIPES = {}
# Degrees about the vertical the gallery turns a box by, so its front faces the viewer.
TURN = {"Console": 180, "Console2": 180}


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
    return [  # by drawing order: back, left, right, bottom; the sides' u runs back → open front
        Placement((0, y, 0), X, Z, -1),
        Placement((0, y, 0), (0, -1, 0), Z, 1),
        Placement((x, y, 0), (0, -1, 0), Z, -1),
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
def NotesHolder(box, parts):
    t, y, sx = box.thickness, box.y, list(box.sx)
    x = sum(sx) + t * (len(sx) - 1)
    o = max(0, min(box.opening, 100)) / 100
    out = []
    # Drawn going round: left side, front (left → right), right side, back (right → left, sx reversed).
    for s, (wall, start, d) in enumerate([(((0, y, 0), (0, -1, 0)), (0, 0, 0), X),
                                          (((x, 0, 0), Y), (x, y, 0), (-1, 0, 0))]):
        out.append(Placement(*wall, Z, 1))
        if box.opening == 0.0 or (s and not box.back_openings):
            out.append(Placement(start, d, Z, 1))
            continue
        out.append(Placement(start, d, Z, 1))
        pos = 0
        for a, b in zip(sx, sx[1:]):  # the pieces around each divider
            pos += a
            out.append(Placement(_add(start, d, pos - a * (1 - o) / 2), d, Z, 1))
            pos += t
        out.append(Placement(_add(start, d, x), tuple(-c for c in d), Z, -1))  # drawn mirrored
        sx = sx[::-1]
    if box.bottom_edge != "e":
        out.append(Placement((0, 0, 0), X, Y, -1))
    pos = 0
    for s in box.sx[:-1]:
        pos += s
        out.append(Placement((pos, 0, 0), Y, Z, 1))
        pos += t
    return out


# Decorations: pieces the 3D view can hide — things shown in the box but never cut (notes in a notes
# holder…), registered here, and parts like a lifted lid, marked by their Placement. A kind with its
# own look in the app (paper) gets that; any other kind (lid, panel — a removable back) is drawn in
# the box's material. The gallery always hides lids.
# name -> fn(box) -> pieces, each marked with its "decoration" kind.
DECORATIONS = {}


def decoration(generator, kind):
    def register(fn):
        DECORATIONS[generator] = lambda box: [dict(p, decoration=kind) for p in fn(box)]
        return fn
    return register


@decoration("NotesHolder", "paper")
def notes_stack(box):
    """A stack of notes in each compartment, 1 mm clear of the walls, three quarters full."""
    t, y, out, pos = box.thickness, box.y, [], 0
    for s in box.sx:
        out += Placement((pos + 1, 1, 0), X, Y, 1).pieces([rect(0, 0, s - 2, y - 2)], box.h * 0.75)
        pos += s + t
    return out


@recipe
def BayonetBox(box, parts):
    """Five discs stacked from the bottom. Discs 3 and 4 are cut into an outer ring, glued to the
    base, and an inner ring with the lugs, glued to the lid (disc 5); the lid is shown lifted, as a
    decoration so it can be hidden."""
    t, r = box.thickness, box.diameter / 2
    lift = 20

    def inner(p):
        return max(math.hypot(*c) for c in p.exterior.coords) < r - t / 2

    out = []
    for i, p in enumerate(parts[:5]):
        z = i * t
        if i in (2, 3):
            out.append((p, Placement((0, 0, z), X, Y, 1, keep=lambda q: not inner(q))))
            out.append((p, Placement((0, 0, z + lift), X, Y, 1, keep=inner, decoration="lid")))
        elif i == 4:
            out.append((p, Placement((0, 0, z + lift), X, Y, 1, decoration="lid")))
        else:
            out.append((p, Placement((0, 0, z), X, Y, 1)))
    return out


@recipe
def Rack19Box(box, parts):
    """Walls round x × y × h, the front with the rack ears, the lid (a decoration, so it can be hidden)
    flush with the top and screwed to four corner triangles just under it. The triangles are one drawn part: the first one (right angle
    at (tr, 0), legs to (0, 0) and (tr, tr), fingers outside both) goes in every corner."""
    t, x, y, h, tr = box.thickness, box.x, box.y, box.h, box.triangle
    right, front, back, left, bottom, lid, triangles = parts[:7]
    ear = 17.0  # the left flange of the front, fixed in rack19box.py
    first = Point(tr - 2, 2)
    out = [
        (right, Placement((x, 0, 0), Y, Z, 1)),
        # the wall starts after the left ear, its floor t above the drawn bottom edge
        (front, Placement((0, 0, 0), X, Z, 1), ~(front.record.matrix * Affine.translation(ear, t))),
        (back, Placement((0, y, 0), X, Z, -1)),
        (left, Placement((0, 0, 0), Y, Z, -1)),
        (bottom, Placement((0, 0, 0), X, Y, -1)),
        (lid, Placement((0, 0, h), X, Y, -1, decoration="lid")),
    ]
    # Corner by corner, turning a quarter each time: (corner, U, V)
    for c, U, V in [((0, 0), (-1, 0, 0), Y), ((x, 0), (0, -1, 0), (-1, 0, 0)),
                    ((x, y), X, (0, -1, 0)), ((0, y), Y, X)]:
        origin = _add((c[0], c[1], h - t), U, -tr)
        out.append((triangles, Placement(origin, U, V, 1, keep=lambda q: q.contains(first))))
    return out


RECIPES["Rack10Box"] = Rack19Box  # the same box, narrower


@recipe
def StevensonScreenBox(box, parts):
    """Two trapezoid sides (local frame = world X, Z: back at u = 0, height h; front at u = x, taller),
    slats at the slat angle along both screens, a board at the top of each screen perpendicular to
    the roof, the roof on the sides' top edges, and the bottom screwed under two ledges with two
    latches through them. Positions follow the generator's finger holes in the sides."""
    t, x, y, h, bw = box.thickness, box.x, box.y, box.h, box.bottom_width
    s = box.stevensonScreenSettings
    ang = math.radians(s.absolute_params["angle"])
    ca, sa = math.cos(ang), math.sin(ang)
    h1 = box.front_h
    front_h = h1 - math.sin(math.radians(box.top_slope)) * 2 * t - t
    fs, bs = box.calculate_slat_geometry(front_h - 2 * t), box.calculate_slat_geometry(h - 2 * t)
    a = math.atan((h1 - h) / x)  # the sides' top edge
    edge = (-math.cos(a), 0, -math.sin(a))  # along the top edge, from the front corner
    down, up = (math.sin(a), 0, -math.cos(a)), (-math.sin(a), 0, math.cos(a))

    def board(d, l):
        """A screen's top board: its holes start d along the top edge and run l into the side."""
        bottom = _add(_add((x, 0, h1), edge, d), down, l)
        return Placement(_add(bottom, (math.cos(a), 0, math.sin(a)), -t / 2), Y, up, 1)

    left, right, bottom, ledge1, ledge2, latch1, latch2 = parts[:7]
    rest = parts[7:]
    out = [
        (left, Placement((0, 0, 0), X, Z, 1)),
        (right, Placement((0, y, 0), X, Z, -1)),
        (bottom, Placement(((x - bw) / 2, 0, 2 * t), X, Y, -1)),
        (ledge1, Placement(((x - bw) / 2, 0, 3 * t), X, Y, -1)),
        (ledge2, Placement(((x - bw) / 2, y, 3 * t), X, (0, -1, 0), 1)),
        (latch1, Placement((x / 2 + t / 2, 0, 3 * t), Z, Y, 1)),
        (latch2, Placement((x / 2 - t / 2, y, 3 * t), Z, (0, -1, 0), 1)),
    ]
    fronts = [p for p in rest if p.record.label == "front slat"]
    backs = [p for p in rest if p.record.label == "back slat"]
    out += [(p, Placement((x - t, 0, i * fs.pitch), Y, (-ca, 0, sa), 1)) for i, p in enumerate(fronts)]
    out += [(p, Placement((t, 0, i * bs.pitch), Y, (ca, 0, sa), -1)) for i, p in enumerate(backs)]
    front, back, roof = rest[len(fronts) + len(backs):][:3]
    out += [
        (front, board(math.sin(math.radians(box.top_slope)) * (front_h - fs.h) + t, front_h - fs.h)),
        (back, board(x / math.cos(math.radians(box.top_slope)) - t, h - bs.h)),
        # the roof's wall starts inside its flanges (t, t); it lies on the sides' top edges
        (roof, Placement((0, 0, h), Y, (math.cos(a), 0, math.sin(a)), -1), ~(roof.record.matrix * Affine.translation(t, t))),
    ]
    return out


def _profile(borders):
    """Corners and directions of a polygon given as boxes.py borders [length, angle, …], from (0, 0)
    heading along +u, turning left by each angle."""
    pos, heading, out = (0.0, 0.0), 0.0, []
    for length, angle in zip(borders[::2], borders[1::2]):
        d = (math.cos(math.radians(heading)), math.sin(math.radians(heading)))
        out.append((pos, d))
        pos = (pos[0] + length * d[0], pos[1] + length * d[1])
        heading += angle
    return out


@recipe
def Console(box, parts):
    """Two sides with the console's profile (side u, v = world Y, Z) and, between them, one wall per
    profile edge, all drawn as one part (see polygonWalls in install). The back can be hidden."""
    x = box.x
    left, right, walls = parts[:3]
    rec = RECORDS["walls"]
    out = [(left, Placement((0, 0, 0), Y, Z, -1)), (right, Placement((x, 0, 0), Y, Z, 1))]
    walls_round = list(zip(_profile(rec["borders"]), rec["starts"]))
    for i, ((corner, d), (m, length)) in enumerate(walls_round):
        mid = Point(length / 2, x / 2)
        back = "panel" if i == len(walls_round) - 1 else None  # the profile ends with the back
        out.append((walls, Placement((0, *corner), (0, *d), X, 1, keep=lambda q, mid=mid: q.contains(mid),
                                     decoration=back), ~m))
    return out


def _latch_hardware(t, x, wall_y, inward, z_left, z_right, decoration=None):
    """Console2's latches on a removable wall's inner face at Y = wall_y, the box towards +Y when
    inward = 1: per side a latch, flat and t thick at its height, its knob out through the wall,
    its tip in the side wall (X -t… / …x + t), through two U clamps standing in the wall's H slot
    (X 2t…3t and 5t…6t from the side). Returns the two latches, then the four clamps."""
    i = (0, inward, 0)
    oy = wall_y - inward * t  # their v = 0: the wall's outer face
    return [Placement((7 * t, oy, z_left - t / 2), (-1, 0, 0), i, -inward, decoration=decoration),
            Placement((x - 7 * t, oy, z_right - t / 2), X, i, inward, decoration=decoration)] + \
           [Placement((x0, oy, z + 2 * t), (0, 0, -1), i, inward, decoration=decoration)
            for x0, z in ((2 * t, z_left), (5 * t, z_left), (x - 3 * t, z_right), (x - 6 * t, z_right))]


@recipe
def Console2(box, parts):
    """Profile sides (drawn from the feet, the floor startWidth higher; side u, v = world Y, Z), floor,
    front, panel, top, back wall (y = 0; it can be hidden) and the hatch hardware:
    - removable back wall: guides, the strip under it, and per side a latch — flat, t thick, at the
      side's latch hole — through two U clamps standing in the wall's H slot, its knob out through
      the slot, its tip in the side wall;
    - removable panel: under it a frame of lips (panel_side) along the sides and, when glued, cross
      beams at the ends; a spring (panel_lock) flat inside each lip, its tabs through the lip into
      the side."""
    t, x = box.thickness, box.x
    b = box.borders()
    sw = box.edges.get(box.bottom_edge).startWidth()
    a = math.radians(box.angle)
    hh = b[-2]
    side = lambda p: ~(p.record.start * Affine.translation(t, sw))
    out = [(parts[0], Placement((0, 0, 0), Y, Z, -1), side(parts[0])),
           (parts[1], Placement((x, 0, 0), Y, Z, 1), side(parts[1]))]
    panel_x = t if box.removable_panel and not box.glued_panel else 0
    place = {
        "Floor": Placement((0, 0, 0), Y, X, 1),
        "Front": Placement((0, b[0], -sw), Z, X, 1),        # from the feet up
        "Panel": Placement((panel_x, b[0], b[2]), (0, -math.cos(a), math.sin(a)), X, 1),
        "Top": Placement((0, 0, hh), Y, X, -1),
        "Back Wall": Placement((0, 0, hh), (0, 0, -1), X, 1, decoration="panel"),  # from the top down
        "Bottom Back": Placement((0, 0, t), (0, 0, -1), X, 1),
    }
    back = "panel" if box.removable_backwall else None  # it comes off with what is glued to it
    guides = [Placement((0, 0, 1.05 * t), Y, Z, 1, decoration=back), Placement((x - t, 0, 1.05 * t), Y, Z, 1, decoration=back)]
    for p in parts[2:]:
        label = p.record.label
        if label == "Guide":
            out.append((p, guides.pop(0)))
        elif label in place:
            out.append((p, place[label]))

    hardware = [p for p in parts[2:] if p.record.label is None]  # drawn by Console2's own methods
    D = (0, -math.cos(a), math.sin(a))     # along the panel, from its front edge
    N = (0, -math.sin(a), -math.cos(a))    # from the panel into the box
    p1 = (0, b[0], b[2])
    at = lambda *terms: tuple(sum(k * v[i] for k, v in terms) for i in range(3))
    if box.removable_panel:
        l = b[4]
        if box.glued_panel:   # cross beams, X across, standing on the panel at both ends
            for d in (0, l - t):
                out.append((hardware.pop(0), Placement(at((1, p1), (d, D)), X, N, -1)))
        # the lock's tabs point to v = 0: through the lip (X 0…t) into the side (X -t…0)
        locks = [Placement(at((1, p1), (2 * t, D), (t, N), (-t, X)), D, X, -1),
                 Placement(at((1, p1), (2 * t, D), (t, N), (x + t, X)), D, (-1, 0, 0), 1)]
        out += [(hardware.pop(0), q) for q in locks]
        out += [(hardware.pop(0), Placement(at((1, p1), (x0, X)), D, N, 1)) for x0 in (0, x - t)]
    if box.removable_backwall:
        lp = box.latchpos
        zl, zr = hh - lp, hh - lp - 0.15 * t   # the right H slot sits 0.15 t lower
        out += [(hardware.pop(0), q) for q in _latch_hardware(t, x, 0, 1, zl, zr, back)]
    return out


@recipe
def Crate(box, parts):
    """Bottom and four walls round x × y × h; the stackable feet hang below the floor. Each wall's
    stabilizer strip (drawn inside the wall's stackable edge) is glued inside it on the floor."""
    x, y = box.x, box.y
    walls = {  # wall: (its placement, the strip's: corner, along, into the box from the wall)
        "Bottom": (Placement((0, 0, 0), Y, X, 1), None),
        "side1": (Placement((0, 0, 0), Y, Z, -1), ((0, 0, 0), Y, 1, y)),
        "side2": (Placement((x, 0, 0), Y, Z, 1), ((x, 0, 0), Y, -1, y)),
        "front": (Placement((0, 0, 0), X, Z, 1), ((0, 0, 0), X, -1, x)),
        "back": (Placement((0, y, 0), X, Z, -1), ((0, y, 0), X, 1, x)),
    }
    out, strip = [], None
    for p in parts:
        if p.record.label in walls:
            place, strip = walls[p.record.label]
            out.append((p, place))
        elif strip:  # the stabilizer of the wall before it, centred along it
            corner, along, side, length = strip
            offset = (length - p.record.args[0]) / 2
            out.append((p, Placement(_add(corner, along, offset), along, Z, side)))
    return out


@recipe
def EngravingFrame(box, parts):
    """Built in the frame's own axes — X across, Z up the frame, Y from its face backwards — then
    leant back by the support angle. Front to back: cover plate, frame plate (its finger holes place
    the pocket walls), the pocket (sides, bottom, the engraving plate in it), back plate. The stand,
    behind each pocket side: a wedge along the back plate, a plate perpendicular to the frame round
    the back plate's lower corner tab and half-lapped into the wedge, a foot on the wedge's lower
    finger, and the two spacers ("width": landscape) in the notches of the wedges' back edges. The
    "height" spacers are for standing it the other way round and are left out."""
    t, ew, eh, m, ft = box.thickness, box.EngravingWidth, box.EngravingHeight, box.Margin, box.FrameThickness
    depth = box.EngravingThickness + m
    a = math.radians(max(box.BackSupportAngle, 0))
    ca, sa = math.cos(a), math.sin(a)

    def lean(v):  # rotate about X: the frame's up tilts backwards (+Y)
        return (v[0], v[1] * ca + v[2] * sa, -v[1] * sa + v[2] * ca)

    def P(origin, U, V, side, **kw):
        return Placement(lean(origin), lean(U), lean(V), side, **kw)

    x0, z0 = ft - t - m / 2, ft - t - m / 2      # the pocket's inner corner (frame plate finger holes)
    w_in = ew + 2 * t + m                        # the pocket's inner width and height
    back_y = t + depth                           # the back plate's front face
    queue = list(parts)
    out = []
    if box.AddCoveringFrontPlate:  # glued on to hide the joints: a lid, so the grid shows them
        out.append((queue.pop(0), P((0, -t, 0), X, Z, -1, decoration="lid")))
    out.append((queue.pop(0), P((0, 0, 0), X, Z, -1)))
    if box.AddDummyFingers:   # the strip across the pocket's open top, fingers into the frame plate
        out.append((queue.pop(0), P((x0 + m / 2, t, z0 + w_in + t), X, (0, -1, 0), 1)))
    out.append((queue.pop(0), P((x0 - 2 * t, back_y, z0 - 2 * t), X, Z, -1)))   # back plate: pocket at (2t, 2t)
    out.append((queue.pop(0), P((x0, t, z0), Z, Y, 1)))                       # sides: up the pocket, into it
    out.append((queue.pop(0), P((x0 + w_in, t, z0), Z, Y, -1)))
    out.append((queue.pop(0), P((x0, t, z0), X, Y, -1)))                      # bottom
    out.append((queue.pop(0), P((x0 + m / 2, t, z0), X, Z, -1)))              # the engraving plate
    if box.BackSupportAngle > 0:
        L, H = box.L, box.H
        sides = (x0 - t / 2, x0 + w_in + t / 2)    # the stand runs behind each pocket side
        tab_z = z0 - t                              # the back plate's corner tab: tab_z - t … tab_z
        # The wedge in its own (x, y): long edge on the back plate (x down from its top end, y back),
        # its slot x = L … L + t holding the plate at the tab; then its lower corner pa, the edge on
        # the foot (heading 90° + angle) to pb, and the back edge (heading 180° + angle) with two
        # t-wide notches at 3t…4t and H-3t…H-2t from pb.
        wtop = tab_z + L
        to_frame = lambda wx, wy: (back_y + t + wy, wtop - wx)
        pa = (L + 2 * t + H * math.tan(a) * sa, 0.0)
        pb = (pa[0] - (H * math.tan(a) + 2 * t) * sa, (H * math.tan(a) + 2 * t) * ca)
        along_back = lambda s_: (pb[0] - s_ * ca, pb[1] - s_ * sa)
        d = (0, ca, sa)                             # along the foot edge (horizontal once leant)
        into = (0, -ca, -sa)                        # from the back edge into the wedge
        for xc in sides:   # the foot, its finger hole (2.5 t across, at its start) under the wedge
            out.append((queue.pop(0), P((xc - 2.5 * t, *to_frame(*pa)), d, X, 1)))
        for xc in sides:   # round the tab (hole centred 1.5 t in), its slot half-lapped into the wedge
            out.append((queue.pop(0), P((xc - 1.5 * t, back_y - t, tab_z), Y, X, 1)))
        for xc in sides:
            out.append((queue.pop(0), P((xc - t / 2, back_y + t, wtop), (0, 0, -1), Y, 1)))
        # the "width" spacers: their notch (1 t … 2 t from the end) half-lapped into the wedge notches
        for s_ in (4 * t, H - 2 * t):
            out.append((queue.pop(0), P((sides[0] - 1.5 * t, *to_frame(*along_back(s_))), X, into, 1)))
    return out


@recipe
def HalfBox(box, parts):
    """An L: the bottom along X (0…x), the back standing at X = x, both across Y; triangular
    supports on the bottom's finger-hole lines (posy as in xHoles). Sturdy: the outer two are larger
    side panels whose h edges hold the bottom and the back 1.5 t in, the bottom x2 = 2t·x/h from
    their corner."""
    t, x = box.thickness, box.x
    sy = box.sy  # render() pads it with 0 at both ends unless Sturdy
    width = sum(sy) + (len(sy) - 1) * t
    centres, pos = [], -t / 2
    for s in sy[:-1]:
        pos += s + t
        centres.append(pos)
    out = [(parts[0], Placement((0, 0, 0), X, Y, -1)), (parts[1], Placement((x, 0, 0), Z, Y, -1))]
    rest = parts[2:]
    if box.Sturdy:
        x2 = 2 * t * x / box.h
        out += [(rest[0], Placement((-x2, 0, -2 * t), X, Z, 1)), (rest[1], Placement((-x2, width, -2 * t), X, Z, -1))]
        rest = rest[2:]
    # a support's base fingers hang t below its corner
    out += [(p, Placement((0, c + t / 2, -t), X, Z, 1)) for p, c in zip(rest, centres)]
    return out


@recipe
def Rack19HalfWidth(box, parts):
    """Front at y = 0 with one rack ear (on the shallow side), trapezoid bottom and top (deep at
    X = 0, shallow at X = x), the deep and the shallow side. The front's wall starts t in from its
    drawn corner, past the left and bottom F edges."""
    t, x, h = box.thickness, box.x, box.y
    front, bottom, top, deep, shallow = parts[:5]
    return [
        (front, Placement((0, 0, 0), X, Z, 1), ~(front.record.matrix * Affine.translation(t, t))),
        (bottom, Placement((0, 0, 0), X, Y, -1)),
        (top, Placement((0, 0, h), X, Y, 1)),
        (deep, Placement((0, 0, 0), Y, Z, -1)),
        (shallow, Placement((x, 0, 0), Y, Z, 1)),
    ]


@recipe
def PirateChest(box, parts):
    """Box x × y (front at y = 0), all walls up to the rim h + hy; the chest hinge's axis runs along X
    at the rim, t behind the back wall. The parts are drawn as seen from outside, so the left wall and
    lid end run back → front. The lid, closed: its ends stand on the side walls with the axis at
    their back corner, and its panels go round the half polygon — back (its pins in the hinge),
    n - 2 top panels, front — each from one corner of the lid end to the next, outside it."""
    t = box.thickness
    walls = {p.record.label: p for p in parts if p.record.label}
    x, h = walls["front"].record.args[:2]
    y = walls["right"].record.args[0]
    rim = h + box.edges["O"].startWidth()
    pm = box.edges["P"].startWidth()            # the lid's straight base is pm above its bottom edge
    n = box.n
    _, _, side = box.regularPolygon((n - 1) * 2, h=y / 2.0)
    corners = [(y, pm), (y, pm + side / 2)]     # (Y, Z above the rim), back → front
    for i in range(1, n - 1):
        a = math.radians(90 + i * 180 / (n - 1))
        corners.append((corners[-1][0] + side * math.cos(a), corners[-1][1] + side * math.sin(a)))
    corners.append((0, 0))
    out = [
        (walls["Bottom"], Placement((0, 0, 0), X, Y, -1)),
        (walls["front"], Placement((0, 0, 0), X, Z, 1)),
        (walls["back"], Placement((x, y, 0), (-1, 0, 0), Z, 1)),
        (walls["right"], Placement((x, 0, 0), Y, Z, 1)),
        (walls["left"], Placement((0, y, 0), (0, -1, 0), Z, 1)),
    ]
    panels = [walls["lid back"]] + [p for p in parts if p.record.label == "lid top"] + [walls["lid front"]]
    for p, (a, b) in zip(panels, zip(corners, corners[1:])):
        d = _norm((0, b[0] - a[0], b[1] - a[1]))
        out.append((p, Placement((0, a[0], rim + a[1]), X, d, -1)))
    lid_left, lid_right = [p for p in parts if not p.record.label][-2:]
    out.append((lid_left, Placement((0, y + t, rim), (0, -1, 0), Z, 1)))   # axis at its (0, 0)
    out.append((lid_right, Placement((x, -t, rim), Y, Z, 1)))              # axis at its (y + 2t, 0)
    return out


@recipe
def SideDoorHousing(box, parts):
    """Console2's hatches on the x faces: floor, top, the fixed sides at X = 0 / x (the first as seen
    from outside), and per door — at Y = y, then (double door) at Y = 0; with a single door Y = 0 is
    a fixed wall — the strip under it, the door from 1.1 t up (a decoration, with what is fixed to
    it), its guides and Console2's latches, latchpos below the top."""
    t, x, y, h = box.thickness, box.x, box.y, box.h
    lp = box.latchpos
    doors = 2 if box.double_door else 1
    q = list(parts)
    out = [(q.pop(0), Placement((0, 0, 0), X, Y, -1)),     # floor
           (q.pop(0), Placement((0, 0, h), X, Y, 1)),      # top
           (q.pop(0), Placement((x, 0, 0), Y, Z, 1)),      # sides
           (q.pop(0), Placement((0, 0, 0), Y, Z, -1))]
    faces = [(y, -1), (0, 1)][:doors]                     # (wall Y, into the box)
    for wy, inward in faces:
        out.append((q.pop(0), Placement((0, wy, 0), X, Z, inward)))                         # strip
        out.append((q.pop(0), Placement((0, wy, 1.1 * t), X, Z, inward, decoration="panel")))  # door
    if not box.double_door:
        out.append((q.pop(0), Placement((0, 0, 0), X, Z, 1)))                               # fixed wall
    for wy, inward in faces:   # the guides stand on the door, along its sides
        for x0 in (0, x - t):
            out.append((q.pop(0), Placement((x0, wy, 1.1 * t), (0, inward, 0), Z, inward, decoration="panel")))
    hardware = [_latch_hardware(t, x, wy, inward, h - lp, h - lp - 0.1 * t, "panel") for wy, inward in faces]
    out += [(q.pop(0), p) for hw in hardware for p in hw[:2]]   # drawn: all latches, then all clamps
    out += [(q.pop(0), p) for hw in hardware for p in hw[2:]]
    return out


@recipe
def SlidingDrawer(box, parts):
    """A sleeve open at the front (y = 0) and the drawer in it, centred with the play all round and
    pulled 40 % out. Sizes come from the drawn parts: the generator derives them in render()."""
    t = box.thickness
    p = box.play * t
    x2, hi = parts[0].record.args[:2]
    y, x = parts[5].record.args[:2]
    h = parts[7].record.args[1]
    y2 = parts[1].record.args[0]
    d = (t + p, t + p - 0.4 * y, t + p)  # the drawer's inner corner
    return [  # by drawing order
        Placement(_add(d, Y, y2), X, Z, -1),     # drawer back
        Placement(d, Y, Z, -1),                  # drawer sides
        Placement(_add(d, X, x2), Y, Z, 1),
        Placement(d, X, Z, 1),                   # drawer front, with the grip
        Placement(d, Y, X, 1),                   # drawer bottom (y × x)
        Placement((0, 0, 0), Y, X, 1),           # sleeve bottom and top (y × x)
        Placement((0, 0, h), Y, X, -1),
        Placement((0, 0, 0), Y, Z, -1),          # sleeve sides
        Placement((x, 0, 0), Y, Z, 1),
        Placement((0, y, 0), X, Z, -1),          # sleeve back
    ]


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
        else:  # the loose lid, lifted off; it is larger by the edge's spacing all round
            e = box.edges[box.edge_style].spacing()
            out.append((p, Placement((r, -e, h + t + 20), X, Y, 1, decoration="lid")))
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
    RECORDS.update(all=[], current=None, pending={}, walls=None, stack=[])
    box.reference = 0  # the reference rectangle (bottom left of the sheet) is never part of the box
    box.open()
    box.render()
    merged = {}  # one part per record: a part interrupted by a nested one continues in a new one
    for p in box.ctx._dwg.parts:
        if p.pathes and getattr(p, "record", None) is not None:
            merged.setdefault(id(p.record), SimpleNamespace(record=p.record, pathes=[])).pathes += p.pathes
    parts = list(merged.values())
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
    pieces += DECORATIONS.get(type(box).__name__, lambda b: [])(box)
    return {"pieces": pieces, "count": len(parts), "turn": TURN.get(type(box).__name__, 0)}
