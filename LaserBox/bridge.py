"""Long-running helper between the app and boxes.py.

Reads one JSON request per line on stdin, writes one JSON response per line on stdout:
  {"cmd": "list"}                                   -> {"groups": [...]}
  {"cmd": "args", "name": "UniversalBox"}           -> {"groups": [...]}
  {"cmd": "render", "name": ..., "args": {...}, "format": "svg"|"dxf"} -> {"data": "..."}
  {"cmd": "assemble", "name": ..., "args": {...}}  -> {"pieces": [...]} (see assembly.py)
Errors come back as {"error": "..."}.
Texts are translated with locale/<LASERBOX_LANG>/LC_MESSAGES/boxes.py.mo next to this file.
"""
import argparse
import contextlib
import gettext
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import boxes
import boxes.generators
import markdown
from boxes.generators.traylayout import TrayLayoutFile

import assembly
from types import SimpleNamespace

from affine import Affine
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, polylabel, unary_union
from svgpathtools import Line, parse_path

TRANSLATIONS = gettext.translation("boxes.py", os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale"),
                                   [os.environ.get("LASERBOX_LANG", "en")], fallback=True)
_ = TRANSLATIONS.gettext

boxes.ArgumentParser = type("ThrowingArgumentParser", (argparse.ArgumentParser,), {
    "error": lambda self, message: (_ for _ in ()).throw(ValueError(message))})


def _adjust_size(adjust):
    """boxes.py's adjustSize (outside sizes to inside ones) takes off each edge's startWidth and
    margin, and a stackable edge's margin has the spacing between parts in it (room on the sheet
    for its stabilizer strip): the box would shrink as the parts are spread. Here without it."""
    def adjustSize(self, *a, **kw):
        spacing, self.spacing = self.spacing, 0.0
        try:
            return adjust(self, *a, **kw)
        finally:
            self.spacing = spacing
    return adjustSize


boxes.Boxes.adjustSize = _adjust_size(boxes.Boxes.adjustSize)

# boxes.py's "Unstable" group (generators still being worked on) is left out.
# Nor the Otto robot's body, legs and soles, nor the generators the user dropped.
DROPPED = {"AirPurifier", "PizzaShovel", "AgricolaInsert", "RoyalGame", "DrillGauge", "Folder", "MakitaPowerSupply"}
GENERATORS = {cls.__name__: cls for cls in boxes.generators.getAllBoxGenerators().values()
              if cls.webinterface and cls.ui_group != "Unstable" and not cls.__name__.startswith("Otto")
              and cls.__name__ not in DROPPED}


class RollHolder(boxes.generators.wallrollholder.WallRollHolder):
    """Holder for kitchen rolls or other rolls"""

    def __init__(self) -> None:
        super().__init__()
        walltype = next(a for a in self.argparser._actions if a.dest == "walltype")
        walltype.choices, walltype.default = ["screws", *walltype.choices], "screws"
        self.argparser.add_argument(
            "--screw_holes", action="store", type=float, default=4,
            help="diameter of mounting holes in mm")
        self.argparser.add_argument(
            "--one_piece", action="store", type=boxes.boolarg, default=True,
            help="have a continuous back plate instead of two separate holders")

    def _impl(self):
        """boxes.py's RollHolder screwed to the wall, its WallRollHolder on a wall system."""
        screwed = self.walltype == "screws"
        return boxes.generators.rollholder.RollHolder if screwed else boxes.generators.wallrollholder.WallRollHolder

    def side(self, move=None):
        return self._impl().side(self, move)

    def backCB(self):
        return self._impl().backCB(self)

    def rings(self):
        self.rings_at = self.ctx._m  # where the rings start: the 3D view places them from it
        return self._impl().rings(self)

    def render(self):
        return self._impl().render(self)


# One roll holder, screwed or on a wall system: boxes.py's two, merged.
GENERATORS["RollHolder"] = RollHolder
del GENERATORS["WallRollHolder"]
# Not offered: the reference rectangle and its QR code are never drawn, debug is off (see configure).
SKIPPED = {"input", "output", "format", "help", "reference", "qr_code", "debug"}
# Options taken out of single generators (left at boxes.py's default).
SKIPPED_BY = {"SBCMicroRack": {"switch"}}  # the switch holder: nothing says where it goes
# The app's own defaults where they differ from boxes.py's (the app sends only the values changed).
DEFAULTS = {
    "CardBox": {"y": 89, "h": 17, "sx": "63.5*2", "openingdirection": "right", "fingerhole": "custom",
                "fingerhole_depth": 10},
    "RobotArm": {"type1": "RobotArmMm", "type2": "RobotArmMu"},  # boxes.py's draws no segment
}
INFO_LINK = re.compile(r"\s*\[[^\]]*\]\([^)]*\)")  # the web form's "[🛈](url)" help links


