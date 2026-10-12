"""One function per boxes.py generator, building its assembled shape with the iso kit.

Keep each model a caricature of the real thing: the right proportions and the parts that
make it recognisable, nothing else. Sizes are mm; walls use iso.T.
"""
from iso import *


@model
def UniversalBox():
    w, d, h = 120, 80, 60
    open_box(0, 0, 0, w, d, h)
    # Lid lifted off the box, a flat sheet with a brim underneath.
    floor(0, 0, h + 26, w, d)
    floor(T + 1, T + 1, h + 26 - T, w - 2 * T - 2, d - 2 * T - 2)


@model
def ClosedBox():
    closed_box(0, 0, 0, 120, 80, 60)


@model
def TypeTray():
    w, d, h = 150, 100, 40
    open_box(0, 0, 0, w, d, h)
    for x in (50, 100):
        wall_y(x - T / 2, 0, 0, d, h)
    wall_x(0, 50 - T / 2, 0, w, h)


@model
def DisplayShelf():
    w, d, h = 140, 50, 160
    wall_y(0, 0, 0, d, h)
    wall_y(w - T, 0, 0, d, h)
    wall_x(0, d - T, 0, w, h)
    for i in range(3):
        floor(0, 0, 10 + i * 50, w, d)
        wall_x(0, 0, 10 + i * 50, w, 18)   # the lip holding the items


@model
def RoundedBox():
    w, d, h, r = 120, 80, 60, 20
    pts = rounded_rect(0, 0, w, d, r)
    prism(pts, 0, T)           # bottom
    hollow(pts, T, h - T)      # the bent wall
    prism(pts, h + 24, T)      # lid, lifted off


@model
def Console():
    # A keyboard console: low front, one flat top sloping up to the back, no tall back block.
    w, d, hf, h = 180, 90, 25, 45
    floor(0, 0, 0, w, d)
    wall_x(T, 0, T, w - 2 * T, hf - 2 * T)                         # low front
    wall_x(T, d - T, T, w - 2 * T, h - 2 * T - 1)                  # back (under the slope)
    side = [(0, 0), (d, 0), (d, h), (0, hf)]                       # side profile in (y, z)
    extrude(side, "yz", 0, T)
    extrude(side, "yz", w - T, T)
    extrude([(0, hf - T), (d, h - T), (d, h), (0, hf)], "yz", T, w - 2 * T)   # the sloping top
    # the keyboard plate inset in the slope (what the console is for)
    m, k = 12, (h - hf) / d
    extrude([(m, hf + k * m), (d - m, hf + k * (d - m)), (d - m, hf + k * (d - m) + 1), (m, hf + k * m + 1)],
            "yz", m, w - 2 * m, (0.25, 0.25, 0.27, 1))
