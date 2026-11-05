# Desk Owl: reel shot list (9:16, 1080x1920, ~20 s)

Hook caption: **"Describe it. Print it."**

| # | Time | Visual | Source file | Caption | Status |
|---|---|---|---|---|---|
| 1 | 0-3 s | Photoreal owl print on a sunlit windowsill, slow push-in | `still_A.png`, animated | Describe it. | PENDING: Sloyd video API |
| 2 | 3-6 s | The prompt typed into Claude Code | screen recording | "A cute chubby owl… 80 mm, Bambu A1, AMS" | TO RECORD |
| 3 | 6-10 s | The real mesh spinning | `turntable.mp4` (rendered from the print-ready STL) | Sloyd builds it in 2 minutes | READY |
| 4 | 10-13 s | print-prep result | `../print_ready/desk-owl_preview.png` + `../print_ready/report.md` | Watertight. 80 mm. 58 g. | READY |
| 5 | 13-17 s | Bambu Studio slice, then the A1 timelapse | user footage | Print it. | TO RECORD (print the owl's print-ready 3MF) |
| 6 | 17-20 s | Photoreal owl, warmer light, pull-back, last frame = shot 1's first frame | `still_B.png` start, `still_A.png` end (start/end-frame mode) | github.com/Sloydai/3D-print-shop | PENDING: Sloyd video API |

## AI clip prompts (for the Sloyd video tool, when it's public)

- **Clip 1**: start frame `still_A.png`. "Slow cinematic push-in toward the 3D printed owl figurine on the windowsill, gentle parallax, dust motes in the morning light, the owl stays perfectly still and unchanged, 3 seconds."
- **Clip 6**: start frame `still_B.png`, end frame `still_A.png`. "Slow pull-back and slight rise from eye level, the light cools from late afternoon to morning, the owl stays unchanged, ends exactly on the opening composition, 3 seconds."

## Sloyd jobs

- reference upload `3oxbl9yo` (0 credits; Sloyd's concept image for model job `(model job ID not published)`)
- still A `ejzns5mc` (generate_image, 10 credits)
- still B `qlijf8ar` (edit_image, 15 credits)

The stills are AI images. Label them as AI or synthetic where the platform asks. The real-object shots (5 and an optional hand-held shot) need the physical print.