def make(name):
    """A generator with the app's defaults, and its spacing between parts in mm (2 by default)."""
    box = GENERATORS[name]()
    for a in box.argparser._actions:
        if a.dest == "spacing":  # boxes.py's: thicknesses [: extra mm]
            a.type, a.default, a.help = spacing_mm, "2", "space between parts in mm"
    box.argparser.set_defaults(**DEFAULTS.get(name, {}))
    return box


def spacing_mm(value):
    """The spacing as boxes.py takes it: no thicknesses, the mm extra (the burn is added to it)."""
    return 0.0, float(value)


def tr(text):
    return _(text) if text else ""


def doc(cls):
    return " ".join(tr(cls.__doc__).split())


def info(cls):
    return {"name": cls.__name__, "title": tr(cls.__name__), "doc": doc(cls),
            "assembled": cls.__name__ in assembly.RECIPES}


# The test pieces (BurnTest, FlexTest…) get a category of their own, last.
TESTS = argparse.Namespace(name="Tests", title="Tests", description="Pieces for trying out the laser settings")


def list_generators():
    by_group = {}
    for cls in GENERATORS.values():
        by_group.setdefault(TESTS.name if "test" in cls.__name__.lower() else cls.ui_group, []).append(info(cls))
    return {"groups": [
        {"name": g.name, "title": tr(g.title), "description": tr(g.description),
         "generators": sorted(by_group.get(g.name, []), key=lambda b: b["title"].casefold())}
        for g in [*boxes.generators.ui_groups, TESTS] if by_group.get(g.name)]}


# Words for boxes.py's short parameter names (x, h, sx…), by what their help says they are there
# ("h" is mostly the height); "*": whatever the help.
PARAMETER_NAMES = {
    ('ah', 'air hole sections bottom to top in mm'): 'air holes, bottom to top',
    ('aw', 'air hole slot width in mm'): 'air hole width',
    ('ax', 'air hole sections left to right in %% of the box width'): 'air holes, left to right',
    ('ay', 'air hole sections back to front in %% of the box depth'): 'air holes, back to front',
    ('d', 'Diameter of top hole [mm]'): 'top hole diameter',
    ('d', 'bin (d)epth'): 'bin depth',
    ('d', 'clearance of the lid'): 'lid clearance',
    ('d1', 'Diameter of the inner lid screw holes in mm'): 'inner lid screw holes',
    ('d2', 'Diameter of the lid screw holes in mm'): 'lid screw holes',
    ('d3', 'Diameter of the mounting screw holes in mm'): 'mounting screw holes',
    ('eye', 'radius of the eye (multiples of thickness)'): 'eye radius',
    ('fw', 'distance of flex cuts in multiples of thickness'): 'flex cut distance',
    ('gap', 'the gap between grooves (fraction of the edge length)'): 'groove gap',
    ('gh', 'height of the grip hole in mm'): 'grip hole height',
    ('gw', 'width of th grip hole in mm (zero for no hole)'): 'grip hole width',
    ('h', 'Height of the matrix'): 'height',
    ('h', 'depth (with walls if outside is selected) in mm'): 'depth',
    ('h', 'height of the ramp in mm'): 'height',
    ('h', "height in mm or add 'u' at the end for Gridfinity units"): 'height',
    ('h', 'height of sidewalls of the tray (mm)'): 'side wall height',
    ('h', 'height of the box'): 'height',
    ('h', 'height of the front plate (in mm) - needs to be at least 7 time the thickness'): 'front plate height',
    ('h', 'height of the lid'): 'lid height',
    ('h', 'height separation walls in mm'): 'separator height',
    ('h', 'inner height in mm'): 'height',
    ('h', 'inner height in mm (unless outside selected)'): 'height',
    ('hi', '*'): 'inner walls height',
    ('hp', 'Width of the case in HP'): 'width (HP)',
    ('id', 'add identifier etching to each piece'): 'identifier',
    ('m', 'Extra margin around the gridfinity base to allow it to drop into the carrier (mm)'): 'margin',
    ('n', 'Number of reinforcement triangle inside'): 'reinforcements',
    ('n', 'number of lights'): 'lights',
    ('n', 'number of sides'): 'sides',
    ('n', 'number of sides on the lid. n ≥ 3'): 'sides',
    ('n', 'number of walls at one side (1+)'): 'walls',
    ('num', 'number of holdfasts'): 'holdfasts',
    ('num', 'number of mounting holes (integer)'): 'mounting holes',
    ('num', 'number of shelves'): 'shelves',
    ('nx', 'Number of holes in width (X).'): 'holes across',
    ('nx', 'number of gridfinity grids in X direction'): 'grids across',
    ('ny', 'Number of holes in depth (Y).'): 'holes in depth',
    ('ny', 'number of gridfinity grids in Y direction'): 'grids in depth',
    ('pin', 'diameter of the pin in mm'): 'pin diameter',
    ('sh', 'sections bottom to top in mm'): 'section heights',
    ('sx', 'sections left to right in mm'): 'compartment widths',
    ('sy', 'sections back to front in mm'): 'compartment depths',
    ('top', 'overlap of top rim (zero for none)'): 'top rim',
    ('top', 'style of the top and lid'): 'top style',
    ('x', 'Width of the photo, not including any border'): 'photo width',
    ('x', 'X dimension of tray/box that this fits into'): 'tray width',
    ('x', 'inner width in mm'): 'width',
    ('x', 'inner width in mm (unless outside selected)'): 'width',
    ('x', 'number of grids in X direction (0=auto)'): 'grids across',
    ('x', 'outer width of the most outer layer'): 'width',
    ('x', 'width of the ramp in mm, generally the width of the step the ramp is built for'): 'width',
    ('y', 'Height of the photo, not including any border'): 'photo height',
    ('y', 'Y dimension of tray/box that this fits into'): 'tray depth',
    ('y', 'depth of the ramp in mm, will influence the steepness of the ramp'): 'depth',
    ('y', 'inner depth in mm'): 'depth',
    ('y', 'inner depth in mm (unless outside selected)'): 'depth',
    ('y', 'number of grids in Y direction (0=auto)'): 'grids in depth',
    ('y', 'outer width of the most outer layer'): 'depth',
    ('z', 'depth of the shorter (rackear) side'): 'rear depth',
    ('z', 'height of the box'): 'height',
    ('z', 'inner depth in mm'): 'depth',
    ("width", "Width of linkages"): "link width",
    ("height", "height of the body"): "body height",
    # by generator: a Z beam's walls (two flanges, the web between) and its length
    ("ZBeam", "x"): "first flange", ("ZBeam", "y"): "web", ("ZBeam", "z"): "second flange", ("ZBeam", "h"): "length",
}


