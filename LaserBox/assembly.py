"""Assembled 3D preview: every cut part, extruded by the material thickness, placed in space.

boxes.py only knows the flat sheet, so the parts are recorded while the generator draws them
(which primitive drew them, the local coordinate frame, where the flex cuts are) and a small
recipe per generator says where each part goes. Flexed regions are bent by slicing the part into
narrow strips that follow an arc.

Protocol: assemble(name, args) -> {"pieces": [{"rings": [[[u, v], …], …], "origin": [x, y, z],
"u": [..], "v": [..], "side": ±1, "t": thickness[, "decoration": kind][, "lid": true]}, …], "turn": degrees,
"galleryLids": bool}  — world(u, v, w) = origin + u·U + v·V + w·side·(U×V)
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
    loops, cur, opens = [], [], []  # opens: [points, black]

    def flush(path):
        if len(cur) > 2 and math.dist(cur[0], cur[-1]) < 0.2:  # a corner's kerf offset can leave 0.14
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
    marks other pieces the 3D view can hide (a removable panel), with that kind."""

    def __init__(self, origin, U, V, side=1, bends=(), offset=(0, 0), keep=None, decoration=None, lid=False):
        self.origin, self.U, self.V, self.side, self.bends, self.offset = origin, _norm(U), _norm(V), side, list(bends), offset
        self.keep, self.decoration, self.lid = keep, decoration, lid

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
        DECORATIONS[generator] = lambda box: [dict(p, decoration=p.get("decoration", kind)) for p in fn(box)]
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
    the compartment or the box is: white edges, and on top the first card's back (see card_back),
    red and blue in turn."""
    t = box.thickness
    inlays = t if box.openingdirection == "right" else 0   # glued to the front and back
    depth = box.boxdepth - 2 * inlays
    high = min(17.0, box.boxhight - 0.5)
    out, pos = [], t
    for i, s in enumerate(box.sx):
        w, l = min(63.5, s - 0.5), min(88.9, depth - 0.5)
        x0, y0 = pos + (s - w) / 2, inlays + (depth - l) / 2
        deck = rect(x0 + 3, y0 + 3, x0 + w - 3, y0 + l - 3).buffer(3, quad_segs=4)
        field, pattern = card_back(x0, y0, w, l)
        back = ("cardback", "cardback-blue")[i % 2]
        out += Placement((0, 0, 0), X, Y, 1).pieces([deck], high)
        out += [dict(p, decoration=back) for p in Placement((0, 0, high), X, Y, 1).pieces([field], 0.08)]
        out += Placement((0, 0, high + 0.08), X, Y, 1).pieces(pattern, 0.08)
        pos += s + t
    return out


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
                     place.bends, place.offset, place.keep, place.decoration, place.lid)


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
    name = type(box).__name__
    return {"pieces": pieces, "count": len(parts), "turn": TURN.get(name, 0), "galleryLids": name in GALLERY_LIDS}
