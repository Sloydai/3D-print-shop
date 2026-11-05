---
name: print-designer
description: Interviews the maker about a 3D print and writes a printable generation prompt plus brief.json, before any 3D model is made. Use at the start of every print job, or when someone says "I want to print...", "design a printable...", "what size should it be", "will this print without supports", or when a generated model came back with thin parts, floating bits or no flat base and needs a better prompt. Covers purpose, size in mm, FDM vs resin, printer, colours and how much support the user will put up with.
---

# Print Designer

Your job is to make the model printable before it exists. AI 3D generators make display assets: thin antennae, floating sparkles, round bottoms, hair strands. A good prompt plus the right settings prevents most print failures. print-prep can only repair what it's given.

## 1. Ask (one short message, defaults shown)

Ask only what you can't infer. Offer defaults so the user can just say "ok".

1. **What is it for?** Display, toy (gets dropped, needs to be sturdy), functional part, gift, or tabletop mini. This sets wall thickness and detail level.
2. **Size**: height or longest side in **mm**. Default 80 mm for figurines and 32 mm for tabletop minis. Quote it in a real-world unit too ("about the height of a coffee mug").
3. **Printer and tech.** FDM (Bambu Lab A1/P1S/X1C/H2D, Prusa MK4S/CORE One/MINI, Elegoo Centauri Carbon/Neptune) or resin (Elegoo Saturn/Mars). Resin allows ~0.4 mm details. FDM needs ~0.8 mm or more.
4. **Colours**: one filament, or multi-colour with an AMS/MMU (how many slots).
5. **Supports**: none (must print support-free), some are OK, or anything goes.
6. **Source**: text only, or a photo/sketch. With a photo, hand over to `modeler` (image-to-3D) or `gift-maker` for pets and people.

## 2. Translate the answers into rules

| Need | Prompt language | Sloyd settings |
|---|---|---|
| Stands on its own | "standing on a flat round base" or "sitting with a flat bottom", "wide stable stance" | |
| No floating bits | "single solid connected piece, every part attached to the body, no separate floating elements, no particles" | |
| Thick parts (FDM) | "chunky proportions, thick limbs, thick tail attached to the body, simplified details, no thin protrusions" | |
| Few or no supports | "arms close to the body, compact pose, no overhanging wings or outstretched limbs, chin tucked" | |
| Resin miniature | "highly detailed miniature, crisp sculpted details", and keep "attached, no floating parts" | `targetFaceCount` 150000-300000 |
| Toy / sturdy | "rounded, durable, no sharp spikes, chibi proportions" | |
| Single filament | leave colour words out | `textureResolution: none` (saves 10 credits) |
| Multi-colour AMS | "distinct colour regions, 3-4 flat solid colours, clear colour boundaries" | `genStyleId: Color3DPrint` (Sloyd's multi-material figurine style), textured |
| Functional part | prefer CAD (OpenSCAD/Fusion). AI meshes aren't dimensionally exact. Say so. | |

Never ask the generator for text, letters or numbers. They come out as noise. Name plaques get their lettering locally (`print_prep.py --label`).

Remove print-hostile words: "hair strands", "fur", "sparkles", "smoke", "floating", "transparent", "glowing", "wings spread", "on a stick", "chains".

## 3. Write the prompt

Pattern (under ~600 characters):

```
<subject, pose>, <style>, <print rules from the table>, studio product shot of a 3D printable figurine, neutral grey
```

Example: the user asks for a "dragon for my desk, Bambu A1, single colour, hates supports".
> A small friendly dragon sitting upright with its wings folded tight against its back and its tail curled around its feet, chunky cartoon proportions, thick horns, single solid connected piece, no thin protrusions, no floating parts, sitting on a flat oval base, 3D printable figurine

Settings: `textureResolution: none`, `topology: triangles`, `genStyleId: Cartoon`, 15 credits. Size 90 mm on a `bambu-a1`, `fdm`.

## 4. Write `brief.json`

Write `print-jobs/<slug>/brief.json` with the fields defined in `print-shop-manager` (`size_mm`, `tech`, `printer`, `colors`, `supports`, `source`, `prompt`, `style`, `texture`). Show the user the prompt and the planned cost in one line, then hand over to `modeler`.

## 5. When a model comes back bad

Read `print_ready/report.md`. Rewrite the prompt for the failing rule and regenerate once, with approval:

- `thin_walls`: add "thicker, chunkier, simplified", drop the thin feature by name ("no antennae"), or raise the size.
- `support_islands` / big `overhangs`: "arms down, wings folded, compact pose".
- `tip_over`: "wide base, low centre of gravity, sitting".
- Floating debris was removed: add "single connected piece".

Rules of thumb are in `references/printability.md`.
