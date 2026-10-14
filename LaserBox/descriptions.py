"""LaserBox's own long descriptions (Markdown) for the generators boxes.py ships without one,
shown in the info panel. Translated in Translations/it.po."""

DESCRIPTIONS = {
    'AllEdges': """\
This is not an object to assemble but a sample sheet: it draws, one under the other, a test piece for every edge type the generator knows, each with its letter and a short description engraved next to it. It is the quickest way to see what a joint looks like before choosing it for another box.

Each sample is a rectangle with the edge under test along one side: finger joints and their counterparts, stackable edges, hinges and hinge pins, slide-on and click-on lids, flex sections, handle edges and so on.

- "width": the length of each sample edge.
- The advanced settings groups (finger joints, stackable edges, hinges, lids, flex, handle edge) change the edges exactly as they would in a real box.

It is worth cutting it from your own material to test "thickness" and "burn": pairing the male and female samples shows at once whether the fit is too loose or too tight.""",
    'AngledBox': """\
The angled box is a box whose footprint is a stretched regular polygon: two long walls at front and back and, at each end, a row of narrower facets that turn the corner instead of a sharp edge. The result is a box with faceted, rounded-looking ends.

The walls are rectangles joined to each other with finger joints cut at the right angle for the facets, and the bottom is a polygon that fits under them.

- "walls": how many facets each end has; with high values the end gets close to a half circle.
- "top style": "none" leaves the box open; "angled lid" gives a two-layer lid, one layer fitting between the walls and one resting on them; "angled hole" adds a top rim with a hole, jointed onto the walls; "angled lid2" adds to that rim a lid resting on it.
- "bottom_edge": how the walls join the bottom (with a straight edge no bottom is drawn).
- "width", "depth", "height" and "outside": the sizes; the width is always the long side.""",
    'AngledCutJig': """\
The angled cut jig lets you cut a piece of wood on the laser at an angle other than 90°. The laser always cuts vertically: by holding the piece tilted, the cut goes through the material at the angle you want.

It is made of a flat base, two pairs of right triangles, a large pair and a small one, that fit into it with finger joints, and two plates resting on the triangles' long sides. The two plates meet in a V at a right angle, where the workpiece rests.

- "angle": the angle of the cut; it sets the slope of the triangles and so of the two plates.
- "width": the base of the large triangles; together with the angle it sets the length of the main sloped plate and the height of the jig.
- "depth": how deep the jig is, i.e. the width of the two plates and so how long the workpiece lying on them can be.

The triangles fit into slots in the base near its front and back edges, and the plates into the slots along the triangles.""",
    'Arcade': """\
The arcade is a desktop cabinet for retro games: at the bottom a sloped control panel for joystick and buttons, above it a large sloped opening for the screen and at the top a panel with holes for two speakers.

Two shaped sides form the frame: they carry the finger holes into which all the cross panels fit, namely the floor, the front, the control panel, the wall behind it, the speaker panel, the top and the upper back. Two strips at the bottom of the back hold the back cover, a plain sheet without joints that is fixed over them.

- "width": the inner width of the cabinet, i.e. the length of every cross panel.
- "monitor_height": the height of the screen opening, to be chosen for the monitor you use.
- "keyboard_depth": how deep the control panel is.

The generator does not draw the holes for joystick and buttons: the control panel comes out blank, to be cut for the controls you fit. The two speaker holes are already there.""",
    'Atreus21': """\
The Atreus21 is a keyboard split into two halves, each with its own columns of keys, based on the Atreus layout. The generator draws the case plates, not the electronics: switches, keycaps and wiring are up to you.

Each half is a stack of four plates with the same rounded outline and a 3 mm hole in each corner to hold them together with screws: at the bottom a frame open in the middle, leaving room for sockets and wires; above it a plate with holes for the switch pins; then a support plate, to be glued under the switch plate, which sits on top.

- "columns_definition": how many columns, how many keys in each and how far each is shifted up; the default reproduces the Atreus.
- "cutout_type": 'castle' makes cutouts that allow switch modding, 'simple' a tighter, simpler square.
- "hotswap_enable": enlarges the pin holes for hot-swap sockets.
- "pcb_mount_enable", "led_enable" and "diode_enable": add holes for the pegs of PCB-mount switches and for the legs of LEDs and diodes.""",
    'BinTray': """\
The bin tray is a grid of compartments to hang on the wall, open at the front: each compartment has a sloped front wall at the bottom, leaning outwards, that holds screws, small parts or tools in while leaving the opening above it free.

It is made of the bottom, the top, two sides with a sawtooth front profile, the back panel, and the vertical and horizontal dividers that form the grid; in front of each row of compartments a retainer fits in at 45°. Everything joins with finger joints and slots.

- "compartment widths" and "section heights": the columns from left to right and the rows from bottom to top.
- "depth": the depth of the compartments.
- "front": what fraction of each compartment's height is covered by the sloped wall.
- "hole_dD": the diameter of the two pear-shaped mounting holes at the top of the back (just the shaft, or shaft:head of the screw).

To hang it, two screws in the wall are enough: the pear-shaped holes slide over their heads.""",
    'BirdHouse': """\
The bird house is a simple little house with a gabled roof, to hang in the garden or on a balcony.

It is made of two pointed gables (front and back), two side walls, a floor and two roof panels. The walls join with finger joints; the floor fits into slots near the bottom edge of the walls, which reach a little below it. The two roof panels rest on the gables' 45° slopes, fit over their fingers and join each other at the ridge. Every wall has a large rectangular opening with rounded corners, three quarters of the wall's width and height.

- "width": the width of the gables, which also sets how high the roof ridge is.
- "depth": the length of the side walls and of the roof.
- "height": the height of the walls up to the eaves.
- "roof_overhang": how far the roof reaches past the walls, as a fraction of the roof panel's length.""",
    'BottleTag': """\
The bottle tag is a tag that slips over the neck of a bottle, for a gift or as a label. It is cut from paper or card, not wood.

It is a single piece: a rectangle with a semicircular top and rounded bottom corners. Near the top is a round hole surrounded by many radial cuts: the tabs between the cuts bend when you push the tag down the neck, so the same hole fits necks of different diameters and the tag stays in place. Small cross cuts at the end of each radial cut help keep the paper from tearing.

- "width" and "height": the size of the tag.
- "min_diameter": the diameter of the hole itself.
- "max_diameter": how far out the radial cuts reach, i.e. the widest neck the tag can take.
- "segment_width": the spacing between cuts at the edge of the hole.
- "radius": the radius of the bottom corners.""",
    'CardHolder': """\
The card holder is a low shelf with one or more compartments side by side, each for a pile of playing cards or notes, held tilted slightly backwards so the top card can be read and picked up easily.

It is made of two sides, a back, a sloped floor and, between one compartment and the next, shaped dividers; everything joins with finger joints. The floor's front edge has a groove for each compartment, to slip your fingers under the cards.

- "compartment widths": how many compartments and how wide each is, from left to right.
- "depth": how deep the shelf is, from front to back.
- "height": the height of the walls.
- "angle": how far the floor tilts backwards.
- "stackable": adds stackable edges, feet below and sockets above, to the sides and back, so you can put several holders on top of each other.""",
    'CoinDisplay': """\
The coin display is a small closed showcase for a single coin, held tilted on a stand in the middle.

The showcase is a cube of six panels joined with finger joints; to see the coin it is best to cut the walls and top from clear acrylic. Inside, the stand fits into slots in the bottom: two sides with a sloped top and a front piece, on which two stacked plates rest. The upper one has a round hole the size of the coin, the lower one is solid and forms the bottom of the recess.

- "coin_d": the diameter of the hole the coin sits in.
- "coin_plate": the side of the square plates holding the coin.
- "coin_showcase_h": the height of the stand.
- "angle": the tilt of the coin.
- "width", "depth", "height" and "outside": the size of the showcase, which must be bigger than the stand.""",
    'ConcaveKnob': """\
The concave knob is a round knob with hollows along its edge for a better grip. It fits on a hex-head bolt, turning it into a screw you can tighten by hand.

It is made of three discs with the same outline, to glue on top of each other: a plain one, one with a hexagonal hole the bolt head sits in so it cannot turn, and one with the hole for the shank, which closes over the head and lets the bolt through.

- "diameter": the diameter of the knob.
- "serrations": how many hollows the edge has.
- "rounded": how much of the circumference is taken by the non-convex parts.
- "angle": the angle between the convex and concave parts, i.e. how pronounced the hollows are.
- "bolthole": the diameter of the shank hole.
- "dhole": with values below 1 the shank hole gets a flat side, for D-shaped shafts.
- "hexhead": the width of the bolt head, i.e. the wrench size.""",
    'DiceBox': """\
The dice box is a flat little box with a hinged lid, made to hold a set of gaming dice, each in its own pocket.

Both the box and the lid are trays closed by an inner plate flush with the rim: each plate has seven hexagonal holes with rounded corners, one in the middle and six around it, sized to the shorter side, where the dice sit. The walls join with finger joints and the hinge is cut into the sides of the box and the lid, with no hardware. Each plate also has two holes for magnets: when you close the box they face each other and keep it shut. So you need four round magnets.

- "width", "depth", "height" and "outside": the box's size; by default these are outside measurements.
- "lidheight": the height of the lid; box and lid must be tall enough to fit the hinge.
- "hex_hole_corner_radius": how rounded the corners of the holes are.
- "magnet_diameter": the diameter of the magnet holes.""",
    'DinRailBox': """\
The DIN rail box is a small closed enclosure that clips onto a DIN rail, like those in electrical cabinets, to house a circuit or module next to the other devices.

It is a finger-jointed box: the back rests on the rail, the two sides have along their back edge the profile that wraps around the rail, and the other two walls close the top and bottom. A sliding latch runs through a guide strip behind the back and hooks under the rail; the bottom wall has a flexible tongue cut into it. The lid sits at the front and has two inner lips that catch in slots in the top and bottom walls, so it opens without screws.

- "width", "depth" and "height": the box's inner size; the height is how far it stands out from the cabinet.
- "rail_width": the width of the rail, usually 35 or 15 mm.
- "rail_offset": how far the rail is moved from the middle of the box.""",
    'DiscRack': """\
The disc rack holds disc-shaped objects upright, side by side, such as vinyl records, CDs, plates or coasters, each in its own slot.

It is made of two square sides and, between them, two boards joined in an L with finger joints and tilted backwards: one at the bottom and one at the back. Both have a row of slots as wide as the discs are thick; each disc goes into a slot in the lower board and one in the rear board and rests on three points.

- "compartment widths": the space for each disc, from left to right; the number of values is the number of discs.
- "disc_diameter" and "disc_thickness": the size of the discs.
- "lower_factor" and "rear_factor": where the two boards sit relative to the discs' centre, as a fraction of the radius.
- "disc_outset": the space between the discs and the edge of the sides.
- "angle": the backwards tilt.

If the sizes do not let the discs be properly supported, the generator gives an error suggesting a larger "disc_outset" or an angle further from 45°.""",
    'Display': """\
The flyer display is a counter stand for showing flyers, leaflets or cards.

It is made of just two pieces, without finger joints: an upright panel with rounded corners and a horizontal slot near the bottom, and a rounded plate that slides through the slot. The part of the plate sticking out in front is the ledge the flyers rest on, the part behind is a leg that holds the panel leaning back.

- "width": the width of the panel; the plate is seven tenths of this wide.
- "height": the useful height of the panel, which is cut somewhat taller.
- "radius": the radius of the rounded corners.
- "angle": with values above zero the panel becomes a trapezoid, wider at the top than at the bottom.""",
    'DisplayCase': """\
The display case is a fully closed box, meant to be cut from clear acrylic to keep the dust off a model, a collection or any object on show.

It is made of six panels: four walls finger-jointed to each other, plus a bottom and a top that reach out beyond the walls all round, with the slots the walls' fingers go into. The overhanging rim gives the case a more finished look, like a base and a frame. The top is fixed like the rest, there is no door: close the case after putting the object inside.

- "width", "depth" and "height": the size of the case.
- "outside": when on, the sizes are outside measurements.
- "overhang": how far the bottom and top reach beyond the walls.""",
    'DisplayShelf': """\
The display shelf is a shelf with several sloped levels, for showing objects such as books, comics, records or models with their front in view. Each level has a lip at the front that stops things from sliding off.

It is made of two sides with slots for the shelves, the shelves themselves with their front lips and, if you divide the width into compartments, dividers on each shelf. Everything joins with finger joints. Optionally you can close it with a back, a front and a bottom panel.

- "compartment widths": the width of the shelf and how it is split into compartments, from left to right.
- "shelves": how many shelves.
- "angle": the slope of the shelves; negative values tilt them backwards.
- "front_wall_height" and "divider_wall_height": how tall the front lips and the dividers are.
- "include_back", "include_front" and "include_bottom": add the closing panels; the front one is meant for shelves tilted backwards.
- "slope_top": slopes the top front of the sides by the height of the front lip.
- "bottom_distance" and "top_distance": the free space below the lowest shelf and above the highest one.""",
    'DoubleFlexDoorBox': """\
The double flex door box is a box with rounded corners whose lid is split into two doors that open to the sides, like the doors of a small cabinet.

It is made of only three pieces: two sides with rounded corners and one long wall that wraps all the way round them, joined to the sides with finger joints. At the four corners the wall has a flex section, a pattern of cuts that lets it bend round the curve. The two halves of the top are the doors: they open by bending the flex at the top corners and close in the middle with snap latches.

- "width", "depth", "height" and "outside": the size of the box.
- "radius": the radius of the rounded corners the wall bends round.
- "latchsize": the length of the latches, in multiples of the thickness.

The flex sections need thin, flexible plywood; the cuts are adjusted in the advanced flex settings.""",
    'DrillBox': """\
The drill box keeps drill bits upright and in order, each in its own hole, sorted by diameter with the size engraved next to each group.

It is a finger-jointed box: four walls, a bottom and, inside, one or more perforated plates fitted into the walls at different heights. The bits go through the plates and rest on the bottom. The top plate also has, besides the holes, an engraved frame for each compartment with the hole diameter.

- "compartment widths" and "compartment depths": the grid of compartments; each compartment holds one bit size.
- "section heights": from the bottom up, the distances between the bottom and the plates; every section but the last has a plate on top.
- "holes": how many bits of the same size go in each compartment.
- "firsthole" and "holeincrement": the hole diameter in the first compartment and how much it grows from one compartment to the next.
- "top_edge" and "bottom_edge": how the walls finish at the top and bottom, for example stackable, to put several boxes on top of each other.

In the advanced lid settings you can add a lid.""",
    'ElectronicsBox': """\
The electronics box is a closed enclosure for boards and circuits, with a screwed-on lid and holes to mount it on a wall or panel.

The four walls and the bottom join with finger joints. In the inside corners, just below the top edge, four triangles fit in: the lid rests on them flush with the rim and is screwed into their holes. The bottom has a mounting hole in each corner; with "outsidemounts" the bottom extends on two sides into rounded flaps and the holes go there, outside the box, easy to reach with the box closed.

- "width", "depth", "height" and "outside": the size of the box.
- "triangle": the side of the triangles holding the lid.
- "lid screw holes" and "inner lid screw holes": the diameter of the holes in the lid and of the narrower ones in the triangles, where the screw bites.
- "mounting screw holes" and "holedist": the diameter of the mounting holes and their distance from the wall.

You need four screws for the lid, chosen to match the holes.""",
    'EuroRackSkiff': """\
The Eurorack skiff is a shallow case, open at the top, for 3U Eurorack synthesizer modules: the modules go in from above and screw onto two rails.

It is a finger-jointed box with a bottom and four walls. On the two long walls, just below the top edge, two rails fit in: 6 mm strips facing inwards, with a 3 mm hole at every HP for the module screws. The inner distance between the long walls is fixed: 128.5 mm, the height of 3U panels.

- "width (HP)": the usable width in HP, the 5.08 mm Eurorack unit; it sets the length of the case and the number of holes in the rails.
- "height": the inner depth of the case, i.e. how much room the modules have below the rails.""",
    'FanHole': """\
The fan hole is the hole pattern to cut into a panel, for example the wall of an electronics box, to mount a cooling fan on it. The generator draws only the holes, without the panel's outline.

The pattern is a round opening for the airflow and four holes for the fan's screws, at the corners of a square as wide as the diameter. The opening can be a swirl grille, with curved arms joining a central disc to the outer ring, or a plain round hole.

- "diameter": the diameter of the opening, which is also the side of the mounting holes' square.
- "mounting_holes" and "mounting_holes_inset": the diameter of the screw holes and their distance from the outer edge of the square.
- "style": "CW Swirl", "CCW Swirl" or "Hole".
- "arms": how many arms the swirl has.
- "inner_disc": the size of the central disc relative to the opening.

Measure your fan: the side and the position of the holes come from its frame.""",
    'FillTest': """\
The fill test is a sample piece: a rectangle holding an irregular area, with narrow recesses, that gets filled with holes. It lets you see how the hole filling settings turn out before using them in a real project.

It is a single piece with nothing to assemble. The outline of the area to fill only appears as an annotation, with a label naming it: what gets cut is the outer rectangle and the holes.

- "width" and "depth": the size of the rectangle; the test area grows or shrinks in proportion.
- The "Settings for Hole filling" group holds the options to try: "fill_pattern" (hex, square, random, hbar, vbar), "hole_style", "hole_max_radius" and "hole_min_radius", "space_between_holes", "space_to_border", "bar_length".

The narrow recesses of the area show how the pattern behaves in corners and thin parts, where the larger holes do not fit.""",
    'FlexBox': """\
This flex box is a box with all four corners rounded, closed by a band of flexible wood that forms the bottom, the walls and the lid in one piece.

The two sides are rectangles with rounded corners. The band wraps around them: it starts at the front, below the latch, goes down, under the bottom, up the back, over the top and back down the front. Up to the back top corner it is finger-jointed to the sides; the rest, the top and the upper part of the front, is not jointed and works as the lid, which bends at the back corner and locks onto a latch tab on the sides.

- "compartment widths": one or more widths separated by colons; with several compartments you get dividers, set in finger holes in the band.
- "depth" and "height": the size of the sides; "outside" makes them outer measurements.
- "radius": the radius of the rounded corners.
- "latchsize": the length of the latch, in multiples of the thickness.

The curved parts are flex cuts: use thin plywood that bends well, and tune the pattern in "Settings for Flex".""",
    'FlexBox2': """\
This flex box variant has its two top corners rounded and a square bottom: the lid is a flexible band that bends over one of the top edges.

The pieces are the bottom, the two sides (square at the bottom, rounded at the top), a low panel on one end and the band. The band is finger-jointed to the sides and the bottom along one whole end; from there it bends over the first rounded corner, covers the top, goes round the second corner and comes down to a latch tab on the sides, just above the low panel. The stretch from the first corner to the latch is not jointed: it is the lid.

- "width", "depth" and "height": the size of the box; with "outside" they are outer measurements.
- "radius": the radius of the top corners.
- "latchsize": the length of the latch, in multiples of the thickness.

Unlike the first flex box, the bottom here is a separate panel and the band does not go under the box. The curves are flex cuts: you need thin, flexible plywood, and the pattern is tuned in "Settings for Flex".""",
    'FlexBox3': """\
This flex box variant is a square box with a hinged cap lid at the back: the back top edge is rounded, and that is where the band bends.

The box has a bottom, a front and two sides with the back top corner rounded. The band is finger-jointed along the back; at the corner it bends and becomes the lid's top, slightly wider than the box. From the top hang the two lid sides and the lid front, which cover the upper part of the box. There is no latch.

- "width", "depth" and "height": the size of the box; with "outside" they are outer measurements.
- "lid height": how far the lid's rim comes down.
- "radius": the radius of the edge the lid bends over.
- "lid clearance": the gap between the lid's sides and the box's, so the lid opens and closes without rubbing.

The curve is a flex cut: use thin, flexible plywood and tune the pattern in "Settings for Flex".""",
    'FlexBox4': """\
This flex box variant has its two top corners rounded and a lid that covers the top and the whole front, closed by a latch tab at the bottom.

The pieces are the bottom, the two sides and the flexible band. The band is finger-jointed to the sides along the back; from the back top corner it bends, runs over the box, goes round the front corner and comes down the whole front to the latch, near the bottom. That part is not jointed: it is the lid, which opens by turning on the back edge. The bottom's front edge is left plain, so the lid closes over it.

- "width", "depth" and "height": the size of the box; with "outside" they are outer measurements.
- "radius": the radius of the top corners.
- "latchsize": the length of the latch, in multiples of the thickness.

Unlike flex box 2, here the latch is at the bottom and the whole front opens. The curves are flex cuts: you need thin, flexible plywood, and the pattern is tuned in "Settings for Flex".""",
    'FlexBox5': """\
This flex box variant has a rounded outline: each side is made of two circles, one at each end, joined by two straight tangent stretches, like a capsule or, with different diameters, a teardrop.

The pieces are the two sides and a flexible band that goes all the way around them. The band is finger-jointed to the sides along the straight stretches, bends around the two circles with its flex cuts, and its two ends meet at a latch tab on the sides.

- "width": the overall length of the box; if it is too short for the two circles and the latch, it is lengthened.
- "height": the distance between the two sides, that is, the width of the band.
- "top_diameter" and "bottom_diameter": the diameters of the two circles; with different values the shape narrows towards one end.
- "latchsize": the length of the latch, in multiples of the thickness.
- "outside": makes the sizes outer measurements.

The curves are flex cuts: use thin, flexible plywood and tune the pattern in "Settings for Flex".""",
    'FlexTest': """\
The flex test is a sample strip for the flex cut, the pattern of cuts that makes a wooden panel bendable. It helps you find the right settings for your material before cutting a box with curved parts.

It is a single piece: a rectangle with its middle covered by the flex pattern and 10 mm of solid material at each end, so you can hold and bend it.

- "width": the length of the flexible part.
- "depth": the height of the strip, that is, the length of the cuts.
- The "Settings for Flex" group holds the values to try: "connection" (the gaps in the cuts), "distance" (the spacing between rows of cuts), "width" (the length of the single cuts) and "stretch".

Use the same plywood and thickness as the final project: a strip that bends without breaking tells you those settings will work for the box too.""",
    'FlexTest2': """\
The 2D flex test is a sample piece for flex cuts in two directions: unlike the usual flex pattern, which lets a panel bend along one axis only, this pattern makes it bendable both ways.

It is a single piece, a rectangle fully covered by the pattern. It helps you see how your material behaves with this kind of cut and which line spacing to pick.

- "width" and "depth": the size of the rectangle.
- "flex cut distance": the spacing between the lines of the pattern, in multiples of the thickness.

If the rectangle is too small for the chosen spacing, no pattern is drawn: each side has to be at least five times the cut spacing. Use the same material as the final project, usually thin plywood.""",
    'GearBox': """\
The gearbox is a narrow box holding a series of identical reduction stages: in each stage a small gear drives a big one, and the speed drops at every step.

The box has a bottom, two sides with holes for the two shafts, and two ends, all finger-jointed; the top stays open. The shafts run across the box: on each one the gears alternate, small and big, one per layer. Each big gear is glued to the small gear of the next layer on the same shaft, so the motion passes from one shaft to the other at every stage. The shafts, rods of the chosen diameter, have to be bought separately.

- "teeth1" and "teeth2": the teeth of the small and the big gear (if you swap them they are swapped back); each stage reduces by "teeth2" divided by "teeth1".
- "modulus": the size of the teeth, and so of the gears and the box.
- "shaft": the diameter of the shafts and of the holes in the gears and the sides.
- "stages": how many stages; the box gets one layer wider per stage.""",
    'Gears': """\
The gears are a pair of meshing gear wheels for a mechanism of your own.

The generator draws the two gears, each with the hole for its shaft, plus two holes at the exact distance between the axes and a text with each gear's pitch radius and outer diameter and the axis distance: you need them to place the shafts in your project. The shafts are not included.

- "teeth1" and "teeth2": the teeth of the two gears; their ratio is the gear ratio.
- "modulus": the size of the teeth; each gear's diameter is about the modulus times its number of teeth.
- "shaft1" and "shaft2": the hole diameters; with 0 the second gear uses the first one's.
- "dpercentage1" and "dpercentage2": make the hole D-shaped, for a shaft with a flat side that does not slip; 100 gives a round hole.
- "pressure_angle" and "profile_shift": the shape of the teeth: the angle at which the teeth touch and the profile shift, in percent of the modulus.""",
    'HeartBox': """\
The heart box is a box shaped like a heart, its point at the front and the two rounded lobes at the back.

The pieces are the bottom and the top, both heart-shaped, and the walls running around them. The walls bend around the lobes thanks to their flex cuts and are finger-jointed to the bottom and the top.

- "width": the size of the heart.
- "height": the height of the walls.
- "top style": "closed" makes a closed box; "hole" opens a heart-shaped opening in the top; "lid" opens the same opening and adds a slightly larger heart-shaped lid that rests on it. Glue the ring cut from the opening's offcut under the lid: it fits into the opening and keeps the lid in place.

The curved walls need thin, flexible plywood; the pattern is tuned in "Settings for Flex".""",
    'HolePattern': """\
The hole pattern generates only a set of holes laid out inside a simple shape, with no outline of a piece around them. It lets you add a perforated area, such as a grille or a decoration, to a panel of a project of your own, placed wherever you like.

There is nothing to assemble: the drawing holds only the holes, filling the chosen shape at the given size.

- "shape": rectangle, ellipse, oval, hexagon or octagon.
- "width" and "depth": the size of the shape to fill.
- In the "Settings for Hole filling" group you choose how to fill it: "fill_pattern" (hex, square, random, hbar, vbar), "hole_style", "hole_max_radius" and "hole_min_radius", "space_between_holes", "space_to_border" and, for bars, "bar_length".

To try the settings on an area with a trickier outline, there is the fill test.""",
    'Hook': """\
The hook is a wall hook with a rectangular mouth facing upwards, to rest whatever you want to hang in it.

It is made of six finger-jointed pieces: a back plate to screw to the wall, with three 3 mm holes for the screws, two shaped sides, the floor of the mouth, the front wall that closes it at the front (with a round 17 mm hole) and a strip covering the top of that wall. Under the hook the sides have a slanted support that carries the load back to the plate.

- "width": the width of the hook; the back plate is a bit wider.
- "height" and "depth": the inner size of the mouth.
- "strength": how wide the hook is seen from the side, that is, how thick the load-bearing part is.
- "angle": the slope of the support under the hook (at most 80°); a larger angle makes the support reach further down.

The wall screws have to be bought separately.""",
    'IntegratedHingeBox': """\
The integrated hinge box is a box with a hinged lid where the hinge is cut into the same wooden pieces: there are no hinges, pins or screws to buy.

The lower part has a bottom, a front, a back and two sides; the lid in turn has a top, a front, a back and two sides, all finger-jointed. At the back of the box's sides there are rings in which discs turn; the lid's sides are shaped around the rings, and the lid's back has pins that sit in the discs' slots. So the lid turns on an axis along the back edge.

- "width", "depth" and "height": the size of the box; with "outside" they are outer measurements.
- "lidheight": the height of the lid; it has to be enough to hold the hinge, otherwise the generator reports an error (the same goes for the box's height).

In the "Settings for Chest Hinges" group you can adjust "pin_height", "hinge_strength" and the hinge's "play", useful if the lid turns too tightly.""",
    'LBeam': """\
The L-beam is a simple L-shaped beam: two wooden strips joined at a right angle with a finger joint. It works as a stiffener, a corner angle or part of a larger frame, much stiffer than a single strip.

There are two pieces: one strip lying flat and one standing on its edge, its fingers going into the first one's joint. They can be glued.

- "width": the width of the flat strip, one leg of the L.
- "depth": the width of the standing strip, the other leg.
- "height": the length of the beam.
- "outside": makes the widths of the two legs outer measurements, thickness included.

If you need a Z or U profile, there is a dedicated generator.""",
    'LaptopStand': """\
The laptop stand is an X-shaped frame that holds the computer tilted at the keyboard angle you choose.

It is made of just two triangular pieces, with no glue or screws: one has a slot from below, the other a slot from above, and they slide into each other, crossing at a right angle. The laptop rests on the slanted edges of the triangles, its back on the tall ends; at the front each triangle has a lip that holds the computer's front edge.

- "l_depth": the depth of the laptop, front to back.
- "l_thickness": the thickness of the laptop, to size the lip.
- "angle": the tilt of the keyboard, in degrees.
- "ground_offset": how high the laptop stays off the surface at the front, its lowest point.
- "nub_size": the thickness of the lip the front of the computer rests against.

The slots are as wide as the "thickness": set the real material's value and adjust the "burn" so the joint is tight.""",
    'LaserHoldfast': """\
The laser holdfast is a small flat hook that holds material down on the honeycomb bed of a laser cutter: the shaft goes into a cell of the bed and the curved arm at the top presses on the sheet, so it does not shift or lift while cutting.

Each holdfast is a single piece, with no joints and nothing to assemble. Usually you use several around the sheet, and the generator can draw them all at once, side by side.

- "width": how far the curved arm reaches.
- "height": the length of the shaft.
- "hookheight": the thickness of the arm at the top.
- "shaftwidth": the width of the shaft; choose it to suit the cells of your bed.
- "cutlength": when above zero, adds a cut along the shaft starting from its tip.
- "holdfasts": how many holdfasts to draw.""",
    'MagazineFile': """\
The magazine file is an open holder for a desk or shelf, for magazines, catalogues and folders: tall at the back, low at the front, with sides that drop from one to the other in a smooth curve, so the papers are easy to see and pick up.

There are five finger-jointed pieces: the bottom, the tall back, the low front and the two shaped sides.

- "width": the inner width, the room for the magazines.
- "depth": how long it is, front to back.
- "height": the height of the back.
- "inner walls height": the height of the front; with 0 it is half the back's height.
- "outside": makes the sizes outer measurements.
- "top_edge": plain or with pear-shaped mounting holes, to hang it on screws.

With mounting holes, the "Settings for Mounting Edge" group sets which side they go on (the back by default), how many there are and which screw diameter they suit.""",
    'NemaMount': """\
The NEMA motor mount is an angle bracket to fix a NEMA stepper motor to a board or a frame. Its sizes are worked out from the motor size.

It is made of four finger-jointed pieces: the motor plate, standing, with the centre hole for the flange and the four screw holes; the base, with two slots for the screws that fix it down; and two triangular gussets at the sides that keep the plate square. The motor sits against the plate, its shaft coming out of the front.

The generator also draws a set of finger holes to cut into a plate of your own: they let you joint the bracket straight onto that plate instead of screwing it down.

- "size": the NEMA size of the motor (8, 11, 14, 16, 17, 23, 24, 34 or 42).

The motor and the screws, of the diameter its size calls for, have to be bought separately.""",
    'NemaPattern': """\
The NEMA motor holes are the drilling template for fixing a NEMA stepper motor to a panel: the centre hole for the motor's flange and the four screw holes, at the right spacing for the chosen size.

The drawing holds only the holes, with no outline of a piece: you use it to add them to a panel of a project of your own, wherever you like. There is nothing to assemble: the motor's shaft passes through the centre hole.

- "size": the NEMA size of the motor (8, 11, 14, 16, 17, 23, 24, 34 or 42); it sets the diameter of the centre hole, the spacing of the screws and their diameter.
- "screwholes": the diameter of the screw holes; with 0 the standard one for the size is used. Useful if you use screws of another size.

If you also need a bracket to hold the motor at an angle, there is the NEMA motor mount. The motor and screws have to be bought separately.""",
    'OpenBox': """\
The open box is a box with no top and no front: just a bottom, a back and two sides. It works as a shelf tray, a desk organiser or a cubby you slide things into from the front.

The four pieces are finger-jointed: the sides join the back, and all three join the bottom. The top and front edges stay plain.

- "width", "depth" and "height": the size of the box; with "outside" they are outer measurements.
- "edgetype": how the back and sides join the bottom and each other. With "F Finger Joint (opposing side)" the edges carry ordinary finger joints; with "h Edge (parallel Finger Joint Holes)" the back and sides get rows of slots that the other piece's fingers fit into, so their edges stay straight.

It is the simplest of the boxes: if you need it closed or with a lid, there are other generators in the box group.""",
    'PaintStorage': """\
The paint storage is an open, stackable holder for hobby paint pots or other small cylindrical things. The pots stand on the bottom and go through the holes of a shelf, which keeps them upright and in rows.

It is made of two end walls joined with finger joints to the bottom and to the perforated shelf; the long sides stay open, so you take the pots out from the side. The end walls have a finger hole that works as a handle and stackable edges, so several units sit on top of each other; two strips go under the bottom, against the end walls.

- "canheight" and "candiameter" set the height of the end walls and the size of the holes, "minspace" the gap between pots.
- "width" and "depth" are the inner sizes of the shelf.
- "additional_bottom" and "additional_top" add more perforated shelves, lower or higher.
- "hexpattern" staggers the holes in a honeycomb instead of rows and columns.
- "drawer" makes a stackable drawer closed on all sides instead, with no perforated shelves.""",
    'PenHolderBox': """\
The pen holder is a box open at the top with two perforated plates inside, one above the other: pens, pencils and markers go through the holes of both and stay upright, each in its own place.

The four walls join each other and the bottom with finger joints; the two plates fit into rows of finger holes in the walls. Around each hole an engraved circle (green in the drawing) marks the room reserved for the cap, and the holes are spaced by exactly that diameter.

- "width", "depth" and "height" are the inner sizes of the box, outer ones with "outside".
- "holes across" and "holes in depth" set how many columns and rows of holes each plate has.
- "pen_diam" is the actual hole, "cap_diam" the pitch from one hole to the next.
- "plate1_offset" is how far below the rim the first plate sits, "plate_gap" how much lower the second one is.
- "bottom_edge" chooses how the bottom joins; with a plain edge no bottom is drawn.""",
    'Planetary': """\
The planetary gear is a reduction gear made of flat gears: a sun gear in the middle, a few planets turning around it and a ring gear with inner teeth enclosing them.

The pieces stack in layers: a base disc with the shaft hole, the ring gear with the sun and planets inside it, and on top the planet carrier, with the holes for the pins the planets turn on. The ring's teeth are worked out from those of the sun and planets, and the planets are placed where they mesh properly. Shafts and pins are not drawn: get them yourself, in the chosen diameter.

- "sunteeth" and "planetteeth" set the sizes and the ratio, "modulus" the size of the teeth.
- "maxplanets" limits the number of planets (0 for as many as fit).
- "shaft" is the diameter of shafts and pins, "play" the clearance in the holes of the parts that turn on them; for ball bearings use outer minus inner diameter.
- "deltateeth" adds, in an extra layer, a second ring gear with that many fewer teeth and a second set of planets.""",
    'PoleHook': """\
The pole hook holds a rod-shaped object, such as a tube or a handle, and is clamped to another pole. The object rests in a U-shaped fork, and a swinging latch closes the opening.

It is made almost entirely of stacked layers. Five forks side by side form the U; the two outer ones have a taller arm with a hole for a pin, on which the three layers of the latch turn, capped on the sides by two small discs. Under the forks there is a stack of four discs (the clamp disc has two parallel cuts) and a three-layer wavy knob. A hex-head screw, its head locked in the knob's hex recess, goes through the discs and into a nut held in the middle fork. Get the screw, the nut and the pin yourself.

- "diameter" is the size of the object to hook and sets the size of the whole hook.
- "screw", "screwhead" and "screwheadheight" fit the holes and recesses to your screw.
- "pin diameter" is the hole for the latch's pin.""",
    'Pulley': """\
The pulley is a toothed wheel for timing belts. It is made by stacking several identical toothed discs, all with the axle hole in the middle.

The generator draws as many layers as it takes to reach the chosen height, rounding up according to the material thickness. If you want, it adds a flange on top: a wider disc that keeps the belt in place. The axle is not included.

- "profile" chooses the type of belt and teeth (GT2, HTD, T5, MXL, XL and others).
- "teeth" sets the number of teeth, and so the pulley's diameter.
- "height" is the total thickness of the toothed part.
- "axle" is the diameter of the centre hole.
- "top rim" is how far the flange reaches beyond the teeth (zero for no flange).
- "insideout" makes a ring with inner teeth instead, with the belt pressed against it from inside.

The thinner the material, the more layers you need, but the closer the height gets to the one you asked for.""",
    'Rack10Box': """\
The 10" rack box is a closed box to mount in a 10-inch rack, to house electronics or other devices. The width is fixed, the standard one for 10" racks, and the height follows rack units: you only choose the depth and how many units it takes up.

Front, back, sides and bottom join with finger joints. The front sticks out on both sides as two ears, each with two slots for the rack screws. The lid is a flat panel screwed to four triangles fitted in the corners just below the rim, so you can open it to work inside. You need four screws for the lid, besides the rack screws.

- "depth" is the inner depth of the box.
- "height" is the height in rack units (U), from 1 to 16.
- "triangle" is the side of the triangles that hold the lid.
- "lid screw holes" is the diameter of the holes in the lid, "inner lid screw holes" that of the holes in the triangles, which the screws bite into.

It is the same box as the 19" rack box, only narrower.""",
    'Rack19Box': """\
The 19" rack box is a closed box to mount in a 19-inch rack, to house electronics or other devices. The width is fixed, the standard one for 19" racks, and the height follows rack units: you only choose the depth and how many units it takes up.

Front, back, sides and bottom join with finger joints. The front sticks out on both sides as two ears, each with two slots for the rack screws. The lid is a flat panel screwed to four triangles fitted in the corners just below the rim, so you can open it to work inside. You need four screws for the lid, besides the rack screws.

- "depth" is the inner depth of the box.
- "height" is the height in rack units (U), from 1 to 16.
- "triangle" is the side of the triangles that hold the lid.
- "lid screw holes" is the diameter of the holes in the lid, "inner lid screw holes" that of the holes in the triangles, which the screws bite into.

For smaller racks there is the 10" rack box, the same but narrower.""",
    'Rack19HalfWidth': """\
The half-width 19" rack unit is a module for musical equipment that takes up half the width of a 19" rack: the front has a single ear, with slots for the screws, and the connector holes already cut. Two modules side by side, screwed together, fill the whole width.

It is made of five pieces joined with finger joints: the front, the trapezoid bottom and top, and two sides of different depths. The short side is on the ear's side, the long one on the side screwed to the other module; the slanted back stays open. The width is fixed, the height follows rack units.

- "ru_count" is the module's height in rack units.
- "holes" lists the connectors on the front: x for XLR, m for MIDI, p for a 9 V power socket, w for a 6.5 mm cable hole; a space moves to the next row, one row per unit.
- "rear depth" and "deepz" are the depths of the short and the long side.""",
    'RackBox': """\
The rack box is a closed box in any size you like, with a screwed-on lid and two drilled flanges on the front to fix it with screws.

Front, back, sides and bottom join with finger joints. The front sticks out on both sides as two flanges, each with two round holes for the mounting screws. The lid is a flat panel screwed to four triangles fitted in the corners just below the rim. You need four screws for the lid, plus the mounting screws.

- "width", "depth" and "height" are the inner sizes, outer ones with "outside".
- "triangle" is the side of the triangles that hold the lid.
- "lid screw holes" and "inner lid screw holes" are the diameters of the holes in the lid and in the triangles.
- "mounting screw holes" is the diameter of the holes in the flanges, "holedist" their distance from the wall, which also sets how wide the flanges are.

Unlike the 10" and 19" rack boxes, here the width is free and the flanges have round holes instead of slots.""",
    'Ramp': """\
The ramp is for accessibility: it goes against a step so you can roll over it instead of climbing it. It is shaped as a triangular prism, with the slope rising from the floor to the top of the step.

It is made of pieces joined with finger joints: the bottom lying on the floor, the vertical wall against the step, the slope and the two triangular sides. If you want, reinforcement triangles go inside, spread evenly across the width and fitted into the bottom and the vertical wall.

- "width" is the width of the ramp, usually the width of the step.
- "height" is the height of the step to reach.
- "depth" is how far the ramp reaches forward: the larger it is, the gentler the slope.
- "reinforcements" is the number of inner triangles; they support the slope when the ramp is wide.""",
    'RectangularWall': """\
The rectangular wall is a single panel where you choose the edge type for each of its four sides. Use it as a spare piece, to add a wall or a shelf to a project, or to try out a joint and its settings before cutting a whole box.

Each side can have any of the boxes.py edges: plain edge, finger joint, dovetail, hinges, click lock, stackable edge, gear rack, grip edge and more. The settings of each edge type are in the advanced groups.

- "width" and "height" are the inner sizes of the panel, not counting what the joints stick out.
- "bottom_edge", "right_edge", "top_edge" and "left_edge" choose the edge of each side.

To try a joint, cut two panels with matching edges, for example "f" on one and "F" on the other, and adjust the "burn" setting until the pieces fit well without forcing.""",
    'RegularStarBox': """\
The star box is a regular polygon box, with three, four or five sides, made of two identical halves that slide into each other. The top half is turned against the bottom one, so when the box is closed the ends of the walls stick out and form the points of a star.

Each half is a polygon base with a wall on every side: the walls join each other with finger joints angled to the polygon's corners, and the base with plain finger joints. The free edge of the walls has notches half the height deep: when you close the box, the notches of the two halves cross and lock together like a half-lap joint.

- "sides" chooses the number of sides: 3, 4 or 5.
- "radius" is the inner radius, from the centre to the corners.
- "height" is the height of each half's walls; with "outside" the sizes become outer ones.

If the radius is too small for the number of sides, the notches don't fit and the generator reports an error.""",
    'RobotArm': """\
The robot arm is a set of segments for building an arm driven by servo motors. Each segment is a small closed box, four walls and two end caps joined with finger joints, with the holes and mounts for the servos or the hinge knuckles that link it to the next segment.

You can define up to five segments, each one of these types:

- MM: two parallel servos;
- Mm: two orthogonal servos;
- UU: two parallel sets of hinge knuckles;
- Uu: two orthogonal sets of knuckles;
- Mu: a servo and an orthogonal set of knuckles.

For each segment, "type1"…"type5" chooses the variant (none to skip it), "length1"…"length5" the distance from axle to axle, "servo1a" and "servo1b" (and so on) the servo on each side; for now only the 9 g micro servo (Servo9g) is offered. The servo motors are bought separately, and how the segments are joined to each other is up to you.""",
    'RoundedRegularBox': """\
The rounded polygon box has the plan of a regular polygon with rounded vertical edges: the wall goes round the corners by bending at flex sections, a pattern of cuts that makes the wood bendable.

The bottom and the top are two polygon plates joined to the wall with finger joints. The wall is split into one or more pieces, each bending round the corners it spans. For the flex sections use thin, flexible plywood.

- "sides" is the number of sides of the polygon, "inner_size" the diameter of the inscribed circle.
- "radius" is the radius of the rounded corners.
- "height" is the inner height.
- "wallpieces" is the number of wall pieces (0 for one per side).
- "top style" chooses the top: with "hole" it has a large opening, with "lid" it has the opening plus a slightly larger plate resting on it, with "closed" it is solid.""",
    'SBCMicroRack': """\
The SBC micro rack is a small shelf for single-board computers such as the Raspberry Pi: the boards sit one above the other, each on its own shelf, and several racks can be stacked.

It is made of two sides with stackable edges, a base and one shelf per board, which fit with finger joints into the slots of the sides. Each shelf has the four holes to screw the board on; the first side has, at the level of each shelf, an opening for the network and USB ports. Get the screws for the boards yourself.

- "sbcs" is the number of shelves.
- "width" and "depth" are the inner sizes of the shelf; "clearance_x" and "clearance_y" the room around the board, "clearance_z" the room above it.
- "hole_grid_dimension_x", "hole_grid_dimension_y", "hole_diameter" and "hole_dist_edge" put the holes where your board has them; the defaults are the Raspberry Pi's.
- "netusb_z" and "netusb_x" set the size of the port openings.
- "stable" adds holes to pass a 1/4" dowel through, to make it steadier.""",
    'SkadisStand': """\
The Skadis stand is a foot that lets an IKEA Skadis pegboard stand on its own on a table, upright or leaning back. The generator draws a single foot: cut two, one for each side of the board.

The foot is a single profile: a horizontal part lying on the table behind the board and an upright with hooks that go into the board's holes, so the board leans on it. If you also want a foot in front, a rounded plate is added to lie on the table, and the profile fits into it with finger joints.

- "angle" is the tilt of the board (90 for vertical).
- "foot" is the length of the horizontal part behind the board; "foot_front" extends it to the front (zero to leave it out).
- "connectors" are the positions of the hooks along the upright, on the grid of the board's holes: the values must be all even or all odd.
- "extra_height_top" and "extra_height_bottom" lengthen the upright above the last hook and below the board.""",
    'SlidingDrawer': """\
The sliding drawer is a box made of a sleeve open at the front and a drawer that slides inside it, to keep small things tidy.

The sleeve is made of a bottom, a top, two sides and a back; the drawer of four walls and a bottom. All the pieces join with finger joints. The drawer front has a notched top edge, to grip with your fingers when you pull it out. The drawer's sizes are worked out from the sleeve's, leaving the play all around.

- "width", "depth" and "height" are the sizes of the box; "outside" is on by default, so they are the outer sizes of the sleeve.
- "inner walls height" makes the drawer's walls lower than its front (0 to keep them the same height).
- "play" is the gap between drawer and sleeve, as a multiple of the material thickness: raise it if the drawer slides stiffly.""",
    'SmallPartsTray': """\
The small parts tray is a tray with compartments whose floor rises in a ramp towards the rim: game tokens, screws and other small bits slide up the ramp and are easy to pick up, instead of staying in the corners.

It is made of two sides and shaped inner dividers, one between each pair of compartments, which hold the floor, the ramps and, if you want, a vertical panel above each ramp; everything joins with finger joints. With ramps on both sides there is also a sliding divider for each compartment, kept upright by two small triangular feet, and you can add a lid by choosing its style in the lid settings.

- "compartment widths" lists the widths from left to right, and so how many compartments there are.
- "depth" and "height" are the tray's sizes, outer ones with "outside" (on by default).
- "angle" is the slope of the ramps, "rampheight" their height as a fraction of the total height.
- "two_sided" puts ramps at the front and the back.
- "front_panel" adds the vertical wall above the ramp.""",
    'SpicesRack': """\
The spice rack is a wall-hung shelf for round spice jars. The jars stand on several shelves, each with a row of shaped holes they slot into, and the front edge of the shelves is cut in arcs, one per jar.

The back panel has two holes at the top to hang it with screws. The shelves fit into the panel with finger joints and rest on supports, one between each pair of jars, also fitted into the panel. With "feet" the lowest row of supports is replaced by feet reaching the floor, so the rack can also stand on its own.

- "diameter" is the jars' diameter, "height" the height of the jars to support: together they set the shape of the holes and the distance between shelves.
- "space" is the gap between jars.
- "numx" and "numy" set how many jars go on a shelf and how many shelves there are.
- "in_place_supports" cuts the supports out of the shelves' holes, to save material: check yourself that they fit.""",
    'Spool': """\
The spool is a reel to wind thread, cable or tape on: two round flanges with the axle hole, joined by a central core.

The core is a polygonal prism made of rectangular staves, which fit with finger joints into the slots of the two flanges. If you want, each flange is stiffened on the outside by a ring of radial ribs, held together in the middle by a small drilled disc. The axle is not part of the drawing.

- "outer_diameter" is the diameter of the flanges, "inner_diameter" that of the core.
- "height" is the inner distance between the flanges, that is the usable width of the spool.
- "axle_diameter" is the diameter of the axle hole.
- "sides" is the number of staves in the core: the more there are, the rounder the core.
- "reinforcements" is the number of ribs per side, "reinforcement_height" how far they stand out from the flanges; with zero height there are none.""",
    'Stachel': """\
The bass recorder endpin is a holder fixed to the foot of a bass recorder, with a rod reaching down to the floor: this way the instrument rests on the floor while you play, like a cello's endpin.

It is made of three layers glued on top of each other, all the same shape: a ring that grips the recorder's foot and, beside it, a hole for the rod. Both the ring and the hole are split by a cut, so they work as clamps. The bottom layer has a smaller opening, and the recorder's foot rests on it; the middle layer has the slots for the bolts that tighten the clamps. The rod is not included.

- "flutediameter" is the diameter of the recorder's foot.
- "polediameter" is the diameter of the rod to fit.
- "wall" is the width of the material around the recorder.""",
    'StackableBin': """\
The stackable bin is a row of trays open at the front, with a sloped front, made to be stacked: each bin stands on feet that lock into the top edge of the one below, so you can build a column of compartments for a shelf or a workbench.

It is made of a bottom, a back, two sides and a front retainer leaning out at 45° that keeps the contents in; a divider stands between neighbouring compartments. Everything joins with finger joints, and the dividers sit in finger holes in the bottom, back and retainer. The sides carry the stackable feet at the bottom and the edge that takes them at the top; the stabilizer strips of the stackable edges are glued inside, along the bottom of the walls.

- "compartment widths": how many compartments and how wide, left to right (for example 50*3 is three 50 mm compartments).
- "height" and "bin depth": the size of each tray.
- "front": the fraction of the height covered by the sloped wall.
- "outside": when on, the sizes are outside measurements.""",
    'Tetris': """\
The Tetris generator makes a three-dimensional Tetris piece: a hollow block shaped like a tetromino, to use as a game piece, a decoration or a small closed box.

Each piece is made of two identical plates with the outline of the shape, one on top and one at the bottom, and a series of walls that run all round the outline and stand between the two plates. The walls join each other and the plates with finger joints. The lines between the single squares are engraved on the plates, so the piece reads as made of blocks.

- "shape": which tetromino to cut, from I, L, O, S and T.
- "blocksize": the side of one square in mm; the piece is just as tall, so each block is a cube.

For a full set generate each shape in turn with the same "blocksize" and "thickness", so the pieces fit together.""",
    'TriangleLamp': """\
The triangle lamp is an LED lamp shaped like a right triangle: a low wooden frame closed at the front by a screen with holes. The generator draws the parts for two identical lamps; the LEDs themselves are not part of the drawing.

Each lamp has a triangular back, three walls (the two legs and the hypotenuse) and the screen, a triangle the same size as the back. The back and walls join with finger joints. In the corners, just below the walls' edge, small wooden triangles with a hole sit in finger holes: the screen rests on them flush with the edge and is fixed with small screws through the matching holes.

- "width": the length of the legs, and so the size of the lamp.
- "height": the depth of the frame.
- "cornersize": the short side of the corner triangles.
- "screenholesize" and "screwholesize": the diameter of the holes in the screen and in the wood.
- "sharpcorners": extends the walls for crisp 45° corners; you then have to grind the edges to a 22.5° bevel by hand.""",
    'TriangularWall': """\
The triangular wall is a single panel shaped like a right triangle, to use as a part in your own builds: a sloped side, a corner brace, a shelf bracket, or a piece of a larger object the ready-made generators don't cover.

For each of the three sides you pick the edge type, from all those boxes.py offers: straight, finger joints, finger holes, dovetails, hinges, stackable edges and so on. This way the triangle joins the other panels of your project, which you can draw with the same edge types.

- "width" and "height": the two legs, horizontal and vertical.
- "bottom_edge": the edge of the horizontal leg.
- "right_edge": the edge of the vertical leg.
- "left_edge": the edge of the sloped side.
- "radius": rounds the corners towards the sloped side, to make them sturdier.

The advanced settings of the single edges (finger joints, hinges, dovetails…) tune the details of the edge type you chose.""",
    'TypeTray': """\
The type tray is a box split into a grid of compartments, like an old printer's type case: handy for small parts, screws, electronic components or cards. The inner walls run unbroken from side to side, so the compartments always line up in rows and columns.

The outer walls join each other and the bottom with finger joints; the inner walls cross with halving joints, slots sliding into each other, and sit in finger holes in the outer walls and the bottom.

- "compartment widths" and "compartment depths": the columns left to right and the rows back to front (for example 50*3 is three 50 mm compartments).
- "height" and "inner walls height": the inner walls can be lower.
- "top_edge": open, with a fixed top or with one of the available lids.
- "fingerholes": notches in the top of the inner walls (and, if you like, of the front and back) to reach the contents.
- "grip hole width" and "handle": a grip hole in the front or a handle on the bottom.

With "label_file" (one line per compartment) you engrave a name on the inner walls.""",
    'UBox': """\
The U-box is a box with rounded bottom corners: the two sides are U-shaped, and a single continuous wall wraps round them, from the top edge of the front down across the bottom and up the back.

The bends of the wall are flex sections, cut in a lattice so the panel can bend: you need thin, flexible plywood and some patience when bending it. The sides join the wall with finger joints along the whole outline of the U.

- "width": the distance between the two sides.
- "depth" and "height": the size of the U.
- "radius": the radius of the bottom corners; it is capped at half the depth and at the height.
- "top_edge": leaves the box open, adds a fixed top or one of the available lids, hinged ones included.

The lid style and its sizes are set in the advanced lid settings, the flex sections in the advanced flex settings.""",
    'UnevenHeightBox': """\
The uneven height box is a box with a different height at each corner, so its top edge slopes. It suits, for example, a container with a low front and a tall back.

The four walls are trapezoids joined to each other and to the bottom with finger joints. The optional lid is a level plate at the height of the tallest corner, with four trapezoid walls hanging down to the box's sloped edge; where both corners already reach the lid, that wall is left out.

- "width" and "depth": the size of the base.
- "height0", "height1", "height2", "height3": the height of the front left, front right, back right and back left corners.
- "add_lid" and "lid_height": the lid and its extra height; it works best with the high corners opposite each other.
- "edge_types": four letters, counter-clockwise from the front, for the top edge of each wall: flat (e) or grooved (z, Z); the lid gets the opposite profile, so the two edges match.
- "bottom_edge": the bottom, or no bottom at all.""",
    'UniversalBox': """\
The universal box is the classic rectangular box, with four walls, a bottom and a wide choice of closures at the top: open, with a fixed top, a lid resting on it, a sliding lid, hinges or a stackable edge. It is the starting point for almost any square container.

The walls join each other and the bottom with finger joints. The vertical edges can be made with finger holes instead: the side walls put their fingers into holes in the front and back, which then cover the sides' edges.

- "width", "depth" and "height": the size of the box.
- "outside": when on, these are outside rather than inside measurements.
- "top_edge": the kind of closure at the top.
- "bottom_edge": the bottom, flat or with other edges, or no bottom at all.
- "vertical_edges": finger joints or finger holes for the vertical edges.

The lid, its handle and the details of hinges and joints are set in the advanced settings.""",
    'WallCaliper': """\
The wall caliper holder keeps a single caliper hanging on a wall or a tool board, always in the same place and ready to grab.

It is made of three parts: a narrow back plate with a rounded flange on each side, and two shaped sides standing in front of it. Each side has a notch the caliper's body slides into, while the beam passes between the two sides. The sides join the back plate with finger joints that go through it to the wall system.

- "height": the height of the holder.
- "width": the distance between the two sides, i.e. the width of the caliper's long end.
- "body height": the depth of the notch, to match the thickness of the caliper's body.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallChiselHolder': """\
The wall chisel holder is a shelf with a row of holes to hang chisels, files and similar tools by their handle: the blade goes through the hole, the handle doesn't and rests on top.

It is made of a back plate that goes on the wall, a horizontal top and triangular braces under the top that carry it. Each hole opens to the front edge of the top through a slot, so the tool slides in from the side. The braces join the top and the back plate with finger joints.

- "number": how many tools.
- "tooldiameter": the room for each tool, including space to grab it; it sets the pitch of the holes.
- "holediameter": the blade must fit through, the handle must not.
- "slot_width" and "radius": the opening towards the front and the rounding of its corners.
- "hooks": braces at every hole, every other hole or every third.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallConsole': """\
The wall console is a panel that stands out from the wall and leans back, like a small fixed lectern to mount the things you want in view and within reach.

It is made of a back plate on the wall, trapezoid sides standing out from it and a front panel resting on their sloped edges. If you split the width into several sections, a trapezoid divider like the sides stands between them. Sides and dividers join the front panel with finger joints and the back plate through the wall system's edge.

- "compartment widths": the total width, split into sections left to right.
- "height": the height of the console.
- "top_depth" and "bottom_depth": how far it stands out at the top and at the bottom; the difference sets the slope of the front panel.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallEdges': """\
The wall edges generator is not a finished object but a test sheet: four sample rectangular panels, each with a pair of the edges wall-mounted holders use to attach to the chosen system. The letter naming each edge is engraved next to it.

Use it, before cutting a real holder, to check that the hooks fit your board or rail and that the joints go together with your material and kerf setting. The four panels show edges a and A (the ones that go against the wall), b and B (with fingers passing through the back), c and C (the back plate's edge), d and D (an edge with a row of holes beside it); the third panel also shows the row of holes that takes the b edges.

- "walltype": the system to test: plain, plain reinforced, slatwall, dinrail, french cleat or skadis.
- "height": the height of the test panels.

The sizes of the hooks (pitch, depth, board thickness…) are set in the advanced settings of the chosen system.""",
    'WallHook': """\
The wall hook is a J-shaped hook to hang on a wall or a tool board, for jackets, bags, cables or anything you want to keep hanging.

It is made of two identical hook-shaped sides, opening upwards, either side of a narrow back plate with rounded flanges. Two strips join the two sides: one lies across the bottom of the hook, the other stands in its tip. The sides join the strips with finger joints and the back plate with joints that go through it to the wall system.

- "height": the overall height of the hook.
- "width": the distance between the two sides, i.e. the width of the hook.
- "hook_inside_diameter": the room inside the bend, where the item rests.
- "hook_thickness": the thickness of the bend, which gives it its strength.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallPinRow': """\
The wall pin row is a bar with a row of pins pointing upwards, to hang tools, keys or anything else on.

The pins are the teeth of a single strip that passes through slots in a front plate; behind it sits a second, parallel plate, and the two are held together by two sides and intermediate supports, which attach to the wall. Everything joins with finger joints, and the front plate leans back by the chosen angle, so the pins point up and items don't slide off.

- "pins": how many pins.
- "pinlength" and "pinwidth": the size of each pin.
- "pinspacing": the distance between centres; "pinspacing_increment" makes it grow from left to right.
- "angle": how far the pins point upwards.
- "hooks": how many attachment points to the wall (sides plus supports).
- "front plate height": at least 7 times the thickness; a smaller value is raised.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallPlaneHolder': """\
The wall plane holder keeps a hand plane upright on the wall, out of the way and always in the same place.

It is made of two rectangular sides fixed to the wall and, between them, four parts: a bottom the plane stands on, two back strips it leans on, one low and one high, and a holder at the front that keeps the plane in at the top. All of them sit in finger holes in the sides.

- "width": the width of the plane, i.e. the distance between the sides.
- "length": the length of the plane, which sets the height of the sides.
- "height": the height of the front of the plane, which sets the depth of the sides.
- "hold_length": how long the part holding the plane at the front is.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallPliersHolder': """\
The wall pliers holder is a bar standing out from the wall to hang pliers, cutters and similar tools astride it: one handle stays in front of the bar and one behind.

It is made of a back plate on the wall, a front bar and a row of curved braces that stand out from the plate and carry the bar at the top. The two outer braces hold the bar in finger holes on their edges, the inner ones go into finger holes in the bar; all of them attach to the back plate through the wall system's edge.

- "compartment widths": the length of the bar, split into sections left to right; a brace stands between sections.
- "depth": how far the bar stands out from the wall.
- "height": the height of the front bar.
- "angle": the bracing angle; a lower value gives a longer, sturdier brace.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallRack': """\
The wall rack is a stack of shelves on a single back panel, to hang on the wall: made for spice jars, but good for any small items you want in view.

The back panel carries the finger holes for all the shelves. Each shelf is a bottom with a front lip and two trapezoid side lips, taller towards the back, joined to each other and to the panel with finger joints. At the top, with the default top edge, the panel has holes to screw it to the wall.

- "width" and "depth": the size of the shelves.
- "section heights": how many shelves and how much room for each, bottom to top (for example 100*3).
- "wall_height": the height of the shelves' front lip.
- "back_height": the height of the side lips at the back, as a fraction of the front.
- "top_edge": straight, with mounting holes or with a handle.
- "side_edges": how the side lips join the front lip.
- "flat_bottom": lets the rack also stand on a surface.""",
    'WallSlottedHolder': """\
The wall slotted holder is a shelf with a row of slots open at the front, to slide in tools that hang by their shank or blade, with the wider part staying on top.

It is made of a back plate that goes on the wall, a horizontal top with the slots in its front edge and triangular braces under the top that carry it. Unlike the chisel holder, the slots are straight with no round hole, and the top carries on behind them for the depth you choose. The braces join the top and the back plate with finger joints.

- "number": how many slots.
- "tool_width": the room for each tool, which sets the pitch of the slots.
- "slot_width" and "slot_depth": the size of each slot; "radius" rounds its corners at the front.
- "additional_depth": how much top is left behind the slots.
- "hooks": braces at every slot, every other slot or every third.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallTypeTray': """\
The wall type tray is the hanging version of the type tray: a box open at the top, split into a grid of compartments, with its back hooked onto the wall.

The outer walls join each other and the bottom with finger joints; the inner walls cross with halving joints and run unbroken from side to side. The back wall and the sides carry the wall system's edges; the back can rise above the rest, with the sides meeting it along a sloped edge.

- "compartment widths" and "compartment depths": the columns left to right and the rows back to front.
- "height" and "inner walls height": the inner walls can be lower.
- "back_height": how far the back rises above the other walls; "radius" rounds where the sides meet it.
- "all_mounts": attaches the inner front-to-back walls to the wall too and makes them full height.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WallWrenchHolder': """\
The wall wrench holder keeps a set of open-end wrenches in order on the wall, from the smallest to the largest, each in its own slot.

It is made of two identical sides and a back plate between them, which goes on the wall. The front edge of each side has a row of sloped slots, getting larger: each wrench lies across, in the slots of both sides. The sides attach to the back plate through the wall system's edge.

- "number": how many wrenches.
- "min_width" and "max_width": the width of the smallest and the largest wrench; the others grow evenly in between.
- "min_strength" and "max_strength": the thickness of the smallest and the largest wrench.
- "extra_distance": extra room between one wrench and the next.
- "width": the distance between the sides; "depth": how far they stand out from the wall.

The "walltype" setting picks the system it attaches to (slatwall, dinrail, french cleat, skadis…) and shapes the edges facing the wall to match; with "plain" they stay straight and how you fix it is up to you.""",
    'WavyKnob': """\
The wavy knob is a round knob with a wavy rim for a firm grip with your fingers: good for tightening a bolt by hand on a jig, a clamp or a lid, or on a shaft.

It is made of three identical discs stacked together. The bottom one is plain, the middle one has a hexagonal hole that locks a bolt's head, the top one has the hole for the shank; the bolt then sticks out of the knob's centre and turns with it. The bolt is bought separately.

- "diameter": the size of the knob.
- "serrations": how many waves the rim has.
- "serrationangle": higher values give deeper waves.
- "bolthole": the diameter of the bolt's shank.
- "dhole": the flat side of the hole as a fraction of the diameter; at 1 the hole is round, below it becomes a D for a shaft with a flat.
- "hexhead": the width of the bolt head, across the flats.

For a snug hexagonal hole, adjust the "burn" setting (kerf compensation).""",
    'WineRack': """\
The honeycomb wine rack is a wine rack with hexagonal cells, like a honeycomb: the bottles slide in lying down, each in its own cell, and the honeycomb holds them in place.

It is made of three panels of the same size. The front panel has the round holes for the bottles and the finger holes for the walls; the back panel has only the finger holes and closes the rear; a third panel with only the holes covers the front and hides the joints. Between the front and back panels a rectangular wall sits in every pair of finger holes: together they form the hexagons.

- "width" and "depth": the size of the panels, i.e. the face of the rack.
- "height": the length of the cells, i.e. how far the bottle goes in.
- "radius": the radius of the bottle holes, which sets the size of the cells; their number follows from the face size.
- "walls": all the honeycomb walls, no vertical ones, or only the bare minimum, to save material.

Pick the "radius" by measuring your bottles at the widest part that goes into the cell.""",
}
