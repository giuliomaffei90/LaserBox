"""Assembled 3D preview: every cut part, extruded by the material thickness, placed in space.

boxes.py only knows the flat sheet, so the parts are recorded while the generator draws them
(which primitive drew them, the local coordinate frame, where the flex cuts are) and a small
recipe per generator says where each part goes. Flexed regions are bent by slicing the part into
narrow strips that follow an arc.

Protocol: assemble(name, args) -> {"pieces": [{"rings": [[[u, v], …], …], "origin": [x, y, z],
"u": [..], "v": [..], "side": ±1, "t": thickness[, "part": n][, "decoration": kind][, "lid": true][, "clear": true]}, …],
"turn": degrees, "galleryLids": bool}  — world(u, v, w) = origin + u·U + v·V + w·side·(U×V). Pieces cut from
the same placed part share its "part" (the exploded view moves them together); decorations that are
not cut (notes, dice…) have none.
"""
import math
import re
import shlex
import sys
from types import SimpleNamespace

from affine import Affine
from shapely import set_precision
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, Polygon, box as rect
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

import boxes
import boxes.drawing
import boxes.edges
import boxes.generators

# ---------------------------------------------------------------- recording

RECORDS = {"current": None, "all": [], "pending": {}, "walls": None, "stack": [], "border": None}
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
        self.caller = None   # the generator's own method that drew it ("roof_tile"): what it is


def _caller(box):
    """The innermost method of the generator (not of boxes.py) on the stack, drawing for box."""
    f = sys._getframe(2)
    while f is not None:
        if "generators" in f.f_code.co_filename and f.f_locals.get("self") is box:
            return f.f_code.co_name
        f = f.f_back
    return None


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
            stack[-1].caller = _caller(self)
            RECORDS["current"] = stack[-1]
            RECORDS["all"].append(stack[-1])
            RECORDS["pending"] = {}
        elif stack:  # a bare move(…) closing a group of parts (HobbyCase) has no part of its own
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

    orig_fill = boxes.Boxes.fillHoles

    def fillHoles(self, pattern, border, *a, **kw):
        RECORDS["border"] = border  # HolePattern draws only the holes: the sheet is the border they fill
        return orig_fill(self, pattern, border, *a, **kw)

    boxes.Boxes.fillHoles = fillHoles

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


def _is_cut(rgb):
    """Black (outer) and blue (inner) paths are cut; red annotations and green or cyan etchings
    aren't, and must not make holes."""
    if rgb is None:
        return True
    r, g, b = (rgb.red, rgb.green, rgb.blue) if hasattr(rgb, "red") else tuple(rgb)[:3]
    return (r, g) == (0, 0)


def _is_black(rgb):
    if rgb is None:
        return True
    r, g, b = (rgb.red, rgb.green, rgb.blue) if hasattr(rgb, "red") else tuple(rgb)[:3]
    return (r, g, b) == (0, 0, 0)


def loops_of(part, inverse, cuts=None):
    """Closed loops of a drawn part, in the part's local coordinates. Open black polylines (flex
    cuts, slits) are appended to `cuts` when given."""
    loops, cur, opens = [], [], []  # opens: [points, black]

    def flush(path):
        if len(cur) > 2 and math.dist(cur[0], cur[-1]) < 0.3:  # a corner's kerf offset can leave 0.14, an outline 0.22
            loops.append(cur[:-1] if len(cur) > 3 else cur)
        elif len(cur) > 1:
            # an outline broken by a hole drawn on the way (SideHingeBox's latch holes) goes on in a
            # new path: join the pieces back up
            o = next((o for o in opens if math.dist(o[0][-1], cur[0]) < 0.2), None)
            if o is None:
                opens.append([list(cur), _is_black(path.params.get("rgb"))])
            else:
                o[0] += cur[1:]
                if math.dist(o[0][0], o[0][-1]) < 0.2:
                    opens.remove(o)
                    loops.append(o[0][:-1])
        cur.clear()

    for path in part.pathes:
        if not _is_cut(path.params.get("rgb")):
            continue
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
    if cuts is not None:
        cuts += [o for o, black in opens if black]
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
            p = max(getattr(p, "geoms", [p]), key=lambda g: g.area)  # a bow tie (impossible sizes)
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
    lid marks a lid (the 3D view has a button for them, the gallery leaves them out); decoration
    marks other pieces the 3D view can hide (a removable panel), with that kind; clear pieces are
    always shown in clear acrylic, whatever the chosen material (a display case's glass). plate is the
    sheet (a polygon in local u, v) for a part that is only holes (a hole pattern): the holes lying in
    it are cut out of it."""

    def __init__(self, origin, U, V, side=1, bends=(), offset=(0, 0), keep=None, decoration=None, lid=False,
                 clear=False, plate=None):
        self.origin, self.U, self.V, self.side, self.bends, self.offset = origin, _norm(U), _norm(V), side, list(bends), offset
        self.keep, self.decoration, self.lid, self.clear, self.plate = keep, decoration, lid, clear, plate

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
        if self.plate is not None:
            sheet = self.plate.difference(unary_union([p for p in polys if p.within(self.plate)]))
            polys = list(getattr(sheet, "geoms", [sheet]))
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
        if self.lid:
            piece["lid"] = True
        if self.clear:
            piece["clear"] = True
        return piece


def local_matrix(record):
    """World→local: local (0, 0) is the start of the part's base line (the inner face)."""
    m = record.matrix or record.start
    return ~(m * Affine.translation(0, record.base_v))


# ---------------------------------------------------------------- recipes

RECIPES = {}
# Degrees about the vertical the gallery turns a box by, so its front faces the viewer.
TURN = {"Console": 180, "Console2": 180,
        "LaptopStand": 25}  # its triangles stand on the diagonals: one would be seen edge-on
# Boxes the gallery shows with their lid (it leaves lids out otherwise): an opened one says what it is.
GALLERY_LIDS = {"IntegratedHingeBox"}


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
# holder…), registered here, and parts like a removable back panel, marked by their Placement. A kind
# with its own look in the app (paper, dice) gets that; any other kind (panel) is drawn in the box's
# material. Lids are not decorations: Placement(lid=True) marks them, with a button of their own.
# name -> fn(box) -> pieces, each marked with its "decoration" kind (a piece may set its own: a die's
# pips).
DECORATIONS = {}


def decoration(generator, kind):
    def register(fn):
        DECORATIONS.setdefault(generator, []).append(
            lambda box: [dict(p, decoration=p.get("decoration", kind)) for p in fn(box)])
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
            out.append((p, Placement((0, 0, z + lift), X, Y, 1, keep=inner, lid=True)))
        elif i == 4:
            out.append((p, Placement((0, 0, z + lift), X, Y, 1, lid=True)))
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
        (lid, Placement((0, 0, h), X, Y, -1, lid=True)),
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
        out.append((queue.pop(0), P((0, -t, 0), X, Z, -1, lid=True)))
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
    lid end run back → front. The lid (a decoration), closed: its ends stand on the side walls with
    the axis at their back corner, and its panels go round the half polygon — back (its pins in the
    discs turning in the side walls' rings), n - 2 top panels, front — each from one corner of the
    lid end to the next, outside it."""
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
    left, right = Placement((0, y, 0), (0, -1, 0), Z, 1), Placement((x, 0, 0), Y, Z, 1)
    out = [
        (walls["Bottom"], Placement((0, 0, 0), X, Y, -1)),
        (walls["front"], Placement((0, 0, 0), X, Z, 1)),
        (walls["back"], Placement((x, y, 0), (-1, 0, 0), Z, 1)),
        (walls["right"], right),
        (walls["left"], left),
    ]
    panels = [walls["lid back"]] + [p for p in parts if p.record.label == "lid top"] + [walls["lid front"]]
    for p, (a, b) in zip(panels, zip(corners, corners[1:])):
        d = _norm((0, b[0] - a[0], b[1] - a[1]))
        out.append((p, Placement((0, a[0], rim + a[1]), X, d, -1, lid=True)))
    lid_left, lid_right = [p for p in parts if not p.record.label][-2:]
    out.append((lid_left, Placement((0, y + t, rim), (0, -1, 0), Z, 1, lid=True)))   # axis at its (0, 0)
    out.append((lid_right, Placement((x, -t, rim), Y, Z, 1, lid=True)))              # axis at its (y + 2t, 0)
    r = box.edges["O"].startWidth()   # the discs turning in the side walls' rings
    out += [(_hinge_disc(walls["left"], (-t, rim), r), left), (_hinge_disc(walls["right"], (y + t, rim), r), right)]
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
def SlidingLidBox(box, parts):
    """x × y × h with the lid sliding out over the front (y = 0, only h high): it lies on the lower
    rails (top at h) under the upper rails on the side walls' tops and the back rail on the back's.
    Sides, rails and lid are drawn from the back (u = 0) to the front, the lid's lip standing on its
    front end between the upper rails."""
    t, x, y, h = box.thickness, box.x, box.y, box.h
    top = h + (1 + box.margin_t) * t      # the side walls' top
    m = box.margin_s * t                  # the lid's side play
    rail = box.rail_mm - box.burn         # where the back rail and the lid's lip start
    F = (0, -1, 0)                        # back → front
    return {
        "right side": Placement((x, y, 0), F, Z, -1),
        "left side": Placement((0, y, 0), F, Z, 1),
        "bottom": Placement((0, 0, 0), Y, X, 1),
        "top right rail": Placement((x, y, top), F, (-1, 0, 0), -1),
        "top left rail": Placement((0, y, top), F, X, 1),
        "bottom right rail": Placement((x, y, h - t), F, (-1, 0, 0), -1),
        "bottom left rail": Placement((0, y, h - t), F, X, 1),
        "lid": Placement((m, y, h), F, X, 1, lid=True),
        "lid lip": Placement((m + rail, 0, h + t), X, Z, 1, lid=True),
        "back": Placement((0, y, 0), X, Z, -1),
        "front": Placement((0, 0, 0), X, Z, 1),
        "back rail": Placement((rail, y, top), X, F, -1),
    }


@recipe
def CardBox(box, parts):
    """Outer walls round x × y, h + t high; x holds an inner side glued inside each end (h high, drawn
    with its finger cutout at the bottom edge: it goes upside down), the compartments sx and the
    dividers. The lid lies at h on the inner walls and slides out over the lowered wall — the front,
    or the right side (then inlays glued to front and back in each compartment carry it) — under the
    lips on the two walls along it; its lip stands on its leading end, the topper between the lips."""
    t, x, y, h, sx = box.thickness, box.boxwidth, box.boxdepth, box.boxhight, box.sx
    starts, pos = [], t   # of the compartments
    for s in sx:
        starts.append(pos)
        pos += s + t
    down = (0, 0, -1)
    place = {
        "Bottom": Placement((0, 0, 0), X, Y, -1),
        "Front": Placement((0, 0, 0), X, Z, 1),
        "Back": Placement((0, y, 0), X, Z, -1),
        "Outer Side Left": Placement((0, 0, 0), Y, Z, -1),
        "Outer Side Right": Placement((x, 0, 0), Y, Z, 1),
        "Inner Side Left": Placement((0, 0, h), Y, down, -1),
        "Inner Side Right": Placement((x, 0, h), Y, down, 1),
    }
    if box.openingdirection == "front":   # the lid from the back (v = 0) to the front
        place.update({
            "Lid": Placement((0.1 * t, y, h), X, (0, -1, 0), -1, lid=True),
            "Lid Lip": Placement((0.1 * t, 0, h + t), X, Z, 1, lid=True),
            "Lid topper (optional)": Placement((1.1 * t, 0, h + t), X, Y, 1, lid=True),
            "Lip Left": Placement((t, 0, h + t), Y, (-1, 0, 0), 1),
            "Lip Right": Placement((x, 0, h + t), Y, (-1, 0, 0), 1),
        })
    else:                                 # the lid from the left (u = 0) to the right
        place.update({
            "Lid": Placement((0, 0.1 * t, h), X, Y, 1, lid=True),
            "Lid Lip": Placement((x, 0.1 * t, h + t), Y, Z, 1, lid=True),
            "Lid topper": Placement((0, 1.1 * t, h + t), X, Y, 1, lid=True),
            "Lip Front": Placement((0, 0, h + t), X, Y, 1),
            "Lip Back": Placement((0, y - t, h + t), X, Y, 1),
        })
    repeated = {
        "Divider": [Placement((s - t, 0, 0), Z, Y, -1) for s in starts[1:]],
        "Front inlay": [Placement((s, 0, 0), X, Z, -1) for s in starts],
        "Back inlay": [Placement((s, y, 0), X, Z, 1) for s in starts],
    }
    return [(p, repeated[p.record.label].pop(0) if p.record.label in repeated else place[p.record.label])
            for p in parts]


def card_back(x0, y0, w, l):
    """The pattern on a card's back, after the classic bicycle back: a coloured field inside a white
    rim, and on it, in white, a frame line, a fine diagonal lattice and two spoked wheels. Returns
    (field, pattern), the pattern one polygon full of holes."""
    rim, line = 0.055 * w, 0.3
    field = rect(x0 + rim, y0 + rim, x0 + w - rim, y0 + l - rim)
    inner = field.buffer(-0.8, join_style=2)
    frame = inner.difference(inner.buffer(-line, join_style=2))
    step, cx = 2.6, x0 + w / 2
    lines = []
    for k in range(-int(l / step) - 4, int((w + l) / step) + 4):
        for a, b in (((x0 + k * step, y0), (x0 + k * step + l * 0.55, y0 + l)),
                     ((x0 + w - k * step, y0), (x0 + w - k * step - l * 0.55, y0 + l))):
            lines.append(LineString([a, b]).buffer(line / 2, cap_style=2))
    lattice = unary_union(lines).intersection(inner)
    r = 0.28 * w
    wheels = []
    for cy in (y0 + l * 0.3, y0 + l * 0.7):
        c = Point(cx, cy)
        ring = c.buffer(r).difference(c.buffer(r - 1.2 * line))
        hub = c.buffer(0.18 * r).difference(c.buffer(0.18 * r - line))
        spokes = [LineString([(cx + 0.18 * r * math.cos(i * math.pi / 8), cy + 0.18 * r * math.sin(i * math.pi / 8)),
                              (cx + r * math.cos(i * math.pi / 8), cy + r * math.sin(i * math.pi / 8))]).buffer(line / 2)
                  for i in range(16)]
        lattice = lattice.difference(c.buffer(r))
        wheels += [ring, hub] + spokes
    pattern = unary_union([frame, lattice] + wheels)
    return field, [g for g in getattr(pattern, "geoms", [pattern]) if g.area > 0.05]


@decoration("CardBox", "cards")
def card_decks(box):
    """A deck of poker cards (63.5 × 88.9, 54 cards ≈ 17 mm) lying in each compartment, smaller if
    the compartment or the box is (see _deck), red and blue in turn."""
    t = box.thickness
    inlays = t if box.openingdirection == "right" else 0   # glued to the front and back
    depth = box.boxdepth - 2 * inlays
    high = min(17.0, box.boxhight - 0.5)
    out, pos = [], t
    for i, s in enumerate(box.sx):
        w, l = min(63.5, s - 0.5), min(88.9, depth - 0.5)
        out += _deck(lambda z: Placement((0, 0, z), X, Y, 1), pos + (s - w) / 2, inlays + (depth - l) / 2, w, l, high, i % 2)
        pos += s + t
    return out


def _deck(at, x0, y0, w, l, high, blue):
    """A deck of cards w × l from (x0, y0), high thick, lying on the plane at(z) puts z above:
    white edges, and on top the first card's back (see card_back), red or blue."""
    deck = rect(x0 + 3, y0 + 3, x0 + w - 3, y0 + l - 3).buffer(3, quad_segs=4)
    field, pattern = card_back(x0, y0, w, l)
    back = ("cardback", "cardback-blue")[blue]
    return at(0).pieces([deck], high) + \
        [dict(p, decoration=back) for p in at(high).pieces([field], 0.08)] + \
        at(high + 0.08).pieces(pattern, 0.08)


@recipe
def RackBox(box, parts):
    """Rack19Box with mounting ears 2 holedist wide and no labels: back, side, front, side, bottom, lid
    (a decoration), the corner triangles."""
    t, x, y, h, tr = box.thickness, box.x, box.y, box.h, box.triangle
    back, side1, front, side2, bottom, lid, triangles = parts[:7]
    first = Point(tr - 2, 2)
    out = [
        (back, Placement((0, y, 0), X, Z, -1)),
        (side1, Placement((x, 0, 0), Y, Z, 1)),
        # the wall starts after the left ear, its floor t above the drawn bottom edge
        (front, Placement((0, 0, 0), X, Z, 1), ~(front.record.matrix * Affine.translation(2 * box.holedist, t))),
        (side2, Placement((0, 0, 0), Y, Z, -1)),
        (bottom, Placement((0, 0, 0), X, Y, -1)),
        (lid, Placement((0, 0, h), X, Y, -1, lid=True)),
    ]
    for c, U, V in [((0, 0), (-1, 0, 0), Y), ((x, 0), (0, -1, 0), (-1, 0, 0)),
                    ((x, y), X, (0, -1, 0)), ((0, y), Y, X)]:
        origin = _add((c[0], c[1], h - t), U, -tr)
        out.append((triangles, Placement(origin, U, V, 1, keep=lambda q: q.contains(first))))
    return out


@recipe
def ElectronicsBox(box, parts):
    """Walls round x × y × h (render() adds the lid's 2 t to h), the bottom — with outside mounts a
    plate flanged left and right, its wall starting holedist + t in from the drawn corner — and the
    lid flush with the top, screwed to four corner triangles just under it, as in Rack19Box."""
    t, x, y, h, tr, hd = box.thickness, box.x, box.y, box.h, box.triangle, box.holedist
    front, left, right, back, bottom, top, triangles = parts[:7]
    first = Point(tr - 2, 2)
    out = [
        (front, Placement((0, 0, 0), X, Z, 1)),
        (left, Placement((0, 0, 0), Y, Z, -1)),
        (right, Placement((x, 0, 0), Y, Z, 1)),
        (back, Placement((0, y, 0), X, Z, -1)),
        (bottom, Placement((0, 0, 0), X, Y, -1),
         ~(bottom.record.matrix * Affine.translation(hd + t, t)) if box.outsidemounts else local_matrix(bottom.record)),
        (top, Placement((0, 0, h), X, Y, -1, lid=True)),
    ]
    for c, U, V in [((0, 0), (-1, 0, 0), Y), ((x, 0), (0, -1, 0), (-1, 0, 0)),
                    ((x, y), X, (0, -1, 0)), ((0, y), Y, X)]:
        out.append((triangles, Placement(_add((c[0], c[1], h - t), U, -tr), U, V, 1, keep=lambda q: q.contains(first))))
    return out


@recipe
def RegularStarBox(box, parts):
    """Two halves, each a polygon plate (its first side from the drawn start, the inner face t in)
    with a wall on every side (u along the side seen from outside, the inner face on the polygon).
    The lid half is turned over, its plate's inner face h up, and turned 180/n against the bottom
    half, so the walls' slots cross half-lapped and the walls' high ends make the star's points."""
    t, n, h = box.thickness, box.n, box.h
    s, sh = parts[2].record.args[0], box.sh
    phi = math.pi / n if n % 2 == 0 else 0.0  # turning over already turns an odd polygon by 180/n
    c, sn = math.cos(phi), math.sin(phi)

    def place(half, origin, U, V, side):
        if half:  # half a turn about X, up by h, then phi about Z
            f = lambda v, dz=0.0: (c * v[0] + sn * v[1], sn * v[0] - c * v[1], dz - v[2])
            origin, U, V = f(origin, h), f(U), f(V)
        return Placement(origin, U, V, side, lid=True if half else None)

    out = []
    for half in (0, 1):
        plate = parts[half]
        out.append((plate, place(half, (-s / 2, -sh, 0), X, Y, -1), ~(plate.record.matrix * Affine.translation(0, t))))
        corner = (-s / 2, -sh, 0)
        for i, w in enumerate(parts[2 + half * n:2 + (half + 1) * n]):
            d = (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0)
            out.append((w, place(half, corner, d, Z, 1)))
            corner = _add(corner, d, s)
    return out


@recipe
def SideHingeBox(box, parts):
    """Inner tray x × yi × hi (bottom, full side D at X = x, low side B at X = 0, hinge sides A at
    Y = 0 and C at Y = yi) in the shell that opens: the lid (the decoration), outer hinge sides p out
    from the inner ones and outer side B over inner B, a small gap between them. The B sides and
    the outer sides are drawn upside down. The hinge axis runs along Y at X = Z = hinge_center - t:
    two pins (2 t along Y) set in the inner sides' slots turn in the outer sides' round holes. A
    latch is a compartment against A (the second against C) by D, the switch behind the button
    holes: a wall along Y, a square end wall, and the loose square plate laid on top at the end wall."""
    t = box.thickness
    p = box.play * t
    hc = box.hinge_center or 2 * t + box.hinge_radius
    walls = {q.record.label: q for q in parts if q.record.label}
    x, hi = walls["inner - hinge side A"].record.args[:2]
    yi = walls["inner - full side D"].record.args[0]
    o, down = t + p, (0, 0, -1)  # the outer hinge sides' inner faces are o out
    place = {
        "inner - hinge side A": Placement((0, 0, 0), X, Z, 1),
        "inner - full side D": Placement((x, 0, 0), Y, Z, 1),
        "inner - hinge side C": Placement((x, yi, 0), (-1, 0, 0), Z, 1),
        "outer - hinge side A": Placement((x, -o, hi), (-1, 0, 0), down, 1),
        "outer - small side B": Placement((0, -o, hi), Y, down, 1),
        "inner - small side B": Placement((0, 0, 2 * hc - t), Y, down, 1),
        "outer - hinge side C": Placement((0, yi + o, hi), X, down, 1),
        "inner - bottom": Placement((0, 0, 0), X, Y, -1),  # drawn as seen from inside (the latch holes)
        "outer - upper lid": Placement((0, -o, hi), X, Y, 1, lid=True),
    }
    out = [(q, place[q.record.label]) for q in parts if q.record.label in place]
    rest = [q for q in parts if not q.record.label]
    out += [(rest[0], Placement((hc - t / 2, 0, hc - 1.75 * t), (0, -1, 0), Z, 1)),
            (rest[1], Placement((hc - 1.5 * t, yi, hc - 1.75 * t), Y, Z, 1))]
    w, l = box.mx_width, box.mx_length
    for i in range(box.cherrymx_latches):
        y0, s = (0, 1) if i == 0 else (yi, -1)   # the hinge side it is against, into the box
        cap, end, wall = rest[2 + 3 * i:5 + 3 * i]
        out += [(cap, Placement((x - w, min(y0 + s * (l + t), y0 + s * (l + t - w)), w), X, Y, 1)),
                (end, Placement((x - w, y0 + s * l, 0), X, Z, -s)),
                (wall, Placement((x - w, y0 + s * l, 0), (0, -s, 0), Z, s))]  # its f end in the hinge side
    return out


@recipe
def HingeBox(box, parts):
    """Box x × y × h (front at y = 0), the lid hl high closed on the rim; with splitlid two lid
    halves, s deep at the front and y - s at the back, open (e) where they meet. Cabinet hinges along
    X on the back (and the front) wall: each eye piece stands across the wall in a slot of the hinge
    edge, its tab through the hole under it, the box's in the even slots and the lid's in the odd
    ones, all on one axis on the rim at the wall's outer face (style outside: ax beyond it). The
    lid's hinged walls go in turned over so their slots run the way the box wall's do (it matters
    for an even eyes_per_hinge). A piece is drawn with its eye at (0, e), +x out of the box."""
    t = box.thickness
    hs = box.edges["u"].settings
    e, p, sp, n = hs.eye, hs.play, hs.spacing, hs.eyes_per_hinge
    x, h = parts[0].record.args[:2]
    y = parts[1].record.args[0]
    hl = parts[4].record.args[1]
    lid = dict(lid=True)
    out = [(parts[0], Placement((0, 0, 0), X, Z, 1)),
           (parts[1], Placement((x, 0, 0), Y, Z, 1)),
           (parts[2], Placement((0, y, 0), (0, -1, 0), Z, 1)),
           (parts[3], Placement((x, y, 0), (-1, 0, 0), Z, 1)),
           (parts[4], Placement((0, y, h), X, Z, -1, **lid))]   # lid back, turned over
    # the hinge edges, top edges of the box walls: along the edge → world X, outer face, outwards
    axes = [(lambda d: d, y + t, 1)]
    if parts[0].record.args[2] == "FFuF":   # split lid
        s = parts[5].record.args[0]
        out += [(parts[5], Placement((x, 0, h), Y, Z, 1, **lid)),            # right, front half
                (parts[6], Placement((x, s, h), Y, Z, 1, **lid)),            # right, back half
                (parts[7], Placement((0, y, h), (0, -1, 0), Z, 1, **lid)),   # left, back half
                (parts[8], Placement((0, s, h), (0, -1, 0), Z, 1, **lid)),   # left, front half
                (parts[9], Placement((x, 0, h), (-1, 0, 0), Z, -1, **lid)),  # lid front, turned over
                (parts[10], Placement((0, 0, 0), X, Y, -1)),
                (parts[11], Placement((0, 0, h + hl), X, Y, 1, **lid)),      # tops: x × s, x × (y - s)
                (parts[12], Placement((0, s, h + hl), X, Y, 1, **lid))]
        hinges = parts[13:]
        axes.append((lambda d: x - d, -t, -1))
    else:
        out += [(parts[5], Placement((x, 0, h), Y, Z, 1, **lid)),
                (parts[6], Placement((0, y, h), (0, -1, 0), Z, 1, **lid)),
                (parts[7], Placement((0, 0, h), X, Z, 1, **lid)),
                (parts[8], Placement((0, 0, 0), X, Y, -1)),
                (parts[9], Placement((0, 0, h + hl), X, Y, 1, **lid))]
        hinges = parts[10:]

    frames = _eye_frames(hinges, e)
    width = (t + p) * n + p + 2 * sp
    hn = min(hs.hinges, int(x // width))
    starts = [(x - width) / 2] if hn == 1 else [j * (width + (x - hn * width) / (hn - 1)) for j in range(hn)]
    beyond = max(t / 2, e - t) if hs.style == "outside" else 0.0
    eye = lambda q: any(Polygon(r).contains(Point(0, e)) for r in q.interiors)
    for along, face, out_y in axes:
        for start in starts:
            for i in range(n):
                if not frames:
                    break
                V = (0, 0, -1) if i % 2 == 0 else Z         # the box's eyes hang down, the lid's up
                axis = (along(start + sp + p + i * (t + p) + t / 2), face + out_y * beyond, h)
                U = (0, out_y, 0)
                origin = _add(_add(axis, V, -e), _cross(U, V), -t / 2)
                part, local = frames.pop(0)
                out.append((part, Placement(origin, U, V, 1, keep=eye, lid=i % 2 == 1), local))
    return out


def _eye_frames(parts, e):
    """(part, its local frame → the piece's own) for each cabinet hinge eye piece drawn in parts: the
    eye at (0, e), the tab towards +y."""
    frames = []
    for part in parts:
        local = local_matrix(part.record)
        for q in polygons_of(loops_of(part, local)):
            if q.interiors:
                c = Polygon(q.interiors[0]).centroid
                _, miny, _, maxy = q.bounds
                turn = Affine.scale(1 if maxy - c.y > c.y - miny else -1)   # drawn upright or turned
                frames.append((part, Affine.translation(0, e) * turn * Affine.translation(-c.x, -c.y) * local))
    return frames


def _turned(place, point, axis, degrees):
    """The placement turned about the axis through point (a hinged lid, opened)."""
    phi = math.radians(degrees)
    turn = lambda v: _rot(v, _norm(axis), phi)
    return Placement(_add(point, turn(_add(place.origin, point, -1))), turn(place.U), turn(place.V), place.side,
                     place.bends, place.offset, place.keep, place.decoration, place.lid, place.clear)


def _hinge_disc(part, centre, r):
    """A chest hinge's disc: the cut round the side's ring is also the outline of the disc turning in
    it, with the slot for the lid's pin (polygons_of drops it as scrap). Its cuts as a part of its own,
    given the axis in the side's local frame."""
    inverse = local_matrix(part.record)
    inside = [path for path in part.pathes
              if all(math.dist(inverse * (c[1], c[2]), centre) < r for c in path.path if c[0] in "MLC")]
    return SimpleNamespace(record=part.record, pathes=inside)


@recipe
def IntegratedHingeBox(box, parts):
    """Box x × y × h (front at y = 0) with a chest hinge: its axis runs along X at the rim, t behind
    the back wall, through the discs turning in the rings at the back of the sides (O on the left, o
    on the right, drawn as seen from outside). The lid, closed, goes from the rim up hl: its sides
    (p, P) are cut round the rings and the pins of its back wall (q) sit in the discs' slots. The
    lid's front and back are drawn from the lid top down to the rim. It is shown opened 25°."""
    t = box.thickness
    r = box.edges["O"].startWidth()            # the ring's outer radius
    hy2 = box.edges["P"].startWidth()          # the lid sides' base line above the rim
    y, x = parts[8].record.args[:2]
    h = parts[4].record.args[1]
    hl = parts[6].record.args[1]
    top = h + hl                               # the lid top's inner face
    lid = dict(lid=True)
    left, right = Placement((0, y, 0), (0, -1, 0), Z, 1), Placement((x, 0, 0), Y, Z, 1)
    places = [
        left,                                                 # O
        Placement((0, y, h + hy2), (0, -1, 0), Z, 1, **lid),  # lid left, p
        right,                                                # o
        Placement((x, 0, h + hy2), Y, Z, 1, **lid),           # lid right, P
        Placement((0, 0, 0), X, Z, 1),                        # front
        Placement((x, y, 0), (-1, 0, 0), Z, 1),               # back
        Placement((0, 0, top), X, (0, 0, -1), -1, **lid),     # lid front
        Placement((0, y, top), X, (0, 0, -1), 1, **lid),      # lid back, q
        Placement((0, 0, 0), Y, X, 1),                        # bottom (y × x)
        Placement((0, 0, top), Y, X, -1, **lid),              # lid top
    ]
    out = list(zip(parts, places))
    out += [(_hinge_disc(parts[0], (-t, h), r), left), (_hinge_disc(parts[2], (y + t, h), r), right)]
    # shown a little open: the lid, and the discs its pins turn, about the axis
    hinge = ((0, y + t, h), (-1, 0, 0), 25)
    return [(q, _turned(p, *hinge) if p.lid or i >= len(parts) else p) for i, (q, p) in enumerate(out)]


@recipe
def DiceBox(box, parts):
    """IntegratedHingeBox's chest hinge, with finger joints, on a box whose walls hold a plate with
    the dice holes flush with their top (h … h + t), and a lid on a second plate on top of it. The
    axis runs along X at the top of the box's plate (the rim), t behind the back wall. Drawn upside
    down: the back wall, the left side (O) and the lid's back and left side (p), from the box's or
    the lid's plate or top."""
    t = box.thickness
    r, hy2 = box.edges["O"].startWidth(), box.edges["P"].startWidth()
    x, y = parts[0].record.args[:2]
    h = parts[2].record.args[1]
    hl = parts[4].record.args[1]
    rim, top = h + t, h + 2 * t + hl          # top: the lid top's inner face
    lid = dict(lid=True)
    left, right = Placement((0, 0, rim - r), Y, (0, 0, -1), 1), Placement((x, 0, 0), Y, Z, 1)
    places = [
        Placement((0, 0, h), X, Y, 1),                          # the box's dice plate
        Placement((0, 0, rim), X, Y, 1, **lid),                 # the lid's dice plate
        Placement((0, 0, 0), X, Z, 1),                          # front
        Placement((0, y, h), X, (0, 0, -1), 1),                 # back
        Placement((0, 0, rim + t), X, Z, 1, **lid),             # lid front
        Placement((0, y, top), X, (0, 0, -1), 1, **lid),        # lid back, q
        Placement((0, 0, 0), Y, X, 1),                          # bottom (y × x)
        Placement((0, 0, top), Y, X, -1, **lid),                # lid top
        Placement((0, 0, top), Y, (0, 0, -1), 1, **lid),        # lid left, p
        left,                                                   # O
        right,                                                  # o
        Placement((x, 0, rim + hy2), Y, Z, 1, **lid),           # lid right, P
    ]
    out = list(zip(parts, places))
    out += [(_hinge_disc(parts[9], (y + t, -r), r), left), (_hinge_disc(parts[10], (y + t, rim), r), right)]
    return out


# Each die's (top, front, right): 1, 2, 3 go anticlockwise round their corner, as on a real die.
DIE_FACES = [(1, 2, 3), (6, 5, 3), (5, 4, 1), (3, 1, 2), (4, 6, 2), (2, 3, 1), (6, 2, 4)]
PIPS = {1: [(0, 0)], 2: [(-1, -1), (1, 1)], 3: [(-1, -1), (0, 0), (1, 1)],
        4: [(-1, -1), (-1, 1), (1, -1), (1, 1)], 5: [(-1, -1), (-1, 1), (0, 0), (1, -1), (1, 1)],
        6: [(-1, -1), (-1, 0), (-1, 1), (1, -1), (1, 0), (1, 1)]}


@decoration("DiceBox", "dice")
def dice(box):
    """A die on the bottom in each hole of the plate (centred as in diceCB, which counts from
    self.x - 2t): 16 mm, smaller if the square that fits the hexagon or the closed box is, its
    pips proud of the top, front and side faces."""
    t = box.thickness
    h, hl = box.h, box.lidheight
    if box.outside:
        h, hl = box.adjustSize(h), box.adjustSize(hl)
    xi, yi = box.x - 2 * t, box.y - 2 * t
    ap = (min(xi, yi) - 4 * t) / 6                        # the holes' apothem
    a = min(16, 0.9 * 4 * ap / (1 + math.sqrt(3)), h + 2 * t + hl - 1)
    if a <= 1:
        return []
    k = 0.08 * a
    cube = rect(k, k, a - k, a - k).buffer(k, quad_segs=2)
    centres = [(xi / 2, yi / 2)] + [(xi / 2 + (2 * ap + t) * math.cos(i * math.pi / 3),
                                     yi / 2 + (2 * ap + t) * math.sin(i * math.pi / 3)) for i in range(6)]
    out = []
    for (cx, cy), (top, front, right) in zip(centres, DIE_FACES):
        x0, y0 = cx - a / 2, cy - a / 2
        out += Placement((x0, y0, 0), X, Y, 1).pieces([cube], a)
        for place, n in [(Placement((x0, y0, a), X, Y, 1), top), (Placement((x0, y0, 0), X, Z, 1), front),
                         (Placement((x0 + a, y0, 0), Y, Z, 1), right), (Placement((x0, y0, 0), Y, Z, -1), 7 - right)]:
            pips = [Point(a / 2 + i * a / 4, a / 2 + j * a / 4).buffer(0.09 * a, quad_segs=3) for i, j in PIPS[n]]
            out += [dict(p, decoration="pip") for p in place.pieces(pips, 0.3)]
    return out


def _walls_round(x, y, at=(0, 0, 0), up=1, **kw):
    """Four walls round x × y from the corner at, inner faces inwards, thickness outward, as boxes.py
    draws them going round as seen from outside: front (Y = 0), right, back, left. up = -1 turns
    them upside down, local v running down from at."""
    corners = [(0, 0), (x, 0), (x, y), (0, y)]
    dirs = [X, Y, (-1, 0, 0), (0, -1, 0)]
    out = []
    for i, d in enumerate(dirs):
        c = corners[i] if up > 0 else corners[(i + 1) % 4]
        out.append(Placement(_add(at, (*c, 0)), d if up > 0 else tuple(-k for k in d), (0, 0, up), 1, **kw))
    return out


@recipe
def TwoPiece(box, parts):
    """Two open shells. The lower one stands on a base whose brim reaches out under the upper one;
    the upper one, the lid (closed), is turned over it, play p clear of it all round: its walls on
    the brim, or, when the lower walls are taller (hi > h), its top on them."""
    t = box.thickness
    o = box.play * t + t  # the upper shell's inner faces, out from the lower one's
    x, hi = parts[0].record.args[:2]
    y = parts[1].record.args[0]
    h = parts[4].record.args[1]
    top = max(h, hi)
    return _walls_round(x, y) + _walls_round(x + 2 * o, y + 2 * o, (-o, -o, top), -1, lid=True) + [
        Placement((0, 0, 0), X, Y, -1),
        Placement((-o, -o, top), X, Y, 1, lid=True),
    ]


@recipe
def UnevenHeightBox(box, parts):
    """Trapezoid walls round x × y, the corner heights counter-clockwise from the front left. The lid
    (closed) lies flat at the highest corner + lid_height, its trapezoid walls hanging from it down
    to the box's slanted top edges: drawn turned round, left, back, right, front, each from the
    corner before it going round; none where both corners already reach the lid."""
    walls, rest = parts[:4], parts[4:]
    x, y = walls[0].record.args[0], walls[1].record.args[0]
    hs = [w.record.args[1] for w in walls]
    # trapezoidWall's cc() leaves the burn out of the base line: give the inner face explicitly
    sw = box.edges[box.bottom_edge].startWidth()
    out = [(w, p, ~(w.record.matrix * Affine.translation(0, sw))) for w, p in zip(walls, _walls_round(x, y))]
    if box.bottom_edge != "e":
        out.append((rest.pop(0), Placement((0, 0, 0), X, Y, -1)))
    if box.add_lid:
        maxh = max(hs)
        top = maxh + box.lid_height
        lh = [maxh - h + box.lid_height for h in hs]
        out.append((rest.pop(0), Placement((0, 0, top), X, Y, 1, lid=True)))
        hanging = _walls_round(x, y, (0, 0, top), -1, lid=True)
        sw = box.edges["F"].startWidth()
        for i in (3, 2, 1, 0):
            if not (lh[i] == lh[(i + 1) % 4] == 0.0):
                w = rest.pop(0)
                out.append((w, hanging[i], ~(w.record.matrix * Affine.translation(0, sw))))
    return out


def _lid(box, parts, x, y, h):
    """The lid style's parts (lids.Lid, drawn last: the lid, then its handle), closed on walls round
    x × y with their top at h, as lids: (part, Placement) for the last parts. A handle
    stands in its slot, its catch under the lid; flatbrim and flatfang lids have no slot for it."""
    lid, t = box.lid, box.thickness
    L = lambda o, U, V, side: Placement(o, U, V, side, lid=True)
    seq, slot = [], None  # slot: centre on the lid's inner face, along the slot, out of the lid
    if lid.style == "flat":  # the bottom fits between the walls, the top lies on them
        bs = lid.brim_spacing
        seq = [L((bs, bs, h), X, Y, -1), L((0, 0, h), X, Y, 1)]
        slot = ((x / 2, y / 2, h - t), X, Z)
    elif lid.style == "flatbrim":  # strips hanging inside the walls from the top's finger holes
        bs = lid.brim_spacing
        down = (0, 0, -1)
        seq = [L((0, 0, h), X, Y, 1), L((bs, bs, h), X, down, 1), L((bs, y - bs, h), X, down, -1),
               L((bs, bs + t, h), Y, down, -1), L((x - bs, bs + t, h), Y, down, 1)]
    elif lid.style == "flatfang":  # a fang through each corner hole, hanging inside the walls
        bs, f, z = lid.brim_spacing, lid.fang_size, h - lid.brim_height
        seq = [L((0, 0, h), X, Y, 1), L((bs, bs, z), Y, Z, 1), L((x - bs - f, bs, z), X, Z, -1),
               L((bs, y - bs - t, z), X, Z, -1), L((x - bs - t, y - bs - f, z), Y, Z, 1)]
    elif lid.style == "chest":  # ends over the front and back walls, the top bent round them
        r = lid.getChestR(x)
        # chestTop passes its cc() y as x: its local v = 0 is its drawn edge, t out from the inner face
        seq = [L((-t, 0, h), X, Z, 1), L((-t, y, h), X, Z, -1),
               Placement((0, -t, h), Z, Y, 1, bends=[(3 * t, 3 * t + math.pi * r, 180, r)], lid=True)]
        slot = ((x, x / 2 - t, h + 1.5 * t), Y, X)  # in the top's last straight 3t, at X = x
    elif lid.style in ("overthetop", "ontop"):  # a top with walls round it, hanging down
        H = lid.height
        if lid.style == "overthetop":  # round the box's walls, the top lying on them
            o, z = -t - lid.play / 2, h
            seq = [L((o, o, z), X, Y, 1)]
        else:  # on the box's walls, with a tab inside each in the middle
            o, z = 0, h + H
            seq = [L((0, 0, z), X, Y, 1)]
        ring = _walls_round(x - 2 * o, y - 2 * o, (o, o, z - H), lid=True)
        seq += [ring[0], ring[2], ring[3], ring[1]]  # front, back, left, right
        if lid.style == "ontop":
            b = h - 2 * t
            seq += [L((x / 2 - t, 0, b), X, Z, -1), L((x / 2 - t, y, b), X, Z, 1),
                    L((0, y / 2 - t, b), Y, Z, 1), L((x, y / 2 - t, b), Y, Z, -1)]
        slot = ((x / 2, y / 2, z), X, Z)
    seq = [[q] for q in seq]
    if seq and lid.handle != "none":
        seq.append([])
        if slot:
            c, A, N = slot
            P = lambda d, U, V, keep=None: Placement(tuple(c[i] + sum(k * w[i] for k, w in d) for i in range(3)),
                                                     U, V, 1, keep=keep, lid=True)
            perp = _cross(A, N)
            if lid.handle.startswith("long"):  # its catch x/2 + 2t across
                seq[-1] = [P([(-x / 4 - t, A), (-t, N), (-t / 2, perp)], A, N)]
            else:  # a knob: two 8t pieces half-lapped across each other
                handle = parts[-1]
                b0 = min(q.bounds[0] for q in polygons_of(loops_of(handle, local_matrix(handle.record)))
                         if q.bounds[0] > 4 * t) + box.burn
                seq[-1] = [P([(-4 * t, A), (-t, N), (-t / 2, perp)], A, N, lambda q: q.bounds[0] < 4 * t),
                           P([(-b0 - 4 * t, perp), (-t, N), (t / 2, A)], perp, N, lambda q: q.bounds[0] > 4 * t)]
    return [(p, q) for p, qs in zip(parts[len(parts) - len(seq):], seq) for q in qs]


@recipe
def BasedBox(box, parts):
    """Walls round x × y standing in the finger holes of a base plate with a brim. The generator
    draws "front" and "back" along y, "left" and "right" along x: as seen from -X, front at X = 0
    and right at Y = 0 (the asymmetric top edges don't match their lid either way). drawLid's part
    closes the walls at h: a fixed "top", or a lid (two plates for E: one in the walls' outset, one
    on it; k: two halves, the right one drawn mirrored; v: the cabinet hinges are left out); then
    the lid style's parts."""
    t, e = box.thickness, box.top_edge
    walls = {p.record.label: p for p in parts}
    x, (y, h) = walls["left"].record.args[0], walls["front"].record.args[:2]
    ring = _walls_round(x, y)
    out = [(walls["right"], ring[0]), (walls["back"], ring[1]), (walls["left"], ring[2]),
           (walls["front"], ring[3]), (walls["base"], Placement((0, 0, 0), X, Y, -1))]
    lid = lambda z, at=0, U=X, side=1: Placement((at, 0, z), U, Y, side, lid=True)
    if e in "cfFhŠY":
        tops = [Placement((0, 0, h), X, Y, 1)]
    elif e in "iLv":
        tops = [lid(h)]
    else:
        tops = {"E": [lid(h + t), lid(h)], "k": [lid(h), lid(h, x, (-1, 0, 0), -1)]}.get(e, [])
    others = [p for p in parts if p.record.label not in ("front", "back", "left", "right", "base")]
    return out + list(zip(others, tops)) + _lid(box, others[len(tops):], x, y, h)


@recipe
def DisplayCase(box, parts):
    """ClosedBox's walls round x × y × h, in clear acrylic, on the bottom (in the chosen material,
    the case's base). Top and bottom are flanged plates whose finger holes are overhang + t/2 in
    from their edge: their inner corner is overhang + t in. The top is glued on, not a lid."""
    x, y, h = inner(box)
    o = box.overhang + box.thickness
    glass = dict(clear=True)
    return [
        Placement((0, 0, 0), X, Z, 1, **glass),          # Wall 1
        Placement((0, 0, 0), Y, Z, -1, **glass),         # Wall 2
        Placement((x, 0, 0), Y, Z, 1, **glass),          # Wall 4
        Placement((0, y, 0), X, Z, -1, **glass),         # Wall 3
        Placement((-o, -o, h), X, Y, 1, **glass),        # Top
        Placement((-o, -o, 0), X, Y, -1),                # Bottom
    ]


def _thick(place, t):
    """The placement, its pieces t thick (a layer cut from another sheet)."""
    pieces = place.pieces
    place.pieces = lambda polys, _: pieces(polys, t)
    return place


def _keypad_levels(box):
    """Keypad's heights: the walls are drawn upside down, their deep finger edge (G) on top holding
    the plates — the switch plate (top1_thickness) on top, the support plate (t) under it, the
    hotswap plate (top2_thickness) under that — and their outset bottom edge (E) t below the
    screwed bottom plate. Returns the walls' inner height h, the plates' (z, thickness) top
    down, and the top of the switch plate."""
    t, h = box.thickness, box.h
    layers = [box.top1_thickness, t] + ([box.top2_thickness] if box.top2_enable else [])
    z, levels = h + t + sum(layers), []
    top = z
    for k in layers:
        z -= k
        levels.append((z, k))
    return h, levels, top


@recipe
def Keypad(box, parts):
    """Walls round x × y, upside down (local v down from the G edge's inner face, h + t up); the
    support, switch and (top2_enable) hotswap plates in the G edge's deep fingers; the bottom plate
    recessed t up from the walls' bottom (their E outset), screwed to the four corner triangles on it
    (as in ElectronicsBox: the triangles' finger holes 1.5 t above the plate's inner face)."""
    t, tr = box.thickness, box.triangle
    x, y = box._get_x_y()
    h, levels, _ = _keypad_levels(box)
    plate = lambda z, k: _thick(Placement((0, 0, z), X, Y, 1), k)
    switch, support = (plate(*l) for l in levels[:2])
    ring = _walls_round(x, y, (0, 0, h + t), -1)
    out = [(p, q) for p, q in zip(parts, [ring[0], ring[1], ring[3], ring[2], support, switch])]
    rest = parts[6:]
    if box.top2_enable:
        out.append((rest.pop(0), plate(*levels[2])))
    out.append((rest[0], Placement((0, 0, t), X, Y, 1)))
    first = Point(tr - 2, 2)
    for c, U, V in [((0, 0), (-1, 0, 0), Y), ((x, 0), (0, -1, 0), (-1, 0, 0)),
                    ((x, y), X, (0, -1, 0)), ((0, y), Y, X)]:
        out.append((rest[1], Placement(_add((c[0], c[1], 3 * t), U, -tr), U, V, 1, keep=lambda q: q.contains(first))))
    return out


@decoration("Keypad", "keycap")
def keycaps(box):
    """On every switch hole (centred as in to_grid_callback) the switch's top housing, 14.6 mm square
    and 6 mm high, in the box's material, and on it a keycap 8 mm high: 18 mm square at the bottom
    (less if the key spacing is), stepped in to 3 mm less for the top 2 mm."""
    spacing = box.btn_size + box.space_between_btn
    m = box.box_padding + box.btn_size / 2
    _, _, top = _keypad_levels(box)
    w = min(18.0, spacing - 1.0)
    sq = lambda s, r: rect(-s / 2 + r, -s / 2 + r, s / 2 - r, s / 2 - r).buffer(r, quad_segs=3)
    housing, cap, crown = sq(14.6, 1), sq(w, 1.5), sq(w - 3, 2)
    out = []
    for i, (offset, n) in enumerate(box.columns_definition):
        for j in range(n):
            c = (m + i * spacing, m + offset + j * spacing)
            out += [dict(p, decoration="switch") for p in Placement((*c, top), X, Y, 1).pieces([housing], 6)]
            out += Placement((*c, top + 6), X, Y, 1).pieces([cap], 6)
            out += Placement((*c, top + 12), X, Y, 1).pieces([crown], 2)
    return out


@recipe
def BrickSorter(box, parts):
    """The whole stack in use, whatever level is chosen (render() draws one): large sieve on top, then
    medium, small, tiny and the bottom tray. Each level is 2 t + wiggle narrower than the one above
    and centred under it; its walls reach startWidth of the "h" edge below its floor, a skirt round
    the top of the level below, its floor lying on that level's walls. Front and back walls along X,
    the floor between them. render() turns x, y, h into the level's inner sizes, so they are reset
    from the arguments before drawing each level."""
    t = box.thickness
    sw = box.edges[box.bottom_edge].startWidth()   # the floor's top face above the walls' bottom
    size = {k: box.non_default_args.get(k, box.argparser.get_default(k)) for k in ("x", "y", "h")}
    chosen, levels = box.level, []
    for level in box.level_desc:
        box.level = level
        box.x, box.y, box.h = size["x"], size["y"], size["h"]
        start = len(RECORDS["all"])
        box.render()
        new, merged = {id(r) for r in RECORDS["all"][start:]}, {}
        for p in box.ctx._dwg.parts:
            if p.pathes and id(getattr(p, "record", None)) in new:
                merged.setdefault(id(p.record), SimpleNamespace(record=p.record, pathes=[])).pathes += p.pathes
        levels.append(list(merged.values()))
    box.level = chosen
    x0, y0 = levels[0][2].record.args[:2]
    out, z = [], sw
    for ps in reversed(levels):   # from the bottom tray up
        (xi, hi), yi = ps[0].record.args[:2], ps[3].record.args[0]
        if hi <= 0:   # h too low for this many levels: the generator's lower ones come out inside out
            continue
        c = ((x0 - xi) / 2, (y0 - yi) / 2, z)
        out += list(zip(ps, [Placement(c, X, Z, 1), Placement(_add(c, Y, yi), X, Z, -1), Placement(c, X, Y, -1),
                             Placement(c, Y, Z, -1), Placement(_add(c, X, xi), Y, Z, 1)]))
        z += hi + t
    return out


@recipe
def EuroRackSkiff(box, parts):
    """A skiff lying open side up, the modules' width (hp × 5.08) along X and their 128.5 mm height
    along Y: walls round it on the bottom, the long walls front and back, each with a 6 mm rail
    inwards from its finger holes 1.5 t under the rim, its holes for the module screws."""
    t, h = box.thickness, box.h
    w, d = box.hp * 5.08, 128.5
    front, right, back, left = _walls_round(w, d)
    return [
        Placement((0, 0, h - t), X, Y, -1),                  # rails: drawn along the hp width
        Placement((w, d, h - t), (-1, 0, 0), (0, -1, 0), -1),
        right, front, back, left,
        Placement((0, 0, 0), Y, X, 1),                       # bottom (128.5 × width)
    ]


@recipe
def ABox(box, parts):
    """Walls round x × y × h on the bottom plate (none for bottom_edge e), drawn: front, back,
    bottom, the lid style's parts (see _lid), then the sides."""
    front, back, *rest, left, right = parts
    x, h = front.record.args[:2]
    y = left.record.args[0]
    ring = _walls_round(x, y)
    out = [(front, ring[0]), (back, ring[2]), (left, ring[3]), (right, ring[1])]
    if box.bottom_edge != "e":
        out.append((rest.pop(0), Placement((0, 0, 0), X, Y, -1)))
    return out + _lid(box, rest, x, y, h)


@recipe
def RegularBox(box, parts):
    """A frustum round the Z axis: the inner faces of the bottom and top plates are the regular
    n-gons of corner radius r0 at z = 0 and r1 at h, their first side at the front; plates and discs
    go in centred, as drawn seen from above. Each wall's inner face is the trapezoid between a bottom
    and a top side (polygonWall: no args, u along the bottom side going round anticlockwise, seen
    from outside). An end's lid style stacks outwards from its plate: angled lid: a plate inside the
    walls and a larger one on them; angled lid2 and round lid: a ring, the lid on it. A bayonet
    mount (top only) is BayonetBox's layers: under the top plate a disc, then the plate, then the lid
    disc; their outer rings stay with the box, the inner ones go with the lid, lifted 20 mm."""
    t, n = box.thickness, box.n
    r0, r1, h = box.radius_bottom, box.radius_top, box.h
    if box.outside:  # as in render()
        r0, r1 = r0 - t / math.cos(math.pi / n), r1 - t / math.cos(math.pi / n)
        if box.top == "none":
            h = box.adjustSize(h, False)
        elif "lid" in box.top and box.top != "angled lid":
            h = box.adjustSize(h) - t
        else:
            h = box.adjustSize(h)
    _, sh0, s0 = box.regularPolygon(n, radius=r0)
    _, sh1, s1 = box.regularPolygon(n, radius=r1)

    # Per part, its placements given its centre c in its drawn frame (centred coordinates, symmetric
    # to the µm, can make SceneKit drop an octagon: the frame stays at the first side's start)
    def end(style, z, out):
        P = lambda dz=0.0, side=out, **kw: lambda c: [Placement((-c.x, -c.y, z + out * dz), X, Y, side, **kw)]
        return {"closed": [P()], "hole": [P()], "angled hole": [P()],
                "angled lid": [P(side=-out, lid=True), P(lid=True)],
                "angled lid2": [P(), P(t, lid=True)], "round lid": [P(), P(t, lid=True)]}.get(style, [])

    def layer(z, lift=20):  # a bayonet layer: its outer ring stays, the inner one goes with the lid
        def places(c):
            inner = lambda q: max(math.dist(p, (c.x, c.y)) for p in q.exterior.coords) < sh1 - t / 2
            return [Placement((-c.x, -c.y, z), X, Y, 1, keep=lambda q: not inner(q)),
                    Placement((-c.x, -c.y, z + lift), X, Y, 1, keep=inner, lid=True)]
        return places

    plates = end(box.bottom, 0.0, -1)
    if box.top == "bayonet mount":
        # render() draws them for the bottom too (it asks self.top): those are left out
        plates += [lambda c: []] * 3 + [layer(h - t), layer(h),
                                         lambda c: [Placement((-c.x, -c.y, h + t + 20), X, Y, 1, lid=True)]]
    else:
        plates += end(box.top, h, 1)
    out = []
    for p, places in zip(parts, plates):
        c = Polygon(max(loops_of(p, local_matrix(p.record)), key=lambda l: abs(Polygon(l).area))).centroid
        out += [(p, q) for q in places(c)]
    H = math.hypot(h, sh1 - sh0)
    for i, p in enumerate(parts[len(plates):]):
        a = 2 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        corner = (-s0 / 2 * ca + sh0 * sa, -s0 / 2 * sa - sh0 * ca, 0)
        V = (sa * (sh1 - sh0) / H, -ca * (sh1 - sh0) / H, h / H)
        out.append((p, Placement(corner, (ca, sa, 0), V, 1)))
    return out


@recipe
def AngledBox(box, parts):
    """A regular 2n + 2-gon stretched along X: the long front and back walls (lx) and n facets at
    each end, drawn going round from the front as seen from outside, like the plates' outlines. The
    plates' drawn edge is startWidth out from the inner polygon. angled lid: a lower lid in the
    walls under an upper one on them; angled hole / lid2: a rim on the walls' fingers, its hole t in
    from the walls; lid2's cut-out, glued under an upper lid on the rim, fills the hole."""
    t = box.thickness
    walls = [p for p in parts if (p.record.label or "").startswith("wall")]
    lx, h = walls[0].record.args[:2]
    side = walls[1].record.args[0]
    n = len(walls) // 2 - 1
    a = 360 / (2 * n + 2)
    profile = _profile(([lx, a] + [side, a] * n) * 2)
    dx = -min(c[0] for c, _ in profile)   # the first corner's X: the box starts at X = 0
    out = [(w, Placement((dx + c[0], c[1], 0), (*d, 0), Z, 1)) for w, (c, d) in zip(walls, profile)]
    plates = []  # (edge, z, side, lid)
    if box.bottom_edge != "e":
        plates.append(("f", 0, -1, False))
    if box.top == "angled lid":
        plates += [("e", h, -1, True), ("E", h, 1, True)]
    elif box.top in ("angled hole", "angled lid2"):
        plates.append(("F", h, 1, False))
        if box.top == "angled lid2":
            plates.append(("E", h + t, 1, True))
    for p, (edge, z, side, lid) in zip(parts, plates):
        local = ~(p.record.matrix * Affine.translation(0, box.edges[edge].startWidth()))
        out.append((p, Placement((dx, 0, z), X, Y, side, lid=lid), local))
        if edge == "F" and box.top == "angled lid2":   # the rim's cut-out, as a part of its own
            hole = min(loops_of(p, local), key=lambda l: abs(Polygon(l).area))
            path = SimpleNamespace(path=[("M", *hole[0])] + [("L", *q) for q in hole[1:] + hole[:1]], params={})
            out.append((SimpleNamespace(record=p.record, pathes=[path]), Placement((dx, 0, h), X, Y, 1, lid=True),
                        Affine.identity()))
    return out


@recipe
def UniversalBox(box, parts):
    """Walls round x × y × h, going round as seen from outside (front and back along x), on the
    bottom. drawLid's part closes the walls at h: a fixed "top", or a lid (two plates for E: one in
    the walls' outset, one on it; v: turned round, its hinge edge (drawn first) at the back, the
    cabinet hinges left out; k: two halves, the right one drawn mirrored); then the lid style's
    parts. The magenta "top hole" (f, F: a flange plate round the walls' top, taking the top's
    place) is left out."""
    t, e = box.thickness, box.top_edge
    walls = {p.record.label: p for p in parts}
    x, h = walls["front"].record.args[:2]
    y = walls["left"].record.args[0]
    ring = _walls_round(x, y)
    out = [(walls["front"], ring[0]), (walls["right"], ring[1]), (walls["back"], ring[2]), (walls["left"], ring[3])]
    if "bottom" in walls:
        out.append((walls["bottom"], Placement((0, 0, 0), X, Y, -1)))
    lid = lambda z, at=(0, 0), U=X, V=Y, side=1: Placement((*at, z), U, V, side, lid=True)
    mx = (-1, 0, 0)
    if e in "cfFhŠY":
        tops = [Placement((0, 0, h), X, Y, 1)]
    else:
        tops = {"E": [lid(h + t), lid(h)], "i": [lid(h)], "L": [lid(h)], "v": [lid(h, (x, y), mx, (0, -1, 0))],
                "k": [lid(h), lid(h, (x, 0), mx, Y, -1)]}.get(e, [])
    others = [p for p in parts if p.record.label not in ("front", "back", "left", "right", "bottom", "top hole")]
    return out + list(zip(others, tops)) + _lid(box, others[len(tops):], x, y, h)


def _flex_walls(walls, t, origin=(0, 0), rot=0.0):
    """polygonWalls' walls (one drawn part, see install) round its borders, which start at origin
    heading rot° in the world's XY: one Placement per wall, from its first bottom edge — after a
    concave corner t·tan(-angle/2) past the corner, as the generator shortens it — its arcs bent
    with their radius (flex), with its local frame. Assumes left-turning arcs."""
    rec = RECORDS["walls"]
    borders, starts = rec["borders"], rec["starts"]
    d = lambda hd: (math.cos(math.radians(hd + rot)), math.sin(math.radians(hd + rot)))
    pos, heading, corr, k, i, out = (0.0, 0.0), 0.0, 0.0, 0, 0, []
    step = lambda p, hd, l: (p[0] + l * d(hd)[0], p[1] + l * d(hd)[1])
    while i < len(borders):
        start, h0, u, bends = step(pos, heading, corr), heading, -corr, []
        while True:
            pos = step(pos, heading, borders[i])
            u += borders[i]
            angle = borders[i + 1]
            if not isinstance(angle, (tuple, list)):
                break
            a, r = angle
            bends.append((u, u + math.radians(a) * r, a, r))
            pos = step(step(pos, heading + 90, r), heading + a - 90, r)   # round the arc's centre
            heading += a
            u += math.radians(a) * r
            i += 2
        heading += angle
        corr = t * math.tan(math.radians(-angle / 2)) if angle < 0 else 0.0
        i += 2
        end = u - corr
        out.append((walls, Placement((origin[0] + start[0], origin[1] + start[1], 0), (*d(h0), 0), Z, 1, bends,
                                     keep=lambda q, end=end: 0 < q.centroid.x < end), ~starts[k][0]))
        k += len(bends) + 1   # a bottom edge before each arc and one after the last
    return out


@recipe
def FlexBox5(box, parts):
    """Two sides (X, Z: their bottom edge's start, the bottom tangent of the r2 circle, at X = r2,
    Z = 0; the first at Y = 0, the second, drawn mirrored, at Y = h) and the wall wrapped round them:
    it starts on the top edge just past the latch and goes round the way the sides are drawn, v
    from the second side's inner face, bent round the r2 and the r1 circle at its flex cuts."""
    t, h = box.thickness, box.h            # render() adjusted them, and the latch size, already
    r1, r2 = box.top_diameter / 2, box.bottom_diameter / 2
    a, l = box.a, box.l
    wall = next(p for p in parts if p.record.primitive == "surroundingWall")
    sides = [p for p in parts if p.record.primitive == "flexBoxSide"]
    # the wall's start: along the bottom (l), round the r1 circle, past the latch
    hd = math.radians(180 + 2 * a)
    px = l + r1 * math.sin(hd) + box.latchsize * math.cos(hd)
    pz = r1 - r1 * math.cos(hd) + box.latchsize * math.sin(hd)
    local = ~(wall.record.start * Affine.translation(0, 1.25 * t))   # moveTo(0, 0.25 t), F edge t in
    bends = [((local * (m * (0, 0)))[0], (local * (m * (0, 0)))[0] + length, math.degrees(length / r), r)
             for (m, length), r in zip(wall.record.flex, (r2, r1))]
    return [(sides[0], Placement((r2, 0, 0), X, Z, 1)), (sides[1], Placement((r2, h, 0), X, Z, -1)),
            (wall, Placement((r2 + px, h, pz), (math.cos(hd), 0, math.sin(hd)), (0, -1, 0), 1, bends), local)]


@recipe
def RoundedRegularBox(box, parts):
    """A regular n-gon round the Z axis, inner circle inner_size, its corners rounded with radius:
    the plates' outline starts at the middle of the front side, -inner_size/2 in Y (the bottom at
    Z = 0, the top at h); the walls polygonWalls drew round it (see _flex_walls), each bent round
    the corners it spans. top lid: a plate t larger all round on the top, its first side's start
    t out from the front side's."""
    t, ap = box.thickness, box.inner_size / 2
    bottom, top = parts[:2]
    out = [(bottom, Placement((0, -ap, 0), X, Y, -1)), (top, Placement((0, -ap, box.h), X, Y, 1))]
    if box.top == "lid":
        out.append((parts[2], Placement((-box.side / 2, -ap - t, box.h + t), X, Y, 1, lid=True)))
    return out + _flex_walls(parts[-1], t, (0, -ap))


@recipe
def HeartBox(box, parts):
    """The heart's outline (polygonWalls' borders) from its tip, turned 45° so the tip is at the
    front (X = 0, Y = 0) and the lobes at the back: the walls round it (see _flex_walls), bent round
    the lobes, the top (drawn first, with the hole) at h and the bottom (drawn mirrored). top lid:
    the cut-out of the top's hole is cut again t smaller: its ring, glued under the lid (t larger
    all round, its start t out from the tip both ways), sits in the hole; the rest is scrap."""
    t, h = box.thickness, box.h
    U, V = (math.sqrt(0.5), math.sqrt(0.5), 0), (-math.sqrt(0.5), math.sqrt(0.5), 0)
    walls, top, bottom = parts[:3]
    lid = box.top == "lid"
    out = [(top, Placement((0, 0, h), U, V, 1, keep=(lambda q: bool(q.interiors)) if lid else None)),
           (bottom, Placement((0, 0, 0), U, V, -1))]
    if lid:
        local = local_matrix(top.record)
        hole, cut = sorted(loops_of(top, local), key=lambda l: -abs(Polygon(l).area))[1:3]
        ring = SimpleNamespace(record=top.record, pathes=[
            SimpleNamespace(path=[("M", *l[0])] + [("L", *q) for q in l[1:] + l[:1]], params={}) for l in (hole, cut)])
        out += [(ring, Placement((0, 0, h), U, V, 1, lid=True), Affine.identity()),
                (parts[3], Placement((0, -t * math.sqrt(2), h + t), U, V, 1, lid=True))]
    return out + _flex_walls(walls, t, rot=45)


def _flex_bends(rec, local, r, y):
    """A surrounding wall's bends, one per flex cut, about the sides' corners of radius r. A flex
    running round both corners at once (y - 2r < t) turns 180° over the side's full depth y."""
    out = []
    for m, length in rec.flex:
        u0 = (local * (m * (0, 0)))[0]
        both = length > 1.01 * math.pi * r / 2
        out.append((u0, u0 + length, 180 if both else 90, y / 2 if both else r))
    return out


def _clip(place, u0, u1):
    """The placement, keeping only u0 … u1 of the part: one cut part shown as two pieces (a flex
    wall's fixed half and its lid)."""
    band, pieces = rect(u0, -1e5, u1, 1e5), place.pieces
    place.pieces = lambda polys, t: pieces([g for p in polys for c in [p.intersection(band)]
                                            for g in getattr(c, "geoms", [c]) if g.geom_type == "Polygon" and not g.is_empty], t)
    return place


def _flex_wall(part, local, bends, hinge, origin, U, V):
    """A surrounding wall placed with its bends, the part from the hinge (u) on as the lid."""
    place = lambda **kw: Placement(origin, U, V, 1, bends, **kw)
    return [(part, _clip(place(), -1e5, hinge), local), (part, _clip(place(lid=True), hinge, 1e5), local)]


@recipe
def FlexBox(box, parts):
    """Sides y × h with all four corners rounded (r), the latch at the front top, at X = x, between
    the compartments and at X = 0. The flex wall goes round them from the front under the latch,
    down, along the bottom, up the back, over the top and down to its latch hole; it is jointed to
    the sides up to the back, the rest (from the back top corner) is the lid. The dividers stand in
    the wall's finger holes, which sit t towards X = 0 from the compartments' sx."""
    t, x, y, h, r, L = box.thickness, box.x, box.y, box.h, box.radius, box.latchsize
    wall, *sides = parts
    local = ~(wall.record.start * Affine.translation(0, 0.25 * t))
    bends = _flex_bends(wall.record, local, r, y)
    out = _flex_wall(wall, local, bends, bends[len(bends) // 2][0], (-t, 0, h - r - L), (0, 0, -1), X)
    # a side's local origin is r behind the front, where its bottom straight starts
    walls, pos = [Placement((x, r, 0), Y, Z, 1)], -t / 2
    for s in box.sx[:-1]:
        pos += s + t
        walls.append(Placement((pos - 1.5 * t, r, 0), Y, Z, 1))   # the wall's v = 0 is at X = -t
    walls.append(Placement((0, r, 0), Y, Z, -1))
    return out + list(zip(sides, walls))


@recipe
def FlexBox4(box, parts):
    """Sides y × h, the top corners rounded (r), the latch at the bottom of the front (Y = 0). The
    flex wall's fingers start in the bottom's back edge; it is jointed up the back, then, from the
    back top corner, the lid: over the top and down the front to the latch, t past the bottom."""
    t, x, y, r = box.thickness, box.x, box.y, box.radius
    wall, right, left, bottom = parts
    local = ~(wall.record.start * Affine.translation(t, 0.25 * t))
    bends = _flex_bends(wall.record, local, r, y)
    return _flex_wall(wall, local, bends, bends[0][0], (-t, y, 0), Z, X) + [
        (right, Placement((x, 0, 0), Y, Z, 1)),
        (left, Placement((0, 0, 0), Y, Z, -1)),
        (bottom, Placement((0, y, 0), (0, -1, 0), X, -1)),   # its open (e) edge at the front
    ]


@recipe
def FlexBox3(box, parts):
    """Box x × y × z, the sides' back top corner rounded (r). The flex wall's fingers start in the
    bottom's back edge; it goes up the back and, from the back top corner, is the lid: over the
    corner (its flex 5 % short of the quarter circle) and, widened by the clearance d each side, over
    the top to t past the front. Lid sides (drawn from the back bottom corner, the arc round the
    flex's outer face, centred on the corner's) and the lid front hang h down from it, d clear of the
    sides and against the front."""
    t, x, y, z, r, d, h = box.thickness, box.x, box.y, box.z, box.radius, box.d, box.h
    wall, bottom, lid_front, lid_right, lid_left, right, left, front = parts
    local = ~(wall.record.start * Affine.translation(t, d + t))
    bends = [(u0, u1, 90, r) for u0, u1, _, _ in _flex_bends(wall.record, local, r, y)]
    if r < h:   # lidSide's bottom edge, its front t in front of the box
        base = y + 2 * t
    else:
        base = y + (r + t) * math.sin(math.acos((r - h) / (r + t))) - r + t
    lid = dict(lid=True)
    return _flex_wall(wall, local, bends, bends[0][0], (-t, y, 0), Z, X) + [
        (bottom, Placement((0, 0, 0), Y, X, 1)),                             # y × x
        (lid_front, Placement((-t - d, -t, z), (0, 0, -1), X, 1, **lid)),     # from the lid top down
        (lid_right, Placement((x + t + d, base - t, z - h), Z, (0, -1, 0), 1, **lid)),
        (lid_left, Placement((-t - d, base - t, z - h), Z, (0, -1, 0), -1, **lid)),
        (right, Placement((x, 0, 0), Y, Z, 1)),
        (left, Placement((0, 0, 0), Y, Z, -1)),
        (front, Placement((0, 0, 0), X, Z, 1)),
    ]


def _arc(c, r, a0, a1, n):
    """The n + 1 corners of n chords on the circle round c (in a plane), from a0 to a1 degrees."""
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


def _guides(parts, path, side):
    """Panels across X (v = 0 at X = 0), one per segment of path (world Y, Z), in order: their inner
    faces on it, the thickness towards the groove."""
    return [(p, Placement((0, *a), (0, b[0] - a[0], b[1] - a[1]), X, side)) for p, a, b in zip(parts, path, path[1:])]


def _rails(part, t, r, h, width):
    """The rails glued on the side walls' inner faces round the top front corner (centre Y = r,
    Z = h - r): per side an outer one (radii r … r + t) and an inner one (r - 2.5 t … r - 1.5 t), the
    door's groove between them. Drawn with the top leg along u, the front corner at the far end
    turning up: (u, v) → (Y, Z) = (r, h - r) + (cx - u, cy - v), (cx, cy) its centre, from its
    bounds (the front leg's outer face at cx + ro, the top leg's at cy - ro)."""
    polys = sorted(polygons_of(loops_of(part, local_matrix(part.record))), key=lambda q: -q.area)
    out = []
    for i, q in enumerate(polys[:4]):
        ro = r + t if i < 2 else r - 1.5 * t
        _, miny, maxx, _ = q.bounds
        cx, cy = maxx - ro, miny + ro
        x0, side = (0, 1) if i % 2 == 0 else (width, -1)
        out.append((part, Placement((x0, r + cx, h - r + cy), (0, -1, 0), (0, 0, -1), side,
                                    keep=lambda p, pt=q.representative_point(): p.contains(pt))))
    return out


def _fillets(box, part, c, d1, d2, width):
    """cornerRadius(two=True): two r × r squares less a quarter disc (the second turned half round,
    r + spacing up), glued on the side walls' inner faces in the corner c (world Y, Z) of the walls
    along d1 and d2, the door's groove going round between them and the guide panels. The first:
    (u, v) → c + (r - u)·d1 + v·d2."""
    r, s = box.radius, box.spacing
    U, V = (0, -d1[0], -d1[1]), (0, *d2)
    side = 1 if _cross(U, V)[0] > 0 else -1   # thickness +X on the left wall
    first, second = Point(0.9 * r, 0.1 * r), Point(0.1 * r, r + s - 0.1 * r)
    return [(part, Placement((0, c[0] + r * d1[0], c[1] + r * d1[1]), U, V, side, keep=lambda q: q.contains(first))),
            (part, Placement((width, c[0] + (r + s) * d2[0], c[1] + (r + s) * d2[1]), (0, *d1), (0, -d2[0], -d2[1]),
                             -side, keep=lambda q: q.contains(second)))]


def _handle(door, t):
    """The handle standing out of a sliding door's outer face, its fingers in the door's holes (door u
    = t, from v = t)."""
    pos, T = door.frame_at(t)
    N = tuple(door.side * c for c in _cross(T, door.V))   # out of the door
    origin = _add(_add(_add(pos, N, t), T, -t / 2), door.V, t)
    return Placement(origin, N, door.V, -door.side, lid=True)


@recipe
def BreadBox(box, parts):
    """Sides l = x deep (drawn as seen from the left, the front at the right: (u, v) from the inner
    back bottom corner → Y = l - u, Z = v), back wall, bottom (out t at the front), the fixed top
    over the back half. Inside, guide panels go up 2.5 t in front of the back wall and round under
    the top (n chords of radius r - 2.5 t) to its front end, the corner fillets behind them: that
    groove takes the door when open. Closed, the door (a lid) runs in the groove between the rails
    at the front: from the bottom (its handle end) up the front, round the corner and back under
    the top, its outer face on the outer rails (radius r)."""
    t, l, w, h, r, n = box.thickness, box.x, box.y, box.h, box.radius, box.n
    q = list(parts)
    side = lambda p: ~(p.record.start * Affine.translation(t, t))
    out = [(q[0], Placement((0, l, 0), (0, -1, 0), Z, 1), side(q[0])),
           (q[1], Placement((w, l, 0), (0, -1, 0), Z, -1), side(q[1])),
           (q[2], Placement((w, l, 0), (-1, 0, 0), Z, 1)),               # back
           (q[3], Placement((0, l, 0), (0, -1, 0), X, -1)),              # bottom
           (q[4], Placement((0, l, h), (0, -1, 0), X, 1))]               # top, back half
    rho = r - t
    door = Placement((w - 0.1 * t, t, 0), Z, (-1, 0, 0), 1, bends=[(h - r, h - r + math.pi * rho / 2, 90, rho)], lid=True)
    out += [(q[5], door), (q[6], _handle(door, t))]
    rr = r - 2.5 * t
    path = [(l - 2.5 * t, 0)] + _arc((l - r, h - r), rr, 0, 90, n) + [(l / 2, h - 2.5 * t)]
    out += _guides(q[7:9 + n], path, 1)
    out += _rails(q[9 + n], t, r, h, w)
    out += _fillets(box, q[10 + n], (l, h), (-1, 0), (0, -1), w)
    return out


@recipe
def ShutterBox(box, parts):
    """Sides l = y deep (drawn as seen from the left, the front at the right: (u, v) from the inner
    back bottom corner → Y = l - u, Z = v), back wall (single: full height, out t at the top), front
    wall h - r high, bottom. Guide panels run 2.5 t over the bottom (double: from the back, down
    2.5 t in front of the back wall first) and round the front (n chords of radius r - 2.5 t) up
    2.5 t behind the front wall, the corner fillets under them: that groove takes the shutter when
    open. Closed, the shutter (a lid) runs in the groove between the rails at the top, its outer
    face on the outer rails (radius r): single from the back wall (its handle end) forward, round
    the corner and down behind the front wall; double from the top of the back wall round both
    corners (its straight handle end bent with the first)."""
    t, w, l, h, r, n = box.thickness, box.x, box.y, box.h, box.radius, box.n
    double = box.style == "double"
    left, right, back, front, *q = parts
    side = lambda p: ~(p.record.start * Affine.translation(t, t))
    out = [(left, Placement((0, l, 0), (0, -1, 0), Z, 1), side(left)),
           (right, Placement((w, l, 0), (0, -1, 0), Z, -1), side(right)),
           (back, Placement((w, l, 0), (-1, 0, 0), Z, 1)),
           (front, Placement((0, 0, 0), X, Z, 1))]
    if double:
        out += _fillets(box, q.pop(0), (l, 0), (0, 1), (-1, 0), w)       # back bottom corner
    out += _fillets(box, q.pop(0), (0, 0), (0, 1), (1, 0), w)            # front bottom corner
    out += _rails(q.pop(0), t, r, h, w)
    out.append((q.pop(0), Placement((0, l, 0), (0, -1, 0), X, -1)))     # bottom
    rho = r - t
    a = math.pi * rho / 2
    if double:
        door = Placement((0.1 * t, l - t, h - r), Z, X, 1, bends=[(0, a, 90, rho), (a + l - 2 * r, 2 * a + l - 2 * r, 90, rho)],
                         lid=True)
    else:
        door = Placement((0.1 * t, l, h - t), (0, -1, 0), X, 1, bends=[(l - r, l - r + a, 90, rho)], lid=True)
    out += [(q.pop(0), door), (q.pop(0), _handle(door, t))]
    rr, up = r - 2.5 * t, h - 2 * r > 2 * t   # the generator's straight guides up at the ends
    ends = [(2.5 * t, h - r)] if up else []
    if double:
        path = [(l - 2.5 * t, h - r)][:len(ends)] + _arc((l - r, r), rr, 0, -90, n) + _arc((r, r), rr, -90, -180, n) + ends
    else:
        path = [(l, 2.5 * t)] + _arc((r, r), rr, -90, -180, n) + ends
    return out + _guides(q, path, -1)


@recipe
def FlexBook(box, parts):
    """A book lying on its base, the spine on the left: render() swaps y and h, so x is the covers'
    width, y the book's height (along Y), h its thickness. The D-shaped sides (u from the lid down,
    v from the fore-edge at X = S to the spine, a half disc of radius h/2 round X = r) close the
    ends; the latch wall stands at the fore-edge and the inner wall at the half discs, both drawn
    from the lid down. The cover, drawn from the base's fore-edge, bends 180° round the half discs
    (its flex is t longer than the arc) into the lid, closed, the latch wall's tab through it. On
    the lid by the tab: per side a notched bracket lying flat, pinned through its square hole into
    the lid's, a plain one on it; between them the bolt, its wings in the notches and its tip
    through the tab's slot, and the grip plate glued on the bolt."""
    t, x, y, h, l = box.thickness, box.x, box.y, box.h, box.latchsize
    r = h / 2
    cover, inner, latch, side1, side2, *hardware = parts
    S = x + 2 * t + r               # the sides' fore-edge: the latch wall's outer face
    local = local_matrix(cover.record)
    bends = _flex_bends(cover.record, local, r, h)
    down = (0, 0, -1)
    out = _flex_wall(cover, local, bends, bends[0][1], (S + t, -2 * t, 0), (-1, 0, 0), Y) + [
        (inner, Placement((r, 0, h), down, Y, 1), ~(inner.record.start * Affine.translation(0, t))),
        (latch, Placement((S - t, 0, h), down, Y, 1),
         ~(latch.record.start * Affine.translation(0 if box.recess_wall else 3 * t, t))),
        (side1, Placement((S, 0, h), down, (-1, 0, 0), -1)),
        (side2, Placement((S, y, h), down, (-1, 0, 0), 1))]
    # the lid's square holes are at (S - 2.5 t, y/2 ± (l/2 + 3.5 t)); the brackets' bottoms face the bolt
    L = lambda o, U, V, side=1: Placement(o, U, V, side, lid=True)
    top, mid = h + t, y / 2         # the lid's outer face
    brackets = lambda z: [L((S - 5 * t, mid + l / 2, z), X, Y), L((S, mid - l / 2, z), (-1, 0, 0), (0, -1, 0))]
    pins = [L((S - 3 * t, mid + s * (l / 2 + 3.5 * t) - t / 2, h), X, Z, -1) for s in (1, -1)]
    held, plain = brackets(top), brackets(top + t)
    places = [held[0], pins[0], held[1], pins[1], plain[0], plain[1],
              L((S - 5 * t, mid - l / 2, top + t), X, Y),                    # grip plate
              L((S - 5 * t, mid + l / 2 + 2 * t, top), (0, -1, 0), X)]      # bolt, its tip towards +X
    return out + list(zip(hardware, places))


@recipe
def DoubleFlexDoorBox(box, parts):
    """Sides x × h at Y = 0 and y, their corners rounded r, drawn from r along the bottom; the wall,
    y + 2t wide over both, bent round them from the latch at the middle of the top (X = x/2):
    right, down, along the bottom, up and back to the middle. Its two top halves, from the latches
    to the flex at the top corners, are the doors (closed)."""
    t = box.thickness
    wall, front, back = parts
    x, h, y, r = wall.record.args[:4]   # surroundingWall(x, h, y, r): its y is the box's h
    local = ~(wall.record.start * Affine.translation(0, 0.25 * t))
    bends = _flex_bends(wall.record, local, r, h)
    a, b = bends[0][0], bends[-1][1]
    place = lambda **kw: Placement((x / 2, -t, h), X, Y, 1, bends, **kw)
    return [(wall, _clip(place(), a, b), local),
            (wall, _clip(place(lid=True), -1e5, a), local),
            (wall, _clip(place(lid=True), b, 1e5), local),
            (front, Placement((r, 0, 0), X, Z, 1)),
            (back, Placement((r, y, 0), X, Z, -1))]


@recipe
def UBox(box, parts):
    """The U (y × h, its bottom corners rounded r, drawn from its bottom's corner) at X = 0 (seen
    from outside, u back to front) and at X = x; the wall, x + 2t wide over both, bent round it
    from the front's top: down, across the bottom and up the back. drawLid's part closes it at h as
    in UniversalBox; the lid style is drawn y × x (a chest across the U's), so _lid's parts are
    turned a quarter round Z."""
    t, e, x, y, h, r = box.thickness, box.top_edge, box.x, box.y, box.h, box.radius
    left, right, wall, *others = parts
    w = box.edges["f"].spacing()
    back = box.topEdges(e)[1]   # the wall's first top edge, at its end
    local = ~(wall.record.start * Affine.translation(box.edges.get(back, back).spacing(), 0))
    # radius 0: square corners, their flex cuts 0 long
    bends = [(u0, max(u1, u0 + 1e-3), a, rr) for u0, u1, a, rr in _flex_bends(wall.record, local, r, y)]
    out = [(left, Placement((0, y, 0), (0, -1, 0), Z, 1), ~(left.record.start * Affine.translation(w, w))),
           (right, Placement((x, 0, 0), Y, Z, 1), ~(right.record.start * Affine.translation(w, w))),
           (wall, Placement((-t, 0, h), (0, 0, -1), X, 1, bends), local)]
    lid = lambda z, at=(0, 0), U=X, V=Y, side=1: Placement((*at, z), U, V, side, lid=True)
    mx = (-1, 0, 0)
    if e in "cfFhŠY":
        tops = [Placement((0, 0, h), X, Y, 1)]
    else:
        tops = {"E": [lid(h + t), lid(h)], "i": [lid(h)], "L": [lid(h)], "v": [lid(h, (x, y), mx, (0, -1, 0))],
                "k": [lid(h), lid(h, (x, 0), mx, Y, -1)]}.get(e, [])
    out += list(zip(others, tops))
    # the lid frame's X (y long) is world Y, its Y (x long) world -X from X = x
    return out + [(p, _turned(q, (x / 2, x / 2, 0), Z, 90)) for p, q in _lid(box, others[len(tops):], y, x, h)]


def _hobbycase_shelf_rows(slots, n):
    """The n shelves' slots (1 … slots, bottom up) spread evenly over a column's slots."""
    return [int((k + 1) * (slots + 1) / (n + 1) + 0.5) for k in range(min(n, slots))]


@recipe
def HobbyCase(box, parts):
    """A case standing open at the front (Y = 0): columns unit_w wide side by side (X), rows unit_h
    high stacked (Z), each slot between rows t high for a shelf or a set of rails. The base plate is
    the back (inner face at Y = outside_depth, drawn as seen from the front) with top and bottom
    plates and the outer side walls, all outside_depth deep, jointed into it; between columns a
    pair of back-to-back walls, unit_d deep from the back (inset 2 t from the front with
    inset_shelves). Walls and plates are drawn from the back (u = 0 / v = 0). Shelves fill the
    slots spread evenly up each column; the rest take a set of rails: one strip lying flat in the
    slot along each side wall and a shorter one along the back, sticking 2 t out into the column.
    The cover stands on the floor in front of it all (a lid)."""
    t, w, rows, uh = box.thickness, box.unit_w, box.rows, box.unit_h
    W, H, D, d = box.inside_w, box.inside_h, box.outside_depth, box.inside_depth
    starts = [sum(w[:c]) + 2 * t * c for c in range(len(w))]   # the columns' left inner faces
    slot_z = lambda r: r * uh + (r - 1) * t                      # a slot's bottom face
    back, inset = (0, -1, 0), D - d
    shelves, rails = [], []
    for c, n in enumerate(box.shelves_n):
        rows_c = _hobbycase_shelf_rows(rows - 1, n)
        shelves.append([Placement((starts[c], inset, slot_z(r)), X, Y, 1) for r in rows_c])
        for r in (r for r in range(1, rows) if r not in rows_c):
            z = slot_z(r)
            rails += [Placement((starts[c], inset, z), Y, X, -1),                       # left side
                      Placement((starts[c] + 4 * t, D, z), X, back, -1),                # back, centred
                      Placement((starts[c] + w[c], inset, z), Y, (-1, 0, 0), 1)]        # right side
    inner_walls = []
    for s in starts[1:]:   # the pair between two columns, facing them
        inner_walls += [Placement((s - 2 * t, D, 0), back, Z, -1), Placement((s, D, 0), back, Z, 1)]
    out = []
    for p in parts:
        kind = (p.record.label or "rail").split()[0]
        if kind == "shelf":
            c = int(p.record.label.split("column ")[1].split(")")[0])
            place = shelves[c].pop(0) if shelves[c] else None   # more shelves than slots
        else:
            place = {
                "base": Placement((0, D, 0), X, Z, -1),
                "cover": Placement((-t, 0, -t), X, Z, 1, lid=True),
                "bottom": Placement((0, D, 0), X, back, 1),
                "top": Placement((0, D, H), X, back, -1),
                "left": Placement((0, D, 0), back, Z, 1),
                "vertical": inner_walls.pop(0) if kind == "vertical" else None,
                "right": Placement((W, D, 0), back, Z, -1),
                "rail": rails.pop(0) if kind == "rail" and rails else None,
            }[kind]
        if place:
            out.append((p, place))
    return out


@recipe
def DrillBox(box, parts):
    """Walls round sum(sx) × sum(sy), all four drawn alike (f on the right, F on the left), on the
    bottom (none for bottom_edge e); the perforated plates in the walls' finger holes, one on top
    of each section sh but the last, the one with the size frames on top. Then the lid style's
    parts (see _lid)."""
    t, sh = box.thickness, box.sh
    x, y = sum(box.sx), sum(box.sy)
    h = sum(sh) + t * (len(sh) - 1)
    front, right, back, left = _walls_round(x, y)
    out = list(zip(parts[:4], [front, right, left, back]))
    rest = [p for p in parts[4:]]
    if box.bottom_edge != "e":
        out.append((rest.pop(0), Placement((0, 0, 0), X, Y, -1)))
    for i in range(len(sh) - 1):
        out.append((rest.pop(0), Placement((0, 0, sum(sh[:i + 1]) + i * t), X, Y, 1)))
    return out + _lid(box, rest, x, y, h)


@recipe
def PenHolderBox(box, parts):
    """Walls round x × y × h (render() turns them into inner sizes), on the bottom (none for
    bottom_edge e), the two perforated plates in the walls' finger holes: plate 1 plate1_offset
    under the top, plate 2 plate_gap under it."""
    t, x, y, h = box.thickness, box.x, box.y, box.h
    z1 = h - box.plate1_offset - t      # plate 1's underside
    front, right, back, left = _walls_round(x, y)
    place = {"front_face": front, "back_face": back, "left_side": left, "right_side": right,
             "bottom": Placement((0, 0, 0), X, Y, -1),
             "plate_1": Placement((0, 0, z1), X, Y, 1), "plate_2": Placement((0, 0, z1 - box.plate_gap), X, Y, 1)}
    return [(p, place[p.record.label]) for p in parts]


@decoration("PenHolderBox", "pen")
def penholder_pens(box):
    """Bic Cristal pens (hexagonal barrel 7.5 mm across flats, 150 mm long with the cap; thinner
    if the holes or the caps' spacing are, shorter if the box is, so a third stands out) standing
    on the bottom in about 40 % of the holes (at most 7), through both plates: half with the cap
    on top (clip and all; the tip is inside it), half tip down with the end plug on top. The ink
    in its tube shows through the translucent barrel."""
    import random
    x, y, h, cd = box.x, box.y, box.h, box.cap_diam
    rh = box.pen_diam / 2
    s = min(1.0, (rh - 0.3) / 4.33, cd / 12.6)       # 4.33: the hexagon's corner radius
    if s <= 0.1:
        return []
    L = min(150.0, 1.5 * h)
    k = L / 150
    x0, y0 = (x - (box.nx - 1) * cd) / 2, (y - (box.ny - 1) * cd) / 2
    holes = [(x0 + i * cd, y0 + j * cd) for j in range(box.ny) for i in range(box.nx)]
    holes = [(cx, cy) for cx, cy in holes if rh <= cx <= x - rh and rh <= cy <= y - rh]
    if not holes:
        return []
    rng = random.Random(len(holes))
    chosen = [rng.randrange(len(holes))]   # spread out: each the farthest from the others, give or take
    while len(chosen) < min(len(holes), 7, max(1, round(0.4 * len(holes)))):
        chosen.append(max((i for i in range(len(holes)) if i not in chosen),
                          key=lambda i: min(math.dist(holes[i], holes[j]) for j in chosen) + rng.uniform(0, 0.8 * cd)))
    out = []

    def add(kind, poly, z0, z1):
        out.extend(dict(p, decoration=kind) for p in Placement((0, 0, z0), X, Y, 1).pieces([poly], z1 - z0))

    for n, i in enumerate(chosen):
        a = math.radians(rng.uniform(-10, 10))
        off, phi = rng.uniform(0, 0.5) * (rh - 4.33 * s), rng.uniform(0, 2 * math.pi)
        cx, cy = holes[i][0] + off * math.cos(phi), holes[i][1] + off * math.sin(phi)
        disc = lambda r: Point(cx, cy).buffer(r * s, quad_segs=4)
        hexagon = Polygon([(cx + 4.33 * s * math.cos(a + j * math.pi / 3), cy + 4.33 * s * math.sin(a + j * math.pi / 3))
                           for j in range(6)])
        ink = rng.uniform(0.3, 0.8)
        if n % 2 == 0:      # the cap on top, the barrel from the bottom up into it
            top = L - 33 * k
            add("pen", hexagon.difference(disc(1.9)), 0, top)
            add("pen-cap", disc(1.4), (1 - ink) * top, top)   # the ink, at the tip end
            add("pen-cap", disc(4.9), top, L - 4 * k)
            add("pen-cap", disc(4.0), L - 4 * k, L - k)
            add("pen-cap", disc(2.8), L - k, L)
            # the clip: a flat strip standing 0.3 mm off the cap, joined to it at the top
            u = (math.cos(a), math.sin(a))
            strip = lambda r0, r1, w: Polygon([(cx + r * s * u[0] - e * w * s * u[1], cy + r * s * u[1] + e * w * s * u[0])
                                               for r, e in ((r0, -1), (r1, -1), (r1, 1), (r0, 1))])
            add("pen-cap", strip(5.2, 6.2, 1.6), L - 28 * k, L - 6 * k)
            add("pen-cap", strip(4.5, 6.2, 1.6), L - 6 * k, L - 2.5 * k)
        else:               # tip down: point, its holder, the clear cone, the barrel, the end plug
            top = 0.93 * L - 3 * k
            add("pen-tip", Point(cx, cy).buffer(0.5, quad_segs=4), 0, 1.5 * k)   # SceneKit drops a smaller one
            add("pen-tip", disc(1.0), 1.5 * k, 4 * k)
            for j, r in enumerate((1.8, 2.6, 3.4)):
                add("pen", disc(r), (4 + 3 * j) * k, (7 + 3 * j) * k)
            add("pen", hexagon.difference(disc(1.9)), 13 * k, top)
            add("pen-cap", disc(1.4), 13 * k, 13 * k + ink * (top - 13 * k))
            add("pen-cap", disc(2.9), top, top + 1.2 * k)
            add("pen-cap", disc(1.8), top + 1.2 * k, top + 3 * k)
    return out


def _gridfinity_plate(part, place):
    """(part, place, local frame) for a Gridfinity plate: its largest piece only (no pads cut from
    the grid's openings, no scrap in the dovetail notches), its etching left out (where the feet or
    the bins go), and outline pieces drawn one by one (TrayLayout's base plate) joined into loops."""
    etched = lambda p: (lambda c: c is not None and (c.red, c.green, c.blue) == (0, 255, 0))(p.params.get("rgb"))
    cuts, opens = [], []
    loops = loops_of(SimpleNamespace(pathes=[p for p in part.pathes if not etched(p)]), local_matrix(part.record), cuts)
    near = lambda a, b: math.dist(a, b) < 0.2
    while cuts:
        chain, turned = cuts.pop(), False
        while not near(chain[0], chain[-1]):
            nxt = next((c for c in cuts if near(chain[-1], c[0]) or near(chain[-1], c[-1])), None)
            if nxt is None:
                if turned:
                    break
                chain, turned = chain[::-1], True
                continue
            cuts.remove(nxt)
            chain += (nxt if near(chain[-1], nxt[0]) else nxt[::-1])[1:]
        (loops.append(chain[:-1]) if near(chain[0], chain[-1]) else opens.append(chain))
    main = max(polygons_of(loops, opens), key=lambda q: q.area)
    ring = lambda r: SimpleNamespace(path=[("M", *r[0])] + [("L", *q) for q in r[1:]], params={})
    return SimpleNamespace(record=part.record, pathes=[ring(list(r.coords)) for r in [main.exterior, *main.interiors]]), \
        place, Affine.identity()


def _gridfinity_feet(box, pads, z):
    """The feet (pads) under the floor at z, centred on the etched corner cells of the nx × ny grid
    (pitch apart, the grid margin / 2 + t out from the inner faces); at most one per corner."""
    t, p, f = box.thickness, box.pitch, box.opening - box.opening_margin
    c = -t - box.margin / 2 + (p - f) / 2
    corners = [(c + i * p, c + j * p) for i in sorted({0, box.nx - 1}) for j in sorted({0, box.ny - 1})]
    return [(pad, Placement((cx, cy, z), X, Y, -1)) for pad, (cx, cy) in zip(pads, corners)]


@recipe
def GridfinityBase(box, parts):
    """The grid plate the bins drop into lies on the floor, centred in walls round it (m clear all
    round), on the bottom; the lid style's parts close the walls at h. h = 0: the grid plate alone,
    refined: on the refined plate (its 8 loose dovetail tabs, joining it to a neighbouring base, are
    left out). panel_x and panel_y split the plates into panels, dovetailed edge to edge, and each
    wall into segments joined in line by fingers, t apart: the generator doesn't allow for that t,
    so the walls come out (segments - 1)·t longer than the floor."""
    t, h = box.thickness, box.h
    split = bool(box.panel_x and box.panel_y)
    cols = rows = 1
    if split:
        pad_x, pad_y = box.size_x - box.x * box.pitch, box.size_y - box.y * box.pitch
        cols, rows, _ = box.subdivide_grid(box.x, box.y, (box.panel_x - pad_x) // box.pitch,
                                           (box.panel_y - pad_y) // box.pitch)
    if h == 0 and box.base_type == "refined" and box.exact_size:
        parts = parts[8:]
    n = cols * rows
    grid, rest = parts[:n], parts[n:]
    walls, floor = [], []
    if h > 0 and not split:  # front, left, right, back
        walls, rest = [rest[0], rest[3], rest[1], rest[2]], rest[4:]
    if (h > 0 and box.bottom_edge != "e") or (h == 0 and box.base_type == "refined" and not split):
        floor, rest = rest[:n], rest[n:]
    if h > 0 and split:  # fronts, backs, lefts, rights
        walls, rest = rest[:2 * (cols + rows)], rest[2 * (cols + rows):]
    size = lambda segs: (sum(p.record.args[0] for p in segs[:cols]), sum(p.record.args[1] for p in segs[::cols]))
    out = []
    if walls:
        W = sum(p.record.args[0] for p in walls[:cols]) + (cols - 1) * t
        D = sum(p.record.args[0] for p in walls[2 * cols:2 * cols + rows]) + (rows - 1) * t
        k = 0
        for (o, U, side), count in zip([((0, 0, 0), X, 1), ((0, D, 0), X, -1), ((0, 0, 0), Y, -1), ((W, 0, 0), Y, 1)],
                                       (cols, cols, rows, rows)):
            pos = 0
            for p in walls[k:k + count]:
                out.append((p, Placement(_add(o, U, pos), U, Z, side)))
                pos += p.record.args[0] + t
            k += count
    else:
        W, D = size(grid)

    def tiles(segs, side):  # centred in W × D, row by row from the front left
        sx, sy = size(segs)
        y0 = (D - sy) / 2
        for r in range(rows):
            x0 = (W - sx) / 2
            for p in segs[r * cols:(r + 1) * cols]:
                out.append(_gridfinity_plate(p, Placement((x0, y0, 0), X, Y, side)))
                x0 += p.record.args[0]
            y0 += segs[r * cols].record.args[1]

    tiles(grid, 1)
    if floor:
        tiles(floor, -1)
    return out + (_lid(box, rest, W, D, h) if rest else [])


@recipe
def GridfinityDrillBox(box, parts):
    """Walls round x × y (drawn back, left, right, front: that is how the generator hands out its
    top edges), on the bottom; a shelf plate in the walls' finger holes on top of each height of sh
    but the last (the drill holes are for the user to add); the lid style's parts at the top; the
    feet (plain pads) under the bottom's etched corner cells."""
    t, x, y = box.thickness, box.x, box.y
    h = sum(box.sh) + t * (len(box.sh) - 1)
    ring = _walls_round(x, y)
    out = [(w, ring[i]) for w, i in zip(parts[:4], (2, 3, 1, 0))]
    out.append(_gridfinity_plate(parts[4], Placement((0, 0, 0), X, Y, -1)))
    rest, z = parts[5:], 0
    for d in box.sh[:-1]:
        z += d
        out.append((rest.pop(0), Placement((0, 0, z), X, Y, 1)))
        z += t
    feet = len(rest) - min(box.nx * box.ny, 4)
    out += _gridfinity_feet(box, rest[feet:], -t)
    return out + (_lid(box, rest[:feet], x, y, h) if feet else [])


@recipe
def GridfinityTrayLayout(box, parts):
    """TrayLayout's tray, columns x from the left, rows y from the back as in the layout text. Each
    line of walls is drawn as its runs of walls: the horizontal ones along +X, the vertical ones
    from the back to the front. They stand in the base plate (drawn mirrored, with its etching
    underneath, F's startWidth out from the inner faces); the feet (pads with magnet holes) go
    under its etched corner cells; then the lid style's parts."""
    t, xs, ys = box.thickness, box.x, box.y
    lx, ly = len(xs), len(ys)
    x0 = [sum(xs[:i]) + i * t for i in range(lx + 1)]           # column i's left: vertical wall line i is the t before it
    y1 = [sum(ys[j:]) + (ly - j - 1) * t for j in range(ly + 1)]  # row j's back: horizontal wall line j is the t behind it
    out, rest = [], list(parts)
    for j in range(ly + 1):
        out += [(rest.pop(0), Placement((x0[a], y1[j], 0), X, Z, -1)) for a, _ in _tray_layout_runs(box.hwalls[j])]
    for i in range(lx + 1):
        out += [(rest.pop(0), Placement((x0[i], y1[a], 0), (0, -1, 0), Z, 1))
                for a, _ in _tray_layout_runs([row[i] for row in box.vwalls])]
    w = box.edges["F"].startWidth()
    out.append(_gridfinity_plate(rest.pop(0), Placement((-w, -w, 0), X, Y, -1)))
    feet = rest[:min(box.nx * box.ny, 4)] if box.gen_pads else []
    out += _gridfinity_feet(box, feet, -t)
    lid = rest[len(feet):]
    return out + (_lid(box, lid, x0[lx] - t, y1[0], box.h) if lid else [])


def _tray_layout_runs(flags):
    """(first, end) of each run of walls along a grid line: one wall part each."""
    out, start = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            out.append((start, i))
            start = None
    return out


def _tray_layout_plate(part, local):
    """TrayLayout's base plate, its outline (drawn edge by edge, in no order and either way round)
    joined into loops, as a part of its own in the plate's local frame."""
    opens = []
    loops = loops_of(part, local, opens)
    while opens:
        chain = opens.pop(0)
        while math.dist(chain[0], chain[-1]) >= 0.2:
            i = next((i for i, o in enumerate(opens) if min(math.dist(chain[-1], o[0]), math.dist(chain[-1], o[-1])) < 0.2), None)
            if i is None:
                break
            o = opens.pop(i)
            chain += (o if math.dist(chain[-1], o[0]) < 0.2 else o[::-1])[1:]
        if math.dist(chain[0], chain[-1]) < 0.2:
            loops.append(chain[:-1])
    path = lambda l: SimpleNamespace(path=[("M", *l[0])] + [("L", *q) for q in l[1:] + l[:1]], params={})
    return SimpleNamespace(record=part.record, pathes=[path(l) for l in loops])


@recipe
def TrayLayout(box, parts):
    """TypeTray from the layout's grid: columns box.x left to right, rows box.y back to front (as in
    the text), the front's inner face at Y = 0. Each run of walls along a grid line is one wall,
    drawn from its first compartment: the lines along X from the back, then the lines along Y from
    the left (u back → front); outer walls h high, inner ones hi (their fingers, or with no floor
    their E edge, under them). Then the base plate (no floor where the layout has an X) and the lid
    style's parts on the outer walls."""
    t, sx, sy = box.thickness, box.x, box.y
    xs, ys = [-t], [-t]   # each grid line's wall: its face towards X = 0 / Y = 0
    for s in sx:
        xs.append(xs[-1] + s + t)
    for s in reversed(sy):
        ys.append(ys[-1] + s + t)
    ys = ys[::-1]         # by line, from the back
    out = []
    for j, flags in enumerate(box.hwalls):
        out += [Placement((xs[a] + t, ys[j] + t, 0), X, Z, 1) for a, _ in _tray_layout_runs(flags)]
    for i in range(len(sx) + 1):
        out += [Placement((xs[i] + t, ys[a], 0), (0, -1, 0), Z, 1)
                for a, _ in _tray_layout_runs(row[i] for row in box.vwalls)]
    out = list(zip(parts, out))
    plate = parts[len(out)]
    w = box.edges["F"].startWidth()   # the plate's outline is w out from the walls' inner faces
    out.append((_tray_layout_plate(plate, ~(plate.record.matrix * Affine.translation(w, w))),
                Placement((0, 0, 0), X, Y, -1), Affine.identity()))
    return out + _lid(box, parts[len(out):], xs[-1], ys[0], box.h)


@recipe
def TrayInsert(box, parts):
    """Only the dividers, half-lapped where they cross: those along Y (slotted from the bottom)
    after each sx, then those along X (slotted from the top) after each sy, the compartments
    counted from X = 0 and Y = 0. render() has already widened sx and sy to fill x and y; a draft
    angle slants the walls' ends outwards."""
    t = box.thickness
    out, pos = [], 0
    for s in box.sx[:-1]:
        pos += s
        out.append(Placement((pos, 0, 0), Y, Z, 1))
        pos += t
    pos = 0
    for s in box.sy[:-1]:
        pos += s
        out.append(Placement((0, pos, 0), X, Z, -1))
        pos += t
    return out


@recipe
def SlantedTray(box, parts):
    """One row of compartments sx along X, y deep: the back wall h high, drawn upside down (its f
    edge on the bottom's back F edge), the bottom (drawn from the back), the front front_height
    high, and len(sx) + 1 trapezoid sides from the back (X = 0 first) sloping down to the front."""
    t, sx, y = box.thickness, box.sx, box.y
    back, bottom, front, *sides = parts
    h = sides[0].record.args[1]
    xs, pos = [0], 0
    for s in sx:
        pos += s + t
        xs.append(pos)
    return [(back, Placement((0, y, h), X, (0, 0, -1), 1)),
            (bottom, Placement((0, y, 0), X, (0, -1, 0), 1)),
            (front, Placement((0, 0, 0), X, Z, 1))] + \
        [(p, Placement((x0, y, 0), (0, -1, 0), Z, 1)) for p, x0 in zip(sides, xs)]


@recipe
def DividerTray(box, parts):
    """Back and front (along X, both drawn from X = 0) round the side walls (Y from the front's
    inner face at 0 to the back's at L), on the bottom if any (drawn from the back: its handle
    sticks out at the front). The side walls' slots, drawn along their top edge from the back,
    lean towards the front by the slot angle; render() derived them, so they are worked out again
    here. In every slot the divider spanning all columns hangs on its tabs, centred across the slot,
    drawn from its top edge down. The per-column dividers are alternatives, left out."""
    from boxes.generators.dividertray import SlotDescription, SlotDescriptionsGenerator
    t, sx = box.thickness, box.sx
    back, front = parts[:2]
    w, h = back.record.args[:2]
    sides = [p for p in parts if (p.record.label or "").startswith("Sidepiece")]
    L = sides[0].record.args[0]
    rest = parts[2 + len(sides):]
    dividers = rest[len(rest) - 1 - 3 * len(sx):]   # the one spanning all columns, then 3 sets of one per column
    lid = rest[:len(rest) - len(dividers) - box.bottom]
    out = [(back, Placement((0, L, 0), X, Z, -1)), (front, Placement((0, 0, 0), X, Z, 1))]
    xs = ([-t] if box.left_wall else []) + ([w] if box.right_wall else [])   # the outer ones first
    pos = -t
    for s in sx[:-1]:
        pos += s + t
        xs.append(pos)
    out += [(p, Placement((x0 + t, 0, 0), Y, Z, -1)) for p, x0 in zip(sides, xs)]
    out += _lid(box, lid, w, L, h)
    if box.bottom:
        out.append((rest[len(lid)], Placement((0, L, 0), X, (0, -1, 0), 1)))
    slots = SlotDescriptionsGenerator().generate_all_same_angles(
        box.sy, t, box.Slot_extra_slack, box.Slot_depth, h, box.Slot_angle, box.Slot_radius)
    if box.outside:
        slots.adjust_to_target_length(sum(box.sy) - 2 * t)
    a = math.radians(box.Slot_angle)
    down, across = (0, -math.sin(a), -math.cos(a)), (0, -math.cos(a), math.sin(a))   # along the slot, to its front
    left = (t if box.left_wall else 0) - box.Divider_play   # the divider's tab, left of X = 0
    height = h / math.cos(a) - t * math.tan(a) - box.Divider_bottom_margin   # as the generator draws it
    # drawn by hand from its top left corner, which is the burn above the part's start
    local = ~(dividers[0].record.start * Affine.translation(0, box.burn))
    u = L
    for s in slots.descriptions:
        if isinstance(s, SlotDescription):
            # the slot's back face meets the top edge round its corner; the divider's top edge is
            # Slot_depth above the slot's bottom, its front face (its local origin) half the slack
            # in from the slot's front face
            top = _add((0, u - s.round_edge_start_correction(), h), down, max(0.0, s.width * math.tan(a)))
            o = _add(_add(top, across, (s.width + t) / 2), X, -left)
            # a negative angle makes the generator's divider too long: then it stands on the floor
            low = o[2] - height * math.cos(a) - max(0.0, t * math.sin(a))
            out.append((dividers[0], Placement(_add(o, down, min(0.0, low) / math.cos(a)), X, down, 1), local))
        u -= s.tracing_length()
    return out


def _small_parts_dividers(s, t):
    """Centres of the dividers between sections s (as fingerHolesAt places them), from the start."""
    out, pos = [], -t / 2
    for a in s[:-1]:
        pos += a + t
        out.append(pos)
    return out


@recipe
def SmallPartsTray(box, parts):
    """Sides y × h (the first drawn from the front, the second mirrored), the inner walls between the
    sx compartments (polygons from the front ramp's foot), and across them: the front panel above the
    ramp, the ramp (its top face on the sides' hole line, down from the panel to the floor at
    ramp_y), the floor, then the back ramp and panel or, one-sided, the back wall. Two-sided: a
    sliding divider across the middle of each compartment, standing in the slots of two triangular
    feet (hypotenuse on the floor, slot up) in its bottom corner notches, and the lid style's parts."""
    t, sx, y, h = box.thickness, box.sx, box.y, box.h
    x = sum(sx) + (len(sx) - 1) * t
    ramp_h = h * box.rampheight   # as in render()
    ramp_y = ramp_h / math.tan(math.radians(box.angle))
    if box.two_sided and 2 * ramp_y + 3 * t > y:
        ramp_y = (y - 3 * t) / 2
        ramp_h = ramp_y * math.tan(math.radians(box.angle))
    elif ramp_y > y - t:
        ramp_y = y - t
        ramp_h = ramp_y * math.tan(math.radians(box.angle))
    a = math.atan2(ramp_h, ramp_y)
    c, s = math.cos(a), math.sin(a)
    out = [Placement((x, 0, 0), Y, Z, 1), Placement((0, 0, 0), Y, Z, -1)]
    out += [Placement((p - t / 2, ramp_y, 0), Y, Z, 1) for p in _small_parts_dividers(sx, t)]
    if box.front_panel:
        out.append(Placement((0, 0, ramp_h), X, Z, 1))
    out += [Placement((0, ramp_y, 0), X, (0, -c, s), 1), Placement((0, ramp_y, 0), X, Y, -1)]
    if not box.two_sided:
        out.append(Placement((0, y, 0), X, Z, -1))
        return list(zip(parts, out))
    out.append(Placement((0, y - ramp_y, 0), X, (0, c, s), -1))
    if box.front_panel:
        out.append(Placement((0, y, ramp_h), X, Z, -1))
    q = list(zip(parts, out))
    rest = parts[len(out):]
    n = len(sx)
    yd, x0 = y / 2, 0.0
    for i, w in enumerate(sx):
        q.append((rest[i], Placement((x0, yd - t / 2, 0), X, Z, -1)))
        # the feet: two right triangles sharing their hypotenuse cut, from (0, 0) to (3.5 t, 3.5 t); the
        # second's outline is left open there, so the first, slot up, goes in at both ends
        o, up, down = (0, yd - 2.5 * t, 0), _norm((0, 1, 1)), _norm((0, 1, -1))
        for xf in (x0, x0 + w - t):
            q.append((rest[n + i], Placement(_add(o, X, xf), up, down, -1, keep=lambda p: p.centroid.x > p.centroid.y)))
        x0 += w + t
    return q + _lid(box, rest[2 * n:], x, y, h)


@recipe
def SmallPartsTray2(box, parts):
    """A type tray x × y (front at Y = 0) whose compartments' floors slope up to the front. Sides,
    floors and inner walls are drawn from the back, the back from X = x, the holes in front, back and
    floors at X = x - posx. Each compartment's slope (its slotted end down) rises at 45° from a gap
    between the floor boards to hi, on the divider or the front wall in front of it; the dividers
    stand on the floor boards."""
    t, sx, sy = box.thickness, box.sx, box.sy
    x = sum(sx) + (len(sx) - 1) * t
    y = sum(sy) + (len(sy) - 1) * t
    hi, r2 = box.hi, 2 ** 0.5
    ends, pos = [], 0.0   # each compartment's front face, from the back
    for s in sy:
        pos += s
        ends.append(pos)
        pos += t
    back, front = (-1, 0, 0), (0, -1, 0)
    out = [Placement((x, y, 0), back, Z, 1), Placement((0, 0, 0), X, Z, 1)]
    out += [Placement((x, y - start, 0), back, front, -1) for start in [0] + [e - hi + r2 * t for e in ends]]
    out += [Placement((x, y - p - t / 2, 0), back, Z, 1) for p in _small_parts_dividers(sy, t)]
    # a slope from its lower end's lower face, up towards the front
    out += [Placement((x, y - e + hi - t / (2 * r2), -1.5 * t / r2), back, (0, -1 / r2, 1 / r2), 1) for e in ends]
    out += [Placement((0, y, 0), front, Z, 1), Placement((x, y, 0), front, Z, -1)]
    # The inner walls' slot for the front slope opens on their front edge, at its top: the outline
    # crosses itself there and polygons_of fills it. Cut it out again.
    sl = hi / r2 + t / 2   # as in TopEdge
    a = (y, hi - r2 * t)
    b = (a[0] - (sl - t) / r2, a[1] - (sl - t) / r2)
    c = (b[0] - t / r2, b[1] + t / r2)
    notch = Polygon([a, b, c, (y, hi), (y + 1, hi + 1), (y + 1, a[1])])
    for p in _small_parts_dividers(sx, t):
        place = Placement((x - p + t / 2, y, 0), front, Z, 1)
        pieces = place.pieces
        place.pieces = lambda polys, th, pieces=pieces: pieces([q.difference(notch) for q in polys], th)
        out.append(place)
    return out


@recipe
def CompartmentBox(box, parts):
    """TypeTray's walls round x × y, drawn as seen from outside (the sides from the back, their
    cutout for the lid at the front; the holes in front and back at X = x - posx), the bottom turned
    round to match. The lid (closed) lies on the inner walls at h under the lips, which lie on the
    side walls' tops (stackable: in the Š edge's finger holes, at the same height); the single
    "Lip" also over the back. With a lip handle the lid ends at the front wall, its lip standing
    on it over the front wall; otherwise it reaches over the front wall."""
    t, sx, sy = box.thickness, box.sx, box.sy
    walls = {p.record.label: p for p in parts}
    x = walls["back"].record.args[0]
    y, H = walls["left side"].record.args[:2]
    h = walls["front"].record.args[1]
    m = box.margin_side * t
    place = {
        "back": Placement((x, y, 0), (-1, 0, 0), Z, 1),
        "front": Placement((0, 0, 0), X, Z, 1),
        "bottom": Placement((x, y, 0), (-1, 0, 0), (0, -1, 0), -1),
        "left side": Placement((0, y, 0), (0, -1, 0), Z, 1),
        "right side": Placement((x, y, 0), (0, -1, 0), Z, -1),
        "lid": Placement((m, 0 if box.handle == "lip" else -t, h), X, Y, 1, lid=True),
        "lid lip": Placement((m, 0, h + t), X, Z, 1, lid=True),
        "Lip Left": Placement((t, 0, H), Y, (-1, 0, 0), 1),
        "Lip Right": Placement((x - t, 0, H), Y, X, -1),
        None: Placement((0, y, H), (0, -1, 0), X, 1),   # the single lip, drawn by hand
    }
    for i, p in enumerate(_small_parts_dividers(sy, t)):
        place[f"inner x {i + 1}"] = Placement((x, y - p - t / 2, 0), (-1, 0, 0), Z, 1)
    for i, p in enumerate(_small_parts_dividers(sx, t)):
        place[f"inner y {i + 1}"] = Placement((x - p + t / 2, y, 0), (0, -1, 0), Z, 1)
    f = box.edges["f"].margin()   # the single lip's first edge starts at (f, f)
    return [(p, place[p.record.label]) if p.record.label else
            (p, place[None], ~(p.record.start * Affine.translation(f, f))) for p in parts]


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
            out.append((p, Placement((r, -e, h + t + 20), X, Y, 1, lid=True)))
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


# ---------------------------------------------------------------- shelves

@recipe
def BinTray(box, parts):
    """A type tray standing upright, open at the front (Y = 0): the back (x × h, the mounting holes
    at the top) at Y = y, the walls drawn from it (v = 0) to the front. The sides' front profile
    puts sh[0] at the top: each compartment has a retainer leaning out at 45° from its floor's front
    edge, its inner face along the sides' sloped edge."""
    t, sx, sh, y = box.thickness, box.sx, box.sh, box.y
    x = sum(sx) + t * (len(sx) - 1)
    h = sum(sh) + t * (len(sh) - 1)
    back, up = (0, -1, 0), (0, -1 / math.sqrt(2), 1 / math.sqrt(2))
    floors = [sum(sh[i + 1:]) + t * (len(sh) - 1 - i) for i in range(len(sh))]   # sh[i]'s floor
    place = {
        "bottom": Placement((0, y, 0), X, back, 1),
        "top": Placement((0, y, h), X, back, -1),
        "left": Placement((0, y, 0), Z, back, -1),
        "right": Placement((x, y, 0), Z, back, 1),
        "back": Placement((0, y, 0), X, Z, -1),
    }
    for i in range(len(sx) - 1):
        place[f"inner vertical {i + 1}"] = Placement((sum(sx[:i + 1]) + i * t, y, 0), Z, back, 1)
    for i in range(len(sh) - 1):
        place[f"inner horizontal {i + 1}"] = Placement((0, y, floors[i] - t), X, back, -1)
    for i in range(len(sh)):
        place[f"retainer {i + 1}"] = Placement((0, 0, floors[i]), X, up, 1)
    return place


@recipe
def CardHolder(box, parts):
    """Sides (u = Y from the open front, v = Z), the back at Y = y between them, the floor sloping
    down to the back by the angle (its finger grooves at the front, its top face meeting the back
    t up), and between the compartments the middle walls, drawn from (t, t) at the back up the floor
    towards the front. h is the full height (render() adds the slope)."""
    t, sx, y, h = box.thickness, box.sx, box.y, box.h
    a = math.radians(box.angle)
    x = sum(sx) + t * (len(sx) - 1)
    down = (0, math.cos(a), -math.sin(a))   # along the floor, front to back
    top = (0, math.sin(a), math.cos(a))     # its top face's normal
    front = _add((0, y, t), down, -y)        # its top face at the front
    out = [Placement((0, 0, 0), Y, Z, -1), Placement((x, 0, 0), Y, Z, 1),
           Placement(front, X, down, -1), Placement((0, y, 0), X, Z, -1)]
    pos = 0
    for s in sx[:-1]:
        pos += s
        out.append(Placement((pos, y + t, 0), (0, -1, 0), Z, -1))
        pos += t
    return out


@decoration("CardHolder", "cards")
def card_piles(box):
    """A pile of poker cards in each compartment (see _deck; smaller if the compartment is),
    slid down the floor against the back, between a third of a deck and a full one, red and
    blue in turn."""
    import random
    t, sx, y = box.thickness, box.sx, box.y
    a = math.radians(box.angle)
    down, top = (0, math.cos(a), -math.sin(a)), (0, math.sin(a), math.cos(a))   # as in CardHolder
    front = _add((0, y, t), down, -y)
    at = lambda z: Placement(_add(front, top, z), X, down, 1)
    rng = random.Random(len(sx))
    out, pos = [], 0
    for i, s in enumerate(sx):
        w, l = min(63.5, s - 0.5), min(88.9, y - 0.5)
        high = min(rng.uniform(6, 17), box.h - t - y * math.sin(a) - 1)
        if high > 0.5:
            out += _deck(at, pos + (s - w) / 2, y - l - 0.3, w, l, high, i % 2)
        pos += s + t
    return out


@recipe
def DiscRack(box, parts):
    """Two square sides (u = Y from the front, v = Z) and between them an L leant back by the angle
    round the discs' centre C: the lower board, its top face r·lower_factor under C, from the front
    to the rear board, whose front face is r·rear_factor behind C; the rear board stands on the
    lower one's top face (its h edge reaches below it)."""
    t, o, r, w = box.thickness, box.outer, box.disc_diameter / 2, sum(box.sx)
    a = math.radians(box.angle)
    along, up = (0, math.cos(a), -math.sin(a)), (0, math.sin(a), math.cos(a))   # the L's frame
    corner = _add(_add((0, o / 2, o / 2), along, r * box.rear_factor), up, -r * box.lower_factor)
    return [Placement((0, 0, 0), Y, Z, -1), Placement((w, 0, 0), Y, Z, 1),
            Placement(_add(corner, along, -box.lower_size), along, X, 1),
            Placement(corner, up, X, 1)]


@recipe
def DisplayShelf(box, parts):
    """Sides drawn from the back (u = 0 at Y = y; the front at Y = 0), their inner bottom at Z = 0:
    sloped tops are polygons from the outer bottom, the bottom's h edge le under it. Each shelf, from
    the sides' finger holes (its mid-plane, from the back, falling by the angle), is drawn from its
    front lip back (v = 0 at the front); the lip stands on its top face, the dividers on it from the
    back. Optional back, front and bottom walls close it."""
    t, x, y, a, sl = box.thickness, box.x, box.y, box.radians, box.sl
    le = box.edges["h"].startWidth() if box.include_bottom else 0
    hs = (sl + t) * math.sin(a) + math.cos(a) * t
    h = box.h - box.bottom_distance - box.top_distance
    side = lambda u, v: (0, y - u, v)                    # the sides' frame in world
    d = (0, -math.cos(a), -math.sin(a))                  # down the shelf, to the front
    n = (0, -math.sin(a), math.cos(a))                   # its top face's normal
    shelves, lips, dividers = [], [], {}
    for i in range(box.num):
        pv = hs - math.cos(a) * 0.5 * t + i * (h - abs(hs)) / (box.num - 0.5) + box.bottom_distance
        if a < 0:
            pv += -math.sin(a) * sl
        back = _add(side(abs(0.5 * t * math.sin(a)), pv), n, t / 2)     # its top face at the back
        front = _add(back, d, sl)
        shelves.append(Placement(front, X, tuple(-c for c in d), -1))
        lips.append(Placement(front, X, n, 1))
        pos = 0
        for j, s in enumerate(box.sx[:-1]):
            pos += s
            dividers[f"divider {j + 1} for shelf {i + 1}"] = Placement(_add(back, X, pos), d, n, -1)
            pos += t
    sides = [Placement(side(0, 0), (0, -1, 0), Z, 1), Placement(_add(side(0, 0), X, x), (0, -1, 0), Z, -1)]
    out = [(p, q, ~(p.record.matrix * Affine.translation(0, le)) if box.slope_top else None)
           for p, q in zip(parts[:2], sides)]
    place = {"back wall": Placement((0, y, 0), X, Z, -1), "front wall": Placement((0, 0, 0), X, Z, 1),
             "bottom wall": Placement((0, 0, 0), X, Y, -1), **dividers}
    for p in parts[2:]:
        label = p.record.label
        if label.startswith("shelf"):
            out.append((p, shelves.pop(0)))
        elif label.startswith("front lip"):
            out.append((p, lips.pop(0)))
        else:
            out.append((p, place[label]))
    return out


@decoration("DiscRack", "vinyl")
def vinyl_records(box):
    """Vinyl records (the disc diameter, 2 mm thick or the slits' width if thinner) standing in
    about three quarters of the slots, centred on the discs' centre and in their slot: black, a
    few fine rings where the tracks part, a coloured paper label (a third of the diameter) on
    each face and the spindle hole through it all."""
    import random
    r, o = box.disc_diameter / 2, box.outer
    th = min(2.0, box.disc_thickness - 0.2)
    c = Point(o / 2, o / 2)
    hole = c.buffer(max(0.6, 0.012 * r * 2), quad_segs=4)
    ring = lambda r0, r1: c.buffer(r1, quad_segs=24).difference(c.buffer(r0, quad_segs=24))
    rng = random.Random(len(box.sx))
    out, pos = [], 0
    for s in box.sx:
        x0 = pos + s / 2 - th / 2
        pos += s
        if rng.random() > 0.75:
            continue
        at = lambda dx, k=x0: Placement((k + dx, 0, 0), Y, Z, 1)
        label = rng.choice(("vinyl-red", "vinyl-blue", "vinyl-yellow", "label"))
        out += at(0).pieces([c.buffer(r, quad_segs=24).difference(hole)], th)
        for dx in (-0.05, th):
            tracks = [ring(r * f, r * f + 0.4) for f in sorted(rng.uniform(0.45, 0.9) for _ in range(3))]
            out += [dict(p, decoration="vinyl-groove") for p in at(dx).pieces(tracks + [ring(0.95 * r, 0.97 * r)], 0.05)]
            out += [dict(p, decoration=label) for p in at(dx).pieces([c.buffer(r / 3, quad_segs=16).difference(hole)], 0.05)]
    return out


@recipe
def SBCMicroRack(box, parts):
    """Two sides (u from the top down, v = Y; the stackable feet at u = H) with the plain base plate
    in the feet's finger holes and a shelf in each row of holes, counted from the top; the boards'
    port holes are in the first side, put on the right. (The switch holder, --switch, is not offered.)"""
    t, hp = box.thickness, box.clearance_z + box.thickness
    H = box.sbcs * hp + hp / 2
    L = box.y + 2 * box.hole_dist_edge
    sides, rest = parts[:2], parts[2:]
    down = (0, 0, -1)
    out = [(sides[0], Placement((L, 0, H), down, Y, 1)), (sides[1], Placement((0, 0, H), down, Y, -1)),
           (rest[0], Placement((0, 0, 0), X, Y, -1))]
    return out + [(p, Placement((0, 0, H - i * hp - hp / 2 - 1.5 + t / 2), X, Y, -1)) for i, p in enumerate(rest[1:])]


@decoration("SBCMicroRack", "pcb")
def raspberry_pis(box):
    """A Raspberry Pi (85 × 56, the shelves' mounting hole grid 3.5 in from its edges) on the base and
    on every shelf but the top one, as in the photo: on brass standoffs that centre its ports in the
    port hole k·hp + 15 up the side (paint_netusb_holes, drawn from the feet), Ethernet and two USB
    stacks out towards the port side at X = L; the SoC, the RAM and the GPIO header on top."""
    t, hp = box.thickness, box.clearance_z + box.thickness
    hx = box.hole_diameter + box.clearance_x + box.hole_dist_edge / 2    # as in paint_mounting_holes
    hy = box.hole_diameter + box.clearance_y + box.hole_dist_edge / 2
    gx, gy = box.hole_grid_dimension_x, box.hole_grid_dimension_y
    x0, y0, x1, y1 = hx - 3.5, hy - 3.5, hx + gx + 23.5, hy + gy + 3.5
    holes = [Point(hx + i * gx, hy + j * gy) for i in (0, 1) for j in (0, 1)]
    out = []

    def add(kind, polys, z0, z1):
        out.extend(dict(p, decoration=kind) for p in Placement((0, 0, z0), X, Y, 1).pieces(polys, z1 - z0))

    for k in range(box.sbcs):
        floor = k * hp - 1.5 + t / 2 if k else 0     # the shelf's top face (see SBCMicroRack), or the base's
        pcb = max(floor, k * hp + 15 - 8 - 1.6)       # the 16 mm USB stacks centred in the port hole
        top = pcb + 1.6
        if pcb > floor:
            add("brass", [h.buffer(2.5, quad_segs=6) for h in holes], floor, pcb)
        board = rect(x0, y0, x1, y1).buffer(-3).buffer(3, quad_segs=4)
        add("pcb", [board.difference(unary_union([h.buffer(1.35, quad_segs=6) for h in holes]))], pcb, top)
        add("steel", [rect(x1 - 21, y0 + 2.25, x1 + 2, y0 + 18.25)], top, top + 13.5)
        add("steel", [rect(x1 - 17, y0 + c - 6.6, x1 + 2, y0 + c + 6.6) for c in (29, 47)], top, top + 16)
        add("steel", [rect(x0 + 18.5, y0 + 24.5, x0 + 33.5, y0 + 39.5)], top, top + 2.4)
        add("tin", [rect(x0 + 38, y0 + 25, x0 + 48, y0 + 39)], top, top + 1.2)
        add("tin", [rect(hx + 3.5, y1 - 6, hx + 54.5, y1 - 1)], top, top + 8.5)
    return out


@recipe
def PaintStorage(box, parts):
    """End walls at X = 0 and y (u from the top down, v = Y; the stackable feet at u = h hold the
    bottom), the bottom, and the plates with the can holes where the end walls' finger holes are
    (the generator's "additional bottom" is the one near the top), all x wide from Y = -t. The two
    strips go inside the end walls under the bottom. As a drawer: front and back walls instead,
    upside down (their bottom edge joins the bottom)."""
    t, x, y, ch = box.thickness, box.x, box.y, box.canheight
    s = box.edges["s"].settings
    h = ch - s.height - s.holedistance + t
    down = (0, 0, -1)
    plate = lambda u: Placement((0, -t, h - u + t / 2), X, Y, -1)   # finger holes' mid-plane u from the top
    out = [Placement((0, 0, h), down, Y, -1), Placement((y, 0, h), down, Y, 1),
           Placement((0, -t, -t), down, Y, 1), Placement((y, -t, -t), down, Y, -1),
           Placement((0, 0, 0), X, Y, -1)]
    if box.drawer:
        return out + [Placement((0, 0, h), X, down, -1), Placement((0, x - 2 * t, h), X, down, 1)]
    out.append(plate(ch * 2 / 3 - 2 * t))
    if box.additional_bottom:
        out.append(plate(ch / 6 - t / 2))
    if box.additional_top:
        out.append(plate(ch - ch / 6 - t))
    return out


@decoration("PaintStorage", "paint")
def paint_bottles(box):
    """Dropper bottles of hobby paint (the can diameter less 1 mm, the can height tall) standing
    on the bottom in about four fifths of the holes, through the plates: the paint showing in the
    body, a white label round it, a stepped shoulder, the white dropper tip and a black cap. Where
    the holes are comes from replaying the plates' callback with its holes recorded."""
    import random
    if box.drawer:
        return []
    t, R, H = box.thickness, box.candiameter / 2 - 1, box.canheight
    if R < 2:
        return []
    at, holes = [(0, 0)], []
    box.moveTo = lambda x, y, *a: at.append((at[-1][0] + x, at[-1][1] + y))
    box.hole = lambda x, y, r=0.0, *a, **kw: holes.append((at[-1][0] + x, at[-1][1] + y))
    try:
        box.paintholes()
    finally:
        del box.moveTo, box.hole
    rng = random.Random(len(holes))
    out = []
    for u, v in holes:
        if rng.random() > 0.8:
            continue
        c = Point(u, v - t)                         # the plates lie from Y = -t
        paint = rng.choice(("paint-red", "paint-blue", "paint-yellow", "paint-green", "paint-white", "paint-black"))

        def add(kind, r, a, b):                    # r and the heights as fractions of R and H
            out.extend(dict(p, decoration=kind) for p in Placement((0, 0, a * H), X, Y, 1)
                       .pieces([c.buffer(r * R, quad_segs=12)], (b - a) * H))

        add(paint, 1, 0, 0.12)
        add("label", 1.02, 0.12, 0.55)
        add(paint, 1, 0.55, 0.62)
        add(paint, 0.85, 0.62, 0.66)
        add(paint, 0.65, 0.66, 0.70)
        add("paint-white", 0.35, 0.70, 0.76)        # the dropper tip
        add("tin", 0.6, 0.76, 1.0)                  # the cap
    return out


@recipe
def SpicesRack(box, parts):
    """The back hangs on the wall (front face at Y = D, the full depth of the shelves, so their
    scalloped fronts reach Y = 0), the shelves out from it, a row every box.h, each on a support
    between every two cans: from the back, its quarter round cut at the front bottom. Feet, when
    asked for, take the bottom row's supports' places and reach the floor (the spare supports are
    left out). Supports drawn in the shelves' holes are parts of their own."""
    t, n, H = box.thickness, box.numx, box.h
    D = box.hole_distance + box.hole_length + box.space / 2
    drawn = [p for p in parts if p.record.primitive]
    loose = [p for p in parts if not p.record.primitive]
    feet = loose[len(loose) - (n - 1):] if box.feet else []
    supports = loose[:len(loose) - len(feet)]
    top = lambda i: (i + 1) * H - H / 2 + t / 2              # row i's shelf, its top face
    bracket = lambda i, j: Placement((j * (box.diameter + box.space) - t / 2, D, top(i) - t - (H - t) / 2),
                                     (0, -1, 0), Z, -1)
    out = [(drawn[-1], Placement((0, D, 0), X, Z, -1))]
    out += [(p, Placement((0, D, top(i)), X, (0, -1, 0), 1)) for i, p in enumerate(drawn[:-1])]
    rows = range(1 if feet else 0, box.numy)
    out += list(zip(supports, [bracket(i, j) for i in rows for j in range(1, n)]))
    # a foot's f edge runs down the back from the bottom shelf (u), its body out from v = t
    return out + [(p, Placement(_add(bracket(0, j).origin, Z, (H - t) / 2), (0, 0, -1), (0, -1, 0), -1),
                   ~(p.record.start * Affine.translation(0, t))) for j, p in enumerate(feet, 1)]


@decoration("SpicesRack", "jar")
def spice_jars(box):
    """A spice jar (the can diameter, 1.6 times as long) in about three quarters of the holes,
    lying out of them tilted up by the rack's angle (adjacent rows d + space apart across their
    axes): the top of its bottom against the back, its underside on the hole's front edge, so its
    bottom crosses the shelf just in front of the hole's back edge. Black tins with a label round
    them and a lid, or spices in glass under a wooden lid, in turn by chance."""
    import random
    t, H, r = box.thickness, box.h, box.diameter / 2 - 0.5
    phi = math.radians(box.angle)
    c, s = math.cos(phi), math.sin(phi)
    D = box.hole_distance + box.hole_length + box.space / 2           # see SpicesRack
    L = 1.6 * box.diameter
    axis, across = (0, -c, s), (0, s, c)                               # out of the rack; up the bottom, to the back
    by = r * s + 0.5                                                    # the bottom's centre, from the back
    sf = (box.hole_distance + box.hole_length - by - r * s) / c        # along the underside to the front edge
    rng = random.Random(box.numx * box.numy)
    out = []
    for i in range(box.numy):
        z = (i + 1) * H - H / 2 + t / 2                                 # the shelf's top face
        bottom = (0, D - by, z + r * c - sf * s)
        for j in range(box.numx):
            if rng.random() > 0.75:
                continue
            out += _jar(bottom, axis, X, ((box.diameter + box.space) * (j + 0.5), 0), r, L, rng)
    return out


@recipe
def StackableBin(box, parts):
    """One compartment row of BinTray standing on stackable feet: sides (u = Y from the open front,
    v = Z), the back at Y = d, the bottom drawn from the back, the retainer leaning out at 45° from
    its front edge, dividers between the compartments. The stackable edges' stabilizer strips are
    glued inside their walls on the bottom, as in Crate (the optional label strip is not drawn, see
    bundle-runtime.sh)."""
    t, sx, d, h = box.thickness, box.sx, box.d, box.h
    x = sum(sx) + t * (len(sx) - 1)
    walls = {  # wall: (its placement, its strip's: corner, along, side, length)
        "bottom": (Placement((0, d, 0), X, (0, -1, 0), 1), None),
        "back": (Placement((0, d, 0), X, Z, -1), ((0, d, 0), X, 1, x)),
        "retainer": (Placement((0, 0, 0), X, (0, -1 / math.sqrt(2), 1 / math.sqrt(2)), 1), None),
        "left": (Placement((0, 0, 0), Y, Z, -1), ((0, 0, 0), Y, 1, d)),
        "right": (Placement((x, 0, 0), Y, Z, 1), ((x, 0, 0), Y, -1, d)),
    }
    dividers = [Placement((sum(sx[:i + 1]) + i * t, 0, 0), Y, Z, 1) for i in range(len(sx) - 1)]
    out, strip = [], None
    for p in parts:
        label = p.record.label
        if label in walls:
            place, strip = walls[label]
            out.append((p, place))
        elif label == "divider":
            out.append((p, dividers.pop(0)))
        elif label is None and strip:
            corner, along, side, length = strip
            out.append((p, Placement(_add(corner, along, (length - p.record.args[0]) / 2), along, Z, side)))
    return out


@recipe
def StorageRack(box, parts):
    """Open at the front (Y = 0): the sides (the second drawn from the back), the back at Y = d, and
    at each level between the compartments sh a pair of rails along the sides (the second from the
    back). The two full floors close the bottom and the top; with an e edge there, the floor is
    the first (last) level's instead, across the back."""
    t, sh, x, d, b, e = box.thickness, box.sh, box.x, box.depth, box.bottom_edge, box.top_edge
    h = sum(sh) + t * (len(sh) - 1)
    levels = [sum(sh[:i + 1]) + (i + 1) * t for i in range(len(sh) - 1)]   # the top faces
    floors = [Placement((0, 0, levels.pop(0) if b == "e" else 0), Y, X, 1),
              Placement((0, 0, levels.pop() if e == "e" else h), Y, X, 1 if e == "e" else -1)]
    rails = [q for z in levels for q in (Placement((0, 0, z), Y, X, 1), Placement((x, d, z), (0, -1, 0), (-1, 0, 0), 1))]
    out = list(zip(parts[:2], [Placement((0, 0, 0), Y, Z, -1), Placement((x, d, 0), (0, -1, 0), Z, -1)]))
    out += list(zip(parts[2:4], floors)) + list(zip(parts[4:-1], rails))
    return out + [(parts[-1], Placement((0, d, 0), X, Z, -1))]


@recipe
def StorageShelf(box, parts):
    """Open at the front (Y = 0), x deep, the compartments sy across (X) and sh up: the sides (the
    right one drawn from the back), the back at Y = x, the floor, top and inner horizontals drawn
    from the front (the horizontals' slots, sy reversed, are at their v = 0 at X = W), the inner
    verticals from the back, and the retainers standing on each level's front edge. A lid style's
    tops lie on the walls, their u across (drawLid draws them y × x, see bundle-runtime.sh), the
    edge meeting the back's (hinge, slide-in groove) at the back. The v edge's cabinet hinges (style
    inside) as in HingeBox, on one axis t above the back's top at its outer face, where the lid's
    top face meets its cut edge: the back's eye pieces in the even slots hang down, their tab through
    the back; the lid's in the odd ones lie along it, their tab down through the lid."""
    t, sy, sh, x = box.thickness, box.sy, box.sh, box.x
    W = sum(sy) + t * (len(sy) - 1)
    h = sum(sh) + t * (len(sh) - 1)
    levels = [sum(sh[:i]) + i * t for i in range(len(sh))]   # top faces: the floor, then the horizontals
    back = (0, -1, 0)
    place = {
        "left": Placement((0, 0, 0), Y, Z, -1),
        "right": Placement((W, x, 0), back, Z, -1),
        "bottom": Placement((0, 0, 0), Y, X, 1),
        "top": Placement((0, 0, h), X, Y, 1, lid=True) if box.top_edge == "c" else Placement((0, 0, h), Y, X, -1),
        "back": Placement((0, x, 0), X, Z, -1),
    }
    for i in range(1, len(sh)):
        place[f"inner horizontal {i}"] = Placement((W, 0, levels[i] - t), Y, (-1, 0, 0), 1)
    for i in range(len(sy) - 1):
        place[f"inner vertical {i + 1}"] = Placement((sum(sy[:i + 1]) + i * t, x, 0), back, Z, -1)
    for i, z in enumerate(levels):
        place[f"retainer {i + 1}"] = Placement((0, 0, z), X, Z, 1)
    at = lambda z: Placement((0, 0, z), X, Y, 1, lid=True)
    lids = {"E": [at(h + t), at(h)], "i": [Placement((0, x, h), X, back, -1, lid=True)], "L": [at(h)],
            "k": [at(h), Placement((W, 0, h), (-1, 0, 0), Y, -1, lid=True)],
            "v": [Placement((0, x, h), X, back, -1, lid=True)]}.get(box.top_edge, [])
    labels = [p.record.label for p in parts]
    first = max(i for i, l in enumerate(labels) if l in ("left", "right", "bottom") or (l or "").startswith("inner horizontal")) + 1
    out = [(p, place[p.record.label]) for p in parts if p.record.label in place]
    hs = box.edges["v"].settings
    if box.top_edge == "v" and hs.style == "inside":
        e, p, sp, n = hs.eye, hs.play, hs.spacing, hs.eyes_per_hinge
        frames = _eye_frames(parts[labels.index("lid top") + 1:labels.index("back")], e)
        width = (t + p) * n + p + 2 * sp
        hn = min(hs.hinges, int(W // width))
        starts = [(W - width) / 2] if hn == 1 else [j * (width + (W - hn * width) / (hn - 1)) for j in range(hn)]
        eye = lambda q: any(Polygon(r).contains(Point(0, e)) for r in q.interiors)
        for start in starts:
            for i in range(n):
                if not frames:
                    break
                axis = (start + sp + p + i * (t + p) + t / 2, x + t, h + t)
                U, V = (Y, (0, 0, -1)) if i % 2 == 0 else (Z, back)
                origin = _add(_add(axis, V, -e), _cross(U, V), -t / 2)
                part, local = frames.pop(0)
                out.append((part, Placement(origin, U, V, 1, keep=eye, lid=i % 2 == 1), local))
    return out + list(zip(parts[first:labels.index("back")], lids))


def _winerack_layout(box):
    """The panel's honeycomb, from replaying its callback with the drawing calls recorded: the
    walls' finger holes (x, y, angle in radians) and the bottle holes (x, y, r), panel coordinates."""
    at, walls, holes = [], [], []
    box.moveTo = lambda x, y, *a: at.append((x, y))
    box.hole = lambda x, y, r=0.0, *a, **kw: holes.append((at[0][0] + x, at[0][1] + y, r))
    box.hexFingerHoles = lambda x, y, l, angle=90: walls.append((at[0][0] + x, at[0][1] + y, math.radians(angle)))
    try:
        box.wallCB()
    finally:
        del box.moveTo, box.hole, box.hexFingerHoles
    return walls, holes


@recipe
def WineRack(box, parts):
    """Standing on its edge, the bottles going in along Y: the panel with the bottle holes and the
    finger holes (u, v = X, Z) at Y = 0, the back (finger holes only) at Y = h, the front cover
    (bottle holes only) on the panel, and between the panel and the back a wall in every pair of
    the honeycomb's finger holes (see _winerack_layout), h deep."""
    t, h = box.thickness, box.h
    out = [Placement((0, 0, 0), X, Z, 1), Placement((0, h, 0), X, Z, -1), Placement((0, -t, 0), X, Z, 1)]
    for x, y, a in _winerack_layout(box)[0]:
        U = (math.cos(a), 0, math.sin(a))
        N = (-math.sin(a), 0, math.cos(a))   # U × Y
        mid = (x + box.delta * U[0], 0, y + box.delta * U[2])
        out.append(Placement(_add(mid, N, -t / 2), U, Y, 1))
    return out


@decoration("WineRack", "bottle")
def wine_bottles(box):
    """Bordeaux bottles (75 mm across, 300 long; thinner if the holes are, and shorter with them)
    in about two thirds of the holes, lying on the front cover's hole, their bottom against the
    back, the neck out of the front: dark green or amber glass, a paper label round the body, the
    shoulder in steps, a red or gold capsule over the neck."""
    import random
    t, h = box.thickness, box.h
    holes = _winerack_layout(box)[1]
    rng = random.Random(len(holes))
    out = []
    for i, (cx, cz, hr) in enumerate(holes):
        R = min(37.5, hr - 1)
        if R < 5 or rng.random() > 0.65:
            continue
        k = R / 37.5
        cz -= hr - R                               # resting on the hole's bottom
        glass = rng.choice(("bottle", "bottle", "bottle-amber"))
        capsule = rng.choice(("capsule-red", "capsule-gold"))

        def add(kind, r, a, b):                    # from a to b mm along the bottle, from its bottom
            out.extend(dict(p, decoration=kind) for p in Placement((0, h - 0.5 - a * k, 0), X, Z, 1)
                       .pieces([Point(cx, cz).buffer(r * k, quad_segs=8)], (b - a) * k))

        add(glass, 37.5, 0, 70)
        add("label", 37.8, 70, 160)
        add(glass, 37.5, 160, 215)
        steps = 6
        for j in range(steps):                      # the shoulder, 37.5 down to the neck's 15
            r = 15 + 22.5 * math.cos(math.pi / 2 * (j + 0.5) / steps)
            add(glass, r, 215 + 5 * j, 220 + 5 * j)
        add(capsule, 15.5, 245, 297)
        add(capsule, 16.0, 297, 300)
    return out


# ---------------------------------------------------------------- wall mounted

# The wall is the plane Y = t behind the back plate, whose front (inner) face is at Y = 0; what hangs
# on it reaches out to the front, -Y. A side's wall edge (b: its fingers set back by t) is drawn on its
# inner frame's line, the back plate's front face.

@recipe
def WallConsole(box, parts):
    """The back plate (x × h), sides and dividers out from it (trapezoids drawn from the top, u
    down, v out from the wall: top_depth at the top, bottom_depth at the bottom), and the front
    plate on their slanted edges, from the bottom up."""
    t, sx, h, td, bd = box.thickness, box.sx, box.h, box.top_depth, box.bottom_depth
    x = sum(sx) + t * (len(sx) - 1)
    down, out = (0, 0, -1), (0, -1, 0)
    sides = [Placement((0, 0, h), down, out, 1)]
    pos = 0
    for s in sx[:-1]:
        pos += s
        sides.append(Placement((pos, 0, h), down, out, -1))
        pos += t
    sides.append(Placement((x, 0, h), down, out, -1))
    return [Placement((0, 0, 0), X, Z, -1), Placement((0, -bd, 0), X, (0, bd - td, h), 1)] + sides


@recipe
def WallHook(box, parts):
    """The hook's two sides (drawn with the wall edge at u = 0, its fingers through the back plate
    to the wall; v up, the hook at the bottom opening upwards) either side of the back plate (w
    wide, its flange at the top), a strip lying across the hook's bottom (10 mm out, ht / 2 up) and
    one standing in its tip."""
    t, w, ht, hid = box.thickness, box.width, box.hook_thickness, box.hook_inside_diameter
    total, ro = hid + 2 * ht, hid / 2 + ht
    out = (0, -1, 0)
    m = box.edges["b"].margin()
    return [(parts[0], Placement((0, t, 0), out, Z, 1), _from_margin(parts[0], m)),
            (parts[1], Placement((w, t, 0), out, Z, -1), _from_margin(parts[1], m)), (parts[2], Placement((0, 0, 0), X, Z, -1)),
            (parts[3], Placement((0, t - (total - ht / 2) + t / 2, ro - ht / 2), X, Z, 1)),
            (parts[4], Placement((0, t - 10, ht / 2 - t / 2), X, out, -1))]


@recipe
def WallCaliper(box, parts):
    """Like WallHook: the two sides (the wall edge at u = 0) either side of the back plate."""
    t, w = box.thickness, box.width
    out, m = (0, -1, 0), box.edges["b"].margin()
    return [(parts[0], Placement((0, t, 0), out, Z, 1), _from_margin(parts[0], m)),
            (parts[1], Placement((w, t, 0), out, Z, -1), _from_margin(parts[1], m)), (parts[2], Placement((0, 0, 0), X, Z, -1))]


@recipe
def WallPinRow(box, parts):
    """Sides and supports share one frame: the wall edge at u = 0 (Y = 0), v up. The front plate
    leans back by the angle, its inner face on the line through T (where the sides' bottom turns up
    into their front edge) along e; the back plate parallel to it 3t behind; the pin strip between
    them, square to both, 2t up them, its pins out through the front plate."""
    t, h, x, n = box.thickness, box.h, box.x, box.hooks
    a = math.radians(box.angle)
    hd, e = (0, -math.cos(a), math.sin(a)), (0, math.sin(a), math.cos(a))   # out of the plates, up them
    T = (0, -(math.sin(a) * h + 4 * t * math.cos(a)), 4 * t * math.sin(a))
    out = (0, -1, 0)
    sides = [Placement((0, 0, 0), out, Z, 1)] + \
        [Placement((i * x / (n - 1) - t / 2, 0, 0), out, Z, -1) for i in range(1, n - 1)] + [Placement((x, 0, 0), out, Z, -1)]
    m = box.edges["a"].margin()
    return [(parts[0], Placement(_add(T, e, 1.5 * t), X, tuple(-c for c in hd), 1)),
            (parts[1], Placement(T, X, e, 1)), (parts[2], Placement(_add(T, hd, -4 * t), X, e, 1))] + \
        [(p, q, _from_margin(p, m)) for p, q in zip(parts[3:], sides)]


@recipe
def WallPlaneHolder(box, parts):
    """Two sides on the wall (Y = 0; u out from it, v up) holding between them the bottom the
    plane stands on, two back strips it leans on (t off the wall) and the holder over its front."""
    t, w, l, h, hl = box.thickness, box.width, box.length, box.height, box.hold_length
    out = (0, -1, 0)
    return [Placement((0, 0, 0), out, Z, 1), Placement((w, 0, 0), out, Z, -1),
            Placement((0, -2 * t, 2 * t), X, out, 1),
            Placement((0, -t, 2 * t), X, Z, 1), Placement((0, -t, 2 * t + 0.75 * l), X, Z, 1),
            Placement((0, -(2 * t + h), 2 * t + l - hl), X, Z, 1)]


@recipe
def WallEdges(box, parts):
    """The four sample walls of the wall edge types, standing in a row as on the sheet."""
    return [Placement((i * 70, 0, 0), X, Z, 1) for i in range(len(parts))]


@recipe
def WallRack(box, parts):
    """The back wall (its front face at Y = y; u = 0 on the side lips' mid-plane, X = -t/2) and a
    shelf in each section sh, its bottom on the section's bottom: the front lip and the two side
    lips (trapezoids from the front, front_height down to back_height) stand on it, holding it in
    their h (or F) edges."""
    t, x, y, fh, sh = box.thickness, box.x, box.y, box.wall_height, box.sh
    bh = fh * box.back_height
    if box.outside:
        x, y = box.adjustSize(x, "h", "f"), box.adjustSize(y)
    place = {"back wall": Placement((-t / 2, y, 0), X, Z, -1)}
    pos = 0
    for i, s in enumerate(sh):
        z = pos + t                       # the shelf's top face
        place.update({f"shelf {i + 1}": Placement((0, 0, z), X, Y, -1),
                      f"front lip {i + 1}": Placement((0, 0, z), X, Z, 1),
                      f"right lip {i + 1}": Placement((x, 0, z), Y, Z, 1),
                      f"left lip {i + 1}": Placement((0, 0, z), Y, Z, -1)})
        pos += s
    return place


@recipe
def WallStairs(box, parts):
    """Profile walls across (drawn from the front, u = Y, the wall at Y = y; the outer ones outside
    the platforms' h edges, the inner ones in their holes), the platforms on their stepped tops,
    sh[i] high from the front to the back, and the brace at the bottom of the back."""
    t, sx, sy, sh, x, y = box.thickness, box.sx, box.sy, box.sh, box.x, box.y
    out = [Placement((0, sum(sy[:i]), sh[i]), X, Y, 1) for i in range(len(sy))]
    if box.braceheight:
        out.append(Placement((0, y - t, 0), X, Z, -1))
    out.append(Placement((0, 0, 0), Y, Z, -1))
    pos = 0
    for s in sx[:-1]:
        pos += s
        out.append(Placement((pos, 0, 0), Y, Z, 1))
        pos += t
    return out + [Placement((x, 0, 0), Y, Z, 1)]


@recipe
def WallTypeTray(box, parts):
    """TypeTray with its back on the wall (Y = y): the back seen from outside (its holes mirrored),
    its C and c edges over the sides' wall joints, the right side drawn from the back; the inner
    y walls are trapezoids from the front with all_mounts."""
    t, sx, sy, h = box.thickness, box.sx, box.sy, box.h
    x = sum(sx) + t * (len(sx) - 1)
    y = sum(sy) + t * (len(sy) - 1)
    out = [Placement((0, 0, 0), X, Z, 1), Placement((x, y, 0), (-1, 0, 0), Z, 1)]
    if box.bottom_edge != "e":
        out.append(Placement((0, 0, 0), X, Y, -1))
    pos = 0
    for s in sy[:-1]:
        pos += s
        out.append(Placement((0, pos, 0), X, Z, -1))
        pos += t
    out += [Placement((0, 0, 0), Y, Z, -1), Placement((x, y, 0), (0, -1, 0), Z, -1)]
    pos = 0
    for s in sx[:-1]:
        pos += s
        out.append(Placement((pos, 0, 0), Y, Z, 1))
        pos += t
    return list(zip(parts, out))


def _right_triangles(part, leg, t, margin=0.0):
    """rectangularTriangle(…, num=n) draws its triangles in one part, nested in pairs (every other
    one turned half round), their two legs fingered. For each: (frame, keep) placing it alone, as
    drawn first: the right angle at local (0, 0), one leg (leg long) along -u, the other along +v,
    their fingers out of the triangle; a wall edge on the second leg reaches margin past them."""
    local = local_matrix(part.record)
    out = []
    for q in polygons_of(loops_of(part, local)):
        u0, v0, u1, v1 = q.bounds
        if v0 < -t / 2:     # its fingers below: the right angle at the bottom right, as drawn
            frame = Affine.translation(-(u1 - 0.1 - t - margin), -(v0 + t))
        else:               # turned half round
            frame = Affine.scale(-1, -1) * Affine.translation(-(u1 - 0.1 - leg), -(v1 - t))
        out.append((frame * local, lambda p: abs(p.bounds[2] - t - 0.1 - margin) < 1 and abs(p.bounds[1] + t) < 1))
    return out


def _from_margin(part, margin):
    """The part's local frame for a part drawn from moveTo(margin) of its wall edge: as on a plain
    wall (margin 0), whatever the wall system's hooks need."""
    return Affine.translation(-margin, 0) * local_matrix(part.record)


def _braced_top(box, parts, depth, xs):
    """WallSlottedHolder and WallChiselHolder: the back plate on the wall, the slotted top over its
    top edge (from its slotted front, depth deep), and under it a triangular brace centred on each
    of xs (see _right_triangles): their f leg under the top, their b leg on the back plate."""
    t, h = box.thickness, box.h
    back, top, braces = parts[:3]
    out = [(back, Placement((0, 0, 0), X, Z, -1)), (top, Placement((0, -depth, h), X, Y, 1))]
    for (frame, kept), xc in zip(_right_triangles(braces, depth, t, box.edges["b"].margin()), xs):
        out.append((braces, Placement((xc - t / 2, 0, h), Y, (0, 0, -1), -1, keep=kept), frame))
    return out


@recipe
def WallSlottedHolder(box, parts):
    n, wt = box.number, box.tool_width
    d = min(2 * box.thickness, (wt - box.slot_width) / 4)
    return _braced_top(box, parts, box.additional_depth + box.slot_depth,
                       [i * wt + d for i in range(n + 1) if box.brace(i)])


@recipe
def WallChiselHolder(box, parts):
    n, wt = box.number, box.tooldiameter
    d = min(2 * box.thickness, (wt - box.holediameter) / 4)
    return _braced_top(box, parts, box.depth,
                       [d] + [i * wt for i in range(1, n) if box.brace(i)] + [n * wt - d])


@recipe
def WallPliersHolder(box, parts):
    """The back plate on the wall (h_t high), braces out from it (drawn with the wall at u = t, the
    back plate's front face at u = 2t, v up from their bottom tip): the outer two hold the front
    bar in their h edges, the inner ones in its holes (centred where frontCB puts them). The front
    bar hangs at the top, y - t to y out from the back plate."""
    t, sx, y, h, ht = box.thickness, box.sx, box.y, box.h, box.h_t
    x = sum(sx) + (len(sx) - 1) * t
    out = (0, -1, 0)
    braces = [Placement((0, 2 * t, 0), out, Z, 1), Placement((x, 2 * t, 0), out, Z, -1)]
    braces += [Placement((sum(sx[:i + 1]) + i * t - t / 2, 2 * t, 0), out, Z, -1) for i in range(len(sx) - 1)]
    m = box.edges["b"].margin()
    return [(parts[0], Placement((0, -(y - t), ht - h), X, Z, 1)), (parts[1], Placement((0, 0, 0), X, Z, -1))] + \
        [(p, q, _from_margin(p, m)) for p, q in zip(parts[2:], braces)]


@recipe
def WallWrenchHolder(box, parts):
    """Two sides from their slotted front (u = 0, depth out) to the wall joint, either side of the
    back plate's inner width x - 2t (its d edges' holes just outside it)."""
    t, x, d = box.thickness, box.x, box.depth
    return [Placement((0, -d, 0), Y, Z, -1), Placement((x - 2 * t, -d, 0), Y, Z, 1), Placement((0, 0, 0), X, Z, -1)]


@recipe
def WallStackableBin(box, parts):
    """Sides from the front (u = Y; v up, the stackable feet holding the bottom), the back on the
    wall behind them (Y = y), the bottom drawn from the back. The sides' front edge (j) runs from
    the bottom's front edge out at the angle to the label's foot, w out and front·h up: the slope
    lies on it, the label stands on the slope's top. Stabilizer strips as in StackableBin."""
    t, sx, y, h = box.thickness, box.sx, box.y, box.h
    x = sum(sx) + t * (len(sx) - 1)
    a, f = math.radians(box.angle), box.front
    w = h * f * math.tan(a)
    walls = {  # wall: (its placement, its strip's: corner, along, side, length)
        "bottom": (Placement((0, y, 0), X, (0, -1, 0), 1), None),
        "slope": (Placement((0, 0, 0), X, (0, -math.sin(a), math.cos(a)), 1), None),
        "label": (Placement((0, -w, f * h), X, Z, 1), None),
        "back": (Placement((0, y, 0), X, Z, -1), None),
        "left side": (Placement((0, 0, 0), Y, Z, -1), ((0, 0, 0), Y, 1, y)),
        "right side": (Placement((x, 0, 0), Y, Z, 1), ((x, 0, 0), Y, -1, y)),
    }
    dividers = [Placement((sum(sx[:i + 1]) + i * t, 0, 0), Y, Z, 1) for i in range(len(sx) - 1)]
    out, strip = [], None
    for p in parts:
        label = p.record.label
        if label in walls:
            place, strip = walls[label]
            out.append((p, place))
        elif label == "dividers":
            out.append((p, dividers.pop(0)))
        elif label is None and strip:
            corner, along, side, length = strip
            out.append((p, Placement(_add(corner, along, (length - p.record.args[0]) / 2), along, Z, side)))
    return out


@recipe
def WallHopper(box, parts):
    """The sides (polygons: the wall at u = 0, the back on it up to u = t, v up from their bottom
    line; their h edges hold the panels 2t in) and dividers (the same frame, v from the bottom's
    top face), the back between them, the bottom from it (its top face 2t up) to the dispenser's
    flat front, the slope rising from there at the angle, the label standing on it, and the
    hopper's front panel, hd in front of the back, up to the top. render() works out the
    dispenser's sizes; this does it again."""
    t, sx, h, hd, dd, dh = box.thickness, box.sx, box.h, box.hopper_depth, box.dispenser_depth, box.dispenser_height
    x = sum(sx) + t * (len(sx) - 1)
    sr = min(box.slope_ratio, 0.999)
    lr = min(box.label_ratio, 0.999) if box.label else 0
    a = max(0, min(box.slope_angle, math.degrees(math.atan(dd / (dh * sr)))))
    if sr + lr >= 1:
        sr, lr = sr / (sr + lr) * 0.95, lr / (sr + lr) * 0.95
    a = math.radians(a)
    df = dd - dh * sr * math.tan(a)
    sl = dh * sr / math.cos(a)
    side = lambda u, v: (0, t - u, v)          # the sides' frame
    foot = (t + hd + df, 2 * t)                # the slope's inner foot, on the bottom's front
    top = (foot[0] + sl * math.sin(a), foot[1] + sl * math.cos(a))
    out = [Placement(side(t, 2 * t), X, (0, -1, 0), 1),
           Placement(side(*foot), X, (0, -math.sin(a), math.cos(a)), 1)]
    if box.label:
        out.append(Placement(side(*top), X, Z, 1))
    out += [Placement(side(t, 2 * t), X, Z, -1), Placement(side(hd + t, dh + 2 * t), X, Z, 1),
            Placement(side(0, 0), (0, -1, 0), Z, 1), Placement(_add(side(0, 0), X, x), (0, -1, 0), Z, -1)]
    pos = 0
    for s in sx[:-1]:
        pos += s
        out.append(Placement(_add(side(0, 2 * t), X, pos), (0, -1, 0), Z, -1))
        pos += t
    return out


@recipe
def RollHolder(box, parts):
    """The back plate on the wall (u = X, v up; its callback's frame r in from its corner), the two
    arms standing out of it (drawn with u up, v out, the plate's face at v = t), w apart, and
    outside each arm a brace lying flat under the axle (see _right_triangles): one leg along the
    plate, one along the arm. Two plates instead of one (screwed, not one_piece): the second turned
    to the right (drawn mirrored). The arms have no hole for the axle: the two rings, drawn last
    (U-shaped, round outside as the arm's tip), are glued on the arms' inner faces round the tip,
    open upwards, and the axle is laid in them. (bridge.RollHolder merges boxes.py's RollHolder,
    walltype screws, and WallRollHolder.)"""
    t, w, d, a, h = box.thickness, box.width, box.diameter, box.axle, box.height
    x0, x1 = h / 4 + t / 2 - 3 * t, h / 4 + t / 2 + t - 3 * t + w     # the arms' mid-planes
    zm = h - 3 * t - a / 2                                            # the braces', and the axle's centre
    out = (0, -1, 0)
    two = box.walltype == "screws" and not box.one_piece
    sides, braces, plates = parts[:2], parts[2], parts[3:5 if two else 4]
    margin = 0 if box.walltype == "screws" else box.edges["B"].margin()   # the arms drawn from moveTo(margin)
    arm = lambda p: Affine.translation(0, -margin) * local_matrix(p.record)
    items = [(sides[0], Placement((x0 - t / 2, t, 0), Z, out, 1), arm(sides[0])),
             (sides[1], Placement((x1 - t / 2, t, 0), Z, out, 1), arm(sides[1]))]
    corners = [Placement((x0 - t / 2, 0, zm + t / 2), X, out, 1), Placement((x1 + t / 2, 0, zm - t / 2), (-1, 0, 0), out, 1)]
    for (frame, kept), q in zip(_right_triangles(braces, h / 4, t), corners):
        q.keep = kept
        items.append((braces, q, frame))
    if len(plates) == 1:
        items.append((plates[0], Placement((0, 0, 0), X, Z, -1)))
    else:
        items += [(plates[0], Placement((0, 0, 0), X, Z, -1)),
                  (plates[1], Placement((x0 + x1, 0, 0), (-1, 0, 0), Z, 1))]
    # rings(), replayed from where it started (bridge.RollHolder records it): from moveTo(0, a + 1.5t,
    # -90) a half ring r + 3t round centred at (r - 1.5t, r + 3t), open towards -x, one leg going on
    # r - 1.5t; then moveTo(a - t, a + 12t, 180) to the second. Turned so they open up (+v).
    r = a / 2
    at = box.rings_at * Affine.translation(0, a + 1.5 * t) * Affine.rotation(-90)
    faces = [Placement((x0 + t / 2, -d / 2, zm), Y, Z, 1), Placement((x1 - t / 2, -d / 2, zm), Y, Z, -1)]
    for q in faces:
        q.keep = lambda p: p.contains(Point(0, -r - 1.5 * t))
        items.append((parts[-1], q, Affine.rotation(-90) * ~(at * Affine.translation(r - 1.5 * t, r + 3 * t))))
        at = at * Affine.translation(a - t, a + 12 * t) * Affine.rotation(180)
    return items


def _drill_stand(box, parts, left_foot, feet=0.0):
    """DrillStand and WallDrillBox, in the frame they are drawn in: the tops level, the bottom
    falling to the right by extra_height (the floor's top face from Z = eh at X = 0 to 0 at x), the
    front and back walls (drawn from the front, their bottom slanted: u = X + their left edge's
    spacing, v = Z + 2t), the inner x walls (u = X + t, v = Z + t), the bottom along the floor from
    t·tan a right of X = 0, the y walls upright from the floor to the top (u = Y + t), and the sides (u = Y + t, their joints from 2t above
    their foot: left_foot below the floor's left end, 2t below its right end, and their stackable
    feet's height (feet) below that)."""
    t, sx, sy, sh, eh = box.thickness, box.sx, box.sy, box.sh, box.extra_height
    x, y = box.x, box.y
    a = math.atan(eh / x)
    d = (math.cos(a), 0, -math.sin(a))     # along the floor
    floor = (0, 0, eh)                                                     # its top face at X = 0
    front, *rest = parts
    xwalls, back, bottom, left = rest[:len(sy) - 1], *rest[len(sy) - 1:len(sy) + 2]
    ywalls, right = rest[len(sy) + 2:len(sy) + 1 + len(sx)], rest[-1]
    out = [(front, Placement((-t, 0, -2 * t), X, Z, 1))]
    pos = 0
    for p, s in zip(xwalls, sy):
        pos += s
        out.append((p, Placement((-t, pos, -t), X, Z, -1)))
        pos += t
    out += [(back, Placement((-t, y, -2 * t), X, Z, -1)),
            (bottom, Placement(_add(floor, d, t * math.tan(a)), d, Y, -1)),
            (left, Placement((0, -t, eh - left_foot - feet), Y, Z, -1))]
    pos = 0
    for p, s in zip(ywalls, sx):
        pos += s
        out.append((p, Placement((pos, -t, eh * (1 - (pos + t / 2) / x)), Y, Z, 1)))
        pos += t
    return out + [(right, Placement((x, -t, -2 * t - feet), Y, Z, 1))]


@recipe
def WallDrillBox(box, parts):
    return _drill_stand(box, parts, 2 * box.thickness)


@recipe
def DrillStand(box, parts):
    """See _drill_stand: the left side's foot reaches down extra_height more, so both stand level."""
    return _drill_stand(box, parts, box.extra_height + 2 * box.thickness, box.edges["š"].startWidth())


@recipe
def KeyHolder(box, parts):
    """The back plate on the wall and a hook standing out of it at each pair of holes (drawn from
    the plate, u out of it, v up: the hook curls up at the bottom)."""
    t, p, d = box.thickness, box.padding_left_right, box.hook_distance
    out = [Placement((0, 0, 0), X, Z, -1)]
    return out + [Placement((p + i * (d + t), 0, box.padding_bot), (0, -1, 0), Z, -1) for i in range(box.num_hooks)]


@recipe
def SkadisBoard(box, parts):
    """The board on the wall. The washers have no place given and are left out."""
    return [Placement((0, 0, 0), X, Z, -1)]


@recipe
def SkadisStand(box, parts):
    """One foot (the generator draws one; the board needs two), its profile in the YZ plane: the
    foot back along +Y, the board leaning on its hooked front. The plate for foot_front lies under
    it, the foot's fingers in its middle."""
    t, w = box.thickness, max(box.foot / 10, box.thickness)
    stand = Placement((-t / 2, 0, 0), Y, Z, 1)
    if not box.foot_front:
        return [stand]
    return [Placement((-w, -(box.foot_front - w), 0), Y, X, 1), stand]


@recipe
def DinRailBox(box, parts):
    """Closed box on a DIN rail: the back at Y = 0..t, the rail 8 behind it, the sides (drawn from
    the top down, v out from the back's front face; their rail edge reaches back over the rail),
    bottom and top from the back, the lid in front (Y = -h) with a lip inside along each side. The
    latch slides down behind the back through the guide strip, its hook under the rail."""
    t, x, y, h, w, o = box.thickness, box.x, box.y, box.h, box.rail_width, box.rail_offset
    out, down = (0, -1, 0), (0, 0, -1)
    guide = (y - w) / 2 - t / 2 + o - 9            # the guide's mid-plane on the back
    place = {
        "Lid": Placement((0, -h, 0), X, Z, 1),
        "Back": Placement((0, 0, 0), X, Z, -1),
        "Left Side upsidedown": Placement((0, 0, y), down, out, 1),
        "Right Side": Placement((x, 0, y), down, out, -1),
        "Bottom": Placement((0, 0, 0), X, out, 1),
        "Top": Placement((0, 0, y), X, out, -1),
    }
    lips = [Placement((1.05 * t, -h - t, 0.05 * t - 1), Z, Y, 1), Placement((x - 1.05 * t, -h - t, 0.05 * t - 1), Z, Y, -1)]
    items = []
    for p in parts:
        label = p.record.label
        if label in place:
            items.append((p, place[label]))
        elif p.record.primitive == "rectangularWall":   # the latch's guide, behind the back
            items.append((p, Placement((0, t, guide - t / 2), X, Y, 1)))
        elif lips:
            items.append((p, lips.pop(0)))
        else:                                          # the latch
            items.append((p, Placement((x / 2 - t / 2, t, (y - w) / 2 + o), down, Y, 1)))
    return items


# ---------------------------------------------------------------- parts and samples

def _gear_phase(poly, teeth, ring=False):
    """Local angle (degrees) of the middle of a tooth: the outline's tips for a gear, the toothed
    hole's for a ring gear (its teeth point in). Teeth repeat every 360/teeth: averaged on that."""
    outline = max(poly.interiors, key=lambda i: Polygon(i).area) if ring else poly.exterior
    pts = list(outline.coords)[:-1]
    rs = [math.hypot(*p) for p in pts]
    lo, hi = min(rs), max(rs)
    tips = [p for p, r in zip(pts, rs) if (r < lo + 0.15 * (hi - lo) if ring else r > hi - 0.15 * (hi - lo))]
    sx = sum(math.cos(teeth * math.atan2(y, x)) for x, y in tips)
    sy = sum(math.sin(teeth * math.atan2(y, x)) for x, y in tips)
    return math.degrees(math.atan2(sy, sx)) / teeth


def _mesh(phase_a, teeth_a, theta, phase_b, teeth_b, inside=False):
    """The turn (degrees) for gear b, whose tooth middle is at phase_b, so it meshes with gear a
    (a tooth middle at phase_a, as turned) when b's centre is at angle theta from a's: a tooth
    of each in a gap of the other on the line of centres. inside: b in the ring gear a."""
    frac_a = ((theta - phase_a) * teeth_a / 360) % 1
    if inside:  # both seen from the same side of the contact
        return theta - phase_b - ((frac_a + 0.5) % 1) * 360 / teeth_b
    return theta + 180 - phase_b - ((0.5 - frac_a) % 1) * 360 / teeth_b


def _turned_frame(part, degrees):
    """The part's local frame turned by degrees about its origin (a gear's centre)."""
    return Affine.rotation(degrees) * local_matrix(part.record)


def _part_polys(part):
    return polygons_of(loops_of(part, local_matrix(part.record)))


def _knob(box, parts):
    """The three discs stacked, the bolt's in the middle: the one with the hex hole for its head
    on the plain one, the one with the D hole for its shank on top (upside down, the bolt up)."""
    t = box.thickness
    plain, nut, shank = parts[2], parts[1], parts[0]
    return [(plain, Placement((0, 0, 0), X, Y, 1)), (nut, Placement((0, 0, t), X, Y, 1)),
            (shank, Placement((0, 0, 2 * t), X, Y, 1))]


@decoration("WavyKnob", "steel")
@decoration("ConcaveKnob", "steel")
def _knob_bolt(box):
    """A hex bolt: its head in the hex hole, its shank through the D hole and 30 mm on."""
    t, s = box.thickness, box.hexhead / 2 - 0.2
    head = Polygon([(s / math.cos(math.pi / 6) * math.cos(math.radians(a)),
                     s / math.cos(math.pi / 6) * math.sin(math.radians(a))) for a in range(0, 360, 60)])
    return (_solid("steel", Placement((0, 0, t), X, Y, 1), head, t) +
            _rod("steel", (0, 0, 0), Z, X, (0, 0), box.bolthole / 2 - 0.2, t, 3 * t + 30))


RECIPES["ConcaveKnob"] = RECIPES["WavyKnob"] = _knob


@recipe
def LBeam(box, parts):
    """The L in the YZ plane, h long along X: x lying, its far edge's counterpart (F) under y,
    which stands on it, its fingers down in the notches."""
    t = box.thickness
    x, y = parts[0].record.args[0], parts[1].record.args[0]
    return [Placement((0, 0, 0), Y, X, -1), Placement((0, x, t), Z, X, 1)]


@recipe
def ZBeam(box, parts):
    """The Z (or U) in the YZ plane, h long along X: x lying, y standing on its far edge, z lying
    on top of y towards +Y. Flanged U: z's far edge on a second web y + t long, down to the floor."""
    t = box.thickness
    x, y, z = (parts[i].record.args[0] for i in range(3))
    out = [Placement((0, 0, 0), Y, X, -1), Placement((0, x, t), Z, X, 1), Placement((0, x + t, t + y), Y, X, -1)]
    if len(parts) > 3:  # its finger joint (f) on its left edge: drawn from the top down
        out.append(Placement((0, x + t + z, t + y), (0, 0, -1), X, -1))
    return out


@recipe
def RectangularWall(box, parts):
    """The wall standing, its front face at Y = 0."""
    return [Placement((0, 0, 0), X, Z, -1)]


RECIPES["TriangularWall"] = RectangularWall


@recipe
def LaserHoldfast(box, parts):
    """Each holdfast standing on its shaft's end, the hook up, side by side 20 mm apart (drawn
    with the shaft along u from the hook at u = 0)."""
    length = box.hookheight + box.h
    return [Placement((i * (box.x + 20), 0, length), (0, 0, -1), X, -1) for i in range(len(parts))]


@recipe
def Pulley(box, parts):
    """The toothed layers stacked, the rim (the generator draws one) on top."""
    t = box.thickness
    layers = parts[1:] + parts[:1] if box.top else parts
    return [(p, Placement((0, 0, i * t), X, Y, 1)) for i, p in enumerate(layers)]


@decoration("Pulley", "steel")
def _pulley_axle(box):
    t = box.thickness
    n = math.ceil(box.h / t) + (1 if box.top else 0)
    return _rod("steel", (0, 0, 0), Z, X, (0, 0), box.axle / 2 - 0.1, -10, n * t + 10)


@recipe
def Gears(box, parts):
    """The two gears lying meshed, the big one round the origin, the small one r1 + r2 along X.
    The template with the two shaft holes at that distance is left out (no outline)."""
    big, small = parts[0], parts[1]
    r1 = box.gears.sizes(teeth=box.teeth1, dimension=box.modulus, angle=box.pressure_angle,
                         profile_shift=box.profile_shift)[0]
    r2 = box.gears.sizes(teeth=box.teeth2, dimension=box.modulus, angle=box.pressure_angle,
                         profile_shift=box.profile_shift)[0]
    pa = _gear_phase(_part_polys(big)[0], box.teeth2)
    turn = _mesh(pa, box.teeth2, 0, _gear_phase(_part_polys(small)[0], box.teeth1), box.teeth1)
    return [(big, Placement((0, 0, 0), X, Y, 1)),
            (small, Placement((r1 + r2, 0, 0), X, Y, 1), _turned_frame(small, turn))]


@recipe
def GearBox(box, parts):
    """The narrow box (x across, X; y long, Y; the bottom on the floor), the two shafts across it
    at y1 and y2, h / 2 up, the gears on them in layers 1.1 t apart: in each a small gear on one
    shaft drives a big one on the other, alternately, each big gear glued to the next layer's
    small gear on its shaft."""
    t = box.thickness
    t1, t2 = sorted((box.teeth1, box.teeth2))
    pitch1, size1, _ = box.gears.sizes(teeth=t1, dimension=box.modulus)
    pitch2, size2, _ = box.gears.sizes(teeth=t2, dimension=box.modulus)
    side, end, end2, side2, bottom = parts[:5]
    x, y, h = end.record.args[0], side.record.args[0], side.record.args[1]
    if box.stages == 1:
        y1, y2 = y / 2 - (pitch1 + pitch2) + pitch1, y / 2 + (pitch1 + pitch2) - pitch2
    else:
        y1, y2 = y / 2 - (pitch1 + pitch2) / 2, y / 2 + (pitch1 + pitch2) / 2
    out = [(side, Placement((0, 0, 0), Y, Z, -1)), (side2, Placement((x, 0, 0), Y, Z, 1)),
           (end, Placement((0, 0, 0), X, Z, 1)), (end2, Placement((0, y, 0), X, Z, -1)),
           (bottom, Placement((0, 0, 0), X, Y, -1))]
    bigs, smalls = parts[5:5 + box.stages], parts[5 + box.stages:5 + 2 * box.stages]
    for i, (big, small) in enumerate(zip(bigs, smalls)):
        xi = (i + 0.05) * 1.1 * t
        a, b = (small, big) if i % 2 == 0 else (big, small)  # on y1, on y2
        ta, tb = (t1, t2) if i % 2 == 0 else (t2, t1)
        turn = _mesh(_gear_phase(_part_polys(a)[0], ta), ta, 0, _gear_phase(_part_polys(b)[0], tb), tb)
        out += [(a, Placement((xi, y1, h / 2), Y, Z, 1)), (b, Placement((xi, y2, h / 2), Y, Z, 1), _turned_frame(b, turn))]
    return out


@decoration("GearBox", "steel")
def _gearbox_shafts(box):
    """The two shafts, through both sides and 5 mm out."""
    t = box.thickness
    t1, t2 = sorted((box.teeth1, box.teeth2))
    pitch1, size1, _ = box.gears.sizes(teeth=t1, dimension=box.modulus)
    pitch2, size2, _ = box.gears.sizes(teeth=t2, dimension=box.modulus)
    x, y, h = 1.1 * t * box.stages, (size1 + size2 if box.stages == 1 else 2 * size2), max(size1, size2) + t
    if box.stages == 1:
        ys = (y / 2 - (pitch1 + pitch2) + pitch1, y / 2 + (pitch1 + pitch2) - pitch2)
    else:
        ys = (y / 2 - (pitch1 + pitch2) / 2, y / 2 + (pitch1 + pitch2) / 2)
    return [p for yc in ys for p in _rod("steel", (0, 0, 0), X, Y, (yc, h / 2), box.shaft / 2 - 0.2, -t - 5, x + t + 5)]


def _planetary(box):
    """(planet positions in degrees, sun-to-planet distance, ring teeth) as the generator works them out."""
    ringteeth = box.sunteeth + 2 * box.planetteeth
    pitch1 = box.gears.sizes(teeth=box.sunteeth, dimension=box.modulus)[0]
    pitch2 = box.gears.sizes(teeth=box.planetteeth, dimension=box.modulus)[0]
    planets = int(math.pi / (math.asin(float(box.planetteeth + 2) / (box.planetteeth + box.sunteeth))))
    if box.maxplanets:
        planets = min(box.maxplanets, planets)
    ta = box.sunteeth + ringteeth
    positions = ([round(i * ta / planets) * 360 / ta for i in range(planets)] if ta % planets
                 else [i * 360 / planets for i in range(planets)])
    return positions, pitch1 + pitch2, ringteeth


@recipe
def Planetary(box, parts):
    """Lying, from the floor: the disc, the ring gear with the sun and the planets meshed inside it
    (the planets where the carrier has their holes), the carrier on top (drawn from its corner,
    its centre width / 2 in). With deltateeth the second ring and its planets go in a layer of
    their own between ring and carrier, on the same positions."""
    t = box.thickness
    positions, r, ringteeth = _planetary(box)
    disc, ring, carrier, sun = parts[:4]
    rest = parts[4:]
    delta = rest.pop(0) if box.deltateeth else None
    planets = rest
    width = 2 * r + 3 * (box.shaft + box.play)
    ps = _gear_phase(_part_polys(sun)[0], box.sunteeth)
    pp = _gear_phase(_part_polys(planets[0])[0], box.planetteeth) if planets else 0
    out = [(disc, Placement((0, 0, 0), X, Y, 1)), (sun, Placement((0, 0, t), X, Y, 1))]
    turns = [_mesh(ps, box.sunteeth, a, pp, box.planetteeth) for a in positions]
    for i, planet in enumerate(planets):
        k = i % len(positions)
        z = t if i < len(positions) else 2 * t
        a = math.radians(positions[k])
        out.append((planet, Placement((r * math.cos(a), r * math.sin(a), z), X, Y, 1), _turned_frame(planet, turns[k])))
    # the ring turned to mesh with the first planet: its teeth facing the planet's gaps
    pr = _gear_phase(_part_polys(ring)[0], ringteeth, ring=True)
    planet_phase = pp + turns[0]
    frac_p = ((positions[0] - planet_phase) * box.planetteeth / 360) % 1
    ring_turn = positions[0] - pr - ((frac_p - 0.5) % 1) * 360 / ringteeth
    out.append((ring, Placement((0, 0, t), X, Y, 1), _turned_frame(ring, ring_turn)))
    if delta is not None:
        out.append((delta, Placement((0, 0, 2 * t), X, Y, 1)))
    out.append((carrier, Placement((-width / 2, -width / 2, (3 if delta is not None else 2) * t), X, Y, 1)))
    return out


@decoration("Planetary", "steel")
def _planetary_pins(box):
    """The sun's shaft and a pin through each planet into the carrier."""
    t = box.thickness
    positions, r, _ = _planetary(box)
    top = (4 if box.deltateeth else 3) * t
    out = _rod("steel", (0, 0, 0), Z, X, (0, 0), box.shaft / 2 - 0.1, -10, top + 15)
    for a in positions:
        c = (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))
        out += _rod("steel", (0, 0, 0), Z, X, c, box.shaft / 2 - 0.1, t, top + 2)
    return out


def _four_bar(a, b, c, ground, start=60):
    """Crank angle (degrees, from start on) and the coupler-rocker joint of a four-bar linkage:
    crank a at the origin, rocker c at (ground, 0), coupler b between; the joint above."""
    for k in range(0, 360, 5):
        th = math.radians(start + k)
        bx, by = a * math.cos(th), a * math.sin(th)
        dx, dy = ground - bx, -by
        d = math.hypot(dx, dy)
        if abs(b - c) < d < b + c:
            m = (b * b - c * c + d * d) / (2 * d)
            hgt = math.sqrt(max(b * b - m * m, 0))
            px, py = bx + m * dx / d, by + m * dy / d
            return (bx, by), (px - hgt * dy / d, py + hgt * dx / d)
    return None


@recipe
def Linkage(box, parts):
    """A four-bar linkage tried on the base plate: the crank (the l/4 link), the coupler (3/4 l)
    and the rocker (l/2) pinned, hole to hole, between the two outer holes of the plate's middle
    row; the crank and the rocker on a spacer disc each, the coupler over them. The other discs
    and links are left out."""
    t, w = box.thickness, box.width
    discs, links = parts[:10], parts[10:27]
    plate = parts[-1]
    holed = links[:10]   # 200, 200, 150, 50, 150, 50, 100, 100, 66, 66
    crank, coupler, rocker = holed[3], holed[2], holed[6]

    def span(link):  # its last hole on the centre line, from the first one at 0: the rounded end is w / 2 on
        return round((_part_polys(link)[0].bounds[2] - w / 2) / box.dist) * box.dist - box.dist

    # the plate's middle row: holes on its centre line
    plate_poly = _part_polys(plate)[0]
    cy = (plate_poly.bounds[1] + plate_poly.bounds[3]) / 2
    row = sorted(Polygon(i).centroid.x for i in plate_poly.interiors if abs(Polygon(i).centroid.y - cy) < 0.5)
    out = [(plate, Placement((0, 0, 0), X, Y, 1))]
    if len(row) < 2:
        return out
    ax, gx = row[0], row[-1] - row[0]
    found = _four_bar(span(crank), span(coupler), span(rocker), gx)
    if not found:
        return out
    (bx, by), (cx, cy2) = found
    A, B, C, D = (ax, cy), (ax + bx, cy + by), (ax + cx, cy + cy2), (ax + gx, cy)

    def link_at(link, p, q, z):
        ux, uy = q[0] - p[0], q[1] - p[1]
        n = math.hypot(ux, uy)
        U, V = (ux / n, uy / n, 0), (-uy / n, ux / n, 0)
        return link, Placement(_add((p[0], p[1], z), V, -w / 2), U, V, 1)

    out += [link_at(crank, A, B, 2 * t), link_at(rocker, D, C, 2 * t), link_at(coupler, B, C, 3 * t),
            (discs[0], Placement((A[0], A[1], t), X, Y, 1)), (discs[1], Placement((D[0], D[1], t), X, Y, 1))]
    box._laserbox_pins = (A, B, C, D)
    return out


@decoration("Linkage", "steel")
def _linkage_pins(box):
    """A pin in each joint, through the plate, the spacers and the links."""
    t = box.thickness
    return [p for x, y in getattr(box, "_laserbox_pins", ())
            for p in _rod("steel", (0, 0, 0), Z, X, (x, y), box.diameter * 0.45, 0, 4 * t + 2)]


@recipe
def NemaMount(box, parts):
    """The bracket on its slotted plate (lying, Y back from the corner), the motor plate standing
    at the front (Y -t..0), a triangle each side from the corner up and back; the motor inside,
    its face on the plate, the shaft out of the front. The finger holes drawn last (for a plate
    of one's own to fix the bracket to) are left out."""
    plate, triangles, base = parts[0], parts[1], parts[2]
    x = plate.record.args[0]
    out = [(base, Placement((0, 0, 0), X, Y, -1)), (plate, Placement((0, 0, 0), X, Z, 1))]
    # both triangles are drawn in one part, the second turned half round (the hypotenuses side by
    # side): it is brought onto the first, whose place each then keeps
    t = box.thickness
    pieces = _part_polys(triangles)
    first = min(pieces, key=lambda q: abs(q.bounds[0]) + abs(q.bounds[1] + t))  # from the origin, fingers below
    second = next(q for q in pieces if q is not first)
    c1, c2 = first.envelope.centroid, second.envelope.centroid
    back = ~(Affine.translation(c1.x + c2.x, c1.y + c2.y) * Affine.rotation(180))
    here = first.centroid
    keep = lambda p: abs(p.centroid.x - here.x) < 1 and abs(p.centroid.y - here.y) < 1
    for frame, (x0, side) in ((Affine.identity(), (0, 1)), (back, (x, -1))):
        out.append((triangles, Placement((x0, x, 0), (0, -1, 0), Z, side, keep=keep), frame * local_matrix(triangles.record)))
    return out


@decoration("NemaMount", "grip-black")
def _mount_motor(box):
    t = box.thickness
    w = box.nema_sizes.get(box.size, box.nema_sizes[8])[0]
    return _stepper(box, t, 0, t)


ROBOT_SEGMENT_GAP = 15


@recipe
def RobotArm(box, parts):
    """Each segment a closed tube along X, end to end ROBOT_SEGMENT_GAP apart in the order drawn:
    its two walls a wide (the servo's) lying, its two walls b wide standing, a cap at each end
    (one of an Mm segment drawn b × a, turned). Neither the servos nor how the segments join."""
    out, x0 = [], 0.0
    for i in range(0, len(parts) - 5, 6):
        w1, w2, w3, w4, c1, c2 = parts[i:i + 6]
        a, b, l = w1.record.args[0], w3.record.args[0], w1.record.args[1]
        out += [(w1, Placement((x0, 0, 0), Y, X, 1)), (w2, Placement((x0, 0, b), Y, X, -1)),
                (w3, Placement((x0, 0, 0), Z, X, -1)), (w4, Placement((x0, a, 0), Z, X, 1))]
        for cap, xc, first in ((c1, x0, True), (c2, x0 + l, False)):
            if abs(cap.record.args[0] - a) < 1e-6:
                out.append((cap, Placement((xc, 0, 0), Y, Z, -1 if first else 1)))
            else:
                out.append((cap, Placement((xc, 0, 0), Z, Y, 1 if first else -1)))
        x0 += l + 2 * box.thickness + ROBOT_SEGMENT_GAP
    return out


# ---------------------------------------------------------------- what hangs on the wall

# Where each wall-mounted box's wall is (Y), as its recipe places it: a pegboard is shown there.
WALLS = {
    **{name: (lambda box: box.thickness) for name in (
        "WallConsole", "WallHook", "WallCaliper", "WallSlottedHolder", "WallChiselHolder", "WallPliersHolder",
        "WallWrenchHolder", "WallHopper", "RollHolder", "KeyHolder", "Hook")},
    "WallPinRow": lambda box: 0.0,
    "WallPlaneHolder": lambda box: 0.0,
    "WallStairs": lambda box: box.y,
    "WallRack": lambda box: (box.adjustSize(box.y) if box.outside else box.y) + box.thickness,
    "WallTypeTray": lambda box: sum(box.sy) + box.thickness * len(box.sy),
    "WallStackableBin": lambda box: box.y + box.thickness,
    "WallDrillBox": lambda box: box.y + box.thickness,
    "DinRailBox": lambda box: box.thickness + 8,       # the rail's back
    "CoffeeCapsuleHolder": lambda box: box.thickness * (3 if box.backplate else 2),
    # hung on the wall, though shelves
    "SpicesRack": lambda box: box.hole_distance + box.hole_length + box.space / 2 + box.thickness,
    "BinTray": lambda box: box.y + box.thickness,
}


def _extent(pieces):
    """(min, max) world corners of the pieces' outlines and thickness."""
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for p in pieces:
        U, V = p["u"], p["v"]
        N = [c * p["side"] for c in _cross(U, V)]
        for u, v in p["rings"][0]:
            for w in (0, p["t"]):
                q = [p["origin"][i] + u * U[i] + v * V[i] + w * N[i] for i in range(3)]
                lo = [min(a, b) for a, b in zip(lo, q)]
                hi = [max(a, b) for a, b in zip(hi, q)]
    return lo, hi


def _skadis(w, h):
    """An IKEA Skådis like pegboard w × h (5 mm thick, rounded corners): slots 5 × 15 every 40 mm in
    a row, the rows 20 mm apart, every other one offset by 20 (as SkadisBoard cuts them)."""
    board = rect(8, 8, w - 8, h - 8).buffer(8, quad_segs=4)
    slots = [LineString([(u, v - 5), (u, v + 5)]).buffer(2.5, quad_segs=4)
             for r in range(1, int((h - 10) // 20)) for c in range(1, int((w - 2) // 20))
             if (r + c) % 2 and 12 <= (u := c * 20 - 8 + (w % 20) / 2) <= w - 12 and 15 <= (v := r * 20) <= h - 15]
    return board.difference(unary_union(slots))


def pegboard(pieces, wall):
    """A white pegboard on the wall behind the box (its front face at Y = wall), reaching 40 mm round
    it, in steps of 20 mm."""
    lo, hi = _extent([p for p in pieces if "decoration" not in p or "part" in p])
    x0, z0 = math.floor((lo[0] - 40) / 20) * 20, math.floor((lo[2] - 40) / 20) * 20
    x1, z1 = math.ceil((hi[0] + 40) / 20) * 20, math.ceil((hi[2] + 40) / 20) * 20
    return [dict(p, decoration="pegboard")
            for p in Placement((x0, wall, z0), X, Z, -1).pieces([_skadis(x1 - x0, z1 - z0)], 5)]


@decoration("SkadisStand", "pegboard")
def stand_board(box):
    """The pegboard the stand holds, 400 wide, leaning on the arm's hooked front edge (the hooks
    through its slots), from the floor up past the top connector."""
    a = math.radians(box.angle)
    length = box.extra_height_bottom + box.extra_height_top + max(box.connectors) * 20 + 60
    up, front = (0, math.cos(a), math.sin(a)), (0, -math.sin(a), math.cos(a))
    return Placement(_add((-200, 0, 0), front, 0.5), X, up, 1).pieces([_skadis(400, round(length / 20) * 20)], 5)


@decoration("DinRailBox", "rail")
def din_rail(box):
    """The 35 mm top hat rail the box clips on (7.5 deep, 1 mm steel), across the box and 40 mm past
    it each side, between the back and the pegboard."""
    t, x, y, w, o = box.thickness, box.x, box.y, box.rail_width, box.rail_offset
    z0 = (y - w) / 2 + o                       # its lower flange edge, as the clips have it
    s = 1.0
    # the hat: its base on the pegboard, the sides forward, the flanges outwards at the front (Y from
    # the pegboard forwards, Z), extruded along X
    profile = Polygon([(0, 5), (0, w - 5), (7.5 - s, w - 5), (7.5 - s, w), (7.5, w), (7.5, w - 5 - s), (s, w - 5 - s),
                       (s, 5 + s), (7.5, 5 + s), (7.5, 0), (7.5 - s, 0), (7.5 - s, 5)])
    return Placement((-40, t + 8, z0), (0, -1, 0), Z, -1).pieces([profile], x + 80)


def _solid(kind, place, polys, depth):
    """Decoration pieces: the polygons (in place's u, v) extruded depth along its normal."""
    return [dict(p, decoration=kind) for p in place.pieces(polys if isinstance(polys, list) else [polys], depth)]


def _rod(kind, at, axis, across, centre, r, a, b, segs=12):
    """A round rod of radius r along axis, from a to b along it (from at), its centre at centre (in
    across, axis × across)."""
    return _solid(kind, Placement(_add(at, axis, a), across, _cross(axis, across), 1),
                  Point(*centre).buffer(r, quad_segs=segs), b - a)


def _kitchen_roll(box):
    """The dowel (width long, 0.5 mm play) lying in the rings between the arms, and a kitchen roll
    (0.9 of the roll diameter allowed, its 44 mm core; 4 mm shorter than the gap between the rings)
    hanging on it by the core's top, a sheet hanging from its front."""
    t, w, d, a, h = box.thickness, box.width, box.diameter, box.axle, box.height
    x0 = h / 4 + t / 2 - 3 * t                      # the left arm's mid-plane (see RollHolder)
    za, ya = h - a / 2 - 3 * t, -d / 2              # the axle's centre
    R, core, rod = 0.45 * d, 22.0, a / 2 - 0.5
    zr = za - (core - 2 - rod)                      # the core rests on the dowel
    out = _rod("dowel", (x0 + t / 2 + 0.25, 0, 0), X, Y, (ya, za), rod, 0, w - 0.5)
    left, inner = x0 + 3 * t / 2 + 2, w - 2 * t                # between the rings
    out += _solid("towel", Placement((left, 0, 0), Y, Z, 1), Point(ya, zr).buffer(R, quad_segs=24).difference(
        Point(ya, zr).buffer(core, quad_segs=16)), inner - 4)
    out += _solid("cardboard", Placement((left - 0.5, 0, 0), Y, Z, 1), Point(ya, zr).buffer(core, quad_segs=16).difference(
        Point(ya, zr).buffer(core - 2, quad_segs=16)), inner - 3)
    out += _solid("towel", Placement((left, ya - R + 0.3, 0), X, Z, 1), rect(0, zr - R - 70, inner - 4, zr), 0.4)
    return out


DECORATIONS.setdefault("RollHolder", []).append(_kitchen_roll)


@decoration("WallPlaneHolder", "iron")
def hand_plane(box):
    """A bench plane standing on its heel on the bottom, its sole against the back strips, its toe
    up under the holder: a cast iron sole and cheeks, the blade under its lever cap, a wooden tote
    at the heel and a knob at the toe, scaled to the holder."""
    t, w, l, h = box.thickness, box.width, box.length, box.height
    sole = lambda dy: (0, -2 * t - dy, 2 * t)                    # the sole's face, dy up from it
    flat = lambda dy: Placement(sole(dy), X, Z, 1)                # plan shapes, extruded up from dy
    side = lambda x0: Placement((x0, -2 * t, 2 * t), (0, -1, 0), Z, -1)   # profiles (height, length)
    k = 0.06 * w
    out = _solid("iron", flat(0), rect(0.5, 0.5, w - 0.5, l - 0.5).buffer(0.5), 0.12 * h)
    out += _solid("iron", flat(0.12 * h), [rect(0.5, 0.04 * l, k, 0.96 * l), rect(w - k, 0.04 * l, w - 0.5, 0.96 * l)], 0.3 * h)
    out += _solid("steel", flat(0.12 * h), rect(0.15 * w, 0.46 * l, 0.85 * w, 0.62 * l), 0.4 * h)
    out += _solid("iron", flat(0.52 * h), rect(0.2 * w, 0.47 * l, 0.8 * w, 0.6 * l), 0.08 * h)
    tote = Polygon([(0.12 * h, 0.05 * l), (0.12 * h, 0.34 * l), (0.45 * h, 0.31 * l), (0.92 * h, 0.2 * l),
                    (0.98 * h, 0.15 * l), (0.9 * h, 0.1 * l), (0.55 * h, 0.12 * l)])
    grip = Polygon([(0.3 * h, 0.14 * l), (0.3 * h, 0.27 * l), (0.75 * h, 0.2 * l), (0.78 * h, 0.15 * l)])
    out += _solid("wood-handle", side(0.38 * w), tote.difference(grip), 0.24 * w)
    out += _solid("wood-handle", flat(0.12 * h), Point(w / 2, 0.88 * l).buffer(0.17 * w, quad_segs=12), 0.5 * h)
    return out


@decoration("WallCaliper", "steel")
def caliper(box):
    """A digital caliper standing in the holder's slot on the end of its beam (the slot hc wide, its
    bottom h/4 up, 12 to 18 mm out of the wall edge), the jaws at the top."""
    t, w, h, hc = box.thickness, box.width, box.h, box.height
    y = t - (4 * t + hc / 2)           # the slot's middle: the sides' u = 4t … 4t + hc, u = 0 at Y = t
    face = lambda dy, depth: Placement((0, y + depth / 2 + dy, 0), X, Z, 1)
    z0, L = h / 4, 230.0
    top = z0 + L
    jaw = Polygon([(0, top - 22), (-40, top - 6), (-41, top), (w, top), (w, top - 22)])
    out = _solid("steel", face(0, 3.5), [rect(0, z0, w, top - 22), jaw], 3.5)
    slider = rect(-2, top - 95, w + 12, top - 30)
    sjaw = Polygon([(-2, top - 30), (-38, top - 12), (-39, top - 8), (-2, top - 22)])
    out += _solid("caliper-body", face(0, hc), [slider], hc)
    out += _solid("steel", face(0, 3.5), [sjaw], 3.5)
    out += _solid("lcd", face(-hc / 2 - 0.1, 0.2), [rect(1, top - 80, w + 8, top - 58)], 0.2)
    return out


class _Turtle:
    """Follows a boxes.py outline (polyline's lengths and corners, radius or not) to find where it goes."""

    def __init__(self, x=0.0, y=0.0, heading=0.0):
        self.x, self.y, self.a = x, y, heading

    def forward(self, l):
        self.x += l * math.cos(math.radians(self.a))
        self.y += l * math.sin(math.radians(self.a))

    def corner(self, angle, r=0.0):
        if r:
            side = 1 if angle > 0 else -1    # the centre: left of the heading for a left turn
            cx = self.x + side * r * -math.sin(math.radians(self.a))
            cy = self.y + side * r * math.cos(math.radians(self.a))
            phi = math.radians(angle)
            dx, dy = self.x - cx, self.y - cy
            self.x, self.y = cx + dx * math.cos(phi) - dy * math.sin(phi), cy + dx * math.sin(phi) + dy * math.cos(phi)
        self.a += angle

    def polyline(self, *args):
        for i, v in enumerate(args):
            if i % 2 == 0:
                self.forward(v)
            else:
                self.corner(*v) if isinstance(v, tuple) else self.corner(v)


@decoration("WallWrenchHolder", "steel")
def wrenches(box):
    """A combination wrench in each pair of slots, on its edge in them, resting on their bottom (the
    slots run into the sides at 45°, down towards the wall; the sides' front edge replayed): w wide,
    s thick, 9 w + 40 long, centred between the sides, an open end and a ring end beyond them."""
    t, n, d = box.thickness, box.number, box.depth
    s_min, s_max, w_min, w_max = box.min_strength, box.max_strength, box.min_width, box.max_width
    h = (s_min + s_max) * n * 2 ** 0.5 + box.extra_distance * (n - 1) + w_max
    xc = (box.x - 2 * t) / 2                            # between the sides' inner faces
    tur = _Turtle(0, h, -90)                            # the sides' front edge (u = 0), drawn downwards
    tur.polyline(t, 45)
    out = []
    for i in range(n):
        w = w_min * ((n - i) / n) + w_max * (i / n)
        s = s_min * ((n - i) / n) + s_max * (i / n)
        a = math.radians(tur.a)
        depth = w - s / 2 + 2 * s
        D = (0, math.cos(a), math.sin(a))               # into the slot, in the sides' frame (u = Y + d)
        N = (0, math.sin(a), -math.cos(a))              # across it, to the right
        start = (0, tur.x - d, tur.y)
        bottom = _add(_add(start, D, depth), N, s / 2)
        if i == n - 1:
            tur.polyline(depth, (-180, s / 2), w - 0.5 * s, (180, s / 2))
        else:
            tur.polyline(depth, (-180, s / 2), w - 0.5 * s, (135, s / 2), box.extra_distance, (45, s / 2))
        L = 9 * w + 40
        jaw = Point(-L / 2, w / 2).buffer(1.1 * w, quad_segs=12).difference(
            rect(-L / 2 - 1.2 * w, 0.1 * w, -L / 2, 0.9 * w)).difference(Point(-L / 2, w / 2).buffer(0.4 * w))
        ring = Point(L / 2, w / 2).buffer(0.95 * w, quad_segs=12).difference(Point(L / 2, w / 2).buffer(0.5 * w, quad_segs=12))
        shape = unary_union([rect(-L / 2 + w, 0.05 * w, L / 2 - w, 0.95 * w), jaw, ring])
        # its plane: X along it, back up the slot from its bottom; X × -D = N, its thickness across
        origin = _add(_add(bottom, N, -(s - 0.2) / 2), X, xc)
        out += _solid("steel", Placement(origin, X, tuple(-c for c in D), 1), shape, s - 0.2)
    return out


@decoration("WallChiselHolder", "steel")
def chisels(box):
    """A chisel in about four fifths of the holes (where the top's front edge replayed puts them):
    its brass bolster on the top, the wooden handle above, the blade down through the hole."""
    import random
    t, n, td, h = box.thickness, box.number, box.tooldiameter, box.h
    rh, r, sw = box.holediameter / 2, box.radius, box.slot_width
    a = math.degrees(math.asin((r + sw / 2) / (r + rh)))
    l = (td - sw - 2 * r) / 2
    tur, centres = _Turtle(), []
    for i in range(n):
        tur.polyline(l, (180 - a, r), 0)
        h_ = math.radians(tur.a)                      # the hole: turning right round its centre
        centres.append((tur.x + rh * math.sin(h_), tur.y - rh * math.cos(h_)))
        tur.polyline(0, (-360 + 2 * a, rh), 0, (180 - a, r), l)
    rng = random.Random(n)
    top = lambda u, v: (u, -box.depth + v, 0)          # the top's frame (it lies at Z = h)
    rH = min(rh + 1, td / 2 - 0.3)
    out = []
    for u, v in centres:
        if rng.random() > 0.8:
            continue
        c = top(u, v)
        bw = min(1.4 * rh, rng.choice((0.6, 0.9, 1.2)) * rh)
        out += _rod("brass", (0, 0, h + t), Z, X, (c[0], c[1]), rH, 0, 6)
        out += _rod("wood-handle", (0, 0, h + t), Z, X, (c[0], c[1]), 0.8 * rH, 6, 110)
        out += _rod("wood-handle", (0, 0, h + t), Z, X, (c[0], c[1]), 0.65 * rH, 110, 116)
        out += _rod("steel", (0, 0, h + t), Z, X, (c[0], c[1]), 4, -t - 15, 0)
        L = min(0.9 * h, 150)
        blade = Polygon([(c[0] - bw / 2, h - L + 6), (c[0] - bw / 2, h - 15), (c[0] + bw / 2, h - 15), (c[0] + bw / 2, h - L)])
        out += _solid("steel", Placement((0, c[1] + 2, 0), X, Z, 1), blade, 4)
    return out


@decoration("WallSlottedHolder", "steel")
def screwdrivers(box):
    """A screwdriver in about four fifths of the slots, its shaft at the slot's end, its handle
    standing on the top (red, yellow or black)."""
    import random
    t, n, wt, ws, ds, h = box.thickness, box.number, box.tool_width, box.slot_width, box.slot_depth, box.h
    d = min(2 * t, (wt - ws) / 4)
    rng = random.Random(n)
    depth = box.additional_depth + ds
    out = []
    for i in range(n):
        if rng.random() > 0.8:
            continue
        c = (d + i * wt + wt / 2, -depth + ds - ws / 2)
        grip = rng.choice(("grip-red", "grip-yellow", "grip-black"))
        rg = min(0.4 * wt, 16)
        out += _rod(grip, (0, 0, h + t), Z, X, c, rg, 0, 85)
        out += _rod(grip, (0, 0, h + t), Z, X, c, 0.75 * rg, 85, 95)
        out += _rod("steel", (0, 0, h + t), Z, X, c, ws / 2 - 0.6, -110, 0, segs=6)
        out += _solid("steel", Placement((0, c[1] + 0.6, 0), X, Z, 1),
                      Polygon([(c[0] - ws / 2 + 0.6, h + t - 110), (c[0] + ws / 2 - 0.6, h + t - 110),
                               (c[0] + 0.8, h + t - 118), (c[0] - 0.8, h + t - 118)]), 1.2)
    return out


@decoration("WallPliersHolder", "steel")
def pliers(box):
    """A pair of pliers hung over the front bar in each compartment: the head up, the handles astride
    the bar, their grips red, yellow or black."""
    import random
    t, sx, y, ht = box.thickness, box.sx, box.y, box.h_t
    x = sum(sx) + (len(sx) - 1) * t
    walls = [0] + [sum(sx[:i + 1]) + i * t for i in range(len(sx) - 1)] + [x]
    yc, zt = -(y - t / 2), ht
    jaws = Polygon([(yc - 7, zt + 10), (yc + 7, zt + 10), (yc + 3, zt + 64), (yc - 3, zt + 64)])
    boss = Point(yc, zt + 12).buffer(9, quad_segs=8)
    handles = unary_union([LineString([(yc + k * 4, zt + 8), (yc + k * 10, zt - 5), (yc + k * 26, zt - 120)]).buffer(4.5)
                           for k in (-1, 1)])
    cut = rect(yc - 60, zt - 40, yc + 60, zt + 80)
    metal = unary_union([jaws, boss, handles.intersection(cut)])
    grips = handles.difference(cut).buffer(1)
    rng = random.Random(len(sx))
    out = []
    for a, b in zip(walls, walls[1:]):
        x0 = (a + b) / 2 - 5
        out += _solid("steel", Placement((x0, 0, 0), Y, Z, 1), metal, 10)
        out += _solid(rng.choice(("grip-red", "grip-yellow", "grip-black")), Placement((x0 - 1, 0, 0), Y, Z, 1), grips, 12)
    return out


def _jar(at, axis, across, centre, r, L, rng):
    """A spice jar r round and L long along axis from at: a black tin with a label round it and on
    its lid, or spices in glass under a wooden lid, by chance."""
    add = lambda kind, rr, a, b: _rod(kind, at, axis, across, centre, rr, a, b, segs=8)
    if rng.random() < 0.5:     # a tin
        return add("tin", r, 0, 0.3 * L) + add("label", r + 0.3, 0.3 * L, 0.75 * L) + add("tin", r, 0.75 * L, L - 10) + \
            add("tin", r + 0.6, L - 10, L) + add("label", r - 6, L, L + 0.2)
    return add(rng.choice(("spice-red", "spice-yellow", "spice-green", "spice-brown")), r, 0, L - 14) + \
        add("lid-wood", r - 1, L - 14, L)


@decoration("WallRack", "jar")
def rack_jars(box):
    """Spice jars standing on each shelf, in a row along it, about four in five places taken: as
    wide as the shelf's depth allows (at most 50), 1.6 times as tall, less than the section."""
    import random
    t, x, y, sh = box.thickness, box.x, box.y, box.sh
    if box.outside:
        x, y = box.adjustSize(x, "h", "f"), box.adjustSize(y)
    r = min(y - 6, 50) / 2
    rng = random.Random(len(sh))
    out, pos = [], 0
    for s in sh:
        L = min(3.2 * r + 10, s - t - 15)
        n = int(x // (2 * r + 6))
        if r > 5 and L > 10:
            for j in range(n):
                if rng.random() < 0.8:
                    out += _jar((0, 0, pos + t), Z, X, (x / 2 + (j - (n - 1) / 2) * (2 * r + 6), y / 2), r, L, rng)
        pos += s
    return out


@decoration("KeyHolder", "brass")
def keys(box):
    """On about two hooks in three a key ring sits in the hook's cup, its top on the hook's bottom
    bar, one to three keys hanging from it, turned a little."""
    import random
    from shapely import affinity
    t, d, p, H, T = box.thickness, box.hook_distance, box.padding_left_right, box.hook_height, box.hook_thickness
    rng = random.Random(box.num_hooks)
    r_in, wire = 9.0, 1.6
    key = unary_union([Point(0, -8).buffer(11.5, quad_segs=10), rect(-3.5, -48, 3.5, -16),
                       Polygon([(-3.5, -48), (3.5, -48), (3.5, -52), (0, -55), (-3.5, -51)])]).difference(
        unary_union([Point(0, 0).buffer(2.4, quad_segs=6)] +
                    [rect(1.5, -22 - 6 * i, 3.6, -19 - 6 * i) for i in range(0, 5, 2)]))
    out = []
    for i in range(box.num_hooks):
        if rng.random() > 0.66:
            continue
        xc = p + i * (d + t) + t / 2
        yc, zc = -(T + 0.5 * 0.7 * H), box.padding_bot + T - r_in   # the ring's centre, in the hook's cup
        ring = Point(xc, zc).buffer(r_in + wire, quad_segs=16).difference(Point(xc, zc).buffer(r_in, quad_segs=16))
        out += _solid("steel", Placement((0, yc + wire / 2, 0), X, Z, 1), ring, wire)
        bottom = zc - r_in - wire / 2
        for k in range(rng.randint(1, 3)):
            shape = affinity.translate(affinity.rotate(key, rng.uniform(-12, 12), origin=(0, 0)), yc, bottom)
            out += _solid(rng.choice(("brass", "brass", "steel")), Placement((xc - 3 + 3 * k - 1, 0, 0), Y, Z, 1), shape, 2)
    return out


def _drill_bits(box):
    """Drill bits standing in about five in six compartments, one to three each, thicker to the right
    (1.5 to 10 mm, as the compartment allows), from the floor to 15–40 mm over the row's top: black
    or gold flutes, a bright shank, a stepped point."""
    import random
    t, sx, sy, sh, eh, x = box.thickness, box.sx, box.sy, box.sh, box.extra_height, box.x
    rng = random.Random(len(sx) * 7 + len(sy))
    out = []
    for i, ry in enumerate(sy):
        y0 = sum(sy[:i]) + i * t
        for j, cx in enumerate(sx):
            x0 = sum(sx[:j]) + j * t
            if rng.random() > 0.85:
                continue
            dia = min(1.5 + 8.5 * j / max(1, len(sx) - 1), min(cx, ry) - 2)
            if dia < 1:
                continue
            flutes = rng.choice(("hss", "hss", "hss-gold"))
            for k in range(rng.randint(1, 3)):
                c = (rng.uniform(x0 + dia / 2 + 0.5, x0 + cx - dia / 2 - 0.5), rng.uniform(y0 + dia / 2 + 0.5, y0 + ry - dia / 2 - 0.5))
                floor = eh * (1 - c[0] / x)
                L = eh + sh[i] - floor + rng.uniform(15, 40)
                at, r = (0, 0, floor), dia / 2
                out += _rod(flutes, at, Z, X, c, 0.35 * r, 0, 0.6) + _rod(flutes, at, Z, X, c, 0.75 * r, 0.6, 0.6 + 0.5 * r)
                out += _rod(flutes, at, Z, X, c, r, 0.6 + 0.5 * r, 0.6 * L, segs=6)
                out += _rod("steel", at, Z, X, c, r, 0.6 * L, L, segs=6)
    return out


DECORATIONS.setdefault("WallDrillBox", []).append(_drill_bits)
DECORATIONS.setdefault("DrillStand", []).append(_drill_bits)


# ---------------------------------------------------------------- hole patterns

# A hole pattern stands upright, read from the front (u along X, v up, its front face at Y = 0, the
# thickness behind). The generators draw only the holes: the sheet round them is the recipe's.
MARGIN = 10  # panel round a fan's or a motor's square


def _upright(z=0.0, plate=None, **kw):
    return Placement((0, 0, z), X, Z, -1, plate=plate, **kw)


@recipe
def FanHole(box, parts):
    """The fan's holes in a panel MARGIN larger than its square."""
    d = box.diameter
    return [_upright(MARGIN, rect(-MARGIN, -MARGIN, d + MARGIN, d + MARGIN))]


@decoration("FanHole", "grip-black")
def fan(box):
    """A d × d fan behind the panel, 0.3 d deep (25 at most): its frame round the bore, with the
    mounting holes, and in its middle a hub (inner_disc of the radius) with seven blades."""
    t, d, i = box.thickness, box.diameter, box.mounting_holes_inset
    depth, c, r = min(25.0, 0.3 * d), (d / 2, d / 2), 0.47 * d
    screws = [Point(p, q).buffer(box.mounting_holes / 2, quad_segs=6) for p in (i, d - i) for q in (i, d - i)]
    frame = rect(0, 0, d, d).difference(unary_union([Point(c).buffer(r, quad_segs=24)] + screws))
    hub = max(box.inner_disc, 0.15) * d / 2

    def polar(rr, a):
        return c[0] + rr * math.cos(math.radians(a)), c[1] + rr * math.sin(math.radians(a))

    blades = [Polygon([polar(0.8 * hub, a), polar(r - 1.5, a + 20), polar(r - 1.5, a + 45), polar(0.8 * hub, a + 30)])
              for a in (i * 360 / 7 for i in range(7))]
    rotor = unary_union([Point(c).buffer(hub, quad_segs=12)] + blades)
    return (_solid("grip-black", Placement((0, t, MARGIN), X, Z, -1), frame, depth) +
            _solid("grip-black", Placement((0, t + depth * 0.3, MARGIN), X, Z, -1), rotor, depth * 0.4))


@recipe
def NemaPattern(box, parts):
    """The motor's holes (centred on its square) in a panel MARGIN larger than the square."""
    w = box.nema_sizes.get(box.size, box.nema_sizes[8])[0]
    return [_upright(MARGIN, rect(-MARGIN, -MARGIN, w + MARGIN, w + MARGIN))]


@decoration("NemaPattern", "grip-black")
def nema_motor(box):
    """The stepper behind the panel (see _stepper)."""
    return _stepper(box, 0, box.thickness, MARGIN)


def _stepper(box, x0, y, z0):
    """A NEMA box.size stepper behind a panel t thick, its face at Y = y, its square from (x0, z0)
    in X, Z: as long as it is wide, black end caps round a steel stack, its corners chamfered, the
    pilot in the flange hole, the shaft through it out of the front."""
    t = box.thickness
    w, flange, holes, screws = box.nema_sizes.get(box.size, box.nema_sizes[8])
    k = 0.12 * w
    body = Polygon([(k, 0), (w - k, 0), (w, k), (w, w - k), (w - k, w), (k, w), (0, w - k), (0, k)])
    out = []
    for y0, y1, kind in ((0, 0.25, "grip-black"), (0.25, 0.75, "steel"), (0.75, 1, "grip-black")):
        out += _solid(kind, Placement((x0, y + y0 * w, z0), X, Z, -1), body, (y1 - y0) * w)
    out += _solid("grip-black", Placement((x0, y - 2, z0), X, Z, -1), Point(w / 2, w / 2).buffer(flange / 2 - 0.3), 2)
    return out + _rod("steel", (0, 0, 0), Y, X, (x0 + w / 2, -(z0 + w / 2)), max(1.5, 0.06 * w), y - t - w / 2, y)


@recipe
def HolePattern(box, parts):
    """The holes in a panel of the shape they fill (the border fillHoles gets)."""
    return [_upright(0, Polygon(RECORDS["border"]))]


@recipe
def FrontPanel(box, parts):
    """The layout's outlines side by side, as the generator spaces them (10 apart), each with the
    holes lying in it. Holes outside every outline are left out."""
    plates, x0, prev = [], 0.0, None
    for line in box.layout.splitlines():
        words = shlex.split(re.sub("#.*$", "", line).strip(), comments=True)
        if words and words[0].lower() == "outline":
            if prev is not None:
                x0 += prev + 10
            prev = float(words[1])
            plates.append(rect(x0, 0, x0 + prev, float(words[2])))
    return [(part, _upright(0, p)) for part in parts[:1] for p in plates]


def _seven_segment_separators(t, x, walls, X0, Z0, y):
    """The 12 separators of one digit (x high) whose holes seven_segment_holes draws from (X0, Z0)
    on a back panel with its inner face at Y = y (SevenSegmentPattern, SevenSegmentClock): walls[2k + half]
    on line k, the second half turned 180° about the digit's middle, each centred on its holes, its
    f edge in them, standing towards -Y."""
    l, w, d = 0.4 * x, 0.05 * x, 0.05 * x
    width = l + 2 * w + d
    lines = [(t / 4 * 2 ** .5, x / 2 + w - t / 4 * 2 ** .5, 2 ** .5 * (width - t) - t / 2, -45),
             (t, t, 2 ** .5 * (.55 * x / 2 - t) - t / 2, 45),
             (width / 2 + t / 2 ** .5 / 2, width / 2 + t / 2 ** .5 / 2, 2 ** .5 * (l / 2 + d / 2) - 1.5 * t, 45),
             (-t / 2, x / 2 + 0.25 * t, x / 2 - 0.25 * t, 90),
             (-t / 2, 0, x / 2 - 0.25 * t, 90),
             (-t, -t / 2, l + 2 * w + d + 2 * t, 0)]
    out, turtle = [], Affine.identity()
    for half in range(2):
        for k, (x0, y0, length, a) in enumerate(lines):
            wall = walls[2 * k + half]
            (px, py), a = turtle * (x0, y0), math.radians(a + 180 * half)
            U = (math.cos(a), 0, math.sin(a))
            N = (math.sin(a), 0, -math.cos(a))  # U × -Y: the side the thickness goes
            o = _add(_add((X0 + px, y, Z0 + py), U, (length - wall.record.args[0]) / 2), N, -t / 2)
            out.append((wall, Placement(o, U, (0, -1, 0), 1)))
        turtle *= Affine.translation(width, x) * Affine.rotation(180)
    return out



@recipe
def SevenSegmentPattern(box, parts):
    """The plate with the segments in front (Y 0..t), the separators behind it standing h deep in
    the finger holes of the back plate. The generator draws neither plate: both are the separators'
    outline and t more round it. The separators, drawn in pairs by length, go where
    seven_segment_holes puts their holes, twice (the second half turned 180° about the middle), each
    centred on its holes."""
    t, x, h = box.thickness, box.digit, box.h
    l, w, d = 0.4 * x, 0.05 * x, 0.05 * x
    width = l + 2 * w + d
    plate = rect(-2 * t, -2 * t, width + 2 * t, x + 2 * t)
    dx = width + box.spacing + t  # the holes are drawn right of the segments, t up
    out = [(parts[0], _upright(2 * t, plate, keep=lambda p: p.centroid.x < width + 1), None),
           (parts[0], Placement((0, t + h, 2 * t), X, Z, -1, plate=plate, keep=lambda p: p.centroid.x > -2 * t),
            Affine.translation(-dx, -t))]
    return out + [item + (None,) for item in _seven_segment_separators(t, x, parts[1:], 0, 2 * t, t + h)]


# ---------------------------------------------------------------- test pieces

@recipe
def BurnTest(box, parts):
    """Each pair tried as meant: the piece with the counterpart edges (F) flat, the one with fingers
    (f) standing on its back edge (the F piece turned round, its drawn bottom edge at the back), its
    fingers in the notches; the pairs side by side. Neither has
    a part of its own: each is picked out of the drawing by where the generator starts it (the f
    piece at its inner corner, the F piece t in from its outer corner, at y 0)."""
    t, x, s = box.thickness, box.x, box.spacing
    near = lambda cx: (lambda p: abs(p.centroid.x - cx) < x / 2)
    out = []
    for c in range(box.pairs):
        ax = t + 2 * c * (x + 2 * t + s)
        bx = ax + x + t + s  # the F piece's outer corner
        ox = c * (x + 2 * t + 20)
        out += [(parts[0], Placement((ox + x + 2 * t, t, 0), (-1, 0, 0), (0, -1, 0), 1, keep=near(x / 2 + t)),
                 Affine.translation(-bx, 0)),
                (parts[0], Placement((ox + t, 0, t), X, Z, -1, keep=near(x / 2)), Affine.translation(-ax, -t))]
    return out


@recipe
def FillTest(box, parts):
    """The sample lying flat."""
    return [Placement((0, 0, 0), X, Y, 1)]


@recipe
def FlexTest(box, parts):
    """The strip on its long edge, bent a quarter turn over its flex (x long, 10 in from the end;
    the generator starts at 5, 5)."""
    return [Placement((-5, 0, -5), X, Z, 1, bends=[(15, 15 + box.x, 90, box.x / (math.pi / 2))])]


@recipe
def FlexTest2(box, parts):
    """The sample on its edge, bent a quarter turn over its whole width (the flex covers it)."""
    return [Placement((0, 0, 0), X, Z, 1, bends=[(0, box.x, 90, box.x / (math.pi / 2))])]


# ---------------------------------------------------------------- misc

# ---------------------------------------------------------------- spools, gauge, arcade, power supply

def _spool_staves(staves, n, apothem, t, R):
    """The staves of a spool round the axle (along X, at Y = 0, Z = R): stave k on the flange's finger
    holes at 90° + k·360/n (the flange drawn x → Y, y → Z), its inner face at the polygon's apothem,
    its thickness outwards, v along the axle from the flange at X = 0."""
    side, out = 2 * math.tan(math.pi / n) * apothem, []
    for k, stave in enumerate(staves):
        phi = math.radians(90 + k * 360 / n)
        radial, tangent = (0, math.cos(phi), math.sin(phi)), (0, math.sin(phi), -math.cos(phi))
        out.append((stave, Placement(_add(_add((0, 0, R), radial, apothem), tangent, -side / 2), tangent, X, -1)))
    return out


@recipe
def Spool(box, parts):
    """Lying on its flanges' rims, the axle along X at Z = R: the flanges outside X = 0 and X = h,
    the n staves of the polygonal core between them on their finger holes (the first one up, the
    flange drawn x → Y, y → Z), thickness outwards. With reinforcements: on each flange's outer face
    a ring of ribs (their stepped edge on the flange's radial finger holes, the plain middle over the
    staves' fingers), a small disc on the ribs' other edge, the first ribs on the left flange."""
    t, n, R, H = box.thickness, box.sides, box.outer_diameter / 2, box.h
    _, apothem, _ = box.regularPolygon(n, radius=box.inner_diameter / 2)
    out = [(parts[0], Placement((0, 0, R), Y, Z, -1)), (parts[1], Placement((H, 0, R), Y, Z, 1))]
    out += _spool_staves(parts[2:2 + n], n, apothem, t, R)
    if box.reinforcement_height:
        m, w = box.reinforcements, box.reinforcement_height - t
        ribs = parts[2 + n:2 + n + 2 * m]
        for j, rib in enumerate(ribs):
            th = math.radians(j % m * 360 / m)
            radial = (0, math.cos(th), math.sin(th))
            x0, U = (-t, (-1, 0, 0)) if j < m else (H + t, X)
            n_ = _cross(U, radial)
            at = _add(_add((x0, 0, R), radial, box.axle_diameter / 2), n_, -t / 2)
            out.append((rib, Placement(at, U, radial, 1)))
        discs = parts[2 + n + 2 * m:]
        out += [(discs[0], Placement((-t - w, 0, R), Y, Z, -1)), (discs[1], Placement((H + t + w, 0, R), Y, Z, 1))]
    return out


@recipe
def FilamentSpool(box, parts):
    """Like Spool, the axle along X at Z = R: the flange with the staves' finger holes outside X = 0,
    the staves h − t long on it, the polygon (the bayonet's upper layer, as upperCB draws it) on
    their tops, its fingers between theirs. As the generator says, the outer parts of the latch
    belong to the core: the outer ring of the lower layer glued under the polygon. The inner parts
    belong to the other flange (outside X = h): the plain inner ring of the upper layer in the
    polygon's hole, the lugged inner ring of the lower layer under it, inside the core. The polygon
    is drawn with its first side down: it, the lower layer and the second flange are turned half
    round (their alignment holes together), so that side is up, on the first stave."""
    t, n, R, H = box.thickness, box.sides, box.outer_diameter / 2, box.h
    _, apothem, _ = box.regularPolygon(n, radius=box.inner_diameter / 2)  # already reduced by render
    flange, other, polygon, lower = parts[:4]
    ring = min(_part_polys(polygon), key=lambda q: q.area)  # the inner ring: centred on the polygon
    c = ring.centroid
    poly_frame = Affine.rotation(180) * Affine.translation(-c.x, -c.y) * local_matrix(polygon.record)
    out = [(flange, Placement((0, 0, R), Y, Z, -1)),
           (polygon, Placement((H - t, 0, R), Y, Z, 1), poly_frame),
           (lower, Placement((H - 2 * t, 0, R), Y, Z, 1), _turned_frame(lower, 180)),
           (other, Placement((H, 0, R), Y, Z, 1), _turned_frame(other, 180))]
    return out + _spool_staves(parts[4:4 + n], n, apothem, t, R)


def _arcade_side(box):
    """side()'s turtle, in the side's frame: {row: (start, angle°)} for each row of finger holes (the
    middle of the slot the panel stands in) and the monitor's opening as ("monitor", (start, angle°,
    length)) along the outline."""
    t, r = box.thickness, 10
    d30 = 2 * r * math.tan(math.radians(15))
    pos, a = [r + (box.front + t) * math.sin(math.radians(15)), 0.0], [0.0]
    rows = {}

    def dirs():
        c, s = math.cos(math.radians(a[0])), math.sin(math.radians(a[0]))
        return (c, s), (-s, c)

    def holes(name, x, y, angle):
        d, n = dirs()
        rows[name] = ((pos[0] + x * d[0] + y * n[0], pos[1] + x * d[1] + y * n[1]), a[0] + angle)

    def line(*steps):  # polyline: lengths, corners (angle or (angle, radius)) between
        for i, k in enumerate(steps):
            d, n = dirs()
            if i % 2 == 0:
                pos[0] += k * d[0]
                pos[1] += k * d[1]
                continue
            ang, rad = k if isinstance(k, tuple) else (k, 0)
            phi = math.radians(ang)
            fwd, sideways = rad * math.sin(abs(phi)), rad * (1 - math.cos(phi)) * (1 if ang > 0 else -1)
            pos[0] += fwd * d[0] + sideways * n[0]
            pos[1] += fwd * d[1] + sideways * n[1]
            a[0] += ang

    holes("floor", 10, r + t / 2, 0)
    line(box.y, (90, r))
    holes("back low", 0.5 * t, r + t / 2, 0)
    holes("back high", box.h - 80, r + t / 2, 0)
    line(box.h, (45, r))
    holes("top back", 0, r + t / 2, 0)
    holes("top", box.topback + t / 2, r + t, 90)
    holes("speaker", box.topback, box.top + r + 1.5 * t, -180)
    line(box.topback + t, (90, r), box.top + 2 * t, (90, r), 100 - 2 * r, (-90, r))
    rows["monitor"] = (tuple(pos), a[0], box.monitor_height - 2 * r - d30)
    line(box.monitor_height - 2 * r - d30, (-30, r))
    holes("keyboard", -d30 + t, r + 0.5 * t, 0)
    holes("key back", -d30 + 0.5 * t, r + t, 90)
    holes("front", box.keyboard_depth - d30 + 1.5 * t, r + t, 90)
    return rows


def _arcade_panel(start, angle, t, length=0.0, flip=False):
    """A panel width wide across X, standing in the sides' slot from start along angle (in the
    sides' frame: u → Y, v → Z): v from start, centred on the slot. flip: v from the slot's other
    end (length further), back along it."""
    if flip:
        start = (start[0] + length * math.cos(math.radians(angle)), start[1] + length * math.sin(math.radians(angle)))
        angle += 180
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return Placement((0, start[0] + t / 2 * s, start[1] - t / 2 * c), X, (0, c, s), 1)


@recipe
def Arcade(box, parts):
    """The two sides at X = -t..0 and width..width + t (their u → Y, front at small Y, v up), every
    panel between them in the slot side() draws for it, as long as the finger holes run. Where a
    panel's joint edge (f) and the holes' direction disagree, the panel is turned end for end so
    its f meets the neighbour's F: the front (f up at the keyboard), the speaker panel (f at the
    marquee's front, the speakers near it) and the top back (f at the marquee's front). The back
    cover (no joints) is screwed outside the two back strips, from the lower one's foot up."""
    t, w = box.thickness, box.width
    rows = _arcade_side(box)
    panels = {0: ("floor", box.bottom, False), 1: ("back low", box.back, False), 3: ("back high", box.back, False),
              4: ("front", box.front, True), 5: ("keyboard", box.keyboard_depth, False),
              6: ("key back", box.keyback, False), 7: ("speaker", box.speaker, True), 8: ("top", box.top, False),
              9: ("top back", box.topback, True)}
    out = [(parts[i], _arcade_panel(*rows[name], t, length, flip)) for i, (name, length, flip) in panels.items()]
    (u, v), angle = rows["back low"]
    out.append((parts[2], _arcade_panel((u + t, v), angle, t)))
    for side, x0, s in ((parts[10], 0, -1), (parts[11], w, 1)):
        out.append((side, Placement((x0, 0, 0), Y, Z, s)))
    return out


@decoration("Arcade", "grip-black")
def _arcade_vitamins(box):
    """The monitor in the opening between the speaker panel and the keyboard (its face on the panels'
    inner plane, r + t inside the outline, 20 deep, the screen 15 in from its edges), and on the keyboard, which the generator leaves
    without holes, a joystick and three buttons for each player."""
    t, w, kd = box.thickness, box.width, box.keyboard_depth
    rows = _arcade_side(box)
    (u, v), angle, L = rows["monitor"]
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    n = (-s, c)  # into the cabinet
    face = (0, u + (10 + t) * n[0], v + (10 + t) * n[1])
    out = _solid("grip-black", Placement(face, X, (0, c, s), 1), rect(0, 0, w, L), 20)
    out += _solid("lcd", Placement(_add(face, (0, n[0], n[1]), -0.3), X, (0, c, s), 1), rect(15, 15, w - 15, L - 15), 0.3)
    (u, v), angle = rows["keyboard"]
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    up = (0, s, -c)
    top = _add((0, u, v), up, t / 2)

    def on_top(kind, x, y, r, z, height):
        return _solid(kind, Placement(_add(top, up, z), X, (0, c, s), -1), Point(x, y).buffer(r, quad_segs=8), height)

    for x0 in (w / 4 - 50, 3 * w / 4 - 50):  # the joystick, the buttons 45 to 105 right of it
        out += on_top("steel", x0, kd / 2, 4, 0, 30) + on_top("grip-red", x0, kd / 2, 12, 30, 18)
        for k, kind in enumerate(("grip-red", "grip-yellow", "grip-yellow")):
            out += on_top(kind, x0 + 45 + 30 * k, kd / 2 + (8 if k == 1 else -8), 11, 0, 6)
    return out


@recipe
def BottleTag(box, parts):
    """The tag lying level round the bottle's neck (see _bottletag_bottle), the neck through its hole,
    its long end to the front. Drawn outside any move(), in sheet coordinates: the hole's centre
    is at (width / 2, height - width / 2)."""
    w, hgt = box.width, box.height
    cx, cy = w / 2, hgt - w / 2
    return [Placement((-cx, -cy, BOTTLETAG_Z), X, Y, 1)]


BOTTLETAG_Z = 150  # the tag's height on the bottle: where the shoulder meets the neck


@decoration("BottleTag", "bottle-amber")
def _bottletag_bottle(box):
    """A bottle whose neck fits the tag's inner hole (min_diameter): a body 3.2 × the neck across,
    the shoulder in steps up to the tag, the neck on above it, a steel cap."""
    rn = box.min_diameter / 2
    rb, out = 3.2 * rn, []
    z_sh = BOTTLETAG_Z - 2.5 * rn               # where the shoulder starts
    out += _rod("bottle-amber", (0, 0, 0), Z, X, (0, 0), rb, 0, z_sh)
    steps = 5
    for j in range(steps):
        r = rn + (rb - rn) * math.cos(math.pi / 2 * (j + 0.5) / steps)
        out += _rod("bottle-amber", (0, 0, 0), Z, X, (0, 0), r, z_sh + j * 2.5 * rn / steps,
                    z_sh + (j + 1) * 2.5 * rn / steps)
    out += _rod("bottle-amber", (0, 0, 0), Z, X, (0, 0), rn, BOTTLETAG_Z, BOTTLETAG_Z + 2.2 * rn)
    out += _rod("steel", (0, 0, 0), Z, X, (0, 0), rn + 1.5, BOTTLETAG_Z + 2.2 * rn, BOTTLETAG_Z + 2.8 * rn)
    return out


@recipe
def AngledCutJig(box, parts):
    """The base (30 + x + 2t by y) on the floor, two pairs of upright triangles in its finger holes
    (4.5 t in from the front and back): the big ones (x by x / tan(angle)) on the right, their
    right angle at the right, X = 30 + t + x; the small ones (20 by 20 tan(angle)) on the left,
    turned round, their right angle at X = 10 - t. On their hypotenuses, which meet in a V near
    X = 30, the two plates the work lies on (l and l2 long, y wide), at right angles to each other.
    Each pair of triangles is drawn in one part, the second turned half round."""
    t, x, y, a = box.thickness, box.x, box.y, math.radians(box.angle)
    base, plate, plate2, big, small = parts
    b = math.atan2(x / math.tan(a), x)             # the big plate's slope: 90° - angle
    out = [(base, Placement((0, 0, t), X, Y, -1)),
           (plate, Placement((30 + t, 0, t), (math.cos(b), 0, math.sin(b)), Y, 1)),
           (plate2, Placement((30 - t, 0, t), (-math.cos(a), 0, math.sin(a)), Y, -1))]
    for tri, x0, U, s in ((big, 30 + t, X, -1), (small, 30 - t, (-1, 0, 0), 1)):
        keep, frames = _angledcutjig_pair(tri)
        out += [(tri, Placement((x0, y0 - t / 2, t), U, Z, s, keep=keep), f)
                for f, y0 in zip(frames, (4.5 * t, y - 4.5 * t))]
    return out


def _angledcutjig_pair(tri):
    """A pair of triangles drawn in one part, the second turned half round: (keep, [two local
    frames]), the second frame bringing the second triangle onto the first, whose place it keeps."""
    pieces = _part_polys(tri)
    first = min(pieces, key=lambda q: q.bounds[1])          # its fingers below its base line
    second = max(pieces, key=lambda q: q.bounds[1])
    c1, c2 = first.envelope.centroid, second.envelope.centroid
    back = ~(Affine.translation(c1.x + c2.x, c1.y + c2.y) * Affine.rotation(180))
    here = first.centroid
    keep = lambda p: abs(p.centroid.x - here.x) < 1 and abs(p.centroid.y - here.y) < 1
    local = local_matrix(tri.record)
    return keep, [local, back * local]


@recipe
def BirdHouse(box, parts):
    """Box x × y (front at Y = 0) on its floor: the gables (h + t high at the eaves, the roof
    slopes at 45° up to a ridge x / 2 higher) at the front and back, the long walls (h high, F
    ends over the gables' fingers) left and right, the floor in the h edges' holes (Z -t … 0; the
    walls go edge_width below it). The two roof panels lie on the gables' slopes, left and right,
    their finger holes on the gables' fingers, from the ridge down. Their outline isn't jointed to
    anything but their ridge: the f one (the first, left) reaches the ridge on its inner face, the F
    one's holes start t below its ridge edge, so it covers the first's thickness there."""
    t, x, y, h = box.thickness, box.x, box.y, box.h
    ov = 2 ** 0.5 * x / 2 * box.roof_overhang
    s = 2 ** -0.5
    peak = (x / 2, -t - ov, h + t + x / 2)       # the ridge on the inner faces, at the panels' u = 0
    out = [Placement((0, 0, 0), X, Z, 1), Placement((0, y, 0), X, Z, -1),
           Placement((0, 0, 0), Y, Z, -1), Placement((x, 0, 0), Y, Z, 1),
           Placement((0, 0, 0), X, Y, -1)]
    for roof, V, side, down in ((parts[5], (s, 0, s), -1, t), (parts[6], (-s, 0, s), 1, 2 * t)):
        top = _part_polys(roof)[0].bounds[3] - 0.1        # the ridge edge's fingers' ends
        out.append(Placement(_add(peak, V, -(top - down)), Y, V, side))
    return out


@recipe
def PhotoFrame(box, parts):
    """The frame upright, as it hangs (its mounting holes at the top of the base), the layers from
    the back: the base (Y 2t … 3t, its photo outline etched on the front), the middle layer (t … 2t:
    the bottom guide guide_h high, a side guide each side from the top down to it, dovetailed into
    it) with the matting in its pocket, standing on the bottom guide, centred, and the front
    (0 … t), one plate with the window or four mitred bits (top, bottom, left, right) dovetailed at
    the corners. The photo the generator draws as a template (not cut) is shown as paper behind
    the matting (_photoframe_photo); no glass."""
    t, d = box.thickness, box.d
    bx, by, gw, gh = d.base_x, d.base_y, d.guide_w, d.guide_h
    back = (0, 0, -1)
    by_caller = {
        "render_base": [Placement((0, 2 * t, 0), X, Z, -1)],
        "middle_unsplit": [Placement((0, t, 0), X, Z, -1)],
        "middle_split": [Placement((0, t, 0), X, Z, -1),                          # bottom guide
                         Placement((0, t, by), back, X, -1),                      # left side, its d down
                         Placement((bx, t, by), back, (-1, 0, 0), 1)],            # right side
        "front_unsplit": [Placement((0, 0, 0), X, Z, -1)],
        "front_split": [Placement((0, 0, by), X, back, 1),                        # top, its wide edge up
                        Placement((0, 0, 0), X, Z, -1),                           # bottom
                        Placement((0, 0, 0), Z, X, 1),                            # left
                        Placement((bx, 0, 0), Z, (-1, 0, 0), -1)],                # right
        "render_matting": [Placement(((bx - d.mat_x) / 2, t, gh), X, Z, -1)],
    }
    out = []
    for p in parts:
        places = by_caller.get(p.record.caller)
        if places:
            out.append((p, places.pop(0)))
    return out


@decoration("PhotoFrame", "paper")
def _photoframe_photo(box):
    """The photo, centred, just behind the matting's window (its back face, in the pocket)."""
    d, t = box.d, box.thickness
    return Placement((0, 2 * t, 0), X, Z, 1).pieces(
        [rect(d.centre_x - d.photo_x / 2, d.centre_y - d.photo_y / 2,
              d.centre_x + d.photo_x / 2, d.centre_y + d.photo_y / 2)], 0.3)


def _canstorage_frame(box):
    """(z of the sides' base line, chute angle in radians, cos, sin): their bottom edge (the stackable
    feet, an outset edge) stands on the floor, the base line its start width above it."""
    a = math.radians(box.chuteAngle)
    return box.edges[box.bottom_edge].startWidth(), a, math.cos(a), math.sin(a)


def _canstorage_side(part):
    """The side's outline when its top edge is plain: the front edge then starts with a jump, so the
    outline is two open cuts, the top edge running on past the front's start: the top edge cut
    short there, then the front."""
    cuts = []
    loops_of(part, local_matrix(part.record), cuts)
    rest, front = sorted(cuts, key=lambda c: c[0][0])   # the front starts on the top edge, the rest at u = 0
    while rest[-1][0] < front[0][0]:
        rest = rest[:-1]
    return Polygon(rest + front)


@recipe
def CanStorage(box, parts):
    """Sides in the YZ plane (u = Y from the front, where the cans come out, to the back; the right
    one at X = width, the left at X = 0, thickness outwards), everything else between them, where
    the sides' finger holes are: the bottom chute rising to the back from the front's foot, the top
    chute falling to the back (its notch at the back lets the cans drop onto the bottom chute), the
    barrier standing at the front of the bottom chute, the back (u from the top down) and the top.
    The three pushers stand in the corner of bottom chute and back, their tabs in the slots; the
    stabilizers inside the feet, the short ones at the front."""
    t, D, W, depth, height = box.thickness, box.canDiameter, box.width, box.depth, box.height
    z0, a, c, s = _canstorage_frame(box)
    up_back, up_front = (0, c, s), (0, c, -s)                # the chutes' slopes
    out, pushers = [], iter((0.15, 0.5, 0.85))                # where the pushers' slots are across
    for part in parts:
        r = part.record
        if r.label in ("right", "left"):
            plate = _canstorage_side(part) if box.top_edge == "e" else None
            p = Placement((W, 0, z0), Y, Z, 1, plate=plate) if r.label == "right" else \
                Placement((0, 0, z0), Y, Z, -1, plate=plate)
        elif r.label == "bottom chute":   # the finger holes' middle starts t/2 above the base line
            p = Placement(_add((0, 0, z0 + t / 2), (0, -s, c), -t / 2), up_back, X, -1)
        elif r.label == "top chute":
            v = t + D + box.bottom_chute_height + box.top_chute_height + t / 2
            p = Placement(_add((0, 0, z0 + v), (0, s, c), -t / 2), up_front, X, -1)
        elif r.label == "barrier":
            p = Placement((0, t, z0 + 1.1 * t + box.burn + s * 2 * t), Z, X, 1)
        elif r.label == "back":
            p = Placement((0, depth, z0 + height), (0, 0, -1), X, -1)
        elif r.label == "top":
            p = Placement((0, 0, z0 + height), Y, X, -1)
        elif r.label and r.label.startswith("Stabilizer"):
            n = int(r.label[-1])
            y0 = 0 if n <= 2 else depth + 2 * t - r.args[0]
            p = Placement((0 if n % 2 else W - t, y0, 0), Y, Z, 1)
        elif r.primitive is None and r.caller == "render":    # a pusher: its A side on the chute,
            across = next(pushers)                               # local (0, 0) under its tab
            corner = (0, depth, z0 + t / 2 + depth * math.tan(a) + t / 2 / c)   # chute's top, back's face
            o = _add(_add(corner, up_back, -box.pusherA), (0, -s, c), -t)
            p = Placement(_add(o, X, W * across - t / 2), up_back, (0, -s, c), 1)
        else:
            continue
        out.append((part, p))
    return out


@decoration("CanStorage", "tin")
def _canstorage_cans(box):
    """The cans lying across, where the generator's debug drawing has them: half on the bottom chute
    from the barrier on, the rest on the top chute, as many as fit before its drop notch."""
    t, D = box.thickness, box.canDiameter
    z0, a = _canstorage_frame(box)[:2]
    n = math.ceil(box.canNum / 2)
    out = []
    top = t + D + box.bottom_chute_height + box.top_chute_height + t / 2
    fit = int((box.top_chute_depth - 1.5 * D) / D + 0.5)   # centres before the notch
    rows = [((0, t), a, [(2 * t + (0.5 + i) * D, D / 2) for i in range(n)]),
            ((0, top), -a, [((0.5 + i) * D, D / 2 + t / 2) for i in range(min(box.canNum - n, fit))])]
    for (u0, v0), ang, cans in rows:
        for u, v in cans:   # in the side's u, v turned by the chute's angle
            y = u0 + u * math.cos(ang) - v * math.sin(ang)
            z = z0 + v0 + u * math.sin(ang) + v * math.cos(ang)
            out += _rod("tin", (0, 0, 0), X, Y, (y, z), D / 2 - 0.5, 0.01 * box.canHeight, 1.01 * box.canHeight, 24)
    return out


def _dispenser_levels(box):
    """(z of the walls' base line, z of the floor's top, wall height): the walls stand on their
    bottom edge (finger holes, or stackable feet with the floor hb up)."""
    t, hb = box.thickness, box.bottomheight
    hb = max(0, hb - box.edges["š"].spacing())
    z0 = box.edges["š" if hb else "h"].startWidth()
    return z0, z0 + (hb + t if hb else 0), box.h + (hb + t if hb else 0)


@recipe
def Dispenser(box, parts):
    """The walls round the inner x × y (the sides' u from the back to the front, where their
    outset bottom leaves the slot; thickness outwards), the floor in the walls' finger holes (its
    finger notch at the front), the front panels above the slot from each side, Y -t..0, and the
    lid's two layers on the walls' top: the plain one inside the opening, the outset one on it."""
    x, y = box.x, box.y
    z0, floor, th = _dispenser_levels(box)
    front = z0 + th - (box.h - box.slotheight)
    back = (0, -1, 0)
    return {
        "Floor": Placement((0, 0, floor), X, Y, -1),
        "Lid bottom": Placement((0, 0, z0 + th), X, Y, -1, lid=True),
        "Lid top": Placement((0, 0, z0 + th), X, Y, 1, lid=True),
        "Left wall": Placement((0, y, z0), back, Z, 1),
        "Right wall": Placement((x, y, z0), back, Z, -1),
        "Back wall": Placement((0, y, z0), X, Z, -1),
        "front": Placement((0, 0, front), X, Z, 1),
        "Left front": Placement((0, 0, front), X, Z, 1),
        "Right front": Placement((x, 0, front), (-1, 0, 0), Z, -1),
    }


@decoration("Dispenser", "cards")
def _dispenser_stack(box):
    """A stack of the items it dispenses (slot height thick, 1 mm clear of the walls) on the
    floor, two thirds up."""
    x, y, hs = box.x, box.y, box.slotheight
    floor = _dispenser_levels(box)[1]
    out = []
    for i in range(max(1, int(box.h * 2 / 3 / hs))):
        out += Placement((1, 1, floor + i * hs), X, Y, 1).pieces([rect(0, 0, x - 2, y - 2)], hs - 0.4)
    return out


def _coindisplay_slope(box):
    """(origin, U, V) of the coin plates' top face: across the holder from its left side's inner
    face, up the slope from the holder's front (the sides' high end at the back)."""
    x, y, h = inner(box)
    a = box.angle  # render() turned it into radians
    return (x / 2 - box.coin_plate / 2, y / 2 - box.coin_plate_x / 2, box.coin_showcase_h), X, (0, math.cos(a), math.sin(a))


@recipe
def CoinDisplay(box, parts):
    """ClosedBox's cube round x × y × h, its walls and top in clear acrylic so the holder shows.
    The holder stands centred on the bottom, in its finger holes: the two sides P apart, front to
    back (u from the back, their slope rising to it), the front piece across their front ends, and
    the two coin plates in the sides' slope, whose finger joint is 2t deep for them: the one with
    the coin's hole on top, flush with the slope, the plain one under it."""
    x, y, h = inner(box)
    t, P, Px = box.thickness, box.coin_plate, box.coin_plate_x
    o, U, V = _coindisplay_slope(box)
    N = _cross(U, V)
    back = (x / 2 - P / 2, y / 2 + Px / 2, 0)
    glass = dict(clear=True)
    return {
        "Wall 1": Placement((0, 0, 0), X, Z, 1, **glass),
        "Wall 2": Placement((0, 0, 0), Y, Z, -1, **glass),
        "Wall 4": Placement((x, 0, 0), Y, Z, 1, **glass),
        "Wall 3": Placement((0, y, 0), X, Z, -1, **glass),
        "Top": Placement((0, 0, h), X, Y, 1, **glass),
        "Bottom": Placement((0, 0, 0), X, Y, -1),
        "CoinSide1": Placement(back, (0, -1, 0), Z, 1),
        "CoinSide2": Placement(_add(back, X, P), (0, -1, 0), Z, -1),
        "CoinSide3": Placement((o[0], o[1], 0), X, Z, 1),
        "Coin Plate": Placement(_add(o, N, -t), U, V, 1),
        "Coin Plate Base": Placement(_add(o, N, -2 * t), U, V, 1),
    }


@decoration("CoinDisplay", "brass")
def _coindisplay_coin(box):
    """The coin, 2 mm thick, lying in the top plate's hole on the plain one."""
    o, U, V = _coindisplay_slope(box)
    P = box.coin_plate
    return _solid("brass", Placement(_add(o, _cross(U, V), -box.thickness), U, V, 1),
                  Point(P / 2, P / 2).buffer(box.coin_d / 2 - 0.3, quad_segs=16), 2)



def _display_lean(box):
    """(the slot's lower edge above the panel's bottom, the panel's up and forward directions, the
    world point of its front face's bottom centre): the shelf a third out in front of the panel,
    square to it, its back end on the floor, sets the lean; the panel's back bottom edge on the
    floor too."""
    t, x = box.thickness, box.x
    low = 0.2 * box.h - 0.65 * t
    th = math.atan2(low, x * 2 / 3 - t)
    up, fwd = (0, math.sin(th), math.cos(th)), (0, -math.cos(th), math.sin(th))
    return low, up, fwd, (0, -t * math.cos(th), t * math.sin(th))


@recipe
def Display(box, parts):
    """The panel leaning back, X centred on 0; the rounded plate through its slot, square to it
    and lying on the slot's lower edge: a third of it in front, the shelf, the rest behind, a
    leg down to the floor."""
    plate, panel = parts[0], parts[1]
    x = box.x
    low, up, fwd, foot = _display_lean(box)
    back = tuple(-c for c in fwd)
    pb = max(_part_polys(plate), key=lambda q: q.area).bounds
    slot = Polygon(max(_part_polys(panel), key=lambda q: q.area).interiors[0]).bounds
    cu, cv = (slot[0] + slot[2]) / 2, slot[1] - low          # the panel's bottom centre, drawn where it was
    tip = _add(_add(foot, up, low), fwd, x / 3)              # the shelf's front edge, on its lower face
    return [(plate, Placement(_add(_add(tip, X, -(pb[0] + pb[2]) / 2), back, -pb[1]), X, back, 1)),
            (panel, Placement(_add(_add(foot, X, -cu), up, -cv), X, up, -1))]


@decoration("Display", "paper")
def _display_flyers(box):
    """A stack of flyers (x − 4 wide, h tall, 3 mm) standing on the shelf against the panel."""
    low, up, fwd, foot = _display_lean(box)
    w = box.x - 4
    return Placement(_add(foot, up, low + box.thickness), X, up, 1).pieces([rect(-w / 2, 0, w / 2, box.h)], 3)


def _carbonfilter_pieces(part, upright=lambda q: True):
    """The pieces of a part drawn as rows of them, left to right: [(piece, frame)], those drawn
    upside down after the others (upright(piece) says which: the outer ribs' second row); the frame
    putting the piece's bounding box's lower left corner at local (0, 0), turned upright first (the
    piece is given in it). Outlines left open by a hair (the outer ribs') are closed."""
    local, cuts = local_matrix(part.record), []
    polys = polygons_of(loops_of(part, local, cuts)) or [
        max(getattr(g, "geoms", [g]), key=lambda g: g.area) for g in (Polygon(c).buffer(0) for c in cuts if len(c) > 2)]
    out = []
    for q in sorted(polys, key=lambda q: (not upright(q), q.bounds[0])):
        x0, y0, x1, y1 = q.bounds
        turn = Affine.identity() if upright(q) else Affine.rotation(180, ((x0 + x1) / 2, (y0 + y1) / 2))
        frame = Affine.translation(-x0, -y0) * turn
        out.append((affine_transform(q, frame.to_shapely()), frame * local))
    return out


def _carbonfilter_foot_down(q):
    """An outer rib stands on its wide rounded foot, its tip up."""
    x0, y0, x1, y1 = q.bounds
    return q.intersection(rect(x0, y0, x1, y0 + 10)).area > q.intersection(rect(x0, y1 - 10, x1, y1)).area


@recipe
def CarbonFilter(box, parts):
    """The end plates (x × h) at Y = -t..0 and y..y + t, everything else between them along Y,
    where their finger holes are. Each of the V pockets (w wide, from X = t) has its bottom plate
    lying at Z 3t..4t and, on each slope, an outer and an inner top rail tilted by a, 50 deep from
    the top, the charcoal layer between them. Ribs stand across Y in the bottom plate's holes:
    those of the left slopes at the holes drawn from the plate's first edge, those of the right
    slopes at the mirrored ones (3t beside them, so they pass each other); the rails are turned
    to match. Inner ribs (straight tops) lean in from the middle of the plate to the inner rail;
    outer ribs stand on the floor under the plate's edge, along the outer rail, their tops out to
    the side bar (the pointier ones, on the outer slopes) or the next pocket. The side holders lie
    on the end plates outside the charcoal, under the rails; the top stabilizers lie across
    three pairs of inner ribs, hooked on them."""
    t, x, y, h, w, R = box.thickness, box.x, box.y, box.h, box.w, box.ribs
    P = box.pockets
    a = math.radians(box.a)
    s, c = math.sin(a), math.cos(a)
    ys = [(i + 1) * y / (R + 1) - 1.5 * t for i in range(R)]     # the ribs' mid-planes (left slopes)
    left, right = (-1, 0, 0), X
    out = []
    by = {}
    for part in parts:
        by.setdefault(part.record.caller if part.record.primitive is None else part.record.label, []).append(part)
    ends, bars = by[None][:2], by["Sides"]
    out += [(ends[0], Placement((0, 0, 0), X, Z, 1)), (ends[1], Placement((0, y, 0), X, Z, -1)),
            (bars[0], Placement((0, 0, h - 50), Y, Z, 1)), (bars[1], Placement((x, 0, h - 50), Y, Z, -1))]
    rails = iter(by["Top rails"])
    inner = iter(_carbonfilter_pieces(by["innerRibs"][0]))
    outer = _carbonfilter_pieces(by["outerRibs"][0], _carbonfilter_foot_down)
    edge, others = iter(outer[:2 * R]), iter(outer[2 * R:])   # the pointier ones are drawn first
    holders = iter(_carbonfilter_pieces(by["sideHolders"][0]))
    stabs = iter(_carbonfilter_pieces(by["topStabilizers"][0]))
    at_origin = lambda q: abs(q.bounds[0]) < 1 and abs(q.bounds[1]) < 1

    def piece(part, it, place, closed=False):
        q, frame = next(it)
        # an outline the generator left open is given whole, as the sheet of a part of no holes
        keep = dict(keep=lambda p: False, plate=q) if closed else dict(keep=at_origin)
        out.append((part, Placement(*place, **keep), frame))

    for k in range(P):
        posx = t + k * w
        plate = posx + w / 2 - 50 + t                              # the bottom plate's left edge
        out.append((by["bottom plate"][k], Placement((plate, 0, 3 * t), Y, X, -1)))
        for d, sgn in ((left, 1), (right, -1)):
            # rails: centred on the holes from (u0, h) down the slope, v = 0 at their lower end
            slope_up = (-s * sgn, 0, c)
            for u0 in ((posx + t / 2, posx + 40 + t / 2) if sgn > 0 else (posx + w - t / 2, posx + w - 40 - t / 2)):
                bottom = (u0 + 50 * s * sgn, 0, h - 50 * c)
                if sgn > 0:
                    out.append((next(rails), Placement(_add(bottom, (c, 0, s), -t / 2), Y, slope_up, 1)))
                else:
                    out.append((next(rails), Placement(_add((bottom[0], y, bottom[2]), (-c, 0, s), -t / 2),
                                                       (0, -1, 0), slope_up, 1)))
            mids = ys if sgn > 0 else [y - m for m in ys]
            # where the slope's outer and inner rib start at the plate (their far end from the layer)
            x_out, x_in = (plate + 12, plate + 57) if sgn > 0 else (plate + 82, plate + 37)
            outer_it = edge if (k == 0 and sgn > 0) or (k == P - 1 and sgn < 0) else others
            ribs = by["outerRibs"][0], by["innerRibs"][0]
            for m in mids:
                piece(ribs[0], outer_it, ((x_out, m - t / 2, 0), d, Z, sgn), closed=True)
                piece(ribs[1], inner, ((x_in, m - t / 2, 3 * t), d, Z, sgn))
            # side holders, 10 wide outside the charcoal, on both end plates
            for x0 in ((plate, plate + 47) if sgn > 0 else (plate + 94, plate + 47)):
                for y0, side in ((0, sgn), (y, -sgn)):
                    piece(by["sideHolders"][0], holders, ((x0, y0, 4 * t), d, Z, side))
    # stabilizers: across the gap between a pocket's two inner ribs (l apart where they hook)
    n = min(3, R)
    l = 2 * (h - 60) * s - 20
    z = 4 * t + (l + 20) / (2 * math.tan(a))
    for k in range(P):
        mid = t + k * w + w / 2
        for m in range(n):
            i = int((m + 0.5) * R / n)
            piece(by["topStabilizers"][0], stabs, ((mid - (l + 4 * t) / 2, ys[i] - 1.5 * t, z), Y, X, -1))
    return out


# ---------------------------------------------------------------- Hook, PoleHook

@recipe
def Hook(box, parts):
    """Hung on the wall, the back plate's back at Y = t: the plate standing (X along its width), the
    two side profiles in its finger holes (their back edge, drawn f.margin() in from their start, on
    its front face), the hook reaching forward (−Y). The mouth's floor lies on the sides' support
    edge (h_a + strength up), the post's inner wall stands on it d forward, the post's top closes it
    at the hook's height."""
    t, d, h = box.thickness, box.depth, box.height
    w = box.width - 2 * t
    z0 = box.h_a + box.strength  # the mouth's floor
    m = box.edges["f"].margin()
    fwd = (0, -1, 0)
    return [Placement((0, 0, 0), X, Z, -1),
            Placement((t, m, 0), fwd, Z, -1), Placement((w + 2 * t, m, 0), fwd, Z, -1),
            Placement((2 * t, 0, z0), fwd, X, 1),
            Placement((2 * t, -d, z0 + t), Z, X, -1),
            Placement((2 * t, -d - t, z0 + h), fwd, X, 1)]




def _polehook_frame(box):
    """(Z of the forks' base line, the pin's (X, Z), the pole's centre (X, Z)): the forks stand
    across X centred on the disc stack, on seven layers (the knob's three, the four discs)."""
    t, d, w = box.thickness, box.diameter, box.ww
    zb = 7 * t
    return zb, (d / 2 + w / 2, zb + 2 * d), (0.0, zb + d)


@recipe
def PoleHook(box, parts):
    """Standing on its knob: the two knob layers with the screw head's hex hole at the bottom, the
    one with the screw hole on them, then the four big discs (the clamp disc, with its strap slot,
    third from the top), the one with the forks' finger holes on top. The five forks stand on it
    across X, side by side (Y −2.5t..2.5t): the two full ones outside (their tall arm's pin hole on
    top), the finger-jointed short one in the middle, the plain short ones between; their U round the
    pole, which lies across Y. The three lock layers turn on the pin through the tall arms, in the
    gap between them: one arm on the line to the pole's centre (its end on the pole), the other up
    over the opening. The two small discs cap the pin outside the full forks."""
    t, d, w = box.thickness, box.diameter, box.ww
    tw = d + 2 * w
    zb, (px, pz), (cx, cz) = _polehook_frame(box)
    mf = box.edges["f"].margin()
    out = []
    for i, n in enumerate((9, 10, 11, 8, 7, 6, 5)):
        out.append((parts[n], Placement((0, 0, i * t), X, Y, 1)))
    for n, c in zip((0, 3, 2, 4, 1), (-2, -1, 0, 1, 2)):
        m = mf if n < 3 else 0.0  # the plain forks' bottom edge has no fingers
        out.append((parts[n], Placement((-tw / 2, c * t + t / 2, zb - m), X, Z, 1)))
    ux, uz = cx - px, cz - pz
    k = math.hypot(ux, uz)
    U, V = (ux / k, 0, uz / k), (uz / k, 0, -ux / k)
    for i in range(3):
        o = _add(_add((px, -1.5 * t + i * t, pz), U, -w / 2), V, -w / 2)
        out.append((parts[12 + i], Placement(o, U, V, 1)))
    out += [(parts[15], Placement((px, -2.5 * t, pz), X, Z, 1)), (parts[16], Placement((px, 2.5 * t, pz), X, Z, -1))]
    return out


@decoration("PoleHook", "grip-red")
def _polehook_pole(box):
    """The pole in the forks' U, 3 diameters long."""
    _, _, (cx, cz) = _polehook_frame(box)
    d = box.diameter
    return _rod("grip-red", (cx, 0, cz), Y, X, (0, 0), d / 2, -1.5 * d, 1.5 * d, segs=24)


@decoration("PoleHook", "steel")
def _polehook_pin(box):
    """The pin through the tall arms and the lock, into the caps."""
    t = box.thickness
    _, (px, pz), _ = _polehook_frame(box)
    return _rod("steel", (px, 0, pz), Y, X, (0, 0), box.pin / 2 - 0.1, -3.5 * t, 3.5 * t)


@recipe
def NightLightBox(box, parts):
    """The box on its stackable feet: the floor's top face at the s edges' finger holes (Z = f),
    front at Y = 0 (its window), back at Y = y (seen from outside), the sides on the feet (u = Y
    from the front: the plates' slots at the front of their top, the hinge at the back). On the
    floor's finger holes two rails (1.5t in from the sides, the diffuser's notch at the back end);
    the art plates and the diffuser stand on the floor in their notches, the plates' ears in the
    sides' top slots. The electronics' top lies in the sides' F edges, its plain 1.5t at the back
    (at the front it would sit on the diffuser); a guide through each side's square hole in
    front of the diffuser's top; the lid on top (u = Y, its pins in the sides' hinge eyes).
    Extra customizable face: the face in front of the front wall, a peg through the first two
    of their square holes. The plates (WoodPlateThickness, DiffuserPlateThickness) are cut from the
    box's thickness here, centred in their slots."""
    t, M, n = box.thickness, box.Margin, box.WoodPlatesCount
    minimal = box.BoxStyle == "minimalist"
    s = box.edges["s"].settings
    f = s.height + s.holedistance + t                      # the floor's top face
    y = box.BackgroundDepth + box.DiffuserPlateThickness + (box.WoodPlateThickness + box.InterPlateSpacing) * n \
        + box.InterPlateSpacing
    x = box.PlateVisibleWidth + t * (4 if minimal else 8) + M
    h = box.PlateVisibleHeight + t * (4 if minimal else 8) + M
    rail_end = box.InterPlateSpacing + t - M / 2 + box.DiffuserPlateThickness \
        + (box.InterPlateSpacing + box.WoodPlateThickness) * n          # the rails' back end (u = 0): start + length
    plate_w = box.PlateVisibleWidth + t * (6 if minimal else 10)
    first = y - box.BackgroundDepth - box.DiffuserPlateThickness - box.InterPlateSpacing \
        - (box.WoodPlateThickness + M) / 2                              # the backmost plate's middle
    by_caller = lambda c: [p for p in parts if p.record.caller == c]
    walls = {p.record.label: p for p in parts if p.record.primitive}
    back = (0, -1, 0)
    out = [(p, Placement((xs, 0, 0), Y, Z, side)) for p, xs, side in zip(by_caller("side"), (0, x), (-1, 1))]
    out += [(p, Placement((xr + t / 2, rail_end, f), back, Z, 1))
            for p, xr in zip(by_caller("rail"), (1.5 * t, x - 1.5 * t))]
    out += [(walls["bottom"], Placement((0, 0, f), X, Y, -1)),
            (walls["back"], Placement((x, y, f), (-1, 0, 0), Z, 1)),
            (walls["front"], Placement((0, 0, f), X, Z, 1)),
            (walls["lid top"], Placement((0, 0, f + h), Y, X, -1, lid=True))]
    # the electronics' top: its v = 0 (the plain 1.5t before its f edge) 1.5t behind the sides' F edge
    out += [(p, Placement((0, y - 3.5 * t, f + h), X, back, 1)) for p in by_caller("elecCompartmentTop")]
    guide_y = y - box.BackgroundDepth - box.DiffuserPlateThickness - t - 1.5 * M
    guide_z = box.PlateVisibleHeight + t * (4 if minimal else 8)            # the side's square hole (Z = its v)
    out += [(p, Placement((xg, guide_y, guide_z), X, Z, -1))
            for p, xg in zip([q for q in parts if q.record.label == "guide"], (-t, x - t))]
    dy = y - box.BackgroundDepth - box.DiffuserPlateThickness / 2 - M / 2
    out += [(p, Placement((M, dy - t / 2, f), X, Z, -1)) for p in by_caller("diffuserPlate")]
    out += [(p, Placement(((x - plate_w) / 2, first - i * (box.WoodPlateThickness + box.InterPlateSpacing) - t / 2, f),
                          X, Z, -1)) for i, p in enumerate(by_caller("woodPlate"))]
    if "customizable face" in walls:
        out.append((walls["customizable face"], Placement((0, -t, f), X, Z, 1)))
        pegs = [p for p in parts if p.record.primitive and p.record.label is None]
        out += [(p, Placement((cx - t / 2, -2 * t, f + t), Y, X, -1))
                for p, cx in zip(pegs, (1.5 * t, box.PlateVisibleWidth / 2 + 4 * t + M / 2))]
    return out


def _trianglelamp_copies(part):
    """rectangularTriangle(…, num=n) draws its triangles in one part, every other one turned half
    round: for each, (frame, keep) bringing it onto the first, as drawn (the right angle at local
    (leg, 0)), and keeping it there."""
    local = local_matrix(part.record)
    polys = _part_polys(part)
    first = min(polys, key=lambda q: abs(q.bounds[0]) + abs(q.bounds[1]))  # the one drawn from the origin
    c1 = first.envelope.centroid
    here = first.centroid
    keep = lambda p: abs(p.centroid.x - here.x) < 1 and abs(p.centroid.y - here.y) < 1
    out = []
    for q in polys:
        cq = q.envelope.centroid
        moved = affine_transform(q, Affine.translation(c1.x - cq.x, c1.y - cq.y).to_shapely())
        if first.symmetric_difference(moved).area < 0.05 * first.area:
            frame = Affine.translation(c1.x - cq.x, c1.y - cq.y)
        else:  # turned half round about the middle of the two envelopes
            frame = Affine.translation(c1.x + cq.x, c1.y + cq.y) * Affine.rotation(180)
        out.append((frame * local, keep))
    return out


@recipe
def TriangleLamp(box, parts):
    """Two lamps (every part is drawn twice), side by side 30 mm apart, each standing on its
    hypotenuse wall, the screen at the front: the fff triangle at the back, the walls standing on
    its edges (inner faces on them; the leg wall with the f end on the leg from the top corner
    down, as seen from outside), the corner triangles in the walls' finger holes 1.5t below the
    top (the ffe one in the right angle, the fef ones in the 45° corners) and the screen on them,
    flush with the walls' front edge. In the lamp's own frame (a, b along the legs from the right
    angle, w from the back to the front) every part is placed by where its local axes go."""
    t, x, h, c = box.thickness, box.x, box.h, box.cornersize
    s = math.sqrt(0.5)
    da, db, dw = (-s, 0, -s), (s, 0, -s), (0, -1, 0)
    neg = lambda d: tuple(-q for q in d)
    hyp = _norm(_add(db, da, -1))
    step = x / s + 30

    def place(k, a, b, w, U, V, D, keep=None):
        """Local (0, 0) at (a, b, w) of lamp k, the thickness towards D."""
        origin = ((x + b - a) * s + k * step, h - w, t + (x - a - b) * s)
        side = 1 if sum(n * d for n, d in zip(_cross(U, V), D)) > 0 else -1
        return Placement(origin, U, V, side, keep=keep)

    screen, base, ffe, fef = parts[0], parts[1], parts[8], parts[9]
    out = []
    for k in range(2):
        out += [(parts[2 + k], place(k, 0, x, 0, neg(db), dw, neg(da))),        # on the b leg, its f end at the right angle
                (parts[4 + k], place(k, 0, 0, 0, da, dw, neg(db))),             # on the a leg
                (parts[6 + k], place(k, x, 0, 0, hyp, dw, _add(da, db)))]       # on the hypotenuse
    for part, w, D in ((base, 0, neg(dw)), (screen, h - t, dw)):
        out += [(part, place(k, x, 0, w, neg(da), db, D, keep), frame)
                for k, (frame, keep) in enumerate(_trianglelamp_copies(part))]
    out += [(ffe, place(k, c, 0, h - 2 * t, neg(da), db, dw, keep), frame)
            for k, (frame, keep) in enumerate(_trianglelamp_copies(ffe))]
    for i, (frame, keep) in enumerate(_trianglelamp_copies(fef)):
        k, corner = divmod(i, 2)
        out.append((fef, place(k, x, 0, h - 2 * t, neg(da), db, dw, keep) if corner == 0 else
                    place(k, 0, x, h - 2 * t, neg(db), da, dw, keep), frame))
    return out


@recipe
def BookHolder(box, parts):
    """The sides standing at X = -t and X = width (u = Y from the low front, the tall back at the
    back), the plates in their F edges, flush with the profile: the book back on the slope from
    the corner C where it meets the book bottom (its bottom fingers down in the book bottom's F
    end, behind C), the book bottom from its front end down to C, the back support standing in
    the sides' finger holes 2t in from their back edge, bottom_support up. The front ledge stands
    at the book bottom's front end, its F edge round the bottom's front fingers, rising
    ledge_height above it."""
    t, r, w = box.thickness, box.radius, box.width
    a = math.radians(box.angle)
    C = (r + r * math.cos(a) + box.book_depth * math.sin(a), box.bottom_support)    # as sideWall draws it
    W = C[0] + box.book_height * math.cos(a) + r * math.sin(a) + r                   # the sides' depth
    up = (0, math.cos(a), math.sin(a))                 # along the slope, upwards
    back = (0, math.sin(a), -math.cos(a))              # along the book bottom, from its front to C
    front = _add((0, *C), back, -box.book_depth)       # the book bottom's front end
    walls = {p.record.label: p for p in parts}
    sides = [p for p in parts if p.record.caller == "sideWall"]
    out = list(zip(sides, [Placement((0, 0, 0), Y, Z, -1), Placement((w, 0, 0), Y, Z, 1)]))
    out += [(walls["book back"], Placement((0, *C), X, up, -1)),
            (walls["book bottom"], Placement(front, X, back, -1))]
    if "back support" in walls:
        out.append((walls["back support"], Placement((0, W - 1.5 * t, box.bottom_support), X, Z, 1)))
    out += [(p, Placement(_add(front, up, box.ledge_height), X, tuple(-c for c in up), -1))
            for p in parts if p.record.caller == "front_ledge"]
    return out


@recipe
def Shadowbox(box, parts):
    """Standing like a picture frame, x across, y up, on its bottom case wall: the mitered
    faceplate at the front (Y 0..t, its outer edge t round the case walls, which stand in its F
    edges from the back), the layer frames stacked behind it inside the case (each two
    horizontal bars, their dovetail sockets inwards, and two vertical bars between them; no
    paper between them), the LED strip holder's ring of walls inside the case at its back, and
    the back panels the back edge asks for (drawLid's), as lids."""
    t, x, y, L = box.thickness, box.x, box.y, box.layers
    fh, fw = box.frameheight, box.framewidth
    H = L * t + box.extraheight
    rear = t + H                                         # the case walls' back end
    fwd = (0, -1, 0)
    out = []
    for i in range(L):
        yl = t + i * t
        out += [(parts[2 * i], Placement((0, yl, t), X, Z, -1)),
                (parts[2 * i + 1], Placement((x, yl, t + y), (-1, 0, 0), (0, 0, -1), -1)),
                (parts[2 * L + 2 * i], Placement((0, yl, t + fh), Z, X, 1)),
                (parts[2 * L + 2 * i + 1], Placement((x - fw, yl, t + fh), Z, X, 1))]
    face = parts[4 * L:4 * L + 4]
    out += [(face[0], Placement((-t, 0, 0), Z, X, 1)),
            (face[1], Placement((x + t, 0, y + 2 * t), (0, 0, -1), (-1, 0, 0), 1)),
            (face[2], Placement((-t, 0, 0), X, Z, -1)),
            (face[3], Placement((x + t, 0, y + 2 * t), (-1, 0, 0), (0, 0, -1), -1))]
    case = parts[4 * L + 4:4 * L + 8]
    out += [(case[0], Placement((0, rear, t), X, fwd, 1)), (case[1], Placement((0, rear, t + y), X, fwd, -1)),
            (case[2], Placement((0, rear, t), Z, fwd, -1)), (case[3], Placement((x, rear, t), Z, fwd, 1))]
    ring = parts[4 * L + 8:4 * L + 12]
    out += [(ring[0], Placement((t, rear, 2 * t), X, fwd, 1)), (ring[1], Placement((t, rear, y), X, fwd, -1)),
            (ring[2], Placement((t, rear, 2 * t), Z, fwd, -1)), (ring[3], Placement((x - t, rear, 2 * t), Z, fwd, 1))]
    backs = parts[4 * L + 12:]
    for p, yb in zip(backs, [rear + t, rear] if box.back_edge == "E" else [rear]):
        out.append((p, Placement((0, yb, t), X, Z, -1, lid=True)))
    return out


@decoration("Shadowbox", "paper")
def _shadowbox_back_layer(box):
    """The blank back paper layer, behind the last frame (the cut paper layers between the
    frames are the user's art: left out)."""
    t = box.thickness
    return Placement((0, t + box.layers * t, t), X, Z, -1).pieces([rect(0, 0, box.x, box.y)], 0.2)


def _fatballdispenser_layout(box):
    """What the recipe and the decorations share: n, the radii render() works out, the cage's
    inner height (2.4 balls: not a parameter; the reference build's poles are 190 mm) and the
    corner angles (degrees) of the polygons, all turned alike: the first side at the front."""
    n, t = box.sides, box.thickness
    ar_base = math.radians((180 - 360 / n) / 2)
    r_clearance = box.pole_clearance / math.sin(ar_base)
    r_pole = box.pole_diameter / 2
    r_poles = box.ball_diameter / 2 + max(r_pole, r_clearance) + r_pole
    r_floor = r_poles + r_pole + max(box.balcony_width, r_clearance, r_pole)
    r_ceiling = r_poles + r_pole + max(r_clearance, r_pole)
    corners = [-90 - 180 / n + k * 360 / n for k in range(n)]
    return SimpleNamespace(n=n, r_poles=r_poles, r_floor=r_floor, r_ceiling=r_ceiling,
                           r_roof=r_floor + box.roof_overhang, H=2.4 * box.ball_diameter, corners=corners)


@recipe
def FatBallDispenser(box, parts):
    """Centred on the Z axis, every polygon turned alike (its first side, local v = 0, at
    the front): the floor on Z = 0, the balcony walls standing in its F edge (outer face on its
    outer edge, u from the left as seen from outside; the chamfers to sand are not modelled, their
    corners overlap inside), the ceiling 2.4 balls above the floor (see the layout), in the
    spacer's U on the bracket's lip, the roof bottom plate on the spacer, the roof tiles on it
    from its edges up to the apex roof_height above (their base on its top face), and the roof
    support inside the roof where the tiles' inner faces meet its edge."""
    t = box.thickness
    g = _fatballdispenser_layout(box)
    n, H = g.n, g.H
    a = math.pi / n

    def polygon(r, z, edge="e"):
        """A regularPolygonWall (or a lock part) r round, centred on the Z axis, its bottom at z."""
        sw = box.edges[edge].startWidth() if edge != "e" else 0
        return Placement((-r * math.sin(a), -r * math.cos(a) - sw, z), X, Y, 1)

    flat = [p for p in parts if p.record.caller == "render"]          # ceiling, roof base, floor[, support]
    walls = [p for p in parts if p.record.caller == "balcony_wall"]
    locks = [p for p in parts if p.record.caller == "lock_part"]      # spacer, bracket
    tiles = [p for p in parts if p.record.caller == "roof_tile"]
    top = 3 * t + H                                                    # the roof bottom plate's top face
    r_outer = g.r_ceiling + box.slide_clearance + box.spacer_width
    out = [(flat[0], polygon(g.r_ceiling, t + H)), (flat[1], polygon(g.r_roof, 2 * t + H)),
           (flat[2], polygon(g.r_floor, 0, "F" if walls else "e")),
           (locks[0], polygon(r_outer, t + H)), (locks[1], polygon(r_outer, H))]
    h_floor, h_roof = g.r_floor * math.cos(a), g.r_roof * math.cos(a)
    L = 2 * (h_floor + t) * math.tan(a)                                # a wall's length: the floor's outer side
    for k, (p, tile) in enumerate(zip(walls or [None] * n, tiles)):
        phi = math.radians(-90 + k * 360 / n)
        nk, tk = (math.cos(phi), math.sin(phi), 0), (-math.sin(phi), math.cos(phi), 0)
        if p is not None:
            out.append((p, Placement(_add(_add((0, 0, t), nk, h_floor + t), tk, -L / 2), tk, Z, -1)))
        up = _norm(_add((0, 0, box.roof_height), nk, -h_roof))
        out.append((tile, Placement(_add(_add((0, 0, top), nk, h_roof), tk, -g.r_roof * math.sin(a)), tk, up, -1)))
    if len(flat) > 3:  # the support: its bottom face's edge on the tiles' inner faces
        r_s = box.roof_support_fraction * g.r_roof
        slope = math.atan2(box.roof_height, h_roof)
        z = top + box.roof_height * (1 - (r_s * math.cos(a) + t / math.sin(slope)) / h_roof)
        out.append((flat[3], polygon(r_s, z)))
    return out


@decoration("FatBallDispenser", "dowel")
def _fatballdispenser_poles(box):
    """The poles (beech rods) at the polygons' corners, through the floor and the ceiling."""
    t, g = box.thickness, _fatballdispenser_layout(box)
    return [p for c in g.corners
            for p in _rod("dowel", (0, 0, 0), Z, X, (g.r_poles * math.cos(math.radians(c)),
                                                      g.r_poles * math.sin(math.radians(c))),
                          box.pole_diameter / 2, 0, 2 * t + g.H)]


@decoration("FatBallDispenser", "cardboard")
def _fatballdispenser_balls(box):
    """Two fat balls stacked on the floor, as slices."""
    t, r = box.thickness, box.ball_diameter / 2 - 1
    out, k = [], 12
    for b in range(2):
        z0 = t + b * 2 * r
        for i in range(k):
            zc = -r + (i + 0.5) * 2 * r / k
            out += _solid("cardboard", Placement((0, 0, z0 + r + zc - r / k), X, Y, 1),
                          Point(0, 0).buffer(math.sqrt(r * r - zc * zc), quad_segs=8), 2 * r / k)
    return out


KAMISHIBAI_DOORS_OPEN = 100  # degrees the two-part front doors are shown open by (the window behind them)


@recipe
def Kamishibai(box, parts):
    """The sheets' slot wi × di × hi between the front wall (Y = 0, its window) and the back wall,
    on the bottom plate, under the top plate (both u = X from -4t, v from the back). The extra
    depths: strips in the plates' side finger holes (X -t..0 and wi..wi+t) behind the back wall
    and in front of the front wall; the side panels slide in at X -3t..-2t (and wi + 2t), Y 0..di,
    their two inner plates behind them filling X -2t..0, a peg through the three at each hole; the
    back panel slides in behind the back strips (seen from the back), the slide-on front panel in
    front of the front strips. The handle: its ceiling in the walls' finger holes 1.5t under the
    top, the HandleThickness plates standing side by side across the middle on it, their tabs in
    its holes, the four holders lying on it (Y 0..di) through their holes and notches, the grip
    through the top. The two-part front: the doors outside the plates' front edge, their pins in
    the plates' hinge eyes, shown opened KAMISHIBAI_DOORS_OPEN degrees; on the left one the main
    lock (outside: knob, external disc; the disc cut from the door; inside: the internal disc, its
    round side over the right door), on the right one the top and bottom locks (grip outside;
    the cut disc; internal, spacer, locker inside, the locker's round side towards the strip
    standing in the plate behind the door), pegs through the stacks. The three-part cover is never
    drawn (render() compares the style with a misspelt name). The key hangs on its peg at the back."""
    t, M, PWM = box.thickness, box.Margin, box.PegsWidthMargin
    HT, HW = box.HandleThickness, box.HandleWidth
    hi = box.SheetHeight + 2 * M + (2 * t if HT > 0 else 0)
    wi, di = box.SheetWidth + M, box.SheetsStackDepth + M
    bed, fed, style = box.BackExtraDepth, box.FrontExtraDepth, box.FrontCoverStyle
    back_y, Yo = (0, -1, 0), -(fed + 2) * t               # the front covers' outer face
    by = lambda c: [p for p in parts if p.record.caller == c]
    labelled = lambda c, label: [p for p in by(c) if p.record.label == label]
    solid = lambda c: [p for p in by(c) if _part_polys(p)]  # the locks' moves leave empty parts
    front, back = by("boxFrontBack")
    top, bottom = by("boxTopBottom")
    plate_y = di + (bed + 3) * t                          # the plates' v = 0 (their back edge)
    out = [(front, Placement((-2 * t, 0, 0), X, Z, 1)), (back, Placement((-2 * t, di, 0), X, Z, -1)),
           (top, Placement((-4 * t, plate_y, hi), X, back_y, -1)),
           (bottom, Placement((-4 * t, plate_y, 0), X, back_y, 1))]
    # the open sides' strips, the first drawn on the right (its N edge with the walls' N)
    out += [(p, Placement((x0, di + t + p.record.args[1], 0), Z, back_y, s))
            for p, (x0, s) in zip(labelled("boxOpenSide", "back side"), ((wi, 1), (0, -1)))]
    out += [(p, Placement((x0, -t - p.record.args[1], 0), Z, Y, s))
            for p, (x0, s) in zip(labelled("boxOpenSide", "front side"), ((wi, -1), (0, 1)))]
    panels, inners = labelled("coverPanel1Lid", "side panel"), labelled("coverPanel1Lid", "side panel inner")
    pegs = labelled("coverPanel1Lid", "")
    for i, (xo, s) in enumerate(((wi, 1), (0, -1))[:len(panels)]):       # xo: the slot's side, s: outwards
        out.append((panels[i], Placement((xo + 2 * s * t, 0, 0), Y, Z, s)))
        out += [(q, Placement((xo + k * s * t, M / 2, 2 * t), Y, Z, s)) for q, k in zip(inners[2 * i:2 * i + 2], (1, 0))]
        out += [(q, Placement((xo if s > 0 else -3 * t, (di - t - PWM) / 2, z - t / 2), Y, X, -1))
                for q, z in zip(pegs[2 * i:2 * i + 2], (3.5 * t, hi - 5.5 * t))]
    if HT > 0 and HW > 0:
        handle = by("topHandle")
        plates, holders, ceiling = handle[:HT], handle[HT:HT + 4], handle[-1]
        out.append((ceiling, Placement((0, -2 * t, hi - 2 * t), X, Y, 1)))
        out += [(p, Placement((0, (di - HT * t) / 2 + i * t, hi - 2 * t), X, Z, -1)) for i, p in enumerate(plates)]
        xs = (t, (wi - HW) / 2 + t, (wi + HW) / 2 - 4 * t, wi - 4 * t)
        out += [(p, Placement((x, 0, hi - t), Y, X, -1)) for p, x in zip(holders, xs)]
    yb = di + (bed + 1) * t                               # the back panel's inner face
    out += [(p, Placement((wi, yb, 0), (-1, 0, 0), Z, 1)) for p in labelled("coverPanel1Lid", "back panel")]
    out += [(p, Placement((wi - 2 * t - (t + PWM) / 2, yb, 1.5 * t), Y, X, -1))
            for p in labelled("coverPanel1Lid", None)]    # the key's peg, out of the back panel
    out += [(p, Placement((0, -(fed + 1) * t, 0), X, Z, 1)) for p in labelled("coverPanel1Lid", "front panel")]

    def on(pane, at, a=(1, 0, 0), b=(0, 1, 0), d=(0, 0, 1), keep=None):
        """A piece on a front pane: local (0, 0) at pane (u, v, w) at (w inwards from its outer
        face), its u, v along a, b and its thickness along d, in the pane's (u, v, w)."""
        O, Eu, Ev, turn = pane
        m = lambda c: tuple(c[0] * Eu[i] + c[1] * Ev[i] + c[2] * Y[i] for i in range(3))
        U, V = m(a), m(b)
        side = 1 if sum(n * e for n, e in zip(_cross(U, V), m(d))) > 0 else -1
        place = Placement(_add(O, m(at)), U, V, side, keep=keep)
        return _turned(place, *turn) if turn else place

    def stack(pane, door, c, r, discs, pegs_):
        """A lock round the hole at c (r round) of door: discs [(part, w, a, b)], the disc cut
        from the door in its place, pegs [(part, u offset)] through the stack from its outer face."""
        w0 = min(w for _, w, _, _ in discs)
        res = [(p, on(pane, (c[0], c[1], w), a, b)) for p, w, a, b in discs]
        res.append((_hinge_disc(door, c, r + 0.5), on(pane, (0, 0, 0))))
        return res + [(p, on(pane, (c[0] + du - (t + PWM) / 2, c[1] - t / 2, w0), (0, 0, 1), (1, 0, 0), (0, 1, 0)))
                      for p, du in pegs_]

    key = solid("lockWithKey")
    if style == "two-part lid with hinge eyes (both ends)":
        right, left = by("coverPanel2Side")
        tabs = _part_polys(left)[0].intersection(rect(-20, hi + 0.5, wi, hi + 20))   # the pin, then the outset top
        pin = min(getattr(tabs, "geoms", [tabs]), key=lambda g: g.bounds[0]).centroid.x
        a = KAMISHIBAI_DOORS_OPEN
        lpane = ((-3 * t, Yo, 0), X, Z, ((-3 * t + pin, Yo + t / 2, 0), Z, -a))
        rpane = ((wi + 3 * t, Yo, 0), (-1, 0, 0), Z, ((wi + 3 * t - pin, Yo + t / 2, 0), Z, a))
        out += [(right, on(rpane, (0, 0, 0))), (left, on(lpane, (0, 0, 0)))]
        quarter, half = ((0, 1, 0), (-1, 0, 0)), ((-1, 0, 0), (0, -1, 0))   # a disc's x along the pane's v / -u
        if key:   # external, front, internal (its side holes along x), two pegs, key
            out += stack(lpane, left, ((wi - M) / 2 - 1.5 * t, hi / 2), 3.5 * t,
                         [(key[1], -2 * t, *quarter), (key[0], -t, *quarter), (key[2], t, *half)],
                         [(key[3], -2 * t), (key[4], 2 * t)])
        simple = solid("lockSimple")
        if simple:   # external, grip, internal, peg
            out += stack(lpane, left, ((wi - M) / 2, hi / 2), 2 * t,
                         [(simple[1], -2 * t, X, Y), (simple[0], -t, X, Y), (simple[2], t, *half)], [(simple[3], 0)])
        extra = solid("lockExtra")   # grip, internal, spacer, locker, peg; top then bottom
        for i, (v, flat) in enumerate(((hi - 4 * t, ((0, -1, 0), (1, 0, 0))), (4 * t, quarter))[:len(extra) // 5]):
            g, inner, spacer, locker, peg = extra[5 * i:5 * i + 5]
            out += stack(rpane, right, ((wi - M) / 2 - t, v), 2 * t,
                         [(g, -t, X, Y), (inner, t, X, Y), (spacer, 2 * t, X, Y), (locker, 3 * t, *flat)], [(peg, 0)])
        if extra:   # the strips the lockers catch, standing on the bottom and hanging from the top
            x0 = wi / 2 - 8 * t
            out += list(zip(by("render"), [Placement((x0, -fed * t, 0), X, Z, -1),
                                           Placement((x0, -fed * t, hi), X, (0, 0, -1), 1)]))
    if len(key) > 5:  # the key, hung on its peg by its hole
        out.append((key[5], Placement((wi - 0.5 * t, yb + t, 0.5 * t), (-1, 0, 0), Z, 1)))
    for item in out:  # Z = 0 was the bottom plate's top face: the box on the floor
        item[1].origin = _add(item[1].origin, Z, t)
    return out


@decoration("Kamishibai", "paper")
def _kamishibai_sheets(box):
    """A stack of sheets (half the stack depth) standing in the slot against the front wall."""
    t, M = box.thickness, box.Margin
    return Placement((M / 2, 0, t + M), X, Z, -1).pieces([rect(0, 0, box.SheetWidth, box.SheetHeight)],
                                                         box.SheetsStackDepth / 2)


# ---------------------------------------------------------------- matrix, clamp, clocks, pizza shovel

def _matrix_stack(box):
    """Y of the layers behind the front plate (the frame with the window, its inner face at Y = 0):
    the plexiglass, the two LED grids, the PCB, then the mount frame on its finger holes."""
    p, t = box.plexiglass_thicknes, box.thickness
    return p, p + 2 * t, p + 2 * t + box.height_pcb


@recipe
def Matrix(box, parts):
    """Standing like a picture, the front frame (Top, the window) facing the viewer: the four walls
    h deep along Y (their top edge at the front, Y = 0; the mount frame's finger holes are drawn
    near it), Wall 1 / Wall 3 lying at the bottom / top, Wall 2 / Wall 4 standing left / right with
    their f edges in the F of the lying ones. Behind the front plate the sandwich the holes leave
    room for: the plexiglass (clear, plexiglass_thicknes thick), the two LED grids, the PCB, the mount
    frame on its finger holes; the back (Bottom, with the keyhole) closes the box at Y = h."""
    t, h = box.thickness, box.h
    x, y = parts[0].record.args[0], parts[1].record.args[0]
    plex, grids, pcb = _matrix_stack(box)
    z = t  # the lower wall's outer face on the floor
    return [
        Placement((0, h, z), X, (0, -1, 0), 1),                     # Wall 1, bottom
        Placement((0, h, z), Z, (0, -1, 0), -1),                    # Wall 2, left
        Placement((x, h, z), Z, (0, -1, 0), 1),                     # Wall 4, right
        Placement((0, h, z + y), X, (0, -1, 0), -1),                # Wall 3, top
        Placement((0, 0, z), X, Z, 1),                              # Top: the front with the window
        Placement((0, h, z), X, Z, -1),                             # Bottom: the back
        Placement((0, pcb + t, z), X, Z, 1),                        # the mount frame
        Placement((0, plex + t, z), X, Z, 1),                       # LED grid
        Placement((0, grids, z), X, Z, 1),                          # LED grid
        _thick(Placement((0, plex, z), X, Z, 1, clear=True), plex),  # plexiglass
    ]


@decoration("Matrix", "grip-black")
def _matrix_pcb(box):
    """The LED matrix: a black PCB height_pcb thick against the mount frame, a white LED (half a
    pixel square, 1.6 high) in the middle of each cell of the grid in front of it."""
    z = box.thickness
    _, grids, pcb = _matrix_stack(box)
    o, w, hh = box.matrix_front_frame_border_offset, box.physical_led_x, box.physical_led_y
    sx, sy = w / box.led_width, hh / box.led_height
    s = min(sx, sy) / 4
    leds = [rect(o + (i + .5) * sx - s, o + (j + .5) * sy - s, o + (i + .5) * sx + s, o + (j + .5) * sy + s)
            for i in range(box.led_width) for j in range(box.led_height)]
    return (_solid("grip-black", Placement((0, pcb, z), X, Z, 1), rect(o, o, o + w, o + hh), box.height_pcb) +
            _solid("paint-white", Placement((0, grids, z), X, Z, 1), leds, 1.6))


@recipe
def LaserClamp(box, parts):
    """Standing in the XZ plane as drawn (seen from the front): the bottom part (its foot's hook up)
    at the back, the rounded plate 1.1 t in front of it on the same finger holes, the spacer between
    them (its f edges in both, its thickness across X on the holes' line). The top part slides in
    the gap, the spacer through its slot: shown closed, the spacer at the slot's top end (the jaws
    minheight apart, as the rubber band holds it), everything lifted so its arm stands on the floor."""
    t = box.thickness
    lift = box.maxheight - box.minheight
    return [
        Placement((-4 * t, 1.05 * t, 0), X, Z, -1),          # top part: its slot (at 9 t) on the holes (5 t)
        Placement((0, 0, lift), X, Z, -1),                   # bottom part
        Placement((4 * t, 2.1 * t, lift), X, Z, -1),         # the plate: its holes (at t) on the same line
        Placement((4.5 * t, t, lift + 2 * t), Y, Z, 1),      # the spacer, u across the gap
    ]


def _clock_frame(box):
    """(Re, Rm, Z of the main plate's bottom, Z of the bottom and of the top shelf's underside) of a
    Clock: the front legs stand on the floor, the bottom shelf (its tabs in the plate's lower holes)
    rests on their shoulders, where their spine starts: the toe Tf high, its fillet, the leg at Af
    from the vertical."""
    t, Re = box.thickness, box.ExternalRadius
    Rm = (Re + box.ClockHandsMaxLength + box.Margin) / 2
    Tf, af, ab = (Re - box.ClockHandsMaxLength - box.Margin) / 2, math.pi / 6, math.pi / 6
    shoulder = Tf + Tf / 2 * (1 - math.sin(af)) + Tf * math.cos(af) + Rm * (1 - math.cos(af))
    z0 = shoulder - (Re - Rm * math.cos(ab) - t / 2)
    return Re, Rm, z0, shoulder, z0 + Re - Rm * math.cos(math.pi / 3) - t / 2


@recipe
def Clock(box, parts):
    """Standing, its dial facing the viewer: the main plate (dial etched on its front, at Y = 0)
    with the front ring in front of it; behind it the front legs, glued flat on its back, their feet
    on the floor. The two half-round shelves lie behind the plate, their corner tabs in its four
    square holes; their straight edges are stepped t back, round the legs' spine: the bottom shelf
    rests on the legs' shoulders, the spine runs up through its notch to the top shelf's top face.
    The back leg stands upright in the shelves' end slots (its notches, crossed with theirs, their
    middles on the shelves'), its plain end up, its round foot down."""
    t = box.thickness
    Re, Rm, z0, zbot, ztop = _clock_frame(box)
    ab, at = math.pi / 6, math.pi / 3
    legs = unary_union(_part_polys(parts[2])).bounds
    return [
        Placement((0, 0, z0), X, Z, -1),                                     # main plate
        Placement((0, -t, z0), X, Z, -1),                                    # front ring
        Placement((Re - (legs[0] + legs[2]) / 2, t, 0), X, Z, -1),           # front legs
        Placement((Re - t / 2, box.BackLegDistance, ztop + 2 * t), (0, 0, -1), Y, 1),    # back leg
        Placement((Re - Rm * math.sin(at) - t / 2, 0, ztop), X, Y, 1),       # top shelf
        Placement((Re - Rm * math.sin(ab) - t / 2, 0, zbot), X, Y, 1),       # bottom shelf
    ]


@decoration("Clock", "grip-black")
def _clock_movement(box):
    """A quartz movement (56 × 56 × 16, Re / 2 square at most) behind the plate on the needles' hole,
    its shaft through the hole, and the hands in the ring's recess at ten past ten (the hour hand 0.6
    the length of the minute hand, ClockHandsMaxLength; the second hand red)."""
    t = box.thickness
    Re, _, z0, _, _ = _clock_frame(box)
    L, c = box.ClockHandsMaxLength, (Re, z0 + Re)
    s = min(56.0, 0.5 * Re)
    out = _solid("grip-black", Placement((Re - s / 2, t, c[1] - s / 2), X, Z, -1), rect(0, 0, s, s), 16)
    out += _rod("brass", (0, 0, 0), Y, X, (Re, -c[1]), box.NeedlesAxisHoleDiameter / 2 - 0.3, -2.6, t)

    def hand(length, width, tail, degrees):  # degrees clockwise from 12
        p = Polygon([(-width / 2, -tail), (width / 2, -tail), (width / 4, length), (-width / 4, length)])
        return affine_transform(p, Affine.rotation(-degrees).to_shapely())

    for kind, y, d, poly in (("grip-black", -0.5, 0.6, hand(0.6 * L, 0.08 * L, 0.1 * L, 305)),
                             ("grip-black", -1.2, 0.6, hand(L, 0.06 * L, 0.12 * L, 60)),
                             ("grip-red", -1.9, 0.4, hand(L, 0.015 * L, 0.2 * L, 220))):
        out += _solid(kind, Placement((c[0], y, c[1]), X, Z, 1), [poly, Point(0, 0).buffer(0.06 * L)], d)
    return out




@recipe
def SevenSegmentClock(box, parts):
    """A flat box standing on its long edge, the segment plate (the four digits and the colon cut
    through) facing the viewer at Y = 0, the back plate with the separators' finger holes at Y = h,
    h deep: the two long walls (f ends) lying below and on top, the two short ones (all F) at the
    ends. The separators stand in the back plate's holes, their plain edge against the front plate,
    four digits of them where backCB draws the holes (0.6 height apart, 0.1 more after the second)."""
    t, H, h = box.thickness, box.height, box.h
    y = parts[1].record.args[0]
    z = t  # the lower wall on the floor
    out = [
        (parts[0], Placement((0, 0, z), Z, Y, 1)),        # left end
        (parts[1], Placement((0, 0, z), X, Y, -1)),       # bottom
        (parts[2], Placement((0, 0, z + H), X, Y, 1)),    # top
        (parts[3], Placement((y, 0, z), Z, Y, -1)),       # right end
        (parts[4], Placement((0, 0, z), X, Z, 1)),        # the segments, in front
        (parts[5], Placement((0, h, z), X, Z, -1)),       # the holes, at the back
    ]
    seps = parts[6:]
    for i in range(4):  # 2 n = 8 walls of each of the 6 lengths, two per digit
        walls = [seps[8 * k + 2 * i + half] for k in range(6) for half in range(2)]
        X0 = 0.1 * H + 0.6 * H * i + 0.1 * H * (i // 2)
        out += _seven_segment_separators(t, 0.8 * H, walls, X0, z + 0.1 * H, h)
    return out


# ---------------------------------------------------------------- joint panel, bottle stack, capsules, magazine file, endpin

@recipe
def JointPanel(box, parts):
    """The panel lying flat, its pieces side by side as they are drawn (row by row from the front,
    left to right): each piece's d edges (right and back) dovetailed into the D edges of its
    neighbours."""
    out, y0 = [], 0
    for sy in box.sy:
        x0 = 0
        for sx in box.sx:
            out.append(Placement((x0, y0, 0), X, Y, 1))
            x0 += sx
        y0 += sy
    return out


def _bottlestack_sizes(box):
    """(r1, r3): the bottles' radius, the fronts' end corners; the fronts' first slot is r3 - t/2 in."""
    return box.diameter / 2, 1.5 * box.thickness if box.double else 0.5 * box.thickness


@recipe
def BottleStack(box, parts):
    """The fronts stand across (X) at the two ends of the beams, which lie along Y on their edge,
    2t high: each front's slots (t deep, from below) over a beam's notches (t deep, from above),
    both on the floor. The long beams' notches are t in from their rounded ends: the fronts at
    Y = t…2t and l…l + t. With "double", the second stand (the fronts with the paired slots and the
    short beams) sits inside the first, its fronts on the short beams' low ends, 0.5t inside the
    first's, its deep slots (2t) over the long beams, and slid one bottle along X: the stand made
    one bottle wider (it slides up to double)."""
    t, nr, l = box.thickness, box.number, box.depth
    r1, r3 = _bottlestack_sizes(box)
    pieces = 2 if box.double else 1
    fronts, beams = parts[:2 * pieces], parts[2 * pieces:]
    out = [(fronts[0], Placement((0, t, 0), X, Z, -1)), (fronts[1], Placement((0, l, 0), X, Z, -1))]
    out += [(b, Placement((r3 - t / 2 + k * 2 * r1, 0, 0), Y, Z, 1)) for k, b in enumerate(beams[:nr + 1])]
    if box.double:
        s, y0 = 2 * r1, 1.5 * t
        out += [(fronts[2], Placement((s, y0 + t, 0), X, Z, -1)), (fronts[3], Placement((s, y0 + l - 3 * t, 0), X, Z, -1))]
        slots = [3 * t] + [2 * j * r1 - t for j in range(1, nr + 1)]
        out += [(b, Placement((s + x, y0, 0), Y, Z, 1)) for x, b in zip(slots, beams[nr + 1:])]
    return out


@decoration("BottleStack", "bottle")
def _bottlestack_bottles(box):
    """Beer bottles lying in the fronts' hollows (r1 round, their bottom t up), the neck to the
    front, the body centred on the stand: one in every hollow (one more with "double", the second
    stand slid one bottle along), one more on top in the middle groove. Glass, a paper label, the
    shoulder in steps, a steel cap; 3.2 × r1 long to the shoulder (no length in the generator)."""
    t, nr, l = box.thickness, box.number, box.depth
    r1, r3 = _bottlestack_sizes(box)
    r = r1 - 0.5
    n = nr + (1 if box.double else 0)
    at = (0, (l + 2 * t) / 2 + 1.6 * r1, 0)
    xs = [r3 + r1 + 2 * r1 * k for k in range(n)]
    spots = [(x, t + r) for x in xs]
    if n > 1:
        mid = n // 2
        spots.append(((xs[mid - 1] + xs[mid]) / 2, t + r + math.sqrt(3) * r1))
    out = []
    for i, (x, z) in enumerate(spots):
        glass = ("bottle", "bottle-amber")[i % 2]
        add = lambda kind, rr, a, b: _rod(kind, at, (0, -1, 0), X, (x, z), rr, a, b, segs=16)
        out += add(glass, r, 0, 0.6 * r1) + add("label", r + 0.3, 0.6 * r1, 2.4 * r1) + add(glass, r, 2.4 * r1, 3.2 * r1)
        for j in range(5):  # the shoulder, down to the neck's 0.4 r
            rr = 0.4 * r + 0.6 * r * math.cos(math.pi / 2 * (j + 0.5) / 5)
            out += add(glass, rr, 3.2 * r1 + 0.2 * r1 * j, 3.2 * r1 + 0.2 * r1 * (j + 1))
        out += add(glass, 0.4 * r, 4.2 * r1, 5.0 * r1) + add("steel", 0.45 * r, 5.0 * r1, 5.15 * r1)
    return out


@recipe
def CoffeeCapsuleHolder(box, parts):
    """Upright against the wall, the capsules' entry (the round end of the columns) at the top: the
    front plate (the narrow slots the capsules' bodies stick out of) at Y = 0…t, the middle plate
    (the wide slots the lids slide down in) behind it, the back plate against the wall."""
    t = box.thickness
    return [Placement((0, (i + 1) * t, 0), X, Z, 1) for i in range(len(parts))]




@decoration("CoffeeCapsuleHolder", "capsule-gold")
def _coffeecapsuleholder_capsules(box):
    """A column of capsules in each slot, one colour each, stacked from the slot's bottom end: the
    lid in the middle plate, the body (as wide as body_size at the lid, tapering, lid_size × 0.75
    long: a Nespresso capsule) out of the front plate. Screw heads in the front plate's big holes,
    on the middle plate."""
    t, lid, body = box.thickness, box.lid_size, box.body_size
    L, om = box.lid_size_with_margin, box.outer_margin
    rows = box.rows                     # render() added the opening's 0.6
    top = om + (rows - 0.5) * lid
    kinds = ("capsule-gold", "capsule-red", "grip-black", "paint-blue", "paint-green", "steel")
    at, out = (0, 2 * t, 0), []
    for col in range(box.columns):
        cx, kind = om + col * (L + box.column_spacing) + L / 2, kinds[col % len(kinds)]
        for j in range(int(rows)):
            c = (cx, top - (rows - 1) * lid + j * lid)
            add = lambda rr, a, b: _rod(kind, at, (0, -1, 0), X, c, rr, a, b, segs=16)
            k = lid / 37
            out += add(lid / 2 - 0.5, 0.3, 1.3)
            out += add(body / 2 - 0.5, 1.3, 1.3 + 8 * k) + add(0.85 * body / 2, 1.3 + 8 * k, 1.3 + 18 * k)
            out += add(0.65 * body / 2, 1.3 + 18 * k, 1.3 + 24 * k) + add(0.4 * body / 2, 1.3 + 24 * k, 1.3 + 27 * k)
    W = box.columns * (L + box.column_spacing) - box.column_spacing + 2 * om
    H = rows * lid + 2 * om
    sm = box.screw_margin
    for x in (sm, W - sm):
        for z in (sm, H - sm):
            out += _rod("steel", (0, t, 0), (0, -1, 0), X, (x, z), 3.2, 0, t - 0.3)
    return out


@recipe
def MagazineFile(box, parts):
    """Box x × y (front at Y = 0) on its bottom, as ClosedBox: the tall wall (h, its top edge
    t2) at the back, the low one (hi) at the front, the two sides (all F edges) outside X = 0 and
    X = x, their tall end at the back, their bottom t below the floor. The two sides are drawn in
    one part, the second turned half round (moveTo(y + 15, h + hi + 15, 180) after the first, each
    starting 3, 3 in): its frame brings it onto the first's place, which it keeps."""
    t, x, y, h, hi = box.thickness, box.x, box.y, box.h, box.hi
    back, front, bottom, sides = parts
    local = local_matrix(sides.record)
    turned = Affine.translation(3, 3) * ~(Affine.translation(y + 18, h + hi + 18) * Affine.rotation(180)
                                          * Affine.translation(3, 3)) * local
    keep = lambda p: p.bounds[1] < 10       # the side at (3, 3): its bottom edge
    at = (0, y + t + 3, -t - 3)              # the drawn (3, 3), the sides' outer corner, at the back
    return [(back, Placement((0, y, 0), X, Z, -1)), (front, Placement((0, 0, 0), X, Z, 1)),
            (bottom, Placement((0, 0, 0), X, Y, -1)),
            (sides, Placement(at, (0, -1, 0), Z, 1, keep=keep), local),
            (sides, Placement(_add(at, X, x), (0, -1, 0), Z, -1, keep=keep), turned)]


def _stachel_pole_centre(box):
    """The pole hole's centre in the layers' frame: layer() starts at (ro, r) going up, the ring's
    arc is centred at (ro, ro + l); the pole arm points 5° above level (the ring's arc
    is 355°), the hole ro cos a2 + 25 + 2rp − 20 − rp cos a3 from the ring's centre."""
    ri, rp = box.flutediameter / 2, box.polediameter / 2
    ro, l = ri + box.wall, 25
    a2, a3 = math.asin((rp + 8) / ro), math.asin(1 / rp)
    d = ro * math.cos(a2) + 25 + 2 * rp - 20 - rp * math.cos(a3)
    return ro + d * math.cos(math.radians(5)), ro + l + d * math.sin(math.radians(5))


STACHEL_POLE = 150  # the pole's length below the clamp (no length in the generator)


@recipe
def Stachel(box, parts):
    """The three layers glued in a stack, lying level STACHEL_POLE up on the pole: the ring with the
    small hole (the recorder's foot stands on it) at the bottom, the one with the bolt slots in the
    middle, the plain one on top."""
    t = box.thickness
    return [Placement((0, 0, STACHEL_POLE + i * t), X, Y, 1) for i in range(len(parts))]


@decoration("Stachel", "dowel")
def _stachel_pole(box):
    """The pole (a dowel) in the arm's clamp, from the floor to 20 mm above the stack."""
    pole = _stachel_pole_centre(box)
    return _rod("dowel", (0, 0, 0), Z, X, pole, box.polediameter / 2 - 0.2, 0, STACHEL_POLE + 3 * box.thickness + 20)


# ---------------------------------------------------------------- ramp, coin bank, shoe, paper box

@recipe
def Ramp(box, parts):
    """The ramp across X (x wide), rising from the toe at Y = 0 to the step at the back, on the
    floor: the bottom (tx deep) from the toe back, the vertical wall (ty high) on its back edge,
    the diagonal on the slope (angle atan(h / y)) from the vertical wall's back face down to the
    floor, its plain ends there; the two side triangles outside X = 0 and x, their fingers in the
    three walls' F edges, the reinforcements inside on the bottom's and the vertical wall's finger
    holes (centred on k·x / (n + 1)). Both kinds of triangle are drawn in pairs in one part
    (see _right_triangles); their right angle at the back, on the floor."""
    t, x, n = box.thickness, box.x, box.n
    a = math.atan(box.h / box.y)
    tx = box.y - t - t * math.sin(a) - 2 * t / math.tan(a)
    ty = tx * math.tan(a)
    corner = (0, tx, t)                     # the triangles' right angle (inner faces)
    out = []
    for part in parts:
        label = part.record.label
        if part is parts[0]:            # rectangularTriangle isn't recorded as a primitive: no label
            for (frame, keep), (x0, side) in zip(_right_triangles(part, tx, t), ((0, -1), (x, 1))):
                out.append((part, Placement(_add(corner, X, x0), Y, Z, side, keep=keep), frame))
        elif label is None:             # the reinforcements
            for k, (frame, keep) in enumerate(_right_triangles(part, tx, t), 1):
                out.append((part, Placement(_add(corner, X, k * x / (n + 1) - t / 2), Y, Z, 1, keep=keep), frame))
        elif label == "Vertical Wall":
            out.append((part, Placement((0, tx, t), X, Z, -1)))
        elif label == "Bottom":
            out.append((part, Placement((0, 0, t), X, Y, -1)))
        elif label == "Diagonal":   # v from the top (t / cos a past the vertical wall's back face) down
            out.append((part, Placement((0, tx + t, t + ty + t * math.tan(a)), X,
                                        (0, -math.cos(a), -math.sin(a)), -1)))
    return out


def _coinbanksafe_door_frame(door, box):
    """The door (drawn outside any move(), in sheet coordinates) → local: (0, 0) at the bottom of
    its free edge, u to the hinge edge, the hinge tabs below 0 and above h."""
    u0, v0, _, _ = _part_polys(door)[0].bounds
    return Affine.translation(-(u0 + box.burn), -(v0 + box.burn + box.thickness)) * local_matrix(door.record)


def _coinbanksafe_cutout(part, frame, centre, r):
    """A disc cut out of a part round centre (in frame's coordinates), with the square hole in it,
    which polygons_of drops as scrap: as a part of its own (see _hinge_disc). Path by subpath: the
    top's hinge hole is drawn in one path with the coin slot."""
    inside = []
    for path in part.pathes:
        subs = []
        for c in path.path:
            if c[0] == "M" or not subs:
                subs.append([])
            subs[-1].append(c)
        inside += [SimpleNamespace(path=sub, params=path.params) for sub in subs
                   if all(math.dist(frame * (c[1], c[2]), centre) < r for c in sub if c[0] in "MLC")]
    return SimpleNamespace(record=part.record, pathes=inside)


@recipe
def CoinBankSafe(box, parts):
    """The safe y wide (X) and x deep, the door at the front (Y = 0), standing on the stackable
    edges' feet (the walls' base line 4t up, the bottom in the feet's finger holes under it). The
    back wall (sFFF) at Y = x, the side walls' f ends in its F edges, their plain ends at the front:
    the left one (seFf, drawn mirrored) at X = 0 on the hinge side, the right one (sfFe) at X = y
    with the locking bar standing inwards in its finger holes, 2.75t behind the front. Top and
    bottom (efff, their plain edge at the front) with the hinge hole near the front left corner.
    The top is turned over: its hinge hole is drawn near its other end. The door between them, 1.25t … 2.25t behind the front (its hinge tabs centred under the hinge
    holes), 0.1t clear of the side walls, shown closed; the handle in its slot. The cut-out discs
    stay where they turn: the hinge discs (on the door's tabs) in the top's and bottom's holes,
    the door-hole discs in the door. Each dial's pin goes in from the front: wiggle knob,
    number disc, door, spacer, D disc (round side against the locking bar: locked), the pin's barb
    behind it."""
    t, x, y, h = box.thickness, box.x, box.y, box.h
    z0 = 4 * t                              # height + holedistance + t of the stackable edge
    left, back, right, bar, door, top, bottom = parts[:7]
    numbers, ds, spacers, knobs, pins, handle = parts[7:10], parts[10:13], parts[13:16], parts[16:19], parts[19:22], parts[22]
    front_door = Placement((y - 0.1 * t, 1.25 * t, z0), (-1, 0, 0), Z, 1)
    # the top's hinge hole is drawn by its second callback, at the start of its right edge: near
    # u = y. It is turned over (u from X = y) to have it over the bottom's.
    top_place, bottom_place = Placement((y, 0, z0 + h), (-1, 0, 0), Y, -1), Placement((0, 0, z0), X, Y, -1)
    door_frame = _coinbanksafe_door_frame(door, box)
    out = [(left, Placement((0, x, z0), (0, -1, 0), Z, 1)),
           (back, Placement((0, x, z0), X, Z, -1)),
           (right, Placement((y, 0, z0), Y, Z, 1)),
           (bar, Placement((y, 2.25 * t, z0), (-1, 0, 0), Z, 1)),
           (door, front_door, door_frame),
           (top, top_place), (bottom, bottom_place)]
    for plate, place, u in ((top, top_place, y - 1.75 * t), (bottom, bottom_place, 1.75 * t)):
        local = local_matrix(plate.record)
        out.append((_coinbanksafe_cutout(plate, local, (u, 1.75 * t), 1.15 * t + 0.5), place, local))
    big = 2.25 * t
    s = 2 * big + (h - 6 * big) / 4
    for k, pz in enumerate((h / 2, h / 2 - s, h / 2 + s)):
        out.append((_coinbanksafe_cutout(door, door_frame, (2.9 * t, pz), 1.25 * t + 0.5), front_door, door_frame))
        c = (y - 3 * t, 0, z0 + pz)         # the pin's axis at the door's front face, Y = 1.25t
        disc = lambda y0, U=X, s_=-1, **kw: Placement((c[0], y0, c[2]), U, Z, s_, **kw)
        out += [(knobs[k], disc(-0.75 * t)), (numbers[k], disc(0.25 * t)), (spacers[k], disc(2.25 * t)),
                (ds[k], disc(3.25 * t, (-1, 0, 0), 1, keep=lambda p: p.area > 4 * t * t)),
                (pins[k], Placement((c[0] - t / 2, -0.75 * t, c[2] - t / 2), Y, X, -1))]
    u0, v0, _, _ = _part_polys(handle)[0].bounds   # its tab at u0, t deep into the door
    hframe = Affine.translation(-(u0 + box.burn + t), -(v0 + box.burn)) * local_matrix(handle.record)
    L = box.handlelength * t
    out.append((handle, Placement((y / 2 - t / 2, 1.25 * t, z0 + h / 2 - L / 2), (0, -1, 0), Z, -1), hframe))
    return out


@recipe
def Shoe(box, parts):
    """The shoe on its bottom, the toe at the front (Y = 0), width x across X: the bottom (FFFF,
    length y from the back), the sides outside X = 0 and x (their profile drawn from the heel,
    u = 0, to the toe, the second mirrored), the back (ffef, h) and the front (ffff, hf) at the ends.
    The lip (shoelip, drawn outside rectangularWall: local (0, 0) the corner of its outline, the
    strip running along v) lies on the sides' upper edge from the front wall's top: flat over the
    toe (tf), round the bend (its flex, drawn dr long, turning 90° − af with the sides' radius r on
    its lower face), then straight up the slope (lf) to the opening. Both shoeside and shoelip
    start t in (the F spacing / f margin)."""
    t, x, y, h, hf = box.thickness, box.width, box.length, box.height, box.frontheight
    tf, r, yg = box.fronttop, box.radius, box.tophole
    atemp = math.degrees(math.atan((h - hf - r) / (y - yg - tf)))
    lf = math.sqrt((h - hf - r) ** 2 + (y - yg - tf) ** 2 - r ** 2)
    af = 90 - atemp - math.degrees(math.atan(r / lf))
    dr = math.radians(90 - af) * (r - t) / box.edges["X"].settings.stretch
    bottom, side1, side2, back, front, lip = parts
    inset = Affine.translation(-t, -t)
    across = Affine(0, 1, -t, -1, 0, x + t)          # (u, v) → (v − t, x + t − u): the strip along u
    return [(bottom, Placement((0, y, t), (0, -1, 0), X, -1)),
            (side1, Placement((0, y, t), (0, -1, 0), Z, 1), inset * local_matrix(side1.record)),
            (side2, Placement((x, y, t), (0, -1, 0), Z, -1), inset * local_matrix(side2.record)),
            (back, Placement((0, y, t), X, Z, -1)),
            (front, Placement((0, 0, t), X, Z, 1)),
            (lip, Placement((0, 0, t + hf), Y, X, -1, bends=[(tf, tf + dr, 90 - af, r)]),
             across * local_matrix(lip.record))]


def _paperbox_panel(place, u0, v0, u1, v1):
    """The placement, keeping only the panel u0 … u1 × v0 … v1 of the folded sheet (see _clip),
    opened by 0.2 mm: the burn's slivers along the neighbours' edges and the fold marks' spikes go."""
    band, pieces = rect(u0, v0, u1, v1), place.pieces
    place.pieces = lambda polys, t: pieces([g for p in polys
                                            for c in [p.intersection(band).buffer(-0.2, join_style=2).buffer(0.2, join_style=2)]
                                            for g in getattr(c, "geoms", [c]) if g.geom_type == "Polygon" and g.area > 0.5], t)
    return place


@recipe
def PaperBox(box, parts):
    """The one outline (drawn outside any move(), in sheet coordinates) folded up: cut into its
    panels along the fold lines (the outline's corners), each placed as a part of its own, the box
    x wide (X), y deep, h high, its front (with the finger hole) at Y = 0, the paper outside the
    fold lines. widebox: the front, bottom, back and lid in a column (v), the sides left and right
    of the bottom, their rim flaps (lid_sides) folded down inside them, the front's and back's glue
    tabs folded in against the sides (under the rim flaps), the lid closed on top, its front flap
    tucked inside the front. tuckbox: the four walls in a row along v (u up: right end, back, left
    end, front, then the glue tab inside the right end), the lid on the back's rim and the bottom on
    its foot, each with its tuck flap inside the front; the ears (dust flaps) on the ends' rim fold
    in under the lid, those at their foot in over the bottom."""
    t, x, y, h, lh = box.thickness, box.x, box.y, box.h, box.lid_height
    sheet = parts[0]
    u_min, _, u_max, v_max = _part_polys(sheet)[0].bounds
    B = 1e4
    out = []
    if box.design == "tuckbox":
        top = 2 * y + 2 * x + y - box.margin - t
        frame = Affine.translation(-((u_min + u_max) / 2 - h / 2), -(v_max - box.burn - top)) * local_matrix(sheet.record)
        panels = [((0, -B, h, y), Placement((x, 0, 0), Z, Y, -1)),                         # right end
                  ((0, y, h, y + x), Placement((x + y, y, 0), Z, (-1, 0, 0), -1)),         # back
                  ((0, y + x, h, 2 * y + x), Placement((0, 2 * y + x, 0), Z, (0, -1, 0), -1)),  # left end
                  ((0, 2 * y + x, h, 2 * y + 2 * x), Placement((-(2 * y + x), 0, 0), Z, X, -1)),  # front
                  ((0, 2 * y + 2 * x, h, B), Placement((x, -(2 * y + 2 * x), 0), Z, Y, 1)),  # glue tab
                  ((h, y, h + y, y + x), Placement((x + y, y + h, h), (0, -1, 0), (-1, 0, 0), -1, lid=True)),
                  ((h + y, y, B, y + x), Placement((x + y, 0, 2 * h + y), (0, 0, -1), (-1, 0, 0), 1, lid=True)),
                  ((-y, y, 0, y + x), Placement((x + y, y, 0), Y, (-1, 0, 0), -1)),        # bottom
                  ((-B, y, -y, y + x), Placement((x + y, 0, -y), (0, 0, -1), (-1, 0, 0), 1)),
                  ((h, -B, B, y), Placement((x + h, 0, h), (-1, 0, 0), Y, 1)),              # ears
                  ((h, y + x, B, B), Placement((-h, 2 * y + x, h), X, (0, -1, 0), 1)),
                  ((-B, -B, 0, y), Placement((x, 0, 0), X, Y, 1)),
                  ((-B, y + x, 0, B), Placement((0, 2 * y + x, 0), (-1, 0, 0), (0, -1, 0), 1))]
    else:
        frame = Affine.translation(-((u_min + u_max) / 2 - x / 2), -(v_max - box.burn - (2 * h + 2 * y + lh))) * \
            local_matrix(sheet.record)
        panels = [((0, -B, x, h), Placement((0, 0, h), X, (0, 0, -1), -1)),                # front
                  ((0, h, x, h + y), Placement((0, -h, 0), X, Y, -1)),                     # bottom
                  ((0, h + y, x, 2 * h + y), Placement((0, y, -(h + y)), X, Z, -1)),        # back
                  ((0, 2 * h + y, x, 2 * h + 2 * y), Placement((0, 2 * h + 2 * y, h), X, (0, -1, 0), -1, lid=True)),
                  ((0, 2 * h + 2 * y, x, B), Placement((0, 0, 3 * h + 2 * y), X, (0, 0, -1), 1, lid=True)),
                  ((x, h, x + h, h + y), Placement((x, -h, -x), Z, Y, -1)),                # right side
                  ((x + h, h, B, h + y), Placement((x - t, -h, 2 * h + x), (0, 0, -1), Y, -1)),
                  ((x, -B, B, h), Placement((x, -x, h), Y, (0, 0, -1), 1)),                 # glue tabs
                  ((x, h + y, B, B), Placement((x, y + x, -(h + y)), (0, -1, 0), Z, 1)),
                  ((-h, h, 0, h + y), Placement((0, -h, 0), (0, 0, -1), Y, -1)),            # left side
                  ((-B, h, -h, h + y), Placement((t, -h, 2 * h), Z, Y, -1)),
                  ((-B, -B, 0, h), Placement((0, 0, h), (0, -1, 0), (0, 0, -1), 1)),
                  ((-B, h + y, 0, B), Placement((0, y, -(h + y)), Y, Z, 1))]
    for region, place in panels:
        place.origin = _add(place.origin, Z, t)   # the bottom's paper under Z = t, on the floor
        out.append((sheet, _paperbox_panel(place, *region), frame))
    return out


@recipe
def TrafficLight(box, parts):
    """n lamps of h × h, h + t apart, d deep, the shades s further forward, the open front at −Y,
    the back (if any) at Y = 0 … t. Upright: the sides (drawn from the top down, u = 0 at the top)
    at X = 0 and h, the lamps stacked up th high; over each lamp a shade (a horizontal wall d + s
    deep) in the sides' finger holes, the F-edged one (the last) on top; the bottom wall under them,
    d deep. Side by side: the lamps along X, the bottom and the top (s deeper: the shades) plates,
    the vertical walls (trapezoids, d deep at the bottom, d + s at the top) between them, the
    F-edged ones at the ends. Each front in the holes 2 t behind the sides' front edge, its
    coloured window (as wide as the front's hole) set in the hole."""
    t, h, d, n = box.thickness, box.h, box.depth, box.n
    th = n * (h + t) - t
    yf = -(d - 2.5 * t)           # the fronts' back face
    out, fronts, walls, windows = [], [], [], 0
    for p in parts:
        label = p.record.label or ""
        if label == "back":
            out.append((p, Placement((0, 0, th), (0, 0, -1), X, -1) if box.upright
                        else Placement((0, 0, 0), X, Z, -1)))
        elif label == "left":
            out.append((p, Placement((0, 0, th), (0, 0, -1), (0, -1, 0), 1)))
        elif label == "right":
            out.append((p, Placement((h, 0, th), (0, 0, -1), (0, -1, 0), -1)))
        elif label == "bottom wall" or label == "bottom":
            out.append((p, Placement((0, 0, 0), X, (0, -1, 0), 1)))
        elif label == "top":
            out.append((p, Placement((0, 0, h + t), X, (0, -1, 0), 1)))
        elif label.startswith(("horizontal Wall", "vertical wall")):
            walls.append(p)
        elif label.startswith("front"):
            fronts.append(p)
        else:  # the coloured windows
            i, windows = windows, windows + 1
            c = (h / 2, yf, th - i * (h + t) - h / 2) if box.upright else (i * (h + t) + h / 2, yf, h / 2)
            out.append((p, Placement(c, X, Z, 1, clear=True)))
    # the inner walls first, in the holes k (h + t) - t / 2 along the lamps; the F-edged (last) ones at the ends
    centres = [k * (h + t) - t / 2 for k in range(1, n)]
    if box.upright:
        for w, c in zip(walls, centres + [-t / 2]):
            out.append((w, Placement((0, 0, th - c + t / 2), X, (0, -1, 0), 1)))
        for i, f in enumerate(fronts):
            out.append((f, Placement((0, yf, th - i * (h + t) - h), X, Z, 1)))
    else:
        for w, c in zip(walls, centres + [-t / 2, th + t / 2]):
            out.append((w, Placement((c - t / 2, 0, 0), Z, (0, -1, 0), 1)))
        for i, f in enumerate(fronts):
            out.append((f, Placement((i * (h + t), yf, 0), Z, X, -1)))
    return out


@recipe
def Sphere(box, parts):
    """The gores (all drawn in one part, side by side moveX apart, from the bottom hole's edge up)
    bent into half meridians round the sphere's axis, 360 / n apart, each a band of flat strips
    tangent to the sphere of radius R (a hosohedron: neighbouring gores meet along their edges),
    the bottom hole's rim on the floor. The tabs are tucked under the neighbouring gore: they are
    left out (clipped off along the gore's edge); a cable hook goes on past the top hole, flat."""
    R, n, part = box.sphere_radius, box.amount_gores, parts[0]
    move_x = box.bellyLens + box.tab_width * 2 + 30
    u_bottom, u_top = box.u_goreBottom, box.u_goreTop
    edge = [(math.pi * R * i / 64, box.halfBellyLens * math.sin(math.pi * i / 64)) for i in range(65)]
    lens = Polygon(edge + [(u, -v) for u, v in reversed(edge)])
    gore = unary_union([lens.buffer(0.2), rect(u_top, -1e4, 1e4, 1e4)])  # what is not a tab
    z_centre = R * math.cos(u_bottom / R) + box.thickness
    out = []
    for k in range(n):
        phi = 2 * math.pi * k / n
        radial, across = (math.cos(phi), math.sin(phi), 0), (math.sin(phi), -math.cos(phi), 0)
        place = Placement((0, 0, z_centre - R), radial, across, 1, bends=[(0, math.pi * R, 180, R)],
                          keep=lambda p: abs(p.centroid.y) < move_x / 2)
        pieces = place.pieces
        place.pieces = lambda polys, t, pieces=pieces: pieces([g for p in polys for c in [p.intersection(gore)]
                                                               for g in getattr(c, "geoms", [c]) if g.geom_type == "Polygon"], t)
        # gore k's centre line from its bottom (u_bottom) on the sheet → (u from the bottom pole, across)
        cx = -box.halfBellyLens - box.x_rightGoreBottom + k * move_x
        local = (Affine.rotation(-90) * Affine.translation(-cx, u_bottom - 30 + box.burn)
                 * local_matrix(part.record))
        out.append((part, place, local))
    return out


@recipe
def LaptopStand(box, parts):
    """The X: the two triangles (base long, the diagonal of the laptop's footprint) standing
    across each other at right angles, crossing in the middle of their bases at the origin, their
    tall rear ends at the back corners, their lips (where the laptop's front rests) at the front
    corners. The one with the slot in its bottom (drawn first, rear left on the sheet) runs from
    the back right to the front left, over the one with the slot in its top (drawn turned half
    round)."""
    t, b = box.thickness, box.burn
    part = parts[0]
    local = local_matrix(part.record)
    lower, upper = sorted(_part_polys(part), key=lambda q: q.bounds[1])
    under = Affine.translation(-lower.bounds[0] - b, -lower.bounds[1] - b) * local          # rear at u = 0, feet at v = 0
    over = Affine.rotation(180) * Affine.translation(-upper.bounds[2] + b, -upper.bounds[3] + b) * local
    c = box.perform_calculations()["base"] / 2 / 2 ** 0.5
    s = 2 ** -0.5
    out = []
    for q, m, rear, U, n in ((lower, under, (c, c, 0), (-s, -s, 0), (-s, s, 0)),
                             (upper, over, (-c, c, 0), (s, -s, 0), (-s, -s, 0))):
        here = affine_transform(q, (m * ~local).to_shapely()).centroid
        keep = lambda p, here=here: p.centroid.distance(here) < 1
        out.append((part, Placement(_add(rear, n, -t / 2), U, Z, 1, keep=keep), m))
    return out




def _phoneholder_frame(box):
    """The front plate's frame: its back face on the side triangles' hypotenuse, from the front
    bottom corner (the origin) up and back at angle from the vertical; U × V points out front."""
    a = math.radians(box.angle)
    return (0, math.sin(a), math.cos(a)), (0, -math.cos(a), math.sin(a))


@recipe
def PhoneHolder(box, parts):
    """The phone leans back at angle on the front plate (w × h, its back face on the side
    triangles' hypotenuse, from Y = 0 on the floor up to the back), the two side triangles (their
    right angle at the back bottom, Y = stand_depth) at X = -t … 0 and w … w + t, their tabs
    standing out in front of the plate along the phone's edges, the back plate upright behind
    their vertical legs. The two bottom supports (drawn the second mirrored) stand in the front
    plate's finger holes, through the slots in its bottom edge, their hooks under the phone."""
    t, w = box.thickness, box.phone_width
    a = math.radians(box.angle)
    up, _ = _phoneholder_frame(box)
    front, back, tri, s1, s2 = parts
    keep, frames = _angledcutjig_pair(tri)
    margin = (w - box.bottom_support_spacing - t) / 2
    top = (box.bottom_margin + box.tab_size) * math.sin(a)   # the supports' back: under their f edge's top
    return [(front, Placement((0, 0, 0), X, up, 1)),
            (back, Placement((0, box.stand_depth, 0), X, Z, -1)),
            (tri, Placement((0, 0, 0), Y, Z, -1, keep=keep), frames[0]),
            (tri, Placement((w, 0, 0), Y, Z, 1, keep=keep), frames[1]),
            (s1, Placement((margin - t / 2, top, 0), (0, -1, 0), Z, -1)),
            (s2, Placement((w - margin - t / 2, top, 0), (0, -1, 0), Z, -1))]


@decoration("PhoneHolder", "lcd")
def _phoneholder_phone(box):
    """The phone (phone_width × phone_height × phone_depth) on the front plate, its bottom in the
    supports' hooks, bottom_margin up the plate."""
    up, out = _phoneholder_frame(box)
    at = _add(_add((0, 0, 0), out, box.thickness), up, box.bottom_margin)
    return _solid("lcd", Placement(at, X, up, 1), rect(0, 0, box.phone_width, box.phone_height), box.phone_depth)


@recipe
def Desksign(box, parts):
    """The plate leaning back at angle, its back face on the two stands' hypotenuses (from the
    front bottom corner, Y = 0, up to the back), the stands (right triangles, base deep and h high,
    the right angle at the back bottom; the second drawn mirrored, or both in one part) behind it
    at X = -t … 0 and width … width + t, their fingers in the plate's holes. With feet, all of it
    stands on the stands' feet. The engraved text is not shown (it is not cut)."""
    w, a = box.width, math.radians(box.angle)
    plate, stand = parts[0], parts[1]
    z = -min(0.0, *(q.bounds[1] for q in _part_polys(stand)))      # the feet's height below the stands
    out = [(plate, Placement((0, 0, z), X, (0, math.cos(a), math.sin(a)), 1))]
    sides = (Placement((0, 0, z), Y, Z, -1), Placement((w, 0, z), Y, Z, 1))
    if len(parts) == 3:
        return out + list(zip(parts[1:], sides))
    keep, frames = _angledcutjig_pair(stand)  # not mirrored: both in one part, the second turned half round
    return out + [(stand, Placement(p.origin, p.U, p.V, p.side, keep=keep), f) for p, f in zip(sides, frames)]


# ---------------------------------------------------------------- keyboard, loom, tetromino, dice tower, edges

ATREUS21_GAP = 40  # between the two halves


def _atreus21_plates(part):
    """The eight plates, all cut in one part (no move()): [(polygon, its min corner)] in drawing
    order — keyholder, support, hotplug, rim of the left half, then of the right one. render() lays
    them out two by two, a row per pair: sorted by row, then left to right."""
    plates = [q for q in polygons_of(loops_of(part, Affine.identity())) if q.area > 1000]
    plates.sort(key=lambda q: (round(q.bounds[1] / 10), q.bounds[0]))
    return [(q, q.bounds[:2]) for q in plates]


@recipe
def Atreus21(box, parts):
    """The two halves side by side (the left one, its thumb key on the right, at X = 0), each a
    stack of its four plates lying flat, their outlines together: the rim (a spacer round the open
    middle, room for the hot-swap sockets and the wiring) on the floor, the hotplug plate on it, then
    the support plate and the keyholder (switch plate) on top, as the support is meant to be glued
    under it."""
    t, part = box.thickness, parts[0]
    plates = _atreus21_plates(part)
    if len(plates) < 8:
        return []
    w = plates[0][0].bounds[2] - plates[0][0].bounds[0]
    out = []
    for k, (q, (x0, y0)) in enumerate(plates):
        half, layer = divmod(k, 4)
        c = q.representative_point()
        out.append((part, Placement((half * (w + ATREUS21_GAP), 0, (3 - layer) * t), X, Y, 1,
                                    keep=lambda p, c=Point(c.x - x0, c.y - y0): p.contains(c)),
                    Affine.translation(-x0, -y0)))
    return out


@decoration("Atreus21", "keycap")
def _atreus21_keys(box):
    """On every keyholder cutout (each half's columns from its corner, reversed for the right half,
    as half() steps them) a switch's top housing (14.6 mm square, 6 mm high) and a keycap 8 mm high:
    18 mm square, stepped in to 15 mm for the top 2 mm (as on Keypad)."""
    t, b, s, m = box.thickness, box.border, box.STANDARD_KEY_SPACING, box.half_btn
    case_x, _ = box._case_x_y()
    top = 4 * t
    sq = lambda a, r: rect(-a / 2 + r, -a / 2 + r, a / 2 - r, a / 2 - r).buffer(r, quad_segs=3)
    housing, cap, crown = sq(14.6, 1), sq(18, 1.5), sq(15, 2)
    out = []
    for half, cols in enumerate((box.columns_definition, list(reversed(box.columns_definition)))):
        x0 = half * (case_x + 2 * b + ATREUS21_GAP) + b + m
        for i, (offset, n) in enumerate(cols):
            for j in range(n):
                c = (x0 + i * s, b + m + offset + j * s)
                out += [dict(p, decoration="switch") for p in Placement((*c, top), X, Y, 1).pieces([housing], 6)]
                out += Placement((*c, top + 6), X, Y, 1).pieces([cap], 6)
                out += Placement((*c, top + 12), X, Y, 1).pieces([crown], 2)
    return out


def _frameloom_loose(items, x0, gap=15):
    """Loose pieces lying flat in a row from X = x0, each from Y = 0: [(part, Placement)]. A
    clip-on heddle's outline is open (two halves split by zigzag cuts meeting it end to end): its
    pieces are the faces its cuts enclose, given as the plate (slivers between the zigzags left out)."""
    out = []
    for part in items:
        polys, plate = _part_polys(part), None
        if not polys:
            cuts = []
            loops_of(part, local_matrix(part.record), cuts)
            ink = unary_union([LineString(c) for c in cuts if len(c) > 1]).buffer(0.2)
            faces = [Polygon(r).buffer(0.2 - KERF / 2) for g in getattr(ink, "geoms", [ink]) for r in g.interiors]
            if not faces:
                continue
            big = max(f.area for f in faces)
            plate = polys = unary_union([f for f in faces if f.area > 0.1 * big])
        minu, minv, maxu, _ = unary_union(polys).bounds
        out.append((part, Placement((x0 - minu, -minv, 0), X, Y, 1, plate=plate,
                                    keep=(lambda q: False) if plate is not None else None)))
        x0 += maxu - minu + gap
    return out


@recipe
def FrameLoom(box, parts):
    """The frame lying with its numbered pins at the front (Y = 0), the two feet standing in its
    slots near the back: their neck (23 long, t high) in the slot, the hooks on the top face, the
    body under the frame with the axle hole towards the front. The heddle stands upright across the
    frame, its handles through the feet's holes and out at the sides, its pins up and down through
    the opening. The loom is tilted about its front edge until the feet's round ends touch the
    floor, as in the photo. Comb, needles, shuttles and any other heddle lie flat beside it."""
    t, n, pw, L = box.thickness, box.warpthreads, box.warpspacing, box.outerframelength
    by = lambda name: [p for p in parts if p.record.caller == name]
    frame, feet, heddles = by("frame"), by("foot"), by("heddle")
    loose = by("comb") + heddles[1:] + by("needle") + by("shuttle")
    if not frame:
        return _frameloom_loose(heddles[:1] + loose, 0)
    fw, offset = 15, 8                                    # frame_thickness, foot_attachment_x_offset
    up = L - 23 / 2 - 20 - 2                              # the slots' middle, as frame() puts them
    foot_poly = _part_polys(feet[0])[0]
    hole = Polygon(max(foot_poly.interiors, key=lambda r: Polygon(r).area)).centroid
    y0 = up - 23 / 2 - 7                                  # the neck starts at u = 7
    axle = (y0 + hole.x, 3 - hole.y)                      # its body down from v = 3, the top face
    loom = [(frame[0], Placement((0, 0, 0), X, Y, -1))]
    for foot, xs in zip(feet, (fw - offset, fw + n * pw + offset)):
        loom.append((foot, Placement((xs + t / 2, y0, 3), Y, (0, 0, -1), 1)))
    if heddles:
        hr = math.sqrt(4 * 4.25 ** 2 - t ** 2) / 2        # the handle's half width, as heddle() has it
        x0 = fw - 20 - (offset - t / 2)                   # its pins start over the frame's
        loom.append((heddles[0], Placement((x0, axle[0] - t / 2, axle[1] - (18 + 1 + hr)), Z, X, 1)))
    # tilt about the frame's bottom front edge until the feet's round ends (radius r) touch the floor
    minu, _, maxu, maxv = foot_poly.bounds
    r = (maxu - minu) / 2
    A, B = y0 + (minu + maxu) / 2, 3 - (maxv - r) + t
    theta = math.degrees(math.asin(r / math.hypot(A, B)) - math.atan2(B, A))
    out = []
    for part, place in loom:
        place = _turned(place, (0, 0, -t), X, theta)
        place.origin = _add(place.origin, Z, t)
        out.append((part, place))
    return out + _frameloom_loose(loose, 2 * fw + n * pw + 30)


@recipe
def Tetris(box, parts):
    """The tetromino lying flat: its two plates (polygonWall: u along the first border, the blocks'
    outline t in) at the bottom (Z = t, thickness down) and at the top, the walls polygonWalls drew
    round them standing between, blocksize − 2t high (see _flex_walls). The second plate is drawn
    mirrored: its local frame undoes it, so it is placed like the first."""
    t, h = box.thickness, box.blocksize - 2 * box.thickness
    bottom, top, walls = parts[:3]
    out = [(bottom, Placement((0, 0, 0), X, Y, -1)), (top, Placement((0, 0, h), X, Y, 1))] + _flex_walls(walls, t)
    for item in out:
        item[1].origin = _add(item[1].origin, Z, t)
    return out


def _dicetower_ramp(d, z0, t, pu, pv, angle):
    """A ramp across the tower on the sides' finger holes from (pu, pv) at angle° (side coordinates:
    u from the back to the front), its middle on the holes' line, v along it."""
    a = math.radians(angle)
    along = (0, -math.cos(a), math.sin(a))
    normal = _cross(X, along)
    return Placement(_add((0, d - pu, z0 + pv), normal, -t / 2), X, along, 1)


@recipe
def DiceTower(box, parts):
    """The tower (inner width × depth × height, the dice coming out at the front, Y = 0) standing at
    the back of its tray: the sides (u from the back to the front, their front edge outset where
    the front wall leaves the gap) outside X = 0 and X = width, the back and the bottom between,
    the front wall over the gap, from depth·tan(angle) up. The ramps on the sides' finger holes,
    the long one at the bottom down to the front, the short ones alternately from the front and
    from the back. The tray is the over-the-top lid turned over: its top on the floor, its walls
    standing round it, the tower's sides and back play/2 in from its back and sides."""
    t, w, d, H = box.thickness, box.width, box.depth, box.height
    a = math.radians(box.angle)
    labelled = lambda name: [p for p in parts if p.record.label == name]
    tray = labelled("lid top")
    z0 = (t if box.bottom else 0) + (t if tray else 0)
    out = [(s, Placement((x, d, z0), (0, -1, 0), Z, side)) for s, x, side in zip(labelled("side"), (0, w), (1, -1))]
    out += [(p, Placement((0, d, z0), X, Z, -1)) for p in labelled("back")]
    out += [(p, Placement((0, 0, z0 + d * math.tan(a)), X, Z, 1)) for p in labelled("front")]
    out += [(p, Placement((0, 0, z0), X, Y, -1)) for p in labelled("bottom")]
    # the ramps as side() lays out their finger holes
    pos_x, pos_y = box.left_ramp_cutoff, (d - box.left_ramp_cutoff) * math.tan(a)
    ramps = [(pos_x, pos_y, -box.angle)]
    for i in range(box.ramps - 1):
        y = pos_y + (H - pos_y - 4 * t) / (box.ramps - 1) * (i + 1)
        ramps.append((d - pos_x, y, 180 + box.angle) if i % 2 == 0 else (pos_x, y, -box.angle))
    out += [(p, _dicetower_ramp(d, z0, t, *r)) for p, r in zip(labelled("ramp"), ramps)]
    if tray:
        x2, y2 = tray[0].record.args[:2]
        h = labelled("lid front")[0].record.args[1]
        o = -(x2 - w) / 2                                 # t and half the play out from the sides
        oy = d - o - y2                                   # the back's outer face play/2 from the tray's
        ring = _walls_round(x2, y2, (o, oy, t + h), -1)
        out.append((tray[0], Placement((o, oy, t), X, Y, -1)))
        out += [(p, q) for name, q in (("lid front", ring[0]), ("lid back", ring[2]), ("lid left", ring[3]),
                                       ("lid right", ring[1])) for p in labelled(name)]
    return out


@decoration("DiceTower", "dice")
def _dicetower_dice(box):
    """Two 16 mm dice that came out in front of the tower, on the tray (or the floor), their pips
    proud of the top, front and side faces."""
    t, w, d = box.thickness, box.width, box.depth
    lid = box.tray_height > 0
    z = t if lid else 0
    reach = box.height - (t if box.bottom else 2 * t)     # the tray's inner length less the tower
    a, out = 16, []
    k = 0.08 * a
    cube = rect(k, k, a - k, a - k).buffer(k, quad_segs=2)
    for (cx, cy), (top, front, right) in zip(((0.3 * w, -t - 0.3 * (reach - d)), (0.65 * w, -t - 0.6 * (reach - d))),
                                             DIE_FACES[1:3]):
        x0, y0 = cx - a / 2, cy - a / 2
        out += Placement((x0, y0, z), X, Y, 1).pieces([cube], a)
        for place, n in [(Placement((x0, y0, z + a), X, Y, 1), top), (Placement((x0, y0, z), X, Z, 1), front),
                         (Placement((x0 + a, y0, z), Y, Z, 1), right), (Placement((x0, y0, z), Y, Z, -1), 7 - right)]:
            pips = [Point(a / 2 + i * a / 4, a / 2 + j * a / 4).buffer(0.09 * a, quad_segs=3) for i, j in PIPS[n]]
            out += [dict(p, decoration="pip") for p in place.pieces(pips, 0.3)]
    return out


ALLEDGES_COLUMNS = 5


def _alledges_samples(parts, t):
    """Each sample's outline: render() draws only three sides of it (up t + startWidth, the edge
    leftwards along the top, down t + endWidth), open at the bottom, and a nested part (the rack
    edge) can carry on in a part of its own: the open cuts are joined across parts, then closed by
    a straight bottom 3t below the lowest point drawn. [(part, sheet → sample matrix, plate in the
    sample's frame: u from its left end, v up from its base line)]."""
    cuts = []
    for part in parts:
        found = []
        loops = loops_of(part, Affine.identity(), found)
        lows = [min(y for _, y in l) for l in loops]
        cuts += [[part, list(c), lows, False] for c in found if len(c) > 2]
        slits = [c for c in found if len(c) == 2]          # the flex edge's cuts
        if slits and cuts:
            cuts[-1].append(slits)
    for c in cuts:  # join a chain cut off by a nested part
        if c[3]:
            continue
        nxt = next((o for o in cuts if o is not c and not o[3] and math.dist(c[1][-1], o[1][0]) < 0.3), None)
        if nxt is not None:
            c[1] += nxt[1][1:]
            c[2] += nxt[2]
            nxt[3] = True
    out = []
    for part, chain, lows, joined, *slits in cuts:
        if joined or abs(chain[0][1] - chain[-1][1]) > 0.5:
            continue
        (x0, base), x1 = chain[-1], chain[0][0]
        bottom = min([base] + [y for _, y in chain] + lows) - 3 * t
        local = Affine.translation(-x0, -base)
        plate = Polygon([local * p for p in chain + [(chain[-1][0], bottom), (x1, bottom)]]).buffer(0)
        # where the outline crosses itself at a burnt corner it leaves µm slivers: they break the triangulation
        plate = max(getattr(plate, "geoms", [plate]), key=lambda g: g.area)
        plate = Polygon(plate.exterior, [r for r in plate.interiors if Polygon(r).area > 0.5])
        if slits:
            plate = plate.difference(unary_union([LineString([local * p for p in s]).buffer(KERF / 2, cap_style=2)
                                                  for s in slits[0]]))
        out.append((part, local, plate, base))
    return out


@recipe
def AllEdges(box, parts):
    """The samples lying flat, each its edge along the top (back), in the order of the sheet, in
    ALLEDGES_COLUMNS columns side by side (the sheet's single column is over 2 m long). The
    generator leaves each sample open at the bottom (the photo's samples have a wavy bottom): it is
    closed straight 3t below its lowest cut, so the holes some edges draw below their base line
    (cabinet hinges, mounting holes) are in it. The closed cuts in it are holes, but for a piece with
    a hole of its own (a chest hinge's disc, cut out of the eye it turns in): it goes in its hole.
    Pieces drawn outside it (the hinge edges' pins) lie where drawn."""
    t = box.thickness
    samples = _alledges_samples(parts, t)
    if not samples:
        return []
    per = math.ceil(len(samples) / ALLEDGES_COLUMNS)
    out = []
    for k, (part, local, plate, base) in enumerate(samples):
        col, first = divmod(k, per)[0], samples[k - k % per][3]
        at = (col * (box.x + 40), base - first, 0)
        out.append((part, Placement(at, X, Y, 1, plate=plate, keep=lambda q: q.area > 0.5), local))
        piece = lambda q, plate=plate: q.area > 0.5 and (bool(q.interiors) or not q.within(plate))
        out.append((part, Placement(at, X, Y, 1, keep=piece), local))
    return out


# ---------------------------------------------------------------- driver

def start():
    """Before drawing a box whose parts are to be placed: the hooks in, the records cleared."""
    install()
    RECORDS.update(all=[], current=None, pending={}, walls=None, stack=[], border=None)


def placed(box):
    """The parts of a drawn box (drawn after start()) by its recipe: ([(n, placement, polygons in
    the part's local frame, the sheet → local matrix)], number of parts drawn)."""
    merged = {}  # one part per record: a part interrupted by a nested one continues in a new one
    for p in box.ctx._dwg.parts:
        if p.pathes and getattr(p, "record", None) is not None:
            merged.setdefault(id(p.record), SimpleNamespace(record=p.record, pathes=[])).pathes += p.pathes
    parts = list(merged.values())
    recipe_fn = RECIPES.get(type(box).__name__)
    if recipe_fn is None:
        raise ValueError(f"No 3D assembly for {type(box).__name__} yet")
    placed_ = recipe_fn(box, parts)
    if isinstance(placed_, dict):
        items = [(p, placed_.get(p.record.label)) for p in parts]
    elif placed_ and isinstance(placed_[0], tuple):
        items = placed_
    else:
        items = list(zip(parts, placed_))
    out, sheet = [], {}
    for n, item in enumerate(items):
        part, placement = item[0], item[1]
        if placement is None:
            continue
        local = item[2] if len(item) > 2 else None
        matrix = local if local is not None else local_matrix(part.record)
        # the outlines once per part, on the sheet: a part placed piece by piece (CarbonFilter's
        # rows of ribs) would be traced again for each; the local frames only turn and move them
        key = (id(part), placement.plate is not None)
        if key not in sheet:
            cuts = []
            loops = loops_of(part, Affine.identity(), cuts)
            if placement.plate is not None:  # only holes: one left open (a fan's swirl arm, by 0.34) is a hole too
                loops += [c for c in cuts if len(c) > 2 and math.dist(c[0], c[-1]) < 1]
                cuts = [c for c in cuts if not (len(c) > 2 and math.dist(c[0], c[-1]) < 1)]
            sheet[key] = polygons_of(loops, cuts)
        out.append((n, placement, [affine_transform(q, matrix.to_shapely()) for q in sheet[key]], matrix))
    return out, len(parts)


def assemble(box):
    """Runs the generator with the recording hooks and returns the placed pieces."""
    start()
    box.open()
    box.render()
    box.ctx.stroke()  # the last path drawn (a fan's swirl) is stroked only by close()
    items, count = placed(box)
    pieces = []
    for n, placement, polys, _ in items:
        pieces += [dict(p, part=n) for p in placement.pieces(polys, box.thickness)]
    name = type(box).__name__
    for fn in DECORATIONS.get(name, []):
        pieces += fn(box)
    if name in WALLS:
        pieces += pegboard(pieces, WALLS[name](box))
    return {"pieces": pieces, "count": count, "turn": TURN.get(name, 0), "galleryLids": name in GALLERY_LIDS}


def piece_roles(box):
    """What each placed piece of a drawn box (drawn after start()) is, from where its recipe puts
    it: [(its outline on the sheet, role)]. Roles: bottom, top, lid, front, back, left side, right
    side, side (upright, at an angle), divider (upright inside), shelf (level inside), sloped panel,
    flex wall (bent); a lid's walls: lid front, lid back, lid left side, lid right side, lid side.
    Front is towards the viewer (after TURN)."""
    found = []
    for n, placement, polys, matrix in placed(box)[0]:
        if placement.decoration or placement.plate is not None:
            continue
        for poly in polys:
            if placement.keep and not placement.keep(poly):
                continue
            pieces = placement.pieces([poly], box.thickness)
            if pieces:
                found.append((affine_transform(poly, (~matrix).to_shapely()), placement, pieces))
    if not found:
        return []
    lo, hi = _extent([p for _, _, ps in found for p in ps])
    edge = 2 * box.thickness + 1
    turned = TURN.get(type(box).__name__, 0) == 180
    out = []
    for sheet, placement, ps in found:
        plo, phi = _extent(ps)
        normals = {tuple(round(c * p["side"], 2) for c in _cross(p["u"], p["v"])) for p in ps}
        nx, ny, nz = (abs(c) for c in next(iter(normals)))
        if len(normals) > 1:
            role = "flex wall"
        elif nz > 0.9:
            role = ("lid" if placement.lid else "bottom" if plo[2] <= lo[2] + edge else
                    "top" if phi[2] >= hi[2] - edge else "shelf")
        elif ny > 0.9:
            role = "front" if plo[1] <= lo[1] + edge else "back" if phi[1] >= hi[1] - edge else "divider"
            role = {"front": "back", "back": "front"}.get(role, role) if turned else role
        elif nx > 0.9:
            role = "left side" if plo[0] <= lo[0] + edge else "right side" if phi[0] >= hi[0] - edge else "divider"
            role = {"left side": "right side", "right side": "left side"}.get(role, role) if turned else role
        else:
            role = "side" if nz < 0.1 else "sloped panel"
        if placement.lid and role in ("front", "back", "left side", "right side", "side", "divider"):
            role = "lid side" if role in ("side", "divider") else "lid " + role  # the lid's own walls
        out.append((sheet, role))
    return out
