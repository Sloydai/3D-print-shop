---
name: multi-color-splitter
description: Splits a Sloyd 3D model into separate parts with split_model_into_parts and turns them into per-part STLs plus a multi-part 3MF for multi-colour printing on a Bambu AMS / AMS lite, Prusa MMU3, Elegoo CANVAS or any multi-material printer, or into flat-laid pieces with pins to print big models in sections. Use when someone asks for "multi-colour", "AMS", "MMU", "print in 4 colours", "separate the parts", "split it into pieces", "too big for my printer", or "print it in sections and glue".
---

# Multi-Color Splitter

There are two jobs, and both start with Sloyd's `split_model_into_parts` on a finished model `jobId`:

1. **Colour split**: one part per filament, loaded as one object with parts in its assembled position. The user assigns an AMS slot per part.
2. **Size split**: pieces that each fit the printer, with pins and holes, laid flat to print, then glued.

## Choose the Sloyd settings

| Goal | `method` | `numberOfParts` | `attachmentPoints` | Why |
|---|---|---|---|---|
| AMS colour split (figurine) | `partition` | number of colour regions, 4-8 | `false` | partition keeps textures (so each part's colour can be read) and caps every cut flat, so parts butt together cleanly |
| Big model in sections | `partition` | enough that each piece fits (see the `too_big` warning) | `true` | adds a round pin on one side and a hole on the other at each joint, for alignment when gluing |
| Layered parts (head under hair, body under clothes) | `decomposition` | auto | n/a | rebuilds hidden surfaces. Parts overlap and have no texture. Good for painting, not for AMS colour |

Cost: **40 credits** per split. A partition split takes about 4 minutes, a decomposition about 2.5. A `partition` split needs a source GLB of 16 MB or less. Splits that can't be done fail and are refunded.

`numberOfParts` must be 4-16, and the result can be 2 more or fewer. For a 2-3 colour print, ask for 4 and let print_prep merge parts that share a colour into the same slot (`--slots`).

If the model wasn't made with Sloyd (the user's own STL/GLB), upload it first with REST `upload-3d` (free; `sloyd.py upload-3d --model file.stl`) and split the returned `jobId`.

## Run

1. Read `brief.json` for the model `jobId`, size, printer and colours. Use `get_credit_balance`, then quote "Split into ~6 parts: 40 credits".
2. Call `split_model_into_parts { jobId, method: "partition", numberOfParts: 6, attachmentPoints: false }`, or the REST fallback:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/sloyd-api/scripts/sloyd.py split --job <modelJobId> --method partition --parts 6 \
     --yes --wait --out print-jobs/<slug>/sloyd/parts.glb
   ```
3. Poll `get_job { wait: 30 }`. The returned `jobId` is the **new split model**. Download `outputs.glbUrl` to `sloyd/parts.glb`.
4. Make the per-part print files with print-prep, using the **same size** as the single-piece version:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/print-prep/scripts/print_prep.py print-jobs/<slug>/sloyd/parts.glb \
     --parts --slots 4 --height 80 --printer bambu-x1c --out-dir print-jobs/<slug>/print_ready --name <slug> --preview
   ```
   Add `--explode` for size splits. It writes `print_flat/` and `<slug>_print_flat.3mf`, with each piece rotated onto its largest flat face (the cut cap) and packed on one plate.
   **Check the colours first.** If the report shows `no_texture_colour` (the GLB's texture is a grayscale AO map, as seen on a real `Color3DPrint` job), re-run with filaments by part name, taken from Sloyd's concept image (`https://storage.googleapis.com/ai-services-quality/jobs/<modelJobId>.input.webp`), e.g. `--colors "Foot_*=orange,Beak=orange,*=brown"`. Sloyd names the parts by anatomy (`Head`, `Body`, `Wing_Left`, `Foot_Right`...), so name globs work.
5. Read the **Parts** table in `report.md`. Each part has its measured colour (from the texture), the nearest common filament and an AMS slot. Parts with the same filament share a slot. With more colours than `--slots`, the closest colours are merged, and the report says which.

## Hand over

- `print_ready/<slug>.3mf`: one object made of components, with `displaycolor` per part, in mm. Bambu Studio/OrcaSlicer and PrusaSlicer load it as a multi-part object in place. Assign each part's filament from the slot table (`print-prep/references/slicer-handoff.md`, step 5).
- `print_ready/parts/*.stl`: one STL per part, all in the same coordinate frame. Load them all at once and answer **Yes** to "single object with multiple parts".
- Colour-print notes:
  - A prime tower is needed and adds filament. Purge waste grows with the number of colour changes per layer. Parts that change colour across many layers (like eyes) cost the most purge.
  - Fewer colours means less waste. 3-4 is the sweet spot on a 4-slot AMS.
- Size-split notes: glue with CA (super glue) for PLA. Print pins vertical for strength. If a pin is too tight, sand it or scale the pin part to 98% in the slicer.

## Limits

- `partition` follows the model's natural parts (head, limbs, body), not paint boundaries. A part whose texture mixes colours gets its average colour. For fine colour detail (pupils, stripes), use the slicer's colour paint tool on that part.
- For figurines planned as multi-colour from the start, ask print-designer for `genStyleId: Color3DPrint` (flat, hard-edged colour regions), so the parts line up with the colours.
