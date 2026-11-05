# Launch tweet: 3D Print Shop

Every asset below comes from a real run of the team on the Sloyd API (`examples/desk-owl/`, 90 credits). The two shots that need the physical print (timelapse, real object) are marked **TO RECORD**.

## Main tweet

Describe it. Print it.

Claude now makes print-ready STLs.

"A cute chubby owl, wings folded, flat base. 80 mm, Bambu A1, AMS."

2 minutes later: watertight STL + 3MF, 80.0 mm, 58 g PLA, fits the plate, split into 6 AMS parts.

8 skills, one print shop:

```
3d-print-shop/
├── print-shop-manager
├── print-designer
├── modeler
├── print-prep
├── multi-color-splitter
├── gift-maker
├── reel-maker
└── sloyd-api
```

Bambu · Prusa · Elegoo

`/plugin marketplace add Sloydai/3D-print-shop`

github.com/Sloydai/3D-print-shop

**Media:**
- Main image: `examples/desk-owl/tweet_hero.png` (prompt, then Sloyd model, then AMS parts, then on the shelf). Panel 4 is labelled as an AI preview.
- Or 4 images:
  1. `examples/desk-owl/reel/still_A.png`: photoreal still of the owl on a windowsill (AI, Sloyd `generate_image` job `ejzns5mc`)
  2. a screenshot of the prompt in Claude Code (**TO RECORD**)
  3. `examples/desk-owl/screenshots/2_print_ready_front.png`: 3D viewer screenshot of the real print-ready parts
  4. a photo of the physical printed owl (**TO RECORD**, after printing it)

## Alt hooks

1. Your printer has been waiting for this. Type what you want, and Claude hands you a watertight STL in real millimetres, ready to slice.
2. "80 mm owl, Bambu A1, AMS." That was the whole prompt. Claude did the rest: model, repair, flat base, wall check, 6-part AMS file. 👇

## Reply thread (optional)

1. How it works: print-designer asks your size, printer and support tolerance, and writes a printable prompt. modeler generates it with Sloyd. print-prep repairs it to a watertight solid, scales it to mm, flattens the base and checks walls and overhangs.
2. Multi-colour: multi-color-splitter cuts the model into parts (head, body, wings, feet) and assigns AMS slots. One 3MF, drop it in Bambu Studio.
3. Gifts: a photo of your dog becomes a figurine with her name raised on the base. The lettering is real geometry, not AI gibberish.

## Demo video shot list (9:16, ~20 s)

It opens and closes on a photoreal clip of the print in a real setting. Full prompts are in `examples/desk-owl/reel/shotlist.md`.

| # | Time | Shot | Source | Caption | Status |
|---|---|---|---|---|---|
| 1 | 0-2 s | Photoreal owl on a sunlit windowsill, push-in | `reel/still_A.png`, animated | Describe it. | still READY, animation PENDING Sloyd video API |
| 2 | 2-5 s | **Prompt**: typing the request into Claude Code | screen recording | "A cute chubby owl… 80 mm, Bambu A1, AMS" | TO RECORD |
| 3 | 5-9 s | **Model**: the real mesh spinning | `reel/turntable.mp4` | Sloyd builds it in 2 min | READY |
| 4 | 9-11 s | print-prep: watertight, 80 mm, 58 g | `print_ready/desk-owl_preview.png` | Print-ready STL + 3MF | READY |
| 5 | 11-16 s | **Printer timelapse** on the A1 | real footage | Print it. | TO RECORD |
| 6 | 16-18 s | **Real object**: a hand picks up the printed owl | real phone footage | | TO RECORD |
| 7 | 18-20 s | Photoreal owl, pull-back; last frame = shot 1's first frame (loop) | `reel/still_B.png` start, `still_A.png` end | github.com/Sloydai/3D-print-shop | still READY, animation PENDING Sloyd video API |

Label the AI stills as synthetic where the platform asks. Don't caption an AI still as a photo of the real print.
