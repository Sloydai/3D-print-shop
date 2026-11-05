#!/usr/bin/env python3
"""Sloyd API client for the 3D Print Shop skills (fallback when the MCP tools are not loaded).

Standard library only. Two transports with the same commands and the same output:

  --via mcp   (default) calls the hosted MCP server, https://api.sloyd.ai/api/mcp, with tools/call
  --via rest  calls the REST API, https://api.sloyd.ai/api, directly

Credentials come from the environment, never from arguments or files:
  SLOYD_CLIENT_ID, SLOYD_CLIENT_SECRET

Every paid command is a dry run unless you pass --yes. The dry run prints the
credit cost and your balance so the user can approve the spend first.

Examples
  sloyd.py balance
  sloyd.py text-to-3d --prompt "a chunky owl figurine on a flat round base"          # dry run
  sloyd.py text-to-3d --prompt "..." --texture none --yes --wait --out owl.glb
  sloyd.py image-to-3d --image pet.jpg --yes --wait --out pet.glb
  sloyd.py split --job <jobId> --method partition --parts 4 --yes --wait --out parts.glb
  sloyd.py text-to-image --prompt "..." --aspect 9:16 --ref-job <uploadJobId> --yes --wait --out still.png
  sloyd.py job <jobId> --wait --out model.glb

Exit codes: 0 ok, 1 usage or API error, 2 needs approval (dry run), 3 not enough credits (402),
4 job failed, 5 rate limited after retries (429).
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

REST_BASE = os.environ.get("SLOYD_API_BASE", "https://api.sloyd.ai/api")
MCP_URL = os.environ.get("SLOYD_MCP_URL", "https://api.sloyd.ai/api/mcp")
GLB_PUBLIC = "https://storage.googleapis.com/ai-services-quality/jobs/{job_id}.glb"
USER_AGENT = "sloyd-3d-print-shop/0.1.0"

# Credit prices from https://www.sloyd.ai/api/pricing (checked 2026-11-04).
# 3D creation = 10 base + 5 text input + 10 multiple images + 10 texturing + 5 quads + 10 for >= 500K faces.
FLAT_PRICES = {
    "retexture": 15,
    "split": 40,
    "text-to-image": 10,
    "image-edit": 15,
    "skybox": 25,
    "upload-image": 0,
    "upload-3d": 0,
}

GEN_STYLES = [  # Sloyd docs: endpoints/gen-styles.md. Live list: `sloyd.py styles`.
    "Auto", "Realistic", "Roblox", "Cartoon", "ClayMorphic", "Color3DPrint", "DetailedAnime",
    "HandpaintedStylized", "IsometricDiorama", "Polygonal", "StylizedAnime", "CozyMobile",
    "RetroCRT90s", "CelShadedComic", "Sketch", "PainterlyComic",
]

MAX_429_RETRIES = 10


class SloydError(Exception):
    def __init__(self, message: str, status: int | None = None, body: dict | None = None):
        super().__init__(message)
        self.status = status
        self.body = body or {}


def creation_cost(*, text: bool, multi: bool, textured: bool, quads: bool, faces: int) -> int:
    cost = 10
    cost += 5 if text else 0
    cost += 10 if multi else 0
    cost += 10 if textured else 0
    cost += 5 if quads else 0
    cost += 10 if faces >= 500_000 else 0
    return cost


def creds() -> tuple[str, str]:
    cid, secret = os.environ.get("SLOYD_CLIENT_ID"), os.environ.get("SLOYD_CLIENT_SECRET")
    if not cid or not secret:
        raise SloydError(
            "SLOYD_CLIENT_ID and SLOYD_CLIENT_SECRET must be set. Create a key at "
            "https://api-dashboard.sloyd.ai (API Keys) and export both variables."
        )
    return cid, secret


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- HTTP


def _http(method: str, url: str, *, headers: dict | None = None, data: bytes | None = None,
          timeout: int = 120) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def _auth_headers() -> dict:
    cid, secret = creds()
    return {"x-client-id": cid, "x-client-secret": secret}


def _parse_json(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {"raw": raw[:500].decode("utf-8", "replace")}


def _raise_for(status: int, body: dict) -> None:
    msg = body.get("message") or body.get("error") or str(body)
    if status == 402:
        raise SloydError(
            f"402 Payment Required: {msg}. Available {body.get('available', '?')} credits, "
            f"required {body.get('required', '?')}. Top up at https://api-dashboard.sloyd.ai and retry; "
            "nothing was charged.", 402, body)
    if status == 429:
        raise SloydError(f"429 Too Many Requests: {msg} (limit: 5 concurrent jobs per key).", 429, body)
    if status == 401:
        raise SloydError(f"401 Unauthorized: {msg}. Check SLOYD_CLIENT_ID / SLOYD_CLIENT_SECRET.", 401, body)
    raise SloydError(f"HTTP {status}: {msg}", status, body)


# --------------------------------------------------------------------------- transports


class Rest:
    name = "rest"

    def _call(self, method: str, path: str, *, json_body: dict | None = None,
              form: dict | None = None, files: dict | None = None) -> dict:
        headers = _auth_headers()
        data = None
        if files is not None or form is not None:
            boundary = uuid.uuid4().hex
            parts: list[bytes] = []
            for k, v in (form or {}).items():
                if v is None:
                    continue
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
            for k, (fname, content, ctype) in (files or {}).items():
                parts.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fname}\"\r\n"
                    f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n")
            parts.append(f"--{boundary}--\r\n".encode())
            data = b"".join(parts)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        status, _, raw = _http(method, REST_BASE + path, headers=headers, data=data, timeout=600)
        body = _parse_json(raw)
        if status >= 400:
            _raise_for(status, body)
        return body

    def balance(self) -> int:
        return int(self._call("GET", "/user/api-access/balance").get("balance", 0))

    def styles(self) -> list:
        return [{"id": s} for s in GEN_STYLES]

    def start(self, op: str, args: dict, images: dict) -> str:
        """images: field -> local path or https URL."""
        if op == "text-to-3d":
            return self._call("POST", "/jobs/text-to-3d", json_body=args)["jobId"]
        if op == "text-to-image":
            return self._call("POST", "/jobs/text-to-image", json_body=args)["jobId"]
        if op == "image-edit":
            return self._call("POST", "/jobs/image-edit", json_body=args)["jobId"]
        if op == "retexture":
            return self._call("POST", "/jobs/retexture", json_body=args)["jobId"]
        if op == "split":
            return self._call("POST", "/jobs/split-to-parts", json_body=args)["jobId"]
        path = {"image-to-3d": "/jobs/image-to-3d", "multi-image-to-3d": "/jobs/multi-image-to-3d",
                "upload-image": "/jobs/image-upload", "upload-3d": "/jobs/upload-3d"}[op]
        files = {k: _read_file_or_url(v) for k, v in images.items()}
        form = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in args.items() if v is not None}
        return self._call("POST", path, form=form, files=files)["jobId"]

    def get_job(self, job_id: str, wait: int = 0) -> dict:
        deadline = time.time() + wait
        while True:
            job = self._call("GET", f"/jobs/{job_id}")
            status = (job.get("status") or "").lower()
            done = status in ("success", "completed", "error", "failed")
            if done or time.time() >= deadline:
                break
            time.sleep(5)
        job["done"] = done
        if status in ("success", "completed"):
            job.setdefault("outputs", {})
            urls = _find_urls(job)
            images = [u for u in urls if re.search(r"\.(png|jpe?g|webp)(\?|$)", u, re.I)]
            if images:
                job["outputs"].setdefault("imageUrl", images[0])
            if not images:
                job["outputs"].setdefault("glbUrl", GLB_PUBLIC.format(job_id=job_id))
        return job


class Mcp:
    name = "mcp"

    def __init__(self) -> None:
        self._id = 0
        self._session: str | None = None
        self._ready = False

    def _post(self, payload: dict) -> dict | None:
        headers = {**_auth_headers(), "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        if self._session:
            headers["mcp-session-id"] = self._session
        status, resp_headers, raw = _http("POST", MCP_URL, headers=headers, data=json.dumps(payload).encode(), timeout=120)
        sid = {k.lower(): v for k, v in resp_headers.items()}.get("mcp-session-id")
        if sid:
            self._session = sid
        if status >= 400:
            _raise_for(status, _parse_json(raw))
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            return None
        if text.startswith("{"):
            return json.loads(text)
        msgs = [json.loads(line[5:].strip()) for line in text.splitlines() if line.startswith("data:")]
        for m in msgs:
            if m.get("id") == payload.get("id"):
                return m
        return msgs[-1] if msgs else None

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        if not self._ready and method != "initialize":
            self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "3d-print-shop", "version": "0.1.0"}})
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._ready = True
        self._id += 1
        msg = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        if msg is None:
            raise SloydError(f"MCP {method}: empty response")
        if "error" in msg:
            raise SloydError(f"MCP {method}: {msg['error'].get('message')}")
        return msg["result"]

    def tool(self, name: str, arguments: dict) -> dict:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        text = "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        data = result.get("structuredContent")
        if data is None:
            try:
                data = json.loads(text)
            except ValueError:
                data = {"text": text}
        if result.get("isError"):
            status = 402 if "402" in text or "Insufficient" in text else 429 if "429" in text or "concurrent" in text.lower() else None
            raise SloydError(f"{name}: {text}", status, data if isinstance(data, dict) else {})
        return data

    def balance(self) -> int:
        return int(self.tool("get_credit_balance", {}).get("balance", 0))

    def styles(self) -> list:
        data = self.tool("get_generation_styles", {})
        return data.get("styles", data) if isinstance(data, dict) else data

    def start(self, op: str, args: dict, images: dict) -> str:
        tool = {"text-to-3d": "generate_3d_from_text", "image-to-3d": "generate_3d_from_image",
                "multi-image-to-3d": "generate_3d_from_images", "upload-image": "upload_image",
                "text-to-image": "generate_image", "image-edit": "edit_image",
                "retexture": "retexture_model", "split": "split_model_into_parts"}.get(op)
        if tool is None:
            raise SloydError(f"{op} has no MCP tool; use --via rest")
        arguments = dict(args)
        if op == "multi-image-to-3d":
            arguments = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in args.items() if v is not None}
        for field, src in images.items():
            arguments[field] = _image_arg(src)
        return self.tool(tool, arguments)["jobId"]

    def get_job(self, job_id: str, wait: int = 0) -> dict:
        deadline = time.time() + wait
        while True:
            job = self.tool("get_job", {"jobId": job_id, "wait": max(0, min(30, int(deadline - time.time())))})
            if job.get("done") or time.time() >= deadline:
                return job


# --------------------------------------------------------------------------- helpers


def _read_file_or_url(src: str) -> tuple[str, bytes, str]:
    if src.startswith("https://"):
        status, headers, raw = _http("GET", src, timeout=120)
        if status >= 400:
            raise SloydError(f"Could not download {src}: HTTP {status}")
        name = src.split("?")[0].rsplit("/", 1)[-1] or "image"
        return name, raw, headers.get("Content-Type", "application/octet-stream")
    with open(src, "rb") as fh:
        content = fh.read()
    return os.path.basename(src), content, mimetypes.guess_type(src)[0] or "application/octet-stream"


def _image_arg(src: str) -> dict:
    if src.startswith("https://"):
        return {"url": src}
    size = os.path.getsize(src)
    if size > 3_000_000:
        raise SloydError(f"{src} is {size/1e6:.1f} MB. Inline images must stay under ~3 MB; "
                         "resize it, pass a public https URL, or use --via rest (20 MB limit).")
    with open(src, "rb") as fh:
        return {"base64": base64.b64encode(fh.read()).decode(), "mimeType": mimetypes.guess_type(src)[0] or "image/png"}


def _find_urls(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += _find_urls(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _find_urls(v)
    elif isinstance(obj, str) and obj.startswith("https://"):
        out.append(obj)
    return out


def download(url: str, out_path: str) -> str:
    status, _, raw = _http("GET", url, timeout=600)
    if status >= 400 or not raw:
        raise SloydError(f"Download failed ({status}) for {url}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # Sloyd images come back as WebP. If the caller asked for .png/.jpg, convert (needs Pillow);
    # otherwise keep the real format by switching the extension, so the file is never mislabelled.
    want = os.path.splitext(out_path)[1].lower()
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" and want in (".png", ".jpg", ".jpeg"):
        try:
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img.save(out_path)
            return out_path
        except ImportError:
            out_path = os.path.splitext(out_path)[0] + ".webp"
            log(f"Pillow not installed; saved the WebP as {out_path}")
    with open(out_path, "wb") as fh:
        fh.write(raw)
    return out_path


def start_with_retry(client, op: str, args: dict, images: dict) -> str:
    """Start a job, waiting out 429 (5 concurrent jobs) with backoff."""
    delay = 15
    for attempt in range(MAX_429_RETRIES + 1):
        try:
            return client.start(op, args, images)
        except SloydError as e:
            if e.status != 429 or attempt == MAX_429_RETRIES:
                raise
            log(f"429: 5 jobs already running on this key. Waiting {delay}s for one to finish...")
            time.sleep(delay)
            delay = min(delay * 2, 120)
    raise AssertionError("unreachable")


def wait_for(client, job_id: str, timeout_s: int = 1800) -> dict:
    t0 = time.time()
    while True:
        job = client.get_job(job_id, wait=30)
        status = job.get("status")
        stage = ""
        frags = job.get("fragments") or []
        if frags and isinstance(frags[-1], dict):
            stage = frags[-1].get("displayName") or frags[-1].get("name") or ""
        log(f"[{int(time.time()-t0):4d}s] {job_id} {status} {stage}".rstrip())
        if job.get("done"):
            if status in ("error", "failed") or job.get("isSuccess") is False:
                raise SloydError(f"Job {job_id} failed: {job.get('errorMessage', 'unknown error')}. "
                                 "Credits for failed jobs are refunded automatically.", None, job)
            return job
        if time.time() - t0 > timeout_s:
            raise SloydError(f"Timed out after {timeout_s}s; job {job_id} still {status}. Resume with: sloyd.py job {job_id} --wait")


# --------------------------------------------------------------------------- CLI


def build_request(a) -> tuple[str, dict, dict, int]:
    """Returns (op, args, images, cost)."""
    op = a.cmd
    if op == "text-to-3d":
        args = {"prompt": a.prompt, "textureResolution": a.texture, "topology": a.topology,
                "targetFaceCount": a.faces}
        if a.style:
            args["genStyleId"] = a.style
        cost = creation_cost(text=True, multi=False, textured=a.texture != "none", quads=a.topology == "quads", faces=a.faces)
        return op, args, {}, cost
    if op == "image-to-3d":
        args = {"textureResolution": a.texture, "topology": a.topology, "targetFaceCount": a.faces}
        images = {}
        if a.image_job:
            args["imageJobId"] = a.image_job
        else:
            images["file"] = a.image
        cost = creation_cost(text=False, multi=False, textured=a.texture != "none", quads=a.topology == "quads", faces=a.faces)
        return op, args, images, cost
    if op == "multi-image-to-3d":
        images = {"frontImage": a.front}
        for k in ("left", "back", "right"):
            if getattr(a, k):
                images[f"{k}Image"] = getattr(a, k)
        if len(images) < 2:
            raise SloydError("multi-image-to-3d needs --front plus at least one of --left/--back/--right")
        args = {"EnablePBR": "true" if a.pbr else "false"}
        if a.faces:
            args["FaceCount"] = str(a.faces)
        # The endpoint picks the polygon type itself; the pricing page quotes 40 for multi-image with quads.
        # Quote the upper bound so the user is never surprised.
        cost = 40 if a.pbr else 30
        return op, args, images, cost
    if op == "upload-image":
        return op, {}, {"file": a.image}, 0
    if op == "upload-3d":
        return op, {}, {"file": a.model}, 0
    if op == "text-to-image":
        args = {"prompt": a.prompt, "aspectRatio": a.aspect}
        if a.style:
            args["genStyleId"] = a.style
        if a.ref_job:
            args["referenceImageJobId"] = a.ref_job
        return op, args, {}, FLAT_PRICES["text-to-image"]
    if op == "image-edit":
        args = {"jobId": a.job, "prompt": a.prompt}
        if a.style:
            args["genStyleId"] = a.style
        return op, args, {}, FLAT_PRICES["image-edit"]
    if op == "retexture":
        return op, {"jobId": a.job, "prompt": a.prompt, "textureResolution": a.texture}, {}, FLAT_PRICES["retexture"]
    if op == "split":
        args = {"jobId": a.job, "method": a.method}
        if a.method == "partition":
            args["numberOfParts"] = a.parts
            args["attachmentPoints"] = a.pins
        return op, args, {}, FLAT_PRICES["split"]
    raise SloydError(f"unknown command {op}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--via", choices=["mcp", "rest"], default=os.environ.get("SLOYD_TRANSPORT", "mcp"))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("balance", help="remaining prepaid credits (free)")
    sub.add_parser("styles", help="built-in genStyleId values (free)")

    def gen_opts(sp, texture_default="auto"):
        sp.add_argument("--texture", default=texture_default, choices=["128", "256", "512", "1k", "2k", "4k", "auto", "none"],
                        help="'none' = geometry only, 10 credits cheaper; fine for single-colour prints")
        sp.add_argument("--topology", default="triangles", choices=["auto", "quads", "triangles"])
        sp.add_argument("--faces", type=int, default=0, help="target face count, 0 = auto, max 500000")

    def run_opts(sp):
        sp.add_argument("--yes", action="store_true", help="approve the spend; without it this is a dry run")
        sp.add_argument("--wait", action="store_true", help="poll get_job until done")
        sp.add_argument("--out", help="download the result here (needs --wait)")
        sp.add_argument("--meta", help="write the final job JSON here")

    sp = sub.add_parser("text-to-3d"); sp.add_argument("--prompt", required=True); sp.add_argument("--style"); gen_opts(sp); run_opts(sp)
    sp = sub.add_parser("image-to-3d"); g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", help="local file or https URL"); g.add_argument("--image-job", help="jobId from upload-image or text-to-image")
    gen_opts(sp); run_opts(sp)
    sp = sub.add_parser("multi-image-to-3d")
    for k in ("front", "left", "back", "right"):
        sp.add_argument(f"--{k}")
    sp.add_argument("--pbr", action="store_true", help="textured PBR output (+10 credits)")
    sp.add_argument("--faces", type=int, default=0); run_opts(sp)
    sp = sub.add_parser("upload-image"); sp.add_argument("--image", required=True); run_opts(sp)
    sp = sub.add_parser("upload-3d", help="REST only: upload an STL/OBJ/GLB you already have"); sp.add_argument("--model", required=True); run_opts(sp)
    sp = sub.add_parser("text-to-image"); sp.add_argument("--prompt", required=True); sp.add_argument("--style")
    sp.add_argument("--aspect", default="1:1", choices=["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16"])
    sp.add_argument("--ref-job", help="upload-image jobId to use as identity reference"); run_opts(sp)
    sp = sub.add_parser("image-edit"); sp.add_argument("--job", required=True); sp.add_argument("--prompt", required=True); sp.add_argument("--style"); run_opts(sp)
    sp = sub.add_parser("retexture"); sp.add_argument("--job", required=True); sp.add_argument("--prompt", required=True)
    sp.add_argument("--texture", default="2k"); run_opts(sp)
    sp = sub.add_parser("split"); sp.add_argument("--job", required=True)
    sp.add_argument("--method", default="partition", choices=["partition", "decomposition"])
    sp.add_argument("--parts", type=int, default=4, help="partition only, 4-16")
    sp.add_argument("--pins", action="store_true", help="partition only: pin + hole at each join (for glued assemblies)")
    run_opts(sp)
    sp = sub.add_parser("job", help="status of a job (free)"); sp.add_argument("job_id")
    sp.add_argument("--wait", action="store_true"); sp.add_argument("--out"); sp.add_argument("--meta")

    a = p.parse_args(argv)
    if a.cmd == "upload-3d":
        a.via = "rest"  # no MCP tool for model upload
    client = Mcp() if a.via == "mcp" else Rest()

    try:
        if a.cmd == "balance":
            print(json.dumps({"balance": client.balance()}))
            return 0
        if a.cmd == "styles":
            print(json.dumps(client.styles(), indent=2))
            return 0
        if a.cmd == "job":
            job = wait_for(client, a.job_id) if a.wait else client.get_job(a.job_id)
            return _finish(job, a)

        if a.cmd == "split" and not 4 <= a.parts <= 16:
            raise SloydError("--parts must be between 4 and 16")
        op, args, images, cost = build_request(a)
        if cost > 0:
            balance = client.balance()
            plan = {"action": op, "cost_credits": cost, "cost_usd": round(cost / 75, 2), "balance": balance,
                    "balance_after": balance - cost, "transport": client.name}
            if balance < cost:
                print(json.dumps({**plan, "error": "insufficient_credits"}, indent=2))
                log(f"Not enough credits: {op} costs {cost}, balance is {balance}. "
                    "Top up at https://api-dashboard.sloyd.ai (minimum $12 = 900 credits).")
                return 3
            if not a.yes:
                print(json.dumps({**plan, "approved": False}, indent=2))
                log(f"Dry run. {op} will cost {cost} credits (${cost/75:.2f}); balance {balance}. "
                    "Ask the user, then re-run with --yes.")
                return 2
        job_id = start_with_retry(client, op, args, images)
        log(f"Started {op}: jobId {job_id}" + (f" ({cost} credits)" if cost else ""))
        if op in ("upload-image", "upload-3d") and not a.wait:
            print(json.dumps({"jobId": job_id}))
            return 0
        if not a.wait:
            print(json.dumps({"jobId": job_id, "next": f"sloyd.py job {job_id} --wait"}))
            return 0
        job = wait_for(client, job_id)
        job.setdefault("id", job_id)
        return _finish(job, a)
    except SloydError as e:
        log(f"ERROR: {e}")
        return {402: 3, 429: 5}.get(e.status or 0, 4 if "failed" in str(e) else 1)


def _finish(job: dict, a) -> int:
    outputs = job.get("outputs") or {}
    if getattr(a, "out", None) and job.get("done"):
        url = outputs.get("glbUrl") or outputs.get("imageUrl") or outputs.get("panoramaUrl")
        if not url:
            log(f"Job finished but has no download URL: {json.dumps(job)[:400]}")
            return 4
        saved = download(url, a.out)
        log(f"Saved {saved}")
        job["savedTo"] = saved
    if getattr(a, "meta", None):
        with open(a.meta, "w") as fh:
            json.dump(job, fh, indent=2)
    keep = {k: job.get(k) for k in ("id", "jobId", "status", "done", "outputs", "errorMessage", "savedTo") if k in job}
    print(json.dumps(keep, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