def label(action, prefix, generator=""):
    name = action.dest
    name = name[len(prefix) + 1:] if prefix and name.startswith(prefix + "_") else name
    help_ = INFO_LINK.sub("", action.help or "").strip()
    if words := (PARAMETER_NAMES.get((generator, name)) or PARAMETER_NAMES.get((name, help_))
                 or PARAMETER_NAMES.get((name, "*"))):
        return TRANSLATIONS.pgettext("parameter", words)
    return tr(name)


def describe(action, prefix, generator):
    arg = {"name": action.dest, "label": label(action, prefix, generator), "help": INFO_LINK.sub("", tr(action.help)).strip(),
           "default": str(action.default)}
    if isinstance(action.type, boxes.BoolArg):
        arg.update(kind="bool", default="1" if action.default else "0")
    elif isinstance(action.type, boxes.ArgparseEdgeType):
        arg.update(kind="choice", choices=[{"value": e, "label": tr(f"{e} {action.type.names[e]}" if e in action.type.names else e)}
                                           for e in action.type.edges])
    elif action.choices:
        arg.update(kind="choice", choices=[{"value": str(c), "label": tr(c) if isinstance(c, str) else str(c)}
                                           for c in action.choices])
    elif generator == "FrontPanel" and action.dest == "layout":
        arg.update(kind="panels")  # edited as panels and holes (FrontPanelEditor.swift)
    elif isinstance(action.default, str) and "\n" in action.default:
        arg.update(kind="multiline")
    else:
        arg.update(kind="text")
    return arg


def generator_args(name):
    box = make(name)
    groups = []
    for group in box.argparser._action_groups:
        args = [describe(a, getattr(group, "prefix", None), name) for a in group._group_actions
                if a.dest not in SKIPPED | SKIPPED_BY.get(name, set())]
        if args:
            groups.append({"title": tr(group.title), "args": args, "advanced": group.title.startswith("Settings for")})
    # The generator's own settings first, then the defaults, then the edge settings.
    groups.sort(key=lambda g: g["advanced"])
    description = markdown.markdown(tr(type(box).description), extensions=["extra"]).replace('src="static/', 'src="')
    return {**info(type(box)), "description": description, "groups": groups}


