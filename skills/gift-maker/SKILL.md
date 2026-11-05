---
name: gift-maker
description: Makes personalised 3D-printed gifts with Sloyd - a pet figurine from a photo, a name plaque or desk sign with a figure and a raised name, a custom toy from a kid's drawing, a mini-me from a description, or an occasion keepsake (birthday, wedding, retirement). Use when someone says "gift", "present", "for my mum/dad/kid/partner", "figurine of my dog/cat", "from this photo of my pet", "with their name on it", "turn my kid's drawing into a toy", or names an occasion. Ends with a print-ready STL/3MF.
---

# Gift Maker

Gifts fail in three ways: it doesn't look like *their* pet, the name is illegible, or it breaks in the gift box. Each preset below handles one of those.

## Presets

### 1. Pet figurine from a photo (most popular)

1. **Photo check.** One pet, whole body, side or 3/4 view, good light, plain background if possible. Ask for a better photo if the pet is cropped, blurred or behind bars. Save it to `print-jobs/<slug>/input/`.
2. **Ask** for the pet's name (for a plaque), its size in mm (default 80 mm tall), the printer, single or multi-colour, and the pose: sitting is the default, because it prints best.
3. **Upload** with `upload_image` (free) and keep the `jobId`.
4. **Concept image** (10 credits, strongly recommended). `generate_image` with `referenceImageJobId` = the upload:
   > This exact <breed/colour> <dog/cat> as a cute 3D printable figurine, sitting upright with paws together, tail wrapped around the body, chunky stylised proportions, same markings and face, single solid piece on a flat oval base, plain white background, studio light, front three-quarter view

   Pick `genStyleId`: `Cartoon` (cute), `Realistic` (lifelike), `ClayMorphic` (soft), or `Color3DPrint` (multi-colour AMS). Show the image and get a yes before spending on 3D.
5. **3D.** `generate_3d_from_image` with `imageJobId` = the concept image's `jobId` (or `file: {url: imageUrl}`). Use `textureResolution: "none"` for one colour (10 credits) or textured for multi-colour (20).
6. **Prep with the name**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/print-prep/scripts/print_prep.py print-jobs/<slug>/sloyd/model.glb \
     --height 80 --label "BISCUIT" --printer bambu-a1 --out-dir print-jobs/<slug>/print_ready --name <slug> --preview
   ```
   `--label` builds a rounded plinth with raised 1 mm letters in front of the pet, as a separate 3MF part. Print the letters in a second colour, either via AMS or with a colour change at the layer where the letters start (Bambu Studio: right-click the layer slider, "Add color change").
7. Multi-colour: hand over to `multi-color-splitter`.

### 2. Name plaque / desk sign

The lettering is always made locally, never by the generator, because AI 3D models can't spell. The figure comes from Sloyd, and the plaque and text come from print_prep.

1. Ask for the name, at most ~12 characters (it's capitalised), the theme figure ("a little rocket", "a cat sleeping"), the width in mm (default 100) and the colours.
2. Prompt for a **small, low figure** that sits at the back: "<theme> lying down, compact, flat bottom, single solid piece, chunky". Use text-to-3D (15 credits untextured).
3. Run `print_prep.py ... --width 100 --label "NAME" --plinth-height 4`. Long names widen the plinth automatically. Letters are 5-10 mm tall, depending on width.

### 3. Toy from a kid's drawing

1. `upload_image` the drawing. Then `generate_image` with a reference: "turn this child's drawing into a friendly 3D toy character, keep its shapes, colours and silly features, chunky rounded, thick limbs attached to the body, no thin parts, standing on a flat base, plain white background". Use `genStyleId: Cartoon`.
2. Show it to the user (and the kid). Then image-to-3D.
3. Toy rules for print-prep: no part thinner than 2 mm, so `--nozzle 0.4` and treat any `thin_walls` warning as blocking. Size at least 70 mm. Recommend PLA+ or PETG with 4 walls and 20% infill. Not for children under 3, because small parts can break off. Say this.

### 4. Mini-me / custom figure (text)

Run print-designer's interview, adding gift details: hobby props held close to the body (a guitar against the chest, not on a strap), a T-shirt colour, hair as a solid mass ("short solid hair, no strands").

## Credits per gift (typical)

| Preset | Steps | Credits |
|---|---|---|
| Pet, one colour | upload 0 + concept 10 + image-to-3D 10 | **20** (~$0.27) |
| Pet, AMS colours | upload 0 + concept 10 + image-to-3D textured 20 + split 40 | **70** |
| Name plaque | text-to-3D 15 | **15** |
| Toy from a drawing | upload 0 + concept 10 + image-to-3D 10-20 | **20-30** |

Always call `get_credit_balance` and quote first. Handle 402 and 429 as in `${CLAUDE_PLUGIN_ROOT}/skills/sloyd-api/references/api.md`.

## Hand over

The STL/3MF, the preview, the slicer steps, and a gift note: "Print at 0.12 mm layers for faces. Sand the base lightly. A drop of CA glue fixes a snapped ear." If they want to show it off, offer `reel-maker`.
