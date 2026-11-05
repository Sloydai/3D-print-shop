# Print prep report: parts.glb

- Size: **73.4 x 64.6 x 80.0 mm** (X x Y x Z)
- Watertight: **yes**, 6 body(ies), 104,280 faces
- Volume: 189.77 cm3, about **69.1 g** of PLA
- Printer: Bambu Lab A1, fits: **yes**
- Wall thickness: thinnest ~1.72 mm (5th percentile 4.61 mm), 0.4% of the surface below the 0.8 mm minimum
- Overhangs > 45 deg: 16.3% of surface; support islands: 15
- Bed contact: 559 mm2, centre of mass over base: True

## Warnings

- **no_texture_colour**: The model's texture has no colour (grayscale, e.g. an ambient-occlusion-only map), so part colours can't be read from it. Fix: Pass --colors with a filament per part name (see the concept image), or assign filaments in the slicer.
- **overhangs**: 16.3% of the surface overhangs more than 45 deg (z 0-5 mm, z 35-40 mm, z 40-45 mm); 15 spot(s) start in mid-air, lowest at z 2.8 mm. Fix: Enable supports: tree supports (Bambu Studio / OrcaSlicer: Support > Type 'tree(auto)'; PrusaSlicer: 'Organic'), threshold 45 deg, or rotate the model so the flat side is down.

## Parts (one filament each)

| # | part | file | size mm | colour | AMS slot |
|---|---|---|---|---|---|
| 1 | Body | (not published) | 57.7 x 61.1 x 41.4 | #6e4628 | 1 (brown) |
| 2 | Foot_Left | (not published) | 14.6 x 7.8 x 8.9 | #f0781e | 2 (orange) |
| 3 | Foot_Right | (not published) | 14.6 x 7.7 x 8.9 | #f0781e | 2 (orange) |
| 4 | Head | (not published) | 58.4 x 62.2 x 42.9 | #6e4628 | 1 (brown) |
| 5 | Wing_Left | (not published) | 10.2 x 32.6 x 35.8 | #6e4628 | 1 (brown) |
| 6 | Wing_Right | (not published) | 10.2 x 32.6 x 35.8 | #6e4628 | 1 (brown) |

## Steps

1. loaded 6 mesh part(s) from parts.glb, Y-up -> Z-up
1. part colours set by name: Foot_*=orange,*=brown
1. scaled x615.4 to 70.0 x 61.6 x 80.0 mm
1. Body: 37,796 faces, 1 shell(s), 0 open
1. Foot_Left: 4,584 faces, 2 shell(s), 0 open
1. Foot_Left: unioned 2 shells into one solid
1. Foot_Right: 4,592 faces, 2 shell(s), 0 open
1. Foot_Right: unioned 2 shells into one solid
1. Head: 47,266 faces, 1 shell(s), 0 open
1. Wing_Left: 7,478 faces, 1 shell(s), 0 open
1. Wing_Right: 7,460 faces, 1 shell(s), 0 open
1. flattened base: cut 3.70 mm off the bottom, contact area 426 mm2 (target 376 mm2)
1. re-fitted to the requested size (x1.0485) after base and cleanup
1. parts could not be unioned; the combined STL holds them as separate shells (slicers merge them)
1. filament slots: 1=brown, 2=orange

## Files

STL, 3MF and per-part files are not published here. Run the prompt with your own Sloyd key.
