---
name: print-prep
description: Makes a 3D model print-ready with a local Python script - converts GLB/OBJ/PLY/STL to STL and 3MF, repairs it to a watertight solid, scales it to real millimetres, adds a flat base or plinth (optionally with a raised name), and reports minimum wall thickness, overhangs, support islands, tip-over risk, filament grams and build-plate fit. Use after modeler, or whenever someone says "make this printable", "convert GLB to STL", "fix my mesh", "is it watertight", "scale to 80 mm", "will it fit my Bambu/Prusa/Elegoo", "add a base", or the slicer complains about non-manifold edges.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/print_prep.py *) Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/render.py *)
---

# Print Prep

You're the person who opens every file in the slicer before it goes to the printer. Run the script and read its report. Fix what blocks the print, and tell the user what to set in the slicer.

## Setup (once)

```bash
python3 -m pip install -r ${CLAUDE_SKILL_DIR}/scripts/requirements.txt
```

These are trimesh, manifold3d (boolean union), scikit-image (voxel rebuild), shapely, fast_simplification and matplotlib (fonts for labels). If pip isn't allowed system-wide, use a venv.

## Run

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/print_prep.py print-jobs/<slug>/sloyd/model.glb \
  --out-dir print-jobs/<slug>/print_ready --name <slug> \
  --height 80 --printer bambu-a1 --tech fdm --preview
```

| Flag | Meaning |
|---|---|
| `--height` / `--max-dim` / `--width` / `--depth` / `--scale` | final size in mm (base included). Always pass one; the default of 60 mm longest side triggers a warning |
| `--printer` | `bambu-x1c`, `bambu-p1s`, `bambu-p2s`, `bambu-a1`, `bambu-a1-mini`, `bambu-h2d`, `prusa-mk4s`, `prusa-core-one`, `prusa-mini`, `prusa-xl`, `elegoo-centauri-carbon`, `elegoo-neptune-4-pro`, `elegoo-saturn-4-ultra`, `elegoo-mars-5-ultra`. Resin printers switch `--tech resin` automatically |
| `--tech fdm\|resin`, `--nozzle 0.4` | thresholds: FDM minimum wall = 2 x nozzle, overhang limit 45 deg; resin 0.4 mm and 30 deg |
| `--base auto\|flatten\|plinth\|none` | `auto` cuts the bottom flat until the contact area is at least 12% of the footprint, and falls back to a plinth if that would remove more than 6% of the height |
| `--label "LUNA"` | rounded plinth with raised 1 mm letters in front of the model, kept as a separate 3MF part so the letters can take another filament |
| `--parts` | keep each mesh of the GLB as its own part (multi-colour); see `multi-color-splitter` |
| `--repair auto\|voxel\|none` | `auto`: clean, then fill holes, then union shells, then voxel rebuild only if still open. `voxel` forces the rebuild (always watertight; smooths details smaller than the pitch) |
| `--rotate x,y,z` | extra rotation in degrees, e.g. `--rotate 0,0,90` or lay it on its back with `-90,0,0` |
| `--up y\|z` | source up axis; GLB is Y-up (handled automatically) |

What the script does, in order: load (Y-up to Z-up), scale to mm, repair, drop floating specks, centre on the bed, add the base, re-fit to the exact requested size, analyse, then write `<slug>.stl`, `<slug>.3mf` (units mm), `parts/` (if more than one part), `report.md`, `report.json` and `<slug>_preview.png` (overhangs tinted red).

Exit code 0 means the files were written. Always read `report.md` anyway.

## Read the report like a print tech

| Warning | Blocking? | What to do |
|---|---|---|
| `not_watertight` | yes | re-run with `--repair voxel`; if detail gets lost, try `--voxel-pitch 0.15` |
| `too_big` | yes | lower the size, or split with `multi-color-splitter --pins` and glue |
| `thin_walls` (over 2% of the surface) | usually | scale up 20-30%, or go back to print-designer to regenerate chunkier. Under 2% on whiskers or tips: tell the user those may come out soft |
| `tip_over`, `small_contact` | yes for FDM | `--base plinth`, or a 5-8 mm brim |
| `overhangs`, support islands | no | turn on supports. Bambu Studio / OrcaSlicer: Support > Enable, Type `tree(auto)`, threshold 45. PrusaSlicer: Supports > `Organic`, "Support on build plate only" if the islands are low |
| `tall_narrow` | no | brim 5-8 mm; slower outer walls on the top half |
| `hollow` (resin) | no | hollow in Chitubox/Lychee with a 2 mm wall and 2 drain holes |
| `default_size` | ask | confirm the size in mm |

Then give the user:
- the size, grams of filament (or ml of resin), supports on/off, and a brim if needed
- the slicer steps for their printer from `references/slicer-handoff.md`
- the preview image

## Renders

`scripts/render.py` makes stills and 360-degree turntables of any STL with no GPU. reel-maker uses it.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/render.py print_ready/<slug>.stl --out reel/turntable.mp4 --frames 120
python3 ${CLAUDE_SKILL_DIR}/scripts/render.py print_ready/<slug>.stl --out reel/ref.png --bg white --no-overlay --size 1024
```

## Limits (say so when relevant)

- AI meshes are organic shapes and aren't dimensionally accurate. For functional parts with tolerances, use CAD.
- Wall thickness comes from sampling about 6000 inward rays. The number is reliable at the percentile level, not per vertex.
- The filament estimate assumes PLA, 2 walls and 15% infill. The slicer's number is the real one.
