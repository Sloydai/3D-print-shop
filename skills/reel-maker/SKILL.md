---
name: reel-maker
description: Plans the social video (YouTube Shorts, Instagram Reels, TikTok, X) of a Sloyd 3D print - photoreal stills of the printed object in a real setting made with Sloyd generate_image/edit_image, a real turntable render of the actual mesh, a shot list with timings and captions, and image-to-video prompts. Use when someone wants a reel, short, TikTok, video, post or launch clip of a print, says "show it off", "make a video of my print", or wants a looping clip. The video always starts and ends on a photoreal clip of the physical print.
---

# Reel Maker

This is the one rule you never break: **the reel starts AND ends on a photoreal clip of the physical print in a real place** (shelf, desk, windowsill, nightstand). Real Sloyd footage goes in the middle. Make each opener and closer as a **photoreal still first**, then animate it.

## Sloyd only, and the video step is pending

Sloyd's public API has **no video tool yet** (see `${CLAUDE_PLUGIN_ROOT}/skills/sloyd-api/references/api.md`). So you:
- make the photoreal stills with Sloyd (`generate_image` / `edit_image`)
- make the real turntable locally from the actual print-ready mesh
- write the shot list and the exact image-to-video prompts
- mark every animation step **`PENDING: Sloyd video API`**

Do not use Runway, Kling, fal, Luma, Pika or any other provider, even if the user has keys. When Sloyd's video tool is public, the prompts plug straight in (start frame = still A, end frame = still A for a loop).

## Inputs

`print-jobs/<slug>/`: `brief.json`, `print_ready/<slug>.stl`, and `sloyd/model.glb` (textured if possible), plus the user's real assets if they have them: a printer timelapse, a phone video of the real print, and a Sloyd web app screen recording.

## Steps

1. **Real reference render** (free, local), from the print-ready mesh so the stills match the file:
   ```bash
   R=${CLAUDE_PLUGIN_ROOT}/skills/print-prep/scripts/render.py
   python3 $R print-jobs/<slug>/print_ready/<slug>.stl --out print-jobs/<slug>/reel/ref.png --bg white --no-overlay --size 1024 --color <r,g,b of the filament>
   python3 $R print-jobs/<slug>/print_ready/<slug>.stl --out print-jobs/<slug>/reel/turntable.mp4 --frames 150 --fps 30 --title "<Name>" --subtitle "<size> mm  |  print-ready"
   ```
   The turntable is real footage of the real mesh, so it can go in the middle section.
2. **Upload the reference** (free). Keep the `jobId`. Prefer Sloyd's own concept image for the model job (`https://storage.googleapis.com/ai-services-quality/jobs/<modelJobId>.input.webp`): it has the same shape as the mesh, plus the colours. Use `ref.png` when the model came from a photo or was retextured.
3. **Still A, the opener and loop frame** (10 credits): `generate_image` with `referenceImageJobId` = the upload and `aspectRatio: "9:16"`. Build the prompt from `references/shots.md` and the brief:
   > Photograph of a 3D printed <matte PLA, <filament colour>> figurine of <subject> standing on <a sunlit oak windowsill>, faint horizontal layer lines visible on the plastic, slight seam, real-world scale <80 mm tall> next to <a coffee mug>, shallow depth of field, soft morning light, shot on iPhone, photorealistic, vertical 9:16

   Use `genStyleId: "Realistic"`. Name the material and the layer lines: that's what makes it read as a *print* and not a toy render. Include a scale object.
4. **Still B, the closer** (15 credits, optional): `edit_image { jobId: <still A jobId>, prompt: "same photo, same object and lighting, camera slightly closer and lower" }`. For a **seamless loop**, the closer must END on still A exactly, so the end clip's last frame = still A. Skip B and use A as both the start and end frame.
5. Check each still against the preview. Same silhouette and colour? If the object changed shape, regenerate once with "exactly the object in the reference, same proportions". Never post a still that doesn't match the file.
6. Write `reel/shotlist.md` using the template in `references/shots.md`: timings, on-screen captions, sources, and for each AI clip the image-to-video prompt plus start and end frame, flagged `PENDING: Sloyd video API`.
7. **Cost**: tell the user first (still A 10 + still B 15 = 25 credits), via `get_credit_balance`.

## Structure (15-25 s vertical, 1080x1920)

| # | Time | Shot | Source |
|---|---|---|---|
| 1 | 0-3 s | **Photoreal clip of the print in a real place**, slow push-in | still A, then video (PENDING) |
| 2 | 3-6 s | The prompt being typed | real Sloyd web app or Claude Code screen recording |
| 3 | 6-10 s | The model appears and spins | `turntable.mp4` (real), or a Sloyd viewer recording |
| 4 | 10-13 s | print_prep report: watertight, mm, grams | screenshot of `<slug>_preview.png` + `report.md` |
| 5 | 13-17 s | Slicer, then printer timelapse | user's real footage (ask for it), otherwise skip |
| 6 | 17-20 s | **Photoreal clip of the print in a real place**, ends on still A's frame | still B/A, then video (PENDING) |

Captions: hook in the first second ("Describe it. Print it."), then one short line per shot. Brand colour accent: Sloyd sky `#45bcff` to green `#03f584`, Poppins.

## Honesty

- Label AI clips as AI if the platform asks (TikTok, YouTube "altered or synthetic content").
- Never present an AI still as a photo of a real print in captions. "Printed result" claims need the user's real photo.
