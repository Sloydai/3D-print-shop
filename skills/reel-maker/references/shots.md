# Reel shot recipes

## Real-world settings that read as "my print, at home"

| Setting | Prompt fragment | Scale object |
|---|---|---|
| Windowsill | "on a sunlit white-painted wooden windowsill, potted succulent behind, soft morning light" | succulent pot |
| Desk | "on a wooden desk next to a mechanical keyboard and a coffee mug, warm lamp light, evening" | mug, keyboard keys |
| Bookshelf | "on a bookshelf between paperback books, soft daylight from the side" | book spines |
| Nightstand | "on a nightstand beside a small lamp, cozy warm light" | lamp |
| Workshop | "on the build plate of a 3D printer, just finished, textured PEI sheet, workshop light" | the printer itself |
| Gift moment | "being lifted out of a kraft-paper gift box with tissue paper, hands visible" | hands |

## Material words (pick one; they decide whether it looks printed)

- FDM PLA: "matte PLA plastic, faint horizontal layer lines, slightly rounded edges"
- Silk PLA: "silk PLA with a soft metallic sheen, visible layer lines"
- Multi-colour AMS: "multi-colour 3D print, crisp colour boundaries between flat colour regions, layer lines"
- Resin: "grey resin miniature, very fine detail, smooth surface, no layer lines visible" (or "hand-painted resin miniature")

## Still prompt template

```
Photograph of a 3D printed <material> <colour> figurine of <subject from brief>, <setting>,
<size> mm tall next to <scale object>, <material words>, shallow depth of field,
natural light, shot on a phone camera, photorealistic, vertical 9:16
```

Use `genStyleId: Realistic`, `aspectRatio: 9:16`, and `referenceImageJobId` = the uploaded `ref.png`.

## Image-to-video prompts (PENDING: Sloyd video API)

Keep the camera moves small. The object must not change shape.

- Opener: "Slow cinematic push-in toward the 3D printed figurine, gentle parallax, dust motes in the light, the object stays perfectly still and unchanged, 3 seconds." Start frame: still A.
- Closer / loop: "Slow pull-back revealing the room, light shifts softly, the object stays unchanged, ends on the exact opening composition, 3 seconds." Start frame: still B (or A), end frame: **still A** (start/end-frame mode, so the reel loops seamlessly).
- Alternative closer: "A hand reaches in and picks the figurine up, turning it slightly to the camera." Only when there's no loop.

## shotlist.md template

```markdown
# <Name>: reel shot list (9:16, 1080x1920, ~20 s)

Hook caption: "Describe it. Print it."

| # | Time | Visual | Source file | Caption | Status |
|---|---|---|---|---|---|
| 1 | 0-3 s | photoreal print on <setting>, push-in | reel/still_A.png -> video | Describe it. | PENDING: Sloyd video API |
| 2 | 3-6 s | prompt typed in Claude Code | screen recording (user) | "<the prompt>" | TO RECORD |
| 3 | 6-10 s | model spin | reel/turntable.mp4 | Sloyd builds it in ~2 min | READY |
| 4 | 10-13 s | print-prep report | print_ready/<slug>_preview.png | Watertight. <H> mm. <g> g. | READY |
| 5 | 13-17 s | printer timelapse | user footage | Print it. | TO RECORD |
| 6 | 17-20 s | photoreal print, pull-back, ends on frame 1 | reel/still_B.png -> video (end frame still_A.png) | Print it. | PENDING: Sloyd video API |

## AI clip prompts
- Clip 1: start frame still_A.png. Prompt: ...
- Clip 6: start frame still_B.png, end frame still_A.png. Prompt: ...

## Sloyd jobs
- reference upload: <jobId>; still A: <jobId> (10 cr); still B: <jobId> (15 cr)
```
