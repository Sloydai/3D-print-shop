# Sloyd API: what the 3D Print Shop team uses

This summarises the Sloyd API docs (`Sloydai/Horizon` `api-dashboard/documentation/`, checked 2026-11-04) and the live `tools/list` of the hosted MCP server. If a tool or field isn't listed here, it doesn't exist. Don't guess.

## Connect

The plugin's `.mcp.json` registers the hosted server, reading the keys from the environment:

```bash
export SLOYD_CLIENT_ID=sok_live_...
export SLOYD_CLIENT_SECRET=...        # shown once in https://api-dashboard.sloyd.ai -> API Keys
```

To add the server by hand in Claude Code:

```bash
claude mcp add --transport http sloyd https://api.sloyd.ai/api/mcp \
  --header "x-client-id: $SLOYD_CLIENT_ID" \
  --header "x-client-secret: $SLOYD_CLIENT_SECRET"
```

Never write the secret into a file, a commit, a log line or a chat message.

## The 14 MCP tools

| Tool | Use in this team | Key arguments | Credits |
|---|---|---|---|
| `get_credit_balance` | before every paid step | none | 0 |
| `get_generation_styles` | pick a `genStyleId` | none | 0 |
| `generate_3d_from_text` | modeler | `prompt` (max 4096 chars), `textureResolution` (`128`..`4k`, `auto`, `none`), `topology` (`auto`/`quads`/`triangles`), `targetFaceCount` (0 = auto, max 500000), `genStyleId`, `tPose` | 25 textured / 15 with `none` (+5 quads, +10 if faces >= 500K) |
| `generate_3d_from_image` | modeler, gift-maker | `file` {`url`} or {`base64`,`mimeType`}, or `imageJobId`; same texture/topology/face options | 20 textured / 10 with `none` |
| `generate_3d_from_images` | modeler (several views) | `frontImage` + at least one of `leftImage`/`backImage`/`rightImage`; `EnablePBR` "true"/"false" (string); `FaceCount` (string) | up to 40 with PBR / 30 without (the pricing page lists 40 for multi-image with quads, and the endpoint picks the polygon type itself, so quote the upper bound) |
| `upload_image` | stage a photo/sketch/render | `file` | 0 |
| `generate_image` | gift concept art, reel stills | `prompt`, `aspectRatio` (`1:1`,`4:3`,`3:4`,`3:2`,`2:3`,`16:9`,`9:16`), `genStyleId`, `referenceImageJobId` (an `upload_image` job = identity reference), `tPose` | 10 |
| `edit_image` | reel stills, photo clean-up | `jobId` (source image job), `prompt`, `genStyleId` | 15 |
| `retexture_model` | new paint job for a model | `jobId`, `prompt`, `textureResolution` | 15 |
| `split_model_into_parts` | multi-color-splitter | `jobId`, `method` `partition` (default, keeps textures, flat-capped cuts, best for printing) or `decomposition`; `numberOfParts` 4-16 (partition); `attachmentPoints` bool (partition: pin + hole at each joint) | 40 |
| `get_job` | poll | `jobId`, `wait` 0-30 | 0 |
| `generate_skybox`, `generate_skybox_from_image`, `edit_skybox` | not used by this team | | 25 |

Prices come from https://www.sloyd.ai/api/pricing ($1 = 75 credits, minimum purchase $12 = 900 credits). 3D creation costs 10 base, +5 for text input, +10 for multiple images, +10 for texturing, +5 for quads, +10 at 500K faces or more. A REST call that would fail with 402 confirmed `text-to-3d` with `textureResolution: none` costs 15.

## The job loop

1. The generation tool returns `{ jobId }` straight away.
2. Call `get_job { jobId, wait: 30 }` again and again until `done: true`. A 3D job usually takes 1-4 minutes, and a `partition` split takes about 4.
3. Read `outputs.glbUrl` for 3D jobs or `outputs.imageUrl` for images, and download the file. 3D results are also public at `https://storage.googleapis.com/ai-services-quality/jobs/{jobId}.glb`.
4. `status: error` means the job failed. Its credits are refunded automatically. Report `errorMessage` and retry once with a simpler prompt.

Keep every `jobId` in the job folder's `brief.json`. There is no list endpoint.

## Spend rules (all skills)

- Call `get_credit_balance` first, then tell the user what the step costs and what will be left, e.g. "Text-to-3D, textured: 25 credits (~$0.33). You have 880, so 855 will be left. Go?" Wait for a yes unless the user already approved a budget for this run.
- **402** means not enough credits. The body has `available` and `required`, and nothing was charged. Stop and tell the user to top up at https://api-dashboard.sloyd.ai, then retry the same call.
- **429** means 5 jobs are already pending or running on this key. Wait for one of your jobs to finish (`get_job`), then retry. Never have more than 5 jobs in flight. Run variations in batches of at most 5.
- **401**: the key is wrong or revoked. Check the env vars. **422**: an invalid field. Fix it, don't retry blindly.

## REST fallback (no MCP in the client)

`skills/sloyd-api/scripts/sloyd.py` uses only the standard library. It has the same commands over MCP (`--via mcp`, the default) or plain REST (`--via rest`). Every paid command is a dry run that prints cost and balance and exits with code 2, until you add `--yes`.

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/sloyd-api/scripts/sloyd.py
python3 $S balance
python3 $S text-to-3d --prompt "..." --texture none                       # dry run: prints cost
python3 $S text-to-3d --prompt "..." --texture none --yes --wait --out job/sloyd/model.glb --meta job/sloyd/job.json
python3 $S image-to-3d --image photo.jpg --yes --wait --out job/sloyd/model.glb
python3 $S split --job <jobId> --parts 6 --yes --wait --out job/sloyd/parts.glb
python3 $S upload-image --image render.png                                 # free, prints jobId
python3 $S text-to-image --prompt "..." --aspect 9:16 --ref-job <uploadJobId> --yes --wait --out still.png
python3 $S job <jobId> --wait --out model.glb                               # resume a job
```

Exit codes: 0 ok, 2 dry run (needs approval), 3 not enough credits, 4 job failed, 5 still rate-limited after retries. The script waits out 429s by itself, with backoff.

REST endpoints, for reference: `POST /jobs/text-to-3d` (JSON), `POST /jobs/image-to-3d` and `/jobs/multi-image-to-3d` and `/jobs/image-upload` (multipart), `POST /jobs/text-to-image`, `/jobs/image-edit`, `/jobs/retexture`, `/jobs/split-to-parts` (JSON), `POST /jobs/upload-3d` (multipart, free, for models the user already has: GLB/OBJ/FBX/STL/PLY/BLEND/USD, up to 500 MB; REST only), `GET /jobs/{jobId}`, `GET /user/api-access/balance`. Base URL `https://api.sloyd.ai/api`, headers `x-client-id`, `x-client-secret`.

## What Sloyd's public API does not have (yet)

- **Video.** There is no text-to-video or image-to-video tool in the public API. reel-maker produces the stills, shot list and prompts, and marks every animation step `PENDING: Sloyd video API`. Don't call any other video provider.
- Animation, auto-rig and spritesheets are documented as "coming soon" and are not enabled for public keys. Don't use them.
