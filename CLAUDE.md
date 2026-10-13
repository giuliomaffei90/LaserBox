# LaserBox

## 3D views: note the open points

Whenever 3D work (a recipe in `LaserBox/assembly.py`, a decoration, the exploded view…) leaves
something out, guesses geometry, follows a quirk of the boxes.py generator, or leaves anything else
for the user to decide, add it to `3D-REVIEW.md` in the repo root, under the matching heading
(Italian, one bullet per point, what was done and why it is doubtful), and commit it with the work.
The user reviews that file at the end.

When a point in `3D-REVIEW.md` is solved, delete its bullet entirely: don't mark it as solved or
leave a note of the fix. Keep only what is still open (e.g. a guess still to verify). `/todo` lists
the first 10 bullets, so the file must hold only open points.
