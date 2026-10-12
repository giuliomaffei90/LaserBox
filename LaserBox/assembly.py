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
    always shown in clear acrylic, whatever the chosen material (a display case's glass)."""

    def __init__(self, origin, U, V, side=1, bends=(), offset=(0, 0), keep=None, decoration=None, lid=False,
                 clear=False):
        self.origin, self.U, self.V, self.side, self.bends, self.offset = origin, _norm(U), _norm(V), side, list(bends), offset
        self.keep, self.decoration, self.lid, self.clear = keep, decoration, lid, clear

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
TURN = {"Console": 180, "Console2": 180}
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

    frames = []  # (part, its local frame → the piece's own) for each eye piece
    for part in hinges:
        local = local_matrix(part.record)
        for q in polygons_of(loops_of(part, local)):
            if q.interiors:
                c = Polygon(q.interiors[0]).centroid
                _, miny, _, maxy = q.bounds
                turn = Affine.scale(1 if maxy - c.y > c.y - miny else -1)   # drawn upright or turned
                frames.append((part, Affine.translation(0, e) * turn * Affine.translation(-c.x, -c.y) * local))
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
    port holes are in the first side, put on the right. The switch holder (--switch) has no holes
    to say where it goes and is left out."""
    t, hp = box.thickness, box.clearance_z + box.thickness
    H = box.sbcs * hp + hp / 2
    L = box.y + 2 * box.hole_dist_edge
    sides, rest = parts[:2], parts[3 if box.switch else 2:]
    down = (0, 0, -1)
    out = [(sides[0], Placement((L, 0, H), down, Y, 1)), (sides[1], Placement((0, 0, H), down, Y, -1)),
           (rest[0], Placement((0, 0, 0), X, Y, -1))]
    return out + [(p, Placement((0, 0, H - i * hp - hp / 2 - 1.5 + t / 2), X, Y, -1)) for i, p in enumerate(rest[1:])]


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
    glued inside their walls on the bottom, as in Crate; the optional label strip is left out."""
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
    the first (last) level's instead, across the back. A plain stackable top (S) holds no floor."""
    t, sh, x, d, b, e = box.thickness, box.sh, box.x, box.depth, box.bottom_edge, box.top_edge
    h = sum(sh) + t * (len(sh) - 1)
    levels = [sum(sh[:i + 1]) + (i + 1) * t for i in range(len(sh) - 1)]   # the top faces
    floors = [Placement((0, 0, levels.pop(0) if b == "e" else 0), Y, X, 1),
              Placement((0, 0, levels.pop() if e == "e" else h), Y, X, 1 if e == "e" else -1)]
    if e == "S":
        floors.pop()
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
    tops lie on the walls, their u along the depth (as drawLid draws them, x × y); the v edge's
    hinge parts are left out."""
    t, sy, sh, x = box.thickness, box.sy, box.sh, box.x
    W = sum(sy) + t * (len(sy) - 1)
    h = sum(sh) + t * (len(sh) - 1)
    levels = [sum(sh[:i]) + i * t for i in range(len(sh))]   # top faces: the floor, then the horizontals
    back = (0, -1, 0)
    place = {
        "left": Placement((0, 0, 0), Y, Z, -1),
        "right": Placement((W, x, 0), back, Z, -1),
        "bottom": Placement((0, 0, 0), Y, X, 1),
        "top": Placement((0, 0, h), Y, X, -1, lid=box.top_edge == "c"),
        "back": Placement((0, x, 0), X, Z, -1),
    }
    for i in range(1, len(sh)):
        place[f"inner horizontal {i}"] = Placement((W, 0, levels[i] - t), Y, (-1, 0, 0), 1)
    for i in range(len(sy) - 1):
        place[f"inner vertical {i + 1}"] = Placement((sum(sy[:i + 1]) + i * t, x, 0), back, Z, -1)
    for i, z in enumerate(levels):
        place[f"retainer {i + 1}"] = Placement((0, 0, z), X, Z, 1)
    at = lambda z: Placement((0, 0, z), Y, X, -1, lid=True)
    lids = {"E": [at(h + t), at(h)], "i": [at(h)], "L": [at(h)], "k": [at(h), Placement((0, x, h), back, X, 1, lid=True)],
            "v": [Placement((W, x, h), back, (-1, 0, 0), -1, lid=True)]}.get(box.top_edge, [])
    labels = [p.record.label for p in parts]
    first = max(i for i, l in enumerate(labels) if l in ("left", "right", "bottom") or (l or "").startswith("inner horizontal")) + 1
    out = [(p, place[p.record.label]) for p in parts if p.record.label in place]
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
    plate, one along the arm. Two plates instead of one: the second turned to the right (drawn
    mirrored). The rings (no part of their own) are left out."""
    t, w, d, a, h = box.thickness, box.width, box.diameter, box.axle, box.height
    x0, x1 = h / 4 + t / 2 - 3 * t, h / 4 + t / 2 + t - 3 * t + w     # the arms' mid-planes
    zm = h - 3 * t - a / 2                                            # the braces'
    out = (0, -1, 0)
    sides, braces, plates = parts[:2], parts[2], parts[3:]
    items = [(sides[0], Placement((x0 - t / 2, t, 0), Z, out, 1)), (sides[1], Placement((x1 - t / 2, t, 0), Z, out, 1))]
    corners = [Placement((x0 - t / 2, 0, zm + t / 2), X, out, 1), Placement((x1 + t / 2, 0, zm - t / 2), (-1, 0, 0), out, 1)]
    for (frame, kept), q in zip(_right_triangles(braces, h / 4, t), corners):
        q.keep = kept
        items.append((braces, q, frame))
    if len(plates) == 1:
        items.append((plates[0], Placement((0, 0, 0), X, Z, -1)))
    else:
        items += [(plates[0], Placement((0, 0, 0), X, Z, -1)),
                  (plates[1], Placement((x0 + x1, 0, 0), (-1, 0, 0), Z, 1))]
    return items


RECIPES["WallRollHolder"] = RollHolder   # the same, the arms' joints to the plate for the wall system


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


# ---------------------------------------------------------------- what hangs on the wall

# Where each wall-mounted box's wall is (Y), as its recipe places it: a pegboard is shown there.
WALLS = {
    **{name: (lambda box: box.thickness) for name in (
        "WallConsole", "WallHook", "WallCaliper", "WallSlottedHolder", "WallChiselHolder", "WallPliersHolder",
        "WallWrenchHolder", "WallHopper", "RollHolder", "WallRollHolder", "KeyHolder")},
    "WallPinRow": lambda box: 0.0,
    "WallPlaneHolder": lambda box: 0.0,
    "WallStairs": lambda box: box.y,
    "WallRack": lambda box: (box.adjustSize(box.y) if box.outside else box.y) + box.thickness,
    "WallTypeTray": lambda box: sum(box.sy) + box.thickness * len(box.sy),
    "WallStackableBin": lambda box: box.y + box.thickness,
    "WallDrillBox": lambda box: box.y + box.thickness,
    "DinRailBox": lambda box: box.thickness + 8,       # the rail's back
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
    """A kitchen roll (0.9 of the roll diameter allowed, its 44 mm core; 4 mm shorter than the axle
    between the arms) hanging on its dowel by the core's top, a sheet hanging from its front."""
    t, w, d, a, h = box.thickness, box.width, box.diameter, box.axle, box.height
    x0 = h / 4 + t / 2 - 3 * t                      # the left arm's mid-plane (see RollHolder)
    za, ya = h - a / 2 - 3 * t, -d / 2              # the axle's centre
    R, core, rod = 0.45 * d, 22.0, a / 2 - 0.5
    zr = za - (core - 2 - rod)                      # the core rests on the dowel
    out = _rod("dowel", (x0 - t / 2 - 6, 0, 0), X, Y, (ya, za), rod, 0, w + 2 * t + 12)
    left = x0 + t / 2 + 2
    out += _solid("towel", Placement((left, 0, 0), Y, Z, 1), Point(ya, zr).buffer(R, quad_segs=24).difference(
        Point(ya, zr).buffer(core, quad_segs=16)), w - 4)
    out += _solid("cardboard", Placement((left - 0.5, 0, 0), Y, Z, 1), Point(ya, zr).buffer(core, quad_segs=16).difference(
        Point(ya, zr).buffer(core - 2, quad_segs=16)), w - 3)
    out += _solid("towel", Placement((left, ya - R + 0.3, 0), X, Z, 1), rect(0, zr - R - 70, w - 4, zr), 0.4)
    return out


DECORATIONS.setdefault("RollHolder", []).append(_kitchen_roll)
DECORATIONS.setdefault("WallRollHolder", []).append(_kitchen_roll)


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
    for n, item in enumerate(items):
        part, placement = item[0], item[1]
        if placement is None:
            continue
        local = item[2] if len(item) > 2 else None
        matrix = local if local is not None else local_matrix(part.record)
        cuts = []
        polys = polygons_of(loops_of(part, matrix, cuts), cuts)
        pieces += [dict(p, part=n) for p in placement.pieces(polys, box.thickness)]
    name = type(box).__name__
    for fn in DECORATIONS.get(name, []):
        pieces += fn(box)
    if name in WALLS:
        pieces += pegboard(pieces, WALLS[name](box))
    return {"pieces": pieces, "count": len(parts), "turn": TURN.get(name, 0), "galleryLids": name in GALLERY_LIDS}
