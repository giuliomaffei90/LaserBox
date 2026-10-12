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
import os
import re
import sys
import xml.etree.ElementTree as ET

import boxes
import boxes.generators
import markdown
from boxes.generators.traylayout import TrayLayoutFile

import assembly
from svgpathtools import Line, parse_path

TRANSLATIONS = gettext.translation("boxes.py", os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale"),
                                   [os.environ.get("LASERBOX_LANG", "en")], fallback=True)
_ = TRANSLATIONS.gettext

boxes.ArgumentParser = type("ThrowingArgumentParser", (argparse.ArgumentParser,), {
    "error": lambda self, message: (_ for _ in ()).throw(ValueError(message))})

GENERATORS = {cls.__name__: cls for cls in boxes.generators.getAllBoxGenerators().values() if cls.webinterface}
SKIPPED = {"input", "output", "format", "help"}
INFO_LINK = re.compile(r"\s*\[[^\]]*\]\([^)]*\)")  # the web form's "[🛈](url)" help links


def tr(text):
    return _(text) if text else ""


def doc(cls):
    return " ".join(tr(cls.__doc__).split())


def info(cls):
    return {"name": cls.__name__, "title": tr(cls.__name__), "doc": doc(cls),
            "assembled": cls.__name__ in assembly.RECIPES}


def list_generators():
    by_group = {}
    for cls in GENERATORS.values():
        by_group.setdefault(cls.ui_group, []).append(info(cls))
    return {"groups": [
        {"name": g.name, "title": tr(g.title), "description": tr(g.description),
         "generators": sorted(by_group.get(g.name, []), key=lambda b: b["title"].casefold())}
        for g in boxes.generators.ui_groups if by_group.get(g.name)]}


def label(action, prefix):
    name = action.dest
    return tr(name[len(prefix) + 1:] if prefix and name.startswith(prefix + "_") else name)


def describe(action, prefix):
    arg = {"name": action.dest, "label": label(action, prefix), "help": INFO_LINK.sub("", tr(action.help)).strip(),
           "default": str(action.default)}
    if isinstance(action.type, boxes.BoolArg):
        arg.update(kind="bool", default="1" if action.default else "0")
    elif isinstance(action.type, boxes.ArgparseEdgeType):
        arg.update(kind="choice", choices=[{"value": e, "label": tr(f"{e} {action.type.names[e]}" if e in action.type.names else e)}
                                           for e in action.type.edges])
    elif action.choices:
        arg.update(kind="choice", choices=[{"value": str(c), "label": tr(c) if isinstance(c, str) else str(c)}
                                           for c in action.choices])
    elif isinstance(action.default, str) and "\n" in action.default:
        arg.update(kind="multiline")
    else:
        arg.update(kind="text")
    return arg


def generator_args(name):
    box = GENERATORS[name]()
    groups = []
    for group in box.argparser._action_groups:
        args = [describe(a, getattr(group, "prefix", None)) for a in group._group_actions if a.dest not in SKIPPED]
        if args:
            groups.append({"title": tr(group.title), "args": args, "advanced": group.title.startswith("Settings for")})
    # The generator's own settings first, then the defaults, then the edge settings.
    groups.sort(key=lambda g: g["advanced"])
    description = markdown.markdown(tr(type(box).description), extensions=["extra"]).replace('src="static/', 'src="')
    return {**info(type(box)), "description": description, "groups": groups}


def render(name, args, fmt):
    box = GENERATORS[name]()
    box.translations = TRANSLATIONS
    try:
        box.parseArgs([f"--{k}={v}" for k, v in args.items()])
        if isinstance(box, boxes.generators.traylayout.TrayLayout):
            # An empty layout means "every compartment from sx and sy", like the web form's first step.
            def generate_layout():
                skeleton = TrayLayoutFile()
                skeleton.fillDefault(box.sx, box.sy)
                return str(skeleton)
            box.generate_layout = generate_layout
        box.open()
        box.render()
    except Exception as e:
        raise ValueError(translate_error(str(e), box)) from e
    data = box.close()
    if data is None:
        raise ValueError(_("{name} doesn't draw anything").replace("{name}", tr(name)))
    svg = data.getvalue().decode()
    return svg if fmt == "svg" else svg_to_dxf(svg)


def translate_error(message, box):
    """Exact catalog match, then the argparse wording, then templates like "Need at least {n} walls"."""
    if (translated := _(message)) != message:
        return translated
    if m := re.match(r"argument --(\w+): invalid .*?: '(.*)'", message):
        action = next((a for a in box.argparser._actions if a.dest == m[1]), None)
        group = next((g for g in box.argparser._action_groups if action in g._group_actions), None)
        name = label(action, getattr(group, "prefix", None)) if action else m[1]
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
        box = GENERATORS[req["name"]]()
        box.translations = TRANSLATIONS
        try:
            box.parseArgs([f"--{k}={v}" for k, v in req.get("args", {}).items()])
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
        assert len(list_generators()["groups"]) > 3
        spec = generator_args("UniversalBox")
        assert any(a["name"] == "x" for g in spec["groups"] for a in g["args"])
        svg = render("UniversalBox", {"x": "120"}, "svg")
        assert svg.startswith("<?xml") and "<path" in svg
        dxf = svg_to_dxf(svg)
        assert dxf.count("\nLINE\n") > 50 and dxf.endswith("EOF\n")
        try:
            render("UniversalBox", {"x": "abc"}, "svg")
            raise AssertionError("bad value accepted")
        except ValueError as e:
            assert "“x”" in str(e), e
        assert "<path" in render("TrayLayout", {}, "svg")
        print("ok")
    else:
        main()
