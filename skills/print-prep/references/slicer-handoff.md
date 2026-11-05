# Slicer handoff

Give the user only the steps for their printer.

## Bambu Studio / OrcaSlicer (Bambu Lab, Elegoo Centauri Carbon, most Klipper printers)

1. **File > Import > Import 3MF/STL**. A multi-part 3MF from print_prep loads as one object with its parts in place. If Bambu Studio asks "Load these files as a single object with multiple parts?", answer **Yes**.
2. Pick your printer, plate and filament profile. For PLA: 0.20 mm layers ("0.20mm Standard"). Fine figurines: 0.12 mm.
3. Supports, only if the report says so: **Support > Enable support**, Type **tree(auto)**, Threshold angle **45**. "On build plate only" is fine when the support islands are low.
4. Brim (tall, narrow or small contact): **Others > Brim type: Outer brim only**, width 5 mm.
5. Multi-colour: **Objects** list, select each part, click the filament number and pick an AMS slot. Use the colours in report.md under "Parts". A prime tower is added automatically.
6. **Slice plate**, check the layer preview for floating starts, then **Print**.

## PrusaSlicer (Prusa MK4S / CORE One / MINI / XL)

1. **Add** (Ctrl+I) the 3MF or STL. For a multi-part 3MF, answer **Yes** to "multi-part object".
2. Print settings **0.20mm SPEED** (or 0.15 QUALITY for figurines).
3. Supports, only if needed: **Supports: For support enforcers only** or **Everywhere**, Style **Organic**.
4. Brim: **Print Settings > Skirt and brim > Brim width 5 mm**.
5. MMU3: right-click each part, **Change extruder**, then pick slots 1-5.
6. **Slice now**, check the preview, then **Export G-code** or **Send to printer**.

## Resin (Chitubox / Lychee / Elegoo Satellite)

1. Import the STL.
2. Hollow at 2 mm wall thickness if the model is over ~20 ml, and punch 2 drain holes (3-4 mm) near the build-plate side.
3. Tilt 15-30 degrees, then **auto supports (medium)**. Make sure every island in the report gets a support.
4. Slice with your resin's exposure profile.

## Print settings by job type

| Job | Layer | Walls | Infill | Supports | Brim |
|---|---|---|---|---|---|
| Shelf figurine 60-120 mm | 0.12-0.16 | 3 | 10-15% gyroid | tree if flagged | if tall_narrow |
| Toy (gets dropped) | 0.20 | 4 | 20% | tree if flagged | yes |
| Name plaque / plinth | 0.20 | 3 | 15% | usually none | no |
| Tabletop mini 32 mm | resin preferred; FDM at 0.08 with a 0.2 mm nozzle | 2 | 100% | yes | no |
