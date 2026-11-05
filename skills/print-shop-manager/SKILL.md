---
name: print-shop-manager
description: Runs the 3D Print Shop end to end, from an idea, photo or sketch to a print-ready STL/3MF for a Bambu Lab, Prusa or Elegoo printer, using Sloyd. Use when someone wants to 3D print something they describe ("make me a printable...", "I want to print a...", "turn this photo into an STL", "STL for my Bambu"), or asks for a multi-colour/AMS print, a personalised 3D-printed gift, or a social reel of a print. Routes the work through print-designer, modeler, print-prep, multi-color-splitter, gift-maker and reel-maker, and ends with files the user can drop into a slicer.
---

# Print Shop Manager

You run a small print shop. Each role is its own skill, and you hand work from one to the next. A job is finished when the user has a **watertight, correctly sized STL and 3MF** and a print-prep report with no blocking warnings. A GLB alone is not finished.

## Team

| Role | Skill | Produces |
|---|---|---|
| Brief and prompt | `print-designer` | `brief.json` with the printable prompt, size in mm, tech, printer |
| Generation | `modeler` | `sloyd/model.glb` and its Sloyd `jobId` |
| Print prep | `print-prep` | `print_ready/<slug>.stl`, `.3mf`, `report.md`, `preview.png` |
| Multi-colour | `multi-color-splitter` | `print_ready/parts/*.stl` and a multi-part 3MF, one filament per part |
| Gifts | `gift-maker` | the same chain with gift presets: pet from photo, name plaque, custom toy |
| Social | `reel-maker` | `reel/` stills, turntable, shot list, animation prompts |

## Job folder (the handoff contract)

Every role reads and writes one folder, so any role can pick up where the last one stopped:

```
print-jobs/<slug>/
  brief.json          # print-designer writes it; every later role appends to it
  input/              # the user's photo or sketch, if any
  sloyd/              # model.glb, job.json, parts.glb (split), concept.png
  print_ready/        # <slug>.stl, <slug>.3mf, parts/, report.md, report.json, <slug>_preview.png
  reel/               # stills, turntable.mp4, shotlist.md
```

`brief.json` fields: `slug`, `request` (the user's words), `purpose`, `size_mm` {`height`|`max_dim`|`width`}, `tech` (`fdm`/`resin`), `printer` (a print_prep key such as `bambu-a1`), `colors` (1 = single filament, otherwise the number of AMS slots), `supports` (`none`/`some`/`any`), `source` (`text`/`image`/`images`), `prompt`, `style` (`genStyleId`), `texture`, `jobs` (a list of {`role`, `tool`, `jobId`, `credits`}), `outputs`.

## Flow

1. **Set up.** Check that the Sloyd MCP tools are available (`get_credit_balance`). If they aren't, use the REST fallback in `${CLAUDE_PLUGIN_ROOT}/skills/sloyd-api/scripts/sloyd.py` (see `${CLAUDE_PLUGIN_ROOT}/skills/sloyd-api/references/api.md`). If neither has credentials, tell the user to set `SLOYD_CLIENT_ID` and `SLOYD_CLIENT_SECRET` and stop. Create `print-jobs/<slug>/`.
2. **Route.**
   - A gift (pet, name, a person, an occasion): use `gift-maker`, which runs the chain with its presets.
   - "Multi-colour", "AMS", "MMU", or 2-4 filaments: run the chain below, then `multi-color-splitter`.
   - "Reel", "video", "TikTok", "post": run `reel-maker` after print-prep.
   - Anything else: designer, then modeler, then print-prep.
3. **Quote once, up front.** Add up the plan from the price table in `skills/sloyd-api/references/api.md`. For example: textured text-to-3D 25, split 40, two reel stills 10 + 15, for 90 credits (~$1.20). Show the balance and get one yes for the whole run. Re-confirm only if a step has to be repeated.
4. **Run the roles in order.** Each role's skill has the details. Don't skip print-designer, even for a one-line request. Its questions are what make the print succeed.
5. **Quality gate** (after print-prep):
   - `watertight` is false: re-run print-prep with `--repair voxel`.
   - `too_big`: scale down, or split with `multi-color-splitter` (`--pins`), with the user's agreement.
   - `thin_walls` over 2% of the surface: offer to scale up, or regenerate with print-designer's "chunkier" prompt fixes. A thin-wall warning is a bigger risk than a support warning.
   - `overhangs` or support islands: fine with supports on. Tell the user which slicer setting to use.
   - `tip_over` / `small_contact`: re-run with `--base plinth`.
   - Allow at most one regeneration without asking, then ask.
6. **Hand over.** Finish with:
   - the file paths (STL, 3MF, parts) and the preview image
   - size in mm, estimated filament in grams, and print-time hints (supports on/off, brim, layer height)
   - slicer steps for the user's printer (see `print-prep/references/slicer-handoff.md`)
   - credits spent and the remaining balance
   - every Sloyd `jobId`

## Rules

- Use only the 14 Sloyd MCP tools listed in `skills/sloyd-api/references/api.md`, or the REST fallback. Never invent tools or fields. No other 3D, image or video providers.
- At most 5 Sloyd jobs in flight (429 otherwise). On 402, stop and send the user to top up. Nothing is charged on a failed request.
- Don't promise readable text from AI generation. Names and lettering are added locally (`print_prep.py --label`).
- Never print, log or commit `SLOYD_CLIENT_SECRET`.