def configure(box, args):
    """The generator's arguments, and what the web form would add."""
    box.parseArgs([f"--{k}={v}" for k, v in args.items()])
    box.reference, box.qr_code, box.debug = 0, False, False
    if isinstance(box, boxes.generators.traylayout.TrayLayout) and not hasattr(box, "generate_layout"):
        # An empty layout means "every compartment from sx and sy", like the web form's first step
        # (GridfinityTrayLayout makes its own).
        def generate_layout():
            skeleton = TrayLayoutFile()
            skeleton.fillDefault(box.sx, box.sy)
            return str(skeleton)
        box.generate_layout = generate_layout


def render(name, args, fmt):
    box = make(name)
    box.translations = TRANSLATIONS
    try:
        configure(box, args)
        assembly.start()  # the parts recorded as the 3D view does: what each piece is, for its label
        box.open()
        box.render()
        box.ctx.stroke()  # the last path, before the parts move (close() would stroke it after)
        drawn = part_groups(box.ctx._dwg.parts)
        try:
            roles = assembly.piece_roles(box) if name in assembly.RECIPES else []
        except Exception:  # a recipe that can't place these settings: no names from the 3D view
            roles = []
        add_labels(drawn, box, roles)
        pack(drawn, box.spacing)
        upright_labels(box.ctx._dwg.parts)
    except Exception as e:
        raise ValueError(translate_error(str(e), box)) from e
    data = box.close()
    if data is None:
        raise ValueError(_("{name} doesn't draw anything").replace("{name}", tr(name)))
    svg = data.getvalue().decode()
    return svg if fmt == "svg" else svg_to_dxf(svg)


def maxrects(sizes, width, gap):
    """Places rectangles (w, h), largest first, in a strip `width` wide, each where its top ends
    lowest (then leftmost), turned a quarter if that is better; gap between them. -> ([(x, y,
    turned)], height). MaxRects: the free space is kept as maximal rectangles."""
    free, places, top = [(0.0, 0.0, width + gap, math.inf)], [None] * len(sizes), 0.0
    for i in sorted(range(len(sizes)), key=lambda i: -sizes[i][0] * sizes[i][1]):
        best = None
        for fx, fy, fw, fh in free:
            for turned in (False, True):
                w, h = sizes[i][::-1] if turned else sizes[i]
                if w + gap <= fw + 1e-9 and h + gap <= fh + 1e-9 and (best is None or (fy + h, fx) < best[0]):
                    best = ((fy + h, fx), fx, fy, turned)
        if best is None:
            return None, math.inf
        _, x, y, turned = best
        w, h = sizes[i][::-1] if turned else sizes[i]
        places[i], top = (x, y, turned), max(top, y + h)
        px1, py1 = x + w + gap, y + h + gap
        split = []
        for f in free:
            fx, fy, fw, fh = f
            if x >= fx + fw or px1 <= fx or y >= fy + fh or py1 <= fy:
                split.append(f)
                continue
            split += [r for r in ((fx, fy, x - fx, fh), (px1, fy, fx + fw - px1, fh),
                                  (fx, fy, fw, y - fy), (fx, py1, fw, fy + fh - py1)) if r[2] > 1e-9 and r[3] > 1e-9]
        split = list(dict.fromkeys(split))
        free = [a for a in split if not any(b != a and b[0] <= a[0] and b[1] <= a[1] and a[0] + a[2] <= b[0] + b[2]
                                            and a[1] + a[3] <= b[1] + b[3] for b in split)]
    return places, top


BED_WEIGHT = 0.3  # how much a sheet off the bed's shape costs, per e-fold of its aspect ratio


def part_groups(parts):
    """The drawn parts that touch or overlap, together: a wall whose drawing a nested part interrupted
    goes on in a part of its own, a ring is drawn in its plate's hole; they move as one."""
    parts = [p for p in parts if p.pathes]
    boxes_ = [p.extents() for p in parts]
    owner = list(range(len(parts)))

    def root(i):
        while owner[i] != i:
            owner[i] = owner[owner[i]]
            i = owner[i]
        return i

    for i, a in enumerate(boxes_):
        for j in range(i):
            b = boxes_[j]
            if a.xmin <= b.xmax + 0.01 and b.xmin <= a.xmax + 0.01 and a.ymin <= b.ymax + 0.01 and b.ymin <= a.ymax + 0.01:
                owner[root(i)] = root(j)
    out = {}
    for i, p in enumerate(parts):
        out.setdefault(root(i), []).append(p)
    return list(out.values())


