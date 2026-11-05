---
name: sloyd-api
description: Use first, before any other 3D Print Shop skill calls Sloyd, and whenever the user needs to connect Sloyd, set or fix SLOYD_CLIENT_ID / SLOYD_CLIENT_SECRET, check their credit balance, estimate what a generation will cost, poll a jobId, download a GLB or image, or recover from a 401, 402 (insufficient credits) or 429 (5 concurrent jobs) error. Also use when the agent has no MCP support and must call Sloyd over plain HTTP.
---

# Sloyd API: connection, credits and the job loop

Every role in the 3D Print Shop (print-designer, modeler, multi-color-splitter, gift-maker, reel-maker) spends real credits through this API. This skill is the shared contract. The full tool, field and price reference is `references/api.md`. Never invent a tool or a parameter that isn't listed there or returned by the MCP server's `tools/list`.

## 1. Credentials: every user brings their own

1. Sign in at https://api-dashboard.sloyd.ai, open **API Keys** and click **Generate Key**.
2. Copy the client secret straight away. It's shown once.
3. Buy credits under **Usage & Billing** (minimum $12 = 900 credits). A key with 0 credits authenticates, but every paid call returns 402.
4. Export the pair in the shell that starts the agent, or put it in a git-ignored `.env` (see `.env.example`):

```bash
export SLOYD_CLIENT_ID="sok_live_..."
export SLOYD_CLIENT_SECRET="..."
```

Rules for the agent:
- Read credentials only from those two variables. Never ask the user to paste the secret into chat, and never write it into a tracked file, a brief, a log or a commit.
- If either variable is missing, stop and give the user the steps above.
- To check without printing anything secret: `[ -n "$SLOYD_CLIENT_ID" ] && echo set`.

## 2. Connect

The plugin's `.mcp.json` registers Sloyd's hosted MCP server, `https://api.sloyd.ai/api/mcp`, with the two variables as `x-client-id` / `x-client-secret` headers. To add it by hand in Claude Code:

```bash
claude mcp add --transport http sloyd https://api.sloyd.ai/api/mcp \
  --header "x-client-id: $SLOYD_CLIENT_ID" \
  --header "x-client-secret: $SLOYD_CLIENT_SECRET"
```

No MCP? Use the standard-library client in `scripts/sloyd.py` (`--via rest` for plain HTTP):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/sloyd.py balance
```

## 3. Price before you spend

Call `get_credit_balance` (free), then tell the user the cost and what's left, and wait for a yes unless they already approved a budget for the run. `sloyd.py` does this for you: every paid command is a dry run (exit code 2) until you add `--yes`.

| Step | Credits |
|---|---|
| Text-to-3D, untextured / textured | 15 / 25 |
| Image-to-3D, untextured / textured | 10 / 20 |
| Multi-image-to-3D | up to 40 |
| Split into parts | 40 |
| Retexture | 15 |
| Text-to-image / image edit | 10 / 15 |
| Upload image or model, balance, job status | 0 |

## 4. Run a job

1. The generation tool returns `{ jobId }` straight away. Save it in the job's `brief.json`.
2. Call `get_job { jobId, wait: 30 }` until `done: true`. 3D jobs take 1-4 minutes, a `partition` split about 4.
3. Download `outputs.glbUrl` (3D) or `outputs.imageUrl` (images, delivered as WebP).
4. At most 5 jobs in flight per key.

## 5. Errors

| Status | Meaning | Do |
|---|---|---|
| 401 | key missing, wrong or revoked | check the env vars |
| 402 | not enough credits; nothing was charged | stop, show `available` / `required`, send the user to the dashboard |
| 422 | invalid field | fix the field, don't retry blindly |
| 429 | 5 jobs already running | wait for one to finish, then retry (`sloyd.py` backs off on its own) |
| job `error` | generation failed; credits refunded | retry once with a simpler prompt, then report |

## 6. Not available in the public API

Video generation, animation, auto-rig and spritesheets. reel-maker marks its animation step `PENDING: Sloyd video API` and never uses another provider.
