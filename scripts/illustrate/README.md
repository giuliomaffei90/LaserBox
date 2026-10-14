# Illustrations of the box generators

Each generator gets one isometric picture of the *assembled* object, rendered by Blender from a
tiny Python model. The look (plywood colour, light, ink outlines, camera) lives in `iso.py`; the
models live in `models/*.py`, one function per generator, registered with `@model` under the
generator's exact class name.

Render (needs Blender 3.x at /Applications/Blender.app):

    /Applications/Blender.app/Contents/MacOS/Blender -b -P scripts/illustrate/render.py -- [--size 512] OUT_DIR [Name …]

No names renders every model. The app looks for `Runtime/samples/<Name>.png` (see
`scripts/bundle-runtime.sh`).

## Modelling rules

- Units are mm of the real object; plywood is `T` (3 mm) thick. Use the generator's default
  parameters for the proportions (read `__init__` / `buildArgParser` in
  `Runtime/site/boxes/generators/<module>.py`), rounded freely. What matters is that someone
  recognises the object and understands its shape at 200 px, not accuracy.
- Reference: the photo `static/samples/<Name>.jpg` in the boxes.py repository (when it exists) shows the real thing; the
  class docstring and `description` say what it is for. Look at the photo before modelling.
- Model only what is visible: outer walls, lids, dividers, the characteristic cut-outs. Skip
  screws, hinges' internals, labels, tiny holes. A lid is usually shown lifted 20–30 mm above the
  box so the inside reads too (see `UniversalBox` in `_samples.py`).
- Axes: x right, y back, z up. The camera looks from the front-left-top (`azimuth=45`). If the
  interesting side is elsewhere, return a dict of `render()` arguments from the model function,
  e.g. `return dict(azimuth=-45)` or `dict(elevation=20)`.
- Parts must not overlap in volume (coplanar faces flicker): walls stand on floors, dividers fit
  between walls. `open_box()` already does this and adds finger joints at the corners.
- Keep models cheap: a few dozen objects, booleans only for holes that define the object
  (`hole`, `round_hole`, `round_holes`, `hollow`). No per-hole booleans for patterns of hundreds.
- Non-wood parts (a rod, a glass pane, a lens) use `ACCENT` or a custom colour tuple, sparingly.
- Helpers in `iso.py`: `box`, `panel`, `floor`, `wall_x`, `wall_y` (with `fingers=True`),
  `open_box`, `closed_box`, `cylinder`, `prism` (polygon in xy extruded up), `extrude` (polygon in
  xy / xz / yz extruded along the third axis), `slanted_panel`, `rounded_rect`, `hollow` (a bent
  wall following an outline), `hole`, `round_hole`, `round_holes`. Do not edit `iso.py`; if a
  module needs its own helper, define it in that module.
- Check every model by rendering it at `--size 512` and looking at the PNG. Fix what does not
  read: wrong proportions, parts hidden behind others, a shape that could be any box.