def pack(groups_, gap):
    """Moves the groups of drawn parts (each as a whole, maybe turned a quarter) closer together:
    their bounding boxes packed `gap` apart (the generator's spacing) in the strip width, among some
    tried, that gives the smallest sheet, shaped like a laser's bed (3:2, landscape): area weighed by
    how far the shape is from it. Kept as drawn unless that scores better."""
    if len(groups_) < 2:
        return
    boxes_ = [sum([p.extents() for p in g[1:]], g[0].extents()) for g in groups_]
    sizes = [(e.width, e.height) for e in boxes_]
    drawn = sum(boxes_[1:], boxes_[0])
    widest, total = max(max(s) for s in sizes), sum(min(s) + gap for s in sizes)

    def score(w, h):
        return w * h * (1 + BED_WEIGHT * abs(math.log(w / h / 1.5)))

    best = (score(drawn.width, drawn.height) * (1 - 1e-6), None)
    for k in range(25):
        width = widest * (max(total, widest) / widest) ** (k / 24)
        places, height = maxrects(sizes, width, gap)
        if places is None:
            continue
        used = max(x + (s[1] if turned else s[0]) for (x, y, turned), s in zip(places, sizes))
        if (area := score(used, height)) < best[0]:
            best = (area, places)
    if best[1] is None:
        return
    for g, e, (x, y, turned) in zip(groups_, boxes_, best[1]):
        m = (Affine.translation(x + e.ymax, y - e.xmin) * Affine.rotation(90) if turned
             else Affine.translation(x - e.xmin, y - e.ymin))
        for p in g:
            p.transform(1.0, m)


LABEL_SIZES = (4, 3, 2)  # mm: boxes.py's labels, then smaller; a piece too small for 2 gets none
LABEL_MARGIN = 0.8       # mm from any cut


def _text_box(m, text, fs, align):
    """The outline a text takes: its matrix's local x along the line (by alignment), y up to fs."""
    w = 0.6 * fs * len(text)
    x0 = {"left": 0, "middle": -w / 2, "end": -w}[align]
    return Polygon([m * (x, y) for x, y in ((x0, -0.15 * fs), (x0 + w, -0.15 * fs), (x0 + w, fs), (x0, fs))])


def _label_spot(free, text, angle, sizes):
    """(centre, angle, size) for a text centred in `free` (a piece shrunk by the margin) near the
    point farthest from its cuts, at the first size and angle (the given one, then across) it fits."""
    target = polylabel(max(getattr(free, "geoms", [free]), key=lambda g: g.area), tolerance=0.5)
    for fs in sizes:
        for a in (angle, angle + 90):
            w, h = 0.6 * fs * len(text), 1.15 * fs
            # turned and squeezed so the text's box is an h × h square: its centres lie at least
            # h / √2 in from the edges (its circumcircle), then back
            to = Affine.scale(h / w, 1) * Affine.rotation(-a)
            valid = affine_transform(free, to.to_shapely()).buffer(-h / 2 ** 0.5)
            if valid.is_empty:
                continue
            t = affine_transform(target, to.to_shapely())
            c = t if valid.contains(t) else nearest_points(valid, t)[0]
            centre = ~to * (c.x, c.y)
            m = Affine.translation(*centre) * Affine.rotation(a) * Affine.translation(0, -fs / 2)
            if _text_box(m, text, fs, "middle").within(free):
                return m, fs
    return None


