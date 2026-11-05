#!/usr/bin/env python3
"""render.py: dependency-light renders of a print-ready mesh (numpy + Pillow, no GPU).

  render.py model.stl --out preview.png                 # still, Sloyd-navy background
  render.py model.stl --out turntable.mp4 --frames 120  # 360-degree turntable (needs imageio-ffmpeg)
  render.py model.stl --out ref.png --bg white --size 1024 --no-overlay   # clean reference for image tools

Renders by sampling points on the surface and keeping the nearest one per pixel (z-buffer),
with smooth normals and soft key/fill lighting. Overhangs can be tinted red (--overhangs 45).
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont, ImageFilter

NAVY = (18, 35, 74)          # Sloyd --color-background #12234a
SKY = np.array([69, 188, 255]) / 255.0   # brand-sky #45bcff
RED = np.array([241, 91, 110]) / 255.0


def _sample(mesh: trimesh.Trimesh, n: int, rng):
    area = mesh.area_faces
    fi = rng.choice(len(area), size=n, p=area / area.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    w = np.stack([1 - s, s * (1 - r2), s * r2], axis=1)
    tri = mesh.vertices[mesh.faces[fi]]
    pts = (tri * w[:, :, None]).sum(axis=1)
    vn = mesh.vertex_normals[mesh.faces[fi]]
    nrm = (vn * w[:, :, None]).sum(axis=1)
    fn = mesh.face_normals[fi]
    # keep hard edges crisp: fall back to the face normal where smoothing bends too far
    bad = (nrm * fn).sum(axis=1) < 0.8
    nrm[bad] = fn[bad]
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    return pts, nrm, fi


def _colors(mesh, fi, base_rgb):
    try:
        vis = mesh.visual
        if vis.kind == "face":
            return np.asarray(vis.face_colors)[fi, :3] / 255.0
    except Exception:
        pass
    return np.tile(base_rgb, (len(fi), 1))


def render(mesh: trimesh.Trimesh, size: int = 900, azim: float = -35.0, elev: float = 22.0,
           bg=NAVY, base_rgb=SKY, overhang_deg: float | None = None, density: float = 5.0,
           seed: int = 0, extent: float | None = None, center=None) -> Image.Image:
    rng = np.random.default_rng(seed)
    ss = 2  # supersample
    W = size * ss
    lo, hi = mesh.bounds
    c = (lo + hi) / 2 if center is None else np.asarray(center)
    ext = extent or float(np.linalg.norm(hi - lo))
    scale = 0.86 * W / ext
    # point count: enough to cover the projected area several times
    n = int(min(9e6, max(4e5, density * (mesh.area * scale ** 2) / 2.2)))
    pts, nrm, fi = _sample(mesh, n, rng)
    col = _colors(mesh, fi, base_rgb)
    if overhang_deg is not None:
        over = (-mesh.face_normals[fi, 2] > math.cos(math.radians(overhang_deg))) & (pts[:, 2] > 0.3)
        col[over] = RED

    a, e = math.radians(azim), math.radians(elev)
    # camera basis (Z up): right, up, forward (towards the viewer)
    fwd = np.array([math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)])
    right = np.array([math.cos(a), math.sin(a), 0.0])
    up = np.cross(fwd, right)
    p = pts - c
    x = (p @ right) * scale + W / 2
    y = -(p @ up) * scale + W / 2
    depth = p @ fwd  # larger = closer

    key = np.array([0.5, -0.7, 0.9]); key /= np.linalg.norm(key)
    fill = np.array([-0.8, 0.2, 0.3]); fill /= np.linalg.norm(fill)
    rim = -fwd + np.array([0, 0, 0.6]); rim /= np.linalg.norm(rim)
    diff = np.clip(nrm @ key, 0, 1)
    half = key + fwd; half /= np.linalg.norm(half)
    spec = np.clip(nrm @ half, 0, 1) ** 40
    lum = 0.28 + 0.62 * diff + 0.18 * np.clip(nrm @ fill, 0, 1) + 0.25 * np.clip(nrm @ rim, 0, 1) ** 3
    rgb = np.clip(col * lum[:, None] + 0.35 * spec[:, None], 0, 1)

    xi, yi = x.astype(int), y.astype(int)
    ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < W) & ((nrm @ fwd) > -0.2)
    xi, yi, depth, rgb = xi[ok], yi[ok], depth[ok], rgb[ok]
    order = np.argsort(depth)  # far first, near last: near wins
    idx = yi[order] * W + xi[order]
    img = np.empty((W * W, 3)); img[:] = np.array(bg) / 255.0
    img[idx] = rgb[order]
    hit = np.zeros(W * W, bool); hit[idx] = True

    # ground shadow (soft), drawn under the model
    out = Image.fromarray((img.reshape(W, W, 3) * 255).astype(np.uint8))
    mask = Image.fromarray((hit.reshape(W, W) * 255).astype(np.uint8))
    mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))  # close splat gaps
    model = out.copy()
    out = Image.new("RGB", (W, W), bg)
    shadow = Image.new("L", (W, W), 0)
    sd = ImageDraw.Draw(shadow)
    base_pts = mesh.vertices[mesh.vertices[:, 2] < lo[2] + 0.02 * (hi[2] - lo[2]) + 0.5] - c
    if len(base_pts):
        bx = (base_pts @ right) * scale + W / 2
        by = -(base_pts @ up) * scale + W / 2
        pad = 0.06 * W
        sd.ellipse([bx.min() - pad, by.min() - pad * 0.4, bx.max() + pad, by.max() + pad * 0.6], fill=110)
        shadow = shadow.filter(ImageFilter.GaussianBlur(W / 40))
        out = Image.composite(Image.new("RGB", (W, W), tuple(int(v * 0.55) for v in bg)), out, shadow)
    model = model.filter(ImageFilter.MedianFilter(3))
    out.paste(model, (0, 0), mask)
    return out.resize((size, size), Image.LANCZOS)


def _font(bold: bool, px: int):
    """Poppins (Sloyd's brand font) if installed, else matplotlib's bundled DejaVu, else PIL default."""
    candidates = [os.environ.get("PRINT_SHOP_FONT_BOLD" if bold else "PRINT_SHOP_FONT", "")]
    try:
        from matplotlib import font_manager as fm
    except ImportError:
        fm = None
    for fam in ("Poppins", "DejaVu Sans"):
        if fm is None:
            break
        try:
            candidates.append(fm.findfont(fm.FontProperties(family=fam, weight="bold" if bold else "normal"),
                                          fallback_to_default=False))
        except Exception:
            continue
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                continue
    return ImageFont.load_default()


def overlay(img: Image.Image, title: str, subtitle: str) -> Image.Image:
    d = ImageDraw.Draw(img)
    font = _font(True, int(img.width / 26))
    small = _font(False, int(img.width / 50))
    d.text((img.width * 0.04, img.width * 0.035), title, fill="white", font=font)
    d.text((img.width * 0.04, img.width * 0.035 + img.width / 20), subtitle, fill=(191, 232, 255), font=small)
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mesh")
    ap.add_argument("--out", required=True, help=".png/.jpg for a still, .mp4/.gif for a turntable")
    ap.add_argument("--size", type=int, default=900)
    ap.add_argument("--azim", type=float, default=-35)
    ap.add_argument("--elev", type=float, default=22)
    ap.add_argument("--frames", type=int, default=120)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--bg", default="navy", help="'navy', 'white' or r,g,b")
    ap.add_argument("--color", help="model colour r,g,b (default Sloyd sky blue; face colours win if present)")
    ap.add_argument("--overhangs", type=float, help="tint faces steeper than this many degrees red")
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--no-overlay", action="store_true")
    a = ap.parse_args(argv)

    mesh = trimesh.load(a.mesh, force="mesh")
    bg = NAVY if a.bg == "navy" else (255, 255, 255) if a.bg == "white" else tuple(int(v) for v in a.bg.split(","))
    base = SKY if not a.color else np.array([float(v) for v in a.color.split(",")]) / 255.0
    title = a.title or os.path.splitext(os.path.basename(a.mesh))[0]
    sub = a.subtitle or "{:.0f} x {:.0f} x {:.0f} mm".format(*mesh.extents)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)

    if a.out.lower().endswith((".mp4", ".gif")):
        import imageio.v2 as imageio
        lo, hi = mesh.bounds
        ext = float(np.linalg.norm(hi - lo))
        frames = []
        for i in range(a.frames):
            im = render(mesh, a.size, a.azim + 360.0 * i / a.frames, a.elev, bg, base, a.overhangs,
                        density=3.0, seed=i, extent=ext, center=(lo + hi) / 2)
            frames.append(np.asarray(im if a.no_overlay else overlay(im, title, sub)))
            print(f"\rframe {i+1}/{a.frames}", end="", file=sys.stderr)
        print(file=sys.stderr)
        if a.out.lower().endswith(".gif"):
            imageio.mimsave(a.out, frames, duration=1 / a.fps, loop=0)
        else:
            imageio.mimsave(a.out, frames, fps=a.fps, codec="libx264", quality=8, macro_block_size=8)
    else:
        im = render(mesh, a.size, a.azim, a.elev, bg, base, a.overhangs)
        if not a.no_overlay:
            im = overlay(im, title, sub)
        im.save(a.out)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
