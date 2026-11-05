---
name: modeler
description: Generates the 3D model (GLB) for a print job with the Sloyd API - text-to-3D from the print-designer prompt, image-to-3D when the user has a photo or sketch, multi-image-to-3D when there are several views. Use when a print brief is ready, when the user says "generate the model", "make it from this photo/sketch/drawing", "try another version", or "retexture it", and whenever a Sloyd generation job needs to be started, polled, downloaded or recovered after a 402/429 error.
---

# Modeler

You turn the brief into `print-jobs/<slug>/sloyd/model.glb` using Sloyd only. Read `${CLAUDE_PLUGIN_ROOT}/skills/sloyd-api/references/api.md` for every tool, field and price.

## Pick the tool

| Input | Tool | Notes |
|---|---|---|
| Text prompt | `generate_3d_from_text` | `prompt`, `textureResolution`, `topology`, `genStyleId` from brief.json |
| One photo or sketch | `upload_image`, then `generate_3d_from_image` with `imageJobId` | or pass `file: {url}` for a public https image |
| 2-4 views of the same object | `generate_3d_from_images` | `frontImage` + at least one of `leftImage`/`backImage`/`rightImage`; `EnablePBR: "true"` only when multi-colour |
| Rough sketch or a messy photo | `upload_image`, then `generate_image` with `referenceImageJobId` and a clean-up prompt, then image-to-3D on the result | +10 credits. Improves results a lot (see below) |
| A model the user already has (STL/OBJ/GLB) | no generation needed: go straight to `print-prep`. For a split or retexture, upload it via REST `upload-3d` (`sloyd.py upload-3d`, free) | |

Defaults for printing:
- `topology: "triangles"`, because slicers want triangles and quads cost +5.
- `targetFaceCount: 0`. Use 150000-300000 only for resin or detailed minis.
- `textureResolution: "none"` for single-filament prints (10 credits cheaper). Keep texture (`"auto"`) when the job is multi-colour or a reel is planned, because the texture drives part colours and the photoreal stills.

### Getting good image-to-3D input

- One subject, centred, fully in frame, plain light background, no hands, no other objects.
- A 3/4 front view beats a straight-on view, which loses depth. Even light, no hard shadows.
- Sketches: clean up first with `generate_image` (`referenceImageJobId` = the uploaded sketch). Prompt: "clean 3D render of this exact character as a solid figurine, front three-quarter view, plain white background, flat base, chunky proportions". Then image-to-3D on the generated image's `jobId`, or on its `imageUrl`.
- Inline base64 images must be under ~3 MB. Use `url` or REST for bigger files (20 MB limit).

## Run it

1. `get_credit_balance`. State the cost and the balance after ("Text-to-3D, untextured: 15 credits. 880 now, 865 after. OK?"), unless the manager already approved the run budget.
2. Call the tool and save the `jobId` into `brief.json.jobs` straight away.
3. Poll with `get_job { jobId, wait: 30 }` until `done`. Give the user a short progress line now and then (stage names come from `fragments`).
4. Download `outputs.glbUrl` to `sloyd/model.glb`, and save the `get_job` result as `sloyd/job.json`.
5. Hand over to `print-prep` with the size, tech and printer from the brief.

Without MCP, the REST fallback does all of this in one command:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/sloyd-api/scripts/sloyd.py text-to-3d --prompt "$PROMPT" --texture none \
  --yes --wait --out print-jobs/<slug>/sloyd/model.glb --meta print-jobs/<slug>/sloyd/job.json
```

### Sloyd's concept image (free, and worth showing)

Text-to-3D first renders a 2D concept, then builds the mesh from it. That image is public at `https://storage.googleapis.com/ai-services-quality/jobs/<jobId>.input.webp`. Save it as `sloyd/concept.png`. It shows the intended colours, which is useful when the GLB's texture is grayscale (seen on a real run). It's also the best identity reference for reel-maker: `upload_image { file: { url } }`.

## Variations

When the user wants options, start up to 3 at once (never more than 5 jobs in flight, the per-key limit). Each costs the full price, so quote the total first. Run print-prep with `--preview` on each and let the user pick.

## Errors

- **402**: stop. Tell the user what they have and what's required (from the error) and link https://api-dashboard.sloyd.ai. Nothing was charged.
- **429**: you have 5 jobs running. Wait on the oldest with `get_job`, then retry. `sloyd.py` backs off automatically.
- **Job `error`**: credits are refunded. Retry once with a simpler prompt (fewer subjects, remove accessories), then report back.
- A timeout while polling isn't a failure. Resume with `get_job` on the same `jobId`.

## Retexture

To change only the colours or paint: `retexture_model { jobId, prompt }` (15 credits) on the existing model job. It's cheaper than regenerating and keeps the geometry the user approved.