# What a piece is, by the generator's method that drew it: a name, or (generic) a name to use only
# when the 3D view says nothing better. Other methods (render, cornerRadius…) say nothing.
CALLER_NAMES = {
    "PCB_Clamp": "PCB clamp", "ankles": "ankle", "balcony_wall": "balcony wall", "basePlate": "base plate",
    "bottomPart": "bottom part", "brace": "brace", "comb": "comb", "dice": "die", "drawTop": "top",
    "flexBookLatchBracket": "latch bracket", "flexBookLatchPin": "latch pin", "flexBookLatchWall": "latch wall",
    "flexBookRecessedWall": "recessed wall", "foot": "foot", "fork": "fork", "frame": "frame", "front": "front",
    "generate_shelves": "shelf", "heddle": "heddle", "innerRibs": "inner rib", "innerWall": "inner wall",
    "laptopstand_triangles": "triangle", "latch": "latch", "layer": "layer", "lidSide": "lid side",
    "lid_lip": "lid lip", "link": "link", "lock": "lock", "lockPin": "lock pin", "lock_part": "lock part",
    "middleWall": "middle wall", "needle": "needle", "outerWall": "outer wall", "panel_cross_beam": "cross beam",
    "panel_side": "panel side", "railSet": "rail", "render_back_plate": "back plate",
    "render_bottom_support": "bottom support", "render_card_divider_tray": "card tray",
    "render_front_plate": "front plate", "render_moor_box": "moor box", "render_plate": "plate",
    "render_player_box": "player box", "render_room_box": "room box", "render_side_plate": "side plate",
    "render_simple_tray": "tray", "render_simple_tray_divider": "tray divider", "roof": "roof",
    "roof_tile": "roof tile", "seven_segment_separators": "separator", "shuttle": "shuttle",
    "sideHolders": "side holder", "support": "support", "supportWall": "support wall", "topHandle": "handle",
    "topStabilizers": "top stabilizer",
}
GENERIC_CALLER_NAMES = {
    "side": "side", "side2": "side", "sideWall": "side", "sidewall": "side", "flexBoxSide": "side",
    "flexBookSide": "side", "wall": "wall", "xWall": "wall", "yWall": "wall", "xOutsideWall": "wall",
    "surroundingWall": "flex wall",
}


def piece(name):
    return TRANSLATIONS.pgettext("piece", name)


def _piece_name(q, g, roles, alone, box):
    """A name for the drawn piece q of the group g: its method's, else its 3D role (roles: from
    assembly.piece_roles), else the generic method's, else the generator's when it is the only
    piece, else "panel w×h" (a wall's inner size) or "piece w×h"."""
    inside = [p for p in g if getattr(p, "record", None) and _contains(p.extents(), q.representative_point())]
    record = min(inside, key=lambda p: p.extents().width * p.extents().height).record if inside else None
    caller = record.caller if record else None
    if caller in CALLER_NAMES:
        return piece(CALLER_NAMES[caller])
    match = [(r.intersection(q).area / r.union(q).area, role) for r, role in roles if r.intersects(q)]
    if match and max(match)[0] > 0.6:
        return piece(max(match)[1])
    if caller in GENERIC_CALLER_NAMES:
        return piece(GENERIC_CALLER_NAMES[caller])
    if alone:
        return tr(type(box).__name__)
    if record and record.primitive == "rectangularWall" and len(record.args) >= 2:
        try:
            return f"{piece('panel')} {float(record.args[0]):.4g}×{float(record.args[1]):.4g}"
        except (TypeError, ValueError):
            pass
    x0, y0, x1, y1 = q.bounds
    return f"{piece('piece')} {x1 - x0:.0f}×{y1 - y0:.0f}"


def _contains(e, point):
    return e.xmin - 0.01 <= point.x <= e.xmax + 0.01 and e.ymin - 0.01 <= point.y <= e.ymax + 0.01


def _pieces(g):
    """The pieces cut from a group of drawn parts: the outlines cut in black (what is cut in blue,
    holes, falls out), in sheet coordinates."""
    pathes = [p for part in g for p in part.pathes]
    cuts = []
    pieces = assembly.polygons_of(assembly.loops_of(SimpleNamespace(pathes=pathes), Affine.identity(), cuts), cuts)
    black_cuts = []  # slits (a flex cut, a shoe's) are outline too: the piece's ring runs along them
    outer = unary_union([LineString(l + l[:1]) for l in assembly.loops_of(
        SimpleNamespace(pathes=[p for p in pathes if assembly._is_black(p.params.get("rgb"))]), Affine.identity(),
        black_cuts)] + [LineString(c) for c in black_cuts if len(c) > 1])
    return [q for q in pieces if q.exterior.distance(outer) < 0.3 and
            outer.distance(q.exterior.interpolate(0.5, normalized=True)) < 0.3]


