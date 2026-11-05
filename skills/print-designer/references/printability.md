# Printability rules of thumb

These are typical starting values. Every printer, material and slicer profile shifts them a little.

## FDM (0.4 mm nozzle, PLA/PETG)

| Feature | Minimum | Comfortable |
|---|---|---|
| Wall / standalone feature thickness | 0.8 mm (2 perimeters) | 1.2-2 mm |
| Pins, horns, tails (diameter) | 2 mm | 3 mm or more |
| Embossed or engraved text: line width / depth | 0.6 mm / 0.4 mm | 1 mm / 0.6-1 mm |
| Raised label letter height (cap) | 4 mm | 6-10 mm |
| Overhang without supports | 45 deg from vertical | 35-40 deg |
| Bridges | under 10 mm | under 5 mm |
| Clearance between moving or fitted parts | 0.2 mm | 0.3-0.4 mm |
| Bed contact for a figurine | 30 mm2 + brim | 15% of the footprint, or a plinth |

The minimum feature size scales with the nozzle. A 0.2 mm nozzle halves it but makes printing about 4x slower.

## Resin (MSLA, Elegoo Saturn / Mars)

| Feature | Minimum |
|---|---|
| Wall / feature | 0.4 mm (0.6 mm survives washing better) |
| Unsupported overhang | ~30 deg; resin prints are always supported |
| Hollow prints | 1.5-2.5 mm wall, with at least 2 drain holes of 3 mm or more near the bed side |
| Typical tilt | 15-30 deg, to cut peel forces and suction cups |

## Scale

- A tabletop mini is 28-32 mm, heroic scale 32-35 mm, base 25 mm.
- Shelf figurines are 60-120 mm. At 40 mm or less, FDM loses facial detail. Suggest resin, or a chunkier style.
- An AI model has no inherent scale. The user's mm number is the truth, and print-prep enforces it.

## What breaks AI-generated models

| Problem | Cause | Prevention |
|---|---|---|
| Rounded bottom, falls over | the generator imagines a floating object | "flat base" / "sitting", plus print-prep flattens or adds a plinth |
| Floating specks | particles, sparkles, separate accessories | "single connected piece", plus print-prep drops specks |
| Paper-thin parts | ears, capes, whiskers, swords | "chunky, thick", or name and remove the feature |
| Open holes and self-intersections | normal for generated meshes | print-prep repair: fill, union, voxel rebuild |
| Gibberish text | generators can't spell | add text locally with `--label` |
