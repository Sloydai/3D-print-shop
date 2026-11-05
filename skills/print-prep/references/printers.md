# Printer presets

Build volumes are in mm (X x Y x Z), from manufacturer spec pages. They're used by `print_prep.py --printer`. Check the spec page for your exact model and firmware; some printers lose a few mm to the purge or wipe area.

| Key | Printer | Build volume | Tech | Multi-colour |
|---|---|---|---|---|
| `bambu-a1-mini` | Bambu Lab A1 mini | 180 x 180 x 180 | FDM | AMS lite (4) |
| `bambu-a1` | Bambu Lab A1 | 256 x 256 x 256 | FDM | AMS lite (4) |
| `bambu-p1s` | Bambu Lab P1S | 256 x 256 x 256 | FDM | AMS (4, chain up to 16) |
| `bambu-p2s` | Bambu Lab P2S | 256 x 256 x 256 | FDM | AMS 2 Pro / AMS HT |
| `bambu-x1c` | Bambu Lab X1 Carbon | 256 x 256 x 256 | FDM | AMS (4, chain up to 16) |
| `bambu-h2d` | Bambu Lab H2D, single-nozzle volume | 325 x 320 x 325 | FDM | dual nozzle + AMS |
| `prusa-mini` | Prusa MINI+ | 180 x 180 x 180 | FDM | none |
| `prusa-mk4s` | Prusa MK4S | 250 x 210 x 220 | FDM | MMU3 (5) |
| `prusa-core-one` | Prusa CORE One | 250 x 220 x 270 | FDM | MMU3 (5) |
| `prusa-xl` | Prusa XL | 360 x 360 x 360 | FDM | up to 5 toolheads |
| `elegoo-neptune-4-pro` | Elegoo Neptune 4 Pro | 225 x 225 x 265 | FDM | none |
| `elegoo-centauri-carbon` | Elegoo Centauri Carbon | 256 x 256 x 256 | FDM | CANVAS (4) |
| `elegoo-mars-5-ultra` | Elegoo Mars 5 Ultra | 153 x 77 x 165 | resin | none (paint) |
| `elegoo-saturn-4-ultra` | Elegoo Saturn 4 Ultra | 218 x 123 x 220 | resin | none (paint) |

The fit check sorts X/Y, so a model that fits rotated 90 degrees on the plate counts as fitting. Z is never swapped. If a model only fits lying down, re-orient it with `--rotate` and re-check the overhangs.