def add_labels(groups_, box, roles=()):
    """A label on every piece: boxes.py's (red text) kept where it lies clear of the cuts, moved to
    a clear spot (smaller if need be) where it doesn't, and a name (see _piece_name) on the pieces
    without one; none on a piece too small for it."""
    if not box.labels:
        return
    cut = [_pieces(g) for g in groups_]
    alone = sum(map(len, cut)) == 1
    for g, pieces in zip(groups_, cut):
        pathes = [p for part in g for p in part.pathes]
        texts = [(c, p) for p in pathes for c in p.path
                 if c[0] == "T" and c[5]["rgb"] == boxes.Color.ANNOTATIONS and c[4].strip()]
        mine = {id(q): [] for q in pieces}
        for c, p in texts:
            centre = _text_box(c[3], c[4], c[5]["fs"], c[5].get("align", "left")).centroid
            home = [q for q in pieces if Polygon(q.exterior).contains(centre)]
            # beside its piece (on a slot, between two): the nearest one it would fit on, if near
            near = [q for q in pieces if q.area > 4 * _text_box(Affine.identity(), c[4], LABEL_SIZES[-1], "left").area
                    and q.distance(centre) < 20]
            if home or near:
                mine[id(min(home, key=lambda q: q.area) if home else min(near, key=lambda q: q.distance(centre)))].append(c)
        new = []
        # clear of the other texts too (etched values, labels already placed)
        writing = {id(c): _text_box(c[3], c[4], c[5]["fs"], c[5].get("align", "left")).buffer(LABEL_MARGIN)
                   for p in pathes for c in p.path if c[0] == "T" and c[4].strip()}

        def clear(q, but=None):
            return q.buffer(-LABEL_MARGIN).difference(unary_union([b for i, b in writing.items() if i != but]))

        for q in sorted(pieces, key=lambda q: (-q.bounds[3], q.bounds[0])):  # top left first
            if q.buffer(-LABEL_MARGIN).is_empty:
                continue
            for c in mine[id(q)]:
                m, text, params = c[3], c[4], c[5]
                free = clear(q, but=id(c))
                if free.is_empty or _text_box(m, text, params["fs"], params.get("align", "left")).within(free):
                    continue
                spot = _label_spot(free, text, math.degrees(math.atan2(m.d, m.a)),
                                   [params["fs"]] + [fs for fs in LABEL_SIZES if fs < params["fs"]])
                c[3], c[4] = (spot[0], text) if spot else (m, "")  # no room: dropped
                if spot:
                    c[1], c[2] = spot[0].c, spot[0].f
                    params.update(fs=spot[1], align="middle")
                writing[id(c)] = _text_box(c[3], c[4], params["fs"], params.get("align", "left")).buffer(LABEL_MARGIN)
            free = clear(q)
            if not mine[id(q)] and not free.is_empty:
                w, h = q.bounds[2] - q.bounds[0], q.bounds[3] - q.bounds[1]
                text = _piece_name(q, g, roles, alone, box)
                if spot := _label_spot(free, text, 0 if w >= h else 90, LABEL_SIZES):
                    m, fs = spot
                    new.append(["T", m.c, m.f, m, text, {"ff": ("sans-serif", False, False), "fs": fs, "lw": 0,
                                                         "rgb": boxes.Color.ANNOTATIONS, "align": "middle"}])
                    writing[id(new[-1])] = _text_box(m, text, fs, "middle").buffer(LABEL_MARGIN)
        for c in new:
            g[-1].pathes.append(boxes.drawing.Path([c], dict(c[5])))


def upright_labels(parts):
    """Labels read left to right or bottom to top, however their part was turned: the others are
    turned half round about their middle."""
    for p in parts:
        for path in p.pathes:
            for c in path.path:
                if c[0] == "T" and c[5]["rgb"] == boxes.Color.ANNOTATIONS:
                    m = c[3]
                    if not -89.5 < math.degrees(math.atan2(m.d, m.a)) < 90.5:
                        mid = _text_box(m, c[4], c[5]["fs"], c[5].get("align", "left")).centroid
                        c[3] = Affine.translation(mid.x, mid.y) * Affine.rotation(180) * Affine.translation(-mid.x, -mid.y) * m
                        c[1], c[2] = c[3].c, c[3].f


def translate_error(message, box):
    """Exact catalog match, then the argparse wording, then templates like "Need at least {n} walls"."""
    if (translated := _(message)) != message:
        return translated
    if m := re.match(r"argument --(\w+): invalid .*?: '(.*)'", message):
        action = next((a for a in box.argparser._actions if a.dest == m[1]), None)
        group = next((g for g in box.argparser._action_groups if action in g._group_actions), None)
        name = label(action, getattr(group, "prefix", None), type(box).__name__) if action else m[1]
        return _("Invalid value for “{label}”: {value}").replace("{label}", name).replace("{value}", m[2])
    for template, translated in TRANSLATIONS._catalog.items() if hasattr(TRANSLATIONS, "_catalog") else ():
        placeholders = re.findall(r"\{[^}]*\}", template) if isinstance(template, str) else []
        if not placeholders:
            continue
        pattern = re.sub(r"\\\{[^}]*\\\}", "(.+?)", re.escape(template))
        if m := re.fullmatch(pattern, message, re.S):
            for placeholder, value in zip(placeholders, m.groups()):
                translated = translated.replace(placeholder, value)
            return translated
    return message


def svg_to_dxf(svg, tolerance=0.1):
    """R12 DXF in mm: every path becomes LINE entities, one layer per stroke colour. Text is left out."""
    root = ET.fromstring(svg)
    height = float(root.get("viewBox").split()[3])
    ns = "{http://www.w3.org/2000/svg}"
    out = ["0", "SECTION", "2", "HEADER", "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
           "0", "SECTION", "2", "ENTITIES"]
    for el in root.iter(ns + "path"):
        # ponytail: assumes untransformed absolute paths, which is what boxes.py writes today.
        layer = re.sub(r"\W", "_", el.get("stroke", "rgb(0,0,0)"))
        for seg in parse_path(el.get("d", "")):
            steps = 1 if isinstance(seg, Line) else max(2, int(seg.length() / tolerance ** 0.5 / 2))
            pts = [seg.point(i / steps) for i in range(steps + 1)]
            for a, b in zip(pts, pts[1:]):
                out += ["0", "LINE", "8", layer,
                        "10", f"{a.real:.4f}", "20", f"{height - a.imag:.4f}",
                        "11", f"{b.real:.4f}", "21", f"{height - b.imag:.4f}"]
    out += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(out) + "\n"


def handle(req):
    if req["cmd"] == "list":
        return list_generators()
    if req["cmd"] == "args":
        return generator_args(req["name"])
    if req["cmd"] == "render":
        return {"data": render(req["name"], req.get("args", {}), req.get("format", "svg"))}
    if req["cmd"] == "assemble":
        box = make(req["name"])
        box.translations = TRANSLATIONS
        try:
            configure(box, req.get("args", {}))
            return assembly.assemble(box)
        except Exception as e:
            raise ValueError(translate_error(str(e), box)) from e
    raise ValueError(f"unknown command {req['cmd']}")


def main():
    out = sys.stdout
    for line in sys.stdin:
        # Generators may print; keep stdout for the protocol only.
        with contextlib.redirect_stdout(sys.stderr):
            try:
                resp = handle(json.loads(line))
            except Exception as e:
                resp = {"error": str(e) or type(e).__name__}
        out.write(json.dumps(resp) + "\n")
        out.flush()


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        groups = list_generators()["groups"]
        assert len(groups) > 3 and groups[-1]["name"] == "Tests"
        assert "Unstable" not in {g["name"] for g in groups} and "Castle" not in GENERATORS
        assert {g["name"] for g in groups[-1]["generators"]} == {"BurnTest", "FillTest", "FlexTest", "FlexTest2"}
        spec = generator_args("UniversalBox")
        assert any(a["name"] == "x" for g in spec["groups"] for a in g["args"])
        svg = render("UniversalBox", {"x": "120"}, "svg")
        assert svg.startswith("<?xml") and "<path" in svg
        assert "burn:" not in render("UniversalBox", {"reference": "100", "qr_code": "1"}, "svg")  # no reference
        w, h = map(float, re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', render("UniversalBox", {}, "svg")).groups())
        assert 1.3 < w / h < 1.7, (w, h)  # five squares drawn 2 × 3 upright, packed 3 × 2 across
        assert ">lid front<" in render("HingeBox", {}, "svg")  # unlabelled pieces named from the 3D view
        labels = {a["name"]: a["label"] for g in spec["groups"] for a in g["args"]}
        assert (labels["x"], labels["h"], labels["spacing"]) == ("width", "height", "spacing"), labels
        box = make("UniversalBox")
        configure(box, {})
        box.open()
        assert abs(box.spacing - (2 + 2 * box.burn)) < 1e-9, box.spacing  # 2 mm apart

        def piece_areas(spacing):
            box = make("StackableBin")
            configure(box, {"spacing": spacing})
            assembly.start()
            box.open()
            box.render()
            box.ctx.stroke()
            return sorted(round(q.area) for g in part_groups(box.ctx._dwg.parts) for q in _pieces(g))
        assert piece_areas("2") == piece_areas("7")  # the spacing moves pieces, never resizes them
        dxf = svg_to_dxf(svg)
        assert dxf.count("\nLINE\n") > 50 and dxf.endswith("EOF\n")
        try:
            render("UniversalBox", {"x": "abc"}, "svg")
            raise AssertionError("bad value accepted")
        except ValueError as e:
            assert "“width”" in str(e), e
        assert "<path" in render("TrayLayout", {}, "svg")
        print("ok")
    else:
        main()
