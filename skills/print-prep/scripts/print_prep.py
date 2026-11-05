#!/usr/bin/env python3
"""print_prep.py: turn a GLB (or OBJ/PLY/STL) into a slicer-ready STL + 3MF.

Pipeline
  1. load the scene, glTF Y-up -> printer Z-up
  2. scale to real millimetres (--height / --max-dim / --width / --depth / --scale)
  3. repair to a watertight solid: clean, fill holes, union overlapping shells,
     voxel remesh as the fallback that always closes
  4. drop floating debris, rest on the bed
  5. flat base: cut a flat footprint, or add a plinth (optionally with a raised name label)
  6. analyse: watertight, volume, filament estimate, build-plate fit,
     wall thickness (ray cast), overhangs, support islands, tip-over risk
  7. export STL + 3MF (+ one STL per part with --parts) + report.json + report.md (+ preview.png)

Exit code 0 = files written (warnings may exist), 1 = failed.
Requires: trimesh, numpy, scipy, networkx, lxml, shapely, manifold3d, fast_simplification.
Optional: matplotlib (preview + text labels), embreex (faster ray casting).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field

import tempfile

import numpy as np
import trimesh

os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "print_prep_mpl"))

try:
    import manifold3d
except ImportError:  # pragma: no cover
    manifold3d = None

# Build volumes in mm (X, Y, Z) from manufacturer spec pages. See references/printers.md.
PRINTERS = {
    "bambu-x1c": ("Bambu Lab X1 Carbon", (256, 256, 256), "fdm"),
    "bambu-p1s": ("Bambu Lab P1S", (256, 256, 256), "fdm"),
    "bambu-p2s": ("Bambu Lab P2S", (256, 256, 256), "fdm"),
    "bambu-a1": ("Bambu Lab A1", (256, 256, 256), "fdm"),
    "bambu-a1-mini": ("Bambu Lab A1 mini", (180, 180, 180), "fdm"),
    "bambu-h2d": ("Bambu Lab H2D (single nozzle)", (325, 320, 325), "fdm"),
    "prusa-mk4s": ("Prusa MK4S", (250, 210, 220), "fdm"),
    "prusa-core-one": ("Prusa CORE One", (250, 220, 270), "fdm"),
    "prusa-mini": ("Prusa MINI+", (180, 180, 180), "fdm"),
    "prusa-xl": ("Prusa XL", (360, 360, 360), "fdm"),
    "elegoo-centauri-carbon": ("Elegoo Centauri Carbon", (256, 256, 256), "fdm"),
    "elegoo-neptune-4-pro": ("Elegoo Neptune 4 Pro", (225, 225, 265), "fdm"),
    "elegoo-saturn-4-ultra": ("Elegoo Saturn 4 Ultra (resin)", (218, 123, 220), "resin"),
    "elegoo-mars-5-ultra": ("Elegoo Mars 5 Ultra (resin)", (153, 77, 165), "resin"),
}

# Thresholds by technology. FDM numbers assume a 0.4 mm nozzle (scaled by --nozzle).
TECH = {
    "fdm": {"min_wall": 0.8, "warn_wall": 1.2, "overhang_deg": 45.0, "density": 1.24, "material": "PLA"},
    "resin": {"min_wall": 0.4, "warn_wall": 0.8, "overhang_deg": 30.0, "density": 1.10, "material": "standard resin"},
}

FILAMENT_COLORS = {  # common Bambu/Prusament/Elegoo basics, for AMS slot suggestions
    "white": (240, 240, 240), "black": (25, 25, 25), "grey": (128, 128, 128), "silver": (180, 185, 190),
    "red": (200, 30, 35), "orange": (240, 120, 30), "yellow": (245, 205, 40), "green": (40, 160, 70),
    "dark green": (30, 80, 45), "blue": (30, 90, 200), "navy": (25, 40, 90), "cyan": (40, 180, 220),
    "purple": (110, 60, 160), "pink": (240, 140, 180), "brown": (110, 70, 40), "beige": (215, 190, 150),
    "gold": (200, 160, 60),
}


@dataclass
class Report:
    source: str
    settings: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    parts: list = field(default_factory=list)
    outputs: dict = field(default_factory=dict)

    def step(self, msg: str) -> None:
        self.steps.append(msg)
        print(f"  - {msg}", file=sys.stderr, flush=True)

    def warn(self, code: str, msg: str, fix: str) -> None:
        self.warnings.append({"code": code, "message": msg, "fix": fix})


# --------------------------------------------------------------------------- load


def load_parts(path: str, up: str) -> list[tuple[str, trimesh.Trimesh]]:
    """Return [(name, mesh)] in world space, Z-up, with visuals kept where possible."""
    loaded = trimesh.load(path, force="scene", process=False)
    parts = []
    for node in loaded.graph.nodes_geometry:
        transform, geom_name = loaded.graph[node]
        geom = loaded.geometry[geom_name]
        if not isinstance(geom, trimesh.Trimesh) or len(geom.faces) == 0:
            continue
        m = geom.copy()
        m.apply_transform(transform)
        parts.append((str(node), m))
    if not parts:
        raise ValueError(f"{path} contains no triangle meshes")
    if up == "y":  # glTF is +Y up, slicers are +Z up: rotate +90 deg about X
        rot = trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0])
        for _, m in parts:
            m.apply_transform(rot)
    return parts


def part_color(mesh: trimesh.Trimesh) -> tuple[list[int], str] | None:
    """Area-weighted mean surface colour, and the nearest common filament colour."""
    try:
        vis = mesh.visual
        if vis.kind == "texture":
            vis = vis.to_color()
        if vis.kind == "vertex":
            cols = np.asarray(vis.vertex_colors)[:, :3].astype(float)
            face_cols = cols[mesh.faces].mean(axis=1)
        elif vis.kind == "face":
            face_cols = np.asarray(vis.face_colors)[:, :3].astype(float)
        else:
            mat = getattr(getattr(mesh.visual, "material", None), "main_color", None)
            if mat is None:
                return None
            face_cols = np.tile(np.asarray(mat[:3], float), (len(mesh.faces), 1))
        w = mesh.area_faces / max(mesh.area_faces.sum(), 1e-12)
        rgb = (face_cols * w[:, None]).sum(axis=0)
        name = min(FILAMENT_COLORS, key=lambda k: np.linalg.norm(np.array(FILAMENT_COLORS[k]) - rgb))
        return [int(round(c)) for c in rgb], name
    except Exception:
        return None


# --------------------------------------------------------------------------- repair


def clean(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    m = trimesh.Trimesh(vertices=mesh.vertices.copy(), faces=mesh.faces.copy(), process=True, validate=True)
    m.merge_vertices(digits_vertex=5)
    m.update_faces(m.nondegenerate_faces(height=1e-9))
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_winding(m)
    trimesh.repair.fix_normals(m, multibody=True)
    return m


def fill_boundary_loops(mesh: trimesh.Trimesh, max_loop: int = 400) -> int:
    """Close every open boundary loop with a fan around its centroid. Returns loops filled.
    trimesh.repair.fill_holes only closes 3-4 edge holes; generated meshes have bigger ones."""
    edges = mesh.edges_sorted
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = uniq[counts == 1]
    if len(boundary) == 0:
        return 0
    # orient boundary edges as they appear in faces, so the fan gets the right winding
    directed = {}
    for a, b in mesh.edges:
        key = (min(a, b), max(a, b))
        directed.setdefault(key, (a, b))
    nxt = {}
    for a, b in boundary:
        u, v = directed[(a, b)]
        nxt[v] = u  # walk opposite to face direction so new faces wind the same way
    new_v, new_f = [], []
    base = len(mesh.vertices)
    seen = set()
    filled = 0
    for start in list(nxt):
        if start in seen:
            continue
        loop, cur = [], start
        while cur not in seen and cur in nxt and len(loop) <= max_loop:
            seen.add(cur)
            loop.append(cur)
            cur = nxt[cur]
        if cur != start or len(loop) < 3 or len(loop) > max_loop:
            continue
        centre = mesh.vertices[loop].mean(axis=0)
        ci = base + len(new_v)
        new_v.append(centre)
        for i in range(len(loop)):
            new_f.append([loop[i], loop[(i + 1) % len(loop)], ci])
        filled += 1
    if filled:
        mesh.vertices = np.vstack([mesh.vertices, np.array(new_v)])
        mesh.faces = np.vstack([mesh.faces, np.array(new_f)])
        trimesh.repair.fix_normals(mesh, multibody=True)
    return filled


def to_manifold(mesh: trimesh.Trimesh):
    return manifold3d.Manifold(manifold3d.Mesh(
        vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
        tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))


def from_manifold(man) -> trimesh.Trimesh:
    out = man.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(out.vert_properties)[:, :3], faces=np.asarray(out.tri_verts), process=True)


def union(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh | None:
    """Boolean union with manifold3d. Returns None if any input isn't a valid manifold."""
    if manifold3d is None:
        return None
    mans = []
    for m in meshes:
        man = to_manifold(m)
        if man.status() != manifold3d.Error.NoError or man.is_empty():
            return None
        mans.append(man)
    result = manifold3d.Manifold.batch_boolean(mans, manifold3d.OpType.Add) if len(mans) > 1 else mans[0]
    out = from_manifold(result)
    return out if out.is_watertight else None


def voxel_remesh(mesh: trimesh.Trimesh, pitch: float, max_faces: int, rep: Report) -> trimesh.Trimesh:
    """Closed solid from any triangle soup: voxelise the surface, fill the inside, marching cubes."""
    from scipy import ndimage

    t0 = time.time()
    src = mesh.copy()
    trimesh.repair.fill_holes(src)
    fill_boundary_loops(src, max_loop=20000)  # close big openings first, or the inside can't be found
    surf = src.voxelized(pitch=pitch)
    pad = 3
    grid = np.pad(surf.matrix, pad)
    grid = ndimage.binary_closing(grid, iterations=2)  # seals leftover gaps up to ~4 voxels
    solid = ndimage.binary_fill_holes(grid)
    if solid.sum() < 1.3 * grid.sum():
        rep.warn("hollow_remesh", "Voxel rebuild could not find a closed inside, so the result may be a thin shell.",
                 "Check the preview. If it's hollow, regenerate the model, or raise --voxel-pitch to close bigger gaps.")
    T = surf.transform.copy()
    T[:3, 3] -= pad * pitch
    vox = trimesh.voxel.VoxelGrid(trimesh.voxel.encoding.DenseEncoding(solid), transform=T)
    out = vox.marching_cubes
    out.apply_transform(vox.transform)
    out = clean(out)
    trimesh.smoothing.filter_taubin(out, lamb=0.5, nu=-0.53, iterations=6)
    rep.step(f"voxel remesh at {pitch:.2f} mm: {len(out.faces):,} faces in {time.time()-t0:.1f}s")
    return decimate(out, max_faces, rep)


def decimate(mesh: trimesh.Trimesh, max_faces: int, rep: Report) -> trimesh.Trimesh:
    if len(mesh.faces) <= max_faces:
        return mesh
    try:
        import fast_simplification
        v, f = fast_simplification.simplify(mesh.vertices, mesh.faces, target_reduction=1 - max_faces / len(mesh.faces))
        out = clean(trimesh.Trimesh(v, f, process=True))
        if out.is_watertight:
            rep.step(f"decimated {len(mesh.faces):,} -> {len(out.faces):,} faces")
            return out
        rep.step("decimation broke watertightness; kept the full-resolution mesh")
    except ImportError:
        rep.step("fast_simplification not installed; skipped decimation")
    return mesh


def repair(mesh: trimesh.Trimesh, mode: str, pitch: float, max_faces: int, rep: Report, label: str) -> trimesh.Trimesh:
    m = clean(mesh)
    shells = m.split(only_watertight=False)
    open_shells = [s for s in shells if not s.is_watertight]
    rep.step(f"{label}: {len(m.faces):,} faces, {len(shells)} shell(s), {len(open_shells)} open")
    if mode == "none":
        return m
    if mode == "auto" and open_shells:
        for s in open_shells:
            trimesh.repair.fill_holes(s)
            if not s.is_watertight:
                fill_boundary_loops(s)
        if all(s.is_watertight for s in shells):
            rep.step(f"{label}: filled holes in {len(open_shells)} shell(s)")
            open_shells = []
            m = clean(trimesh.util.concatenate(shells)) if len(shells) > 1 else clean(shells[0])
    if mode == "auto" and not open_shells:
        solid = union([s for s in shells if s.volume > 0]) if len(shells) > 1 else (m if m.is_watertight else None)
        if solid is not None and solid.is_watertight and solid.volume > 0:
            if len(shells) > 1:
                rep.step(f"{label}: unioned {len(shells)} shells into one solid")
            return decimate(solid, max_faces, rep)
    rep.step(f"{label}: needs a full rebuild ({'requested' if mode == 'voxel' else 'holes or self-overlaps left'})")
    return voxel_remesh(m, pitch, max_faces, rep)


def drop_debris(mesh: trimesh.Trimesh, rep: Report, keep_frac: float = 0.002) -> trimesh.Trimesh:
    """Remove tiny disconnected bodies (floating specks that would print as spaghetti)."""
    bodies = mesh.split(only_watertight=False)
    if len(bodies) <= 1:
        return mesh
    vols = np.array([abs(b.volume) for b in bodies])
    keep = [b for b, v in zip(bodies, vols) if v >= keep_frac * vols.max()]
    dropped = len(bodies) - len(keep)
    if dropped:
        rep.step(f"removed {dropped} floating speck(s) smaller than {keep_frac:.1%} of the main body")
    return trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]


# --------------------------------------------------------------------------- base


def section_area(mesh: trimesh.Trimesh, z: float) -> float:
    sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None:
        return 0.0
    try:
        planar, _ = sec.to_2D()
        return float(sum(p.area for p in planar.polygons_full))
    except Exception:
        return 0.0


def footprint_hull(mesh: trimesh.Trimesh):
    """Convex hull of the XY projection. Computed from points, so overlapping parts can't break it."""
    from shapely.geometry import MultiPoint
    return MultiPoint(mesh.convex_hull.vertices[:, :2]).convex_hull


def footprint_target(mesh: trimesh.Trimesh) -> tuple[float, float]:
    hull_area = footprint_hull(mesh).area
    return max(30.0, 0.12 * hull_area), hull_area


def flatten_base(meshes: list[trimesh.Trimesh], rep: Report, max_frac: float = 0.06) -> tuple[list[trimesh.Trimesh], float, bool]:
    """Cut every mesh at the lowest Z that gives a stable flat footprint. Returns (meshes, cut, ok)."""
    whole = trimesh.util.concatenate(meshes)
    height = whole.bounds[1, 2]
    target, hull_area = footprint_target(whole)
    cut, area = None, 0.0
    for z in np.linspace(0.4, max(0.5, max_frac * height), 25):
        area = sum(section_area(m, z) for m in meshes)
        if area >= target:
            cut = float(z)
            break
    ok = cut is not None
    if not ok:
        cut = float(max_frac * height)
        area = sum(section_area(m, cut) for m in meshes)
    out = []
    for m in meshes:
        if m.bounds[1, 2] <= cut:
            continue  # part entirely under the cut
        if m.bounds[0, 2] >= cut:
            out.append(m.copy())
            continue
        s = m.slice_plane(plane_origin=[0, 0, cut], plane_normal=[0, 0, 1], cap=True)
        if s is not None and len(s.faces):
            out.append(s)
    for m in out:
        m.apply_translation([0, 0, -cut])
    rep.step(f"flattened base: cut {cut:.2f} mm off the bottom, contact area {area:.0f} mm2 (target {target:.0f} mm2)")
    return out, cut, ok


def text_polygons(text: str, height_mm: float):
    """Shapely polygons for TEXT, cap height ~height_mm, centred at the origin. Uses matplotlib's bundled DejaVu font."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from shapely import affinity

    tp = TextPath((0, 0), text, size=10, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    geom = Polygon()
    for ring in tp.to_polygons():
        if len(ring) >= 3:
            p = Polygon(ring).buffer(0)
            geom = geom.symmetric_difference(p)  # even-odd fill handles counters in A, O, B...
    geom = unary_union(geom)
    minx, miny, maxx, maxy = geom.bounds
    s = height_mm / max(maxy - miny, 1e-6)
    geom = affinity.scale(geom, s, s, origin=(0, 0))
    minx, miny, maxx, maxy = geom.bounds
    return affinity.translate(geom, -(minx + maxx) / 2, -(miny + maxy) / 2)


def add_plinth(meshes: list[trimesh.Trimesh], thickness: float, label: str | None, rep: Report,
               margin: float = 3.0) -> tuple[list[trimesh.Trimesh], trimesh.Trimesh, trimesh.Trimesh | None]:
    """Put the model on a rounded plinth. With a label, the plinth gets a front strip with raised text.
    Returns (model meshes moved up, plinth mesh, label mesh or None)."""
    from shapely.geometry import box

    whole = trimesh.util.concatenate(meshes)
    lo, hi = whole.bounds
    sink = min(0.6, thickness / 3)  # embed the model into the plinth so they fuse
    moved = []
    for m in meshes:
        mm = m.copy()
        mm.apply_translation([0, 0, thickness - sink])
        moved.append(mm)

    if label:
        width = max(hi[0] - lo[0], 0) + 2 * margin
        letter_h = min(10.0, max(5.0, 0.12 * width))
        txt = text_polygons(label.upper(), letter_h)
        tw = txt.bounds[2] - txt.bounds[0]
        width = max(width, tw + 2 * margin + 4)
        strip = letter_h + 2 * margin
        depth = (hi[1] - lo[1]) + 2 * margin + strip
        cx = (lo[0] + hi[0]) / 2
        outline = box(cx - width / 2, lo[1] - margin - strip, cx + width / 2, hi[1] + margin)
        r = min(4.0, width / 6, depth / 6)
        outline = outline.buffer(-r).buffer(r, resolution=12)
    else:
        outline = footprint_hull(whole).buffer(margin, resolution=16)

    plinth = trimesh.creation.extrude_polygon(outline, thickness)
    label_mesh = None
    if label:
        ty = lo[1] - margin - strip / 2
        glyphs = list(getattr(txt, "geoms", [txt]))
        txt_mesh = trimesh.util.concatenate([trimesh.creation.extrude_polygon(g, 1.0 + 0.2) for g in glyphs if g.area > 0.05])
        txt_mesh.apply_translation([cx, ty, thickness - 0.2])  # sunk 0.2 mm so it fuses with the plinth
        label_mesh = clean(txt_mesh)
        rep.step(f"plinth {width:.0f} x {depth:.0f} x {thickness:.1f} mm with raised label '{label.upper()}' ({letter_h:.1f} mm letters, 1.0 mm tall)")
    else:
        rep.step(f"plinth {thickness:.1f} mm thick, {margin:.0f} mm margin around the footprint")
    return moved, clean(plinth), label_mesh


# --------------------------------------------------------------------------- analysis


def wall_thickness(mesh: trimesh.Trimesh, samples: int, seed: int = 0) -> dict:
    """Local thickness: cast a ray inward from sampled surface points, distance to the opposite wall."""
    rng = np.random.default_rng(seed)
    n = min(samples, len(mesh.faces))
    p = mesh.area_faces / mesh.area_faces.sum()
    idx = rng.choice(len(mesh.faces), size=n, replace=len(mesh.faces) < n, p=p)
    normals = mesh.face_normals[idx]
    origins = mesh.triangles_center[idx] - normals * 1e-4
    locs, ray_idx, _ = mesh.ray.intersects_location(origins, -normals, multiple_hits=False)
    if len(ray_idx) == 0:
        return {"samples": 0}
    d = np.full(n, np.nan)
    d[ray_idx] = np.linalg.norm(locs - origins[ray_idx], axis=1)
    valid = ~np.isnan(d) & (d > 1e-3)
    d, pts = d[valid], mesh.triangles_center[idx][valid]
    return {"samples": int(valid.sum()), "values": d, "points": pts,
            "p1": float(np.percentile(d, 1)), "p5": float(np.percentile(d, 5)), "median": float(np.median(d))}


def support_islands(mesh: trimesh.Trimesh, bed_eps: float = 0.3) -> list[dict]:
    """Local Z minima above the bed: places where a layer starts in mid-air and needs a support."""
    z = mesh.vertices[:, 2]
    e = mesh.edges_unique
    is_min = np.ones(len(z), bool)
    lower_b = z[e[:, 1]] < z[e[:, 0]] - 1e-6
    lower_a = z[e[:, 0]] < z[e[:, 1]] - 1e-6
    is_min[e[lower_b, 0]] = False
    is_min[e[lower_a, 1]] = False
    # A real island starts on a downward-facing surface. Flat tops (plinth surface around the model)
    # also have no lower neighbour, but they face up and print fine.
    facing_down = mesh.vertex_normals[:, 2] < -0.5
    cand = np.where(is_min & facing_down & (z > bed_eps))[0]
    if len(cand) == 0:
        return []
    from scipy.cluster.hierarchy import fcluster, linkage
    pts = mesh.vertices[cand]
    if len(pts) == 1:
        labels = np.array([1])
    else:
        labels = fcluster(linkage(pts, "single"), t=2.0, criterion="distance")
    out = []
    for lab in np.unique(labels):
        c = pts[labels == lab]
        lowest = c[np.argmin(c[:, 2])]
        out.append({"x": round(float(lowest[0]), 1), "y": round(float(lowest[1]), 1), "z": round(float(lowest[2]), 1)})
    return sorted(out, key=lambda d: d["z"])


def bands(z: np.ndarray, weights: np.ndarray, step: float = 5.0, top: int = 3) -> list[str]:
    if len(z) == 0:
        return []
    b = np.floor(z / step).astype(int)
    agg = {}
    for k, w in zip(b, weights):
        agg[k] = agg.get(k, 0.0) + w
    best = sorted(agg.items(), key=lambda kv: -kv[1])[:top]
    return [f"z {k*step:.0f}-{(k+1)*step:.0f} mm" for k, _ in sorted(best)]


def analyse(mesh: trimesh.Trimesh, tech: str, nozzle: float, printer: str | None, samples: int, rep: Report) -> dict:
    t = dict(TECH[tech])
    if tech == "fdm":
        t["min_wall"] = round(2 * nozzle, 2)
        t["warn_wall"] = round(3 * nozzle, 2)
    ext = mesh.extents
    stats = {
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "bodies": len(mesh.split(only_watertight=False)),
        "faces": int(len(mesh.faces)),
        "size_mm": [round(float(x), 1) for x in ext],
        "volume_cm3": round(float(mesh.volume) / 1000, 2) if mesh.is_watertight else None,
        "surface_cm2": round(float(mesh.area) / 100, 1),
        "tech": tech,
        "thresholds": t,
    }
    if not mesh.is_watertight:
        rep.warn("not_watertight", "The mesh still has holes after repair.",
                 "Re-run with --repair voxel, or let the slicer's 'fix model' repair it.")

    if mesh.is_watertight:
        vol = mesh.volume / 1000
        if tech == "fdm":
            shell = min(vol, mesh.area / 100 * 0.12)  # ~2 perimeters + top/bottom skins
            grams = t["density"] * (shell + 0.15 * (vol - shell))
            stats["filament_estimate_g"] = round(grams, 1)
            stats["filament_estimate_note"] = "PLA, 2 walls, 15% infill; your slicer gives the exact number"
        else:
            stats["resin_estimate_ml"] = round(vol, 1)
            if vol > 20:
                rep.warn("hollow", f"Solid resin print uses ~{vol:.0f} ml.",
                         "Hollow it in the slicer (2 mm wall) and add 2 drain holes near the base.")

    if printer:
        pname, vol_mm, ptech = PRINTERS[printer]
        fits = all(a <= b for a, b in zip(sorted(ext[:2]) + [ext[2]], sorted(vol_mm[:2]) + [vol_mm[2]]))
        stats["printer"] = {"name": pname, "build_volume_mm": vol_mm, "fits": bool(fits)}
        if not fits:
            rep.warn("too_big", f"{ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} mm does not fit the {pname} ({vol_mm[0]} x {vol_mm[1]} x {vol_mm[2]} mm).",
                     "Scale down, or split it with multi-color-splitter (partition + attachment pins) and glue.")
        if ptech != tech:
            rep.warn("tech_mismatch", f"Analysed for {tech} but the {pname} is a {ptech} printer.", f"Re-run with --tech {ptech}.")

    wt = wall_thickness(mesh, samples, seed=1)
    if wt.get("samples"):
        thin = wt["values"] < t["min_wall"]
        stats["wall_thickness_mm"] = {"min_p1": round(wt["p1"], 2), "p5": round(wt["p5"], 2), "median": round(wt["median"], 2),
                                      "thin_area_pct": round(100 * float(thin.mean()), 1), "samples": wt["samples"]}
        if thin.mean() > 0.005:
            where = bands(wt["points"][thin, 2], np.ones(int(thin.sum())))
            rep.warn("thin_walls", f"{100*thin.mean():.1f}% of the surface is thinner than {t['min_wall']} mm "
                     f"(thinnest ~{wt['p1']:.2f} mm, mostly at {', '.join(where)}).",
                     "Scale up, ask print-designer for chunkier details, or print with a 0.2 mm nozzle." if tech == "fdm"
                     else "Scale up or thicken those details; resin features under 0.4 mm break off in washing.")
        elif wt["p5"] < t["warn_wall"]:
            rep.warn("fine_detail", f"Some details are close to the limit ({wt['p5']:.2f} mm at the 5th percentile).",
                     "Print slower walls or use a 0.2 mm layer height for these details.")

    # overhangs: faces facing down more steeply than the limit, ignoring the face on the bed
    limit = math.radians(t["overhang_deg"])
    down = -mesh.face_normals[:, 2]
    cz = mesh.triangles_center[:, 2]
    over = (down > math.cos(limit)) & (cz > 0.3)
    area = mesh.area_faces
    over_area = float(area[over].sum())
    stats["overhangs"] = {"limit_deg_from_vertical": t["overhang_deg"], "area_mm2": round(over_area, 0),
                          "pct_of_surface": round(100 * over_area / float(area.sum()), 1)}
    islands = support_islands(mesh)
    stats["support_islands"] = {"count": len(islands), "lowest": islands[:5]}
    if over_area / area.sum() > 0.02 or islands:
        where = bands(cz[over], area[over])
        msg = f"{100*over_area/area.sum():.1f}% of the surface overhangs more than {t['overhang_deg']:.0f} deg"
        msg += f" ({', '.join(where)})" if where else ""
        if islands:
            msg += f"; {len(islands)} spot(s) start in mid-air, lowest at z {islands[0]['z']} mm"
        fix = ("Enable supports: tree supports (Bambu Studio / OrcaSlicer: Support > Type 'tree(auto)'; PrusaSlicer: 'Organic'), "
               "threshold 45 deg, or rotate the model so the flat side is down." if tech == "fdm"
               else "Tilt 15-30 deg in the resin slicer and use auto supports; islands must be supported.")
        rep.warn("overhangs", msg + ".", fix)

    # tip-over: centre of mass must sit over the contact patch
    if mesh.is_watertight:
        com = mesh.center_mass
        contact = mesh.section(plane_origin=[0, 0, 0.2], plane_normal=[0, 0, 1])
        if contact is not None:
            from shapely.geometry import Point, MultiPolygon
            try:
                polys = [trimesh.path.polygons.Polygon(np.asarray(e)[:, :2]) for e in contact.discrete]
                patch = MultiPolygon([p.buffer(0) for p in polys if p.is_valid or p.buffer(0).is_valid]).convex_hull
                inside = patch.contains(Point(com[0], com[1]))
                min_w = 2 * patch.minimum_rotated_rectangle.exterior.distance(Point(*patch.centroid.coords[0])) if patch.area else 0
                stats["stability"] = {"contact_area_mm2": round(patch.area, 0), "com_over_base": bool(inside),
                                      "com_height_mm": round(float(com[2]), 1)}
                if not inside:
                    rep.warn("tip_over", "The centre of mass is outside the base, so the print will fall over.",
                             "Add a plinth (--base plinth) or re-orient.")
                elif min_w > 0 and com[2] / min_w > 3:
                    rep.warn("tall_narrow", f"Tall and narrow (centre of mass {com[2]:.0f} mm up on a ~{min_w:.0f} mm base).",
                             "Use a 5-8 mm brim, or --base plinth, and keep print speed down for the top half.")
                if patch.area < 30:
                    rep.warn("small_contact", f"Only {patch.area:.0f} mm2 touches the bed.",
                             "Use --base plinth or a brim so it doesn't detach mid-print.")
            except Exception:
                pass
    return stats


def assign_slots(part_cols: list, n_slots: int, rep: Report) -> list:
    """Map each part to a filament slot 1..n_slots. Parts with the same suggested filament share a slot;
    if there are more filaments than slots, merge the closest colours."""
    names = [c[1] if c else "grey" for c in part_cols]
    rgbs = {nm: np.array(FILAMENT_COLORS[nm], float) for nm in names}
    groups = [[nm] for nm in dict.fromkeys(names)]  # keep first-seen order
    while len(groups) > max(1, n_slots):
        best = None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                d = min(np.linalg.norm(rgbs[a] - rgbs[b]) for a in groups[i] for b in groups[j])
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        rep.step(f"only {n_slots} filament slots: merged {'/'.join(groups[j])} into {'/'.join(groups[i])}")
        groups[i] += groups.pop(j)
    slot_of = {nm: (k + 1, g[0]) for k, g in enumerate(groups) for nm in g}
    rep.step("filament slots: " + ", ".join(f"{k+1}={g[0]}" for k, g in enumerate(groups)))
    return [slot_of[nm] for nm in names]


def lay_flat(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, float]:
    """Rotate so the largest flat facet (e.g. a partition cut cap) faces the bed. Returns (mesh, facet area)."""
    m = mesh.copy()
    if len(m.facets):
        k = int(np.argmax(m.facets_area))
        n, area = m.facets_normal[k], float(m.facets_area[k])
    else:
        n, area = np.array([0, 0, -1.0]), 0.0
    R = trimesh.geometry.align_vectors(n, [0, 0, -1])
    m.apply_transform(R)
    m.apply_translation(-m.bounds[0])
    return m, area


def lay_flat_and_arrange(solids, rep: Report, printer: str | None, gap: float = 6.0):
    """Each part flat side down, packed in rows on the plate (for print-in-pieces-and-glue)."""
    plate_x = PRINTERS[printer][1][0] if printer else 250
    out, x, y, row_h = [], 0.0, 0.0, 0.0
    for n, m in sorted(solids, key=lambda s: -s[1].extents[:2].prod()):
        f, area = lay_flat(m)
        w, d = f.extents[0], f.extents[1]
        if x > 0 and x + w > plate_x:
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        f.apply_translation([x, y, 0])
        x += w + gap
        row_h = max(row_h, d)
        out.append((n, f))
        rep.step(f"print-flat: '{n}' on its {area:.0f} mm2 flat face, {f.extents[2]:.1f} mm tall")
    whole = trimesh.util.concatenate([m for _, m in out])
    c = (whole.bounds[0] + whole.bounds[1]) / 2
    for _, m in out:
        m.apply_translation([-c[0], -c[1], 0])
    rep.step(f"print-flat plate: {whole.extents[0]:.0f} x {whole.extents[1]:.0f} mm for {len(out)} parts")
    return out


# --------------------------------------------------------------------------- output


def export_3mf(objects: list[tuple[str, trimesh.Trimesh]], path: str, assembly_name: str = "model",
               colors: list | None = None) -> None:
    """3MF core spec, units mm. Several parts become ONE object built from components, so
    Bambu Studio / OrcaSlicer / PrusaSlicer load them as parts of one object in their
    assembled positions, and you give each part its own filament (AMS / MMU)."""
    import zipfile
    from xml.sax.saxutils import quoteattr

    def mesh_xml(m: trimesh.Trimesh) -> str:
        v = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in m.vertices)
        t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in m.faces)
        return f"<mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh>"

    res, build = [], []
    has_col = bool(colors) and len(objects) > 1 and any(colors)
    if has_col:
        bases = "".join(f'<base name={quoteattr(n)} displaycolor="#{(c or [200,200,200])[0]:02X}{(c or [200,200,200])[1]:02X}{(c or [200,200,200])[2]:02X}FF"/>'
                        for (n, _), c in zip(objects, colors))
        res.append(f'<basematerials id="1">{bases}</basematerials>')
    oid = 2
    ids = []
    for i, (n, m) in enumerate(objects):
        mat = f' pid="1" pindex="{i}"' if has_col else ""
        res.append(f'<object id="{oid}" name={quoteattr(n)} type="model"{mat}>{mesh_xml(m)}</object>')
        ids.append(oid)
        oid += 1
    if len(objects) == 1:
        build.append(f'<item objectid="{ids[0]}"/>')
    elif assembly_name is None:  # separate objects (a plate of loose parts)
        build.extend(f'<item objectid="{i}"/>' for i in ids)
    else:
        comps = "".join(f'<component objectid="{i}"/>' for i in ids)
        res.append(f'<object id="{oid}" name={quoteattr(assembly_name)} type="model"><components>{comps}</components></object>')
        build.append(f'<item objectid="{oid}"/>')
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             '<metadata name="Application">Sloyd 3D Print Shop print_prep.py</metadata>'
             f'<resources>{"".join(res)}</resources><build>{"".join(build)}</build></model>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


def render_preview(mesh: trimesh.Trimesh, stats: dict, path: str, tech: str, title: str) -> bool:
    """Shaded preview with overhangs tinted red (render.py, numpy + Pillow)."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import render as R
    except ImportError:
        return False
    s = stats["size_mm"]
    img = R.render(mesh, size=900, overhang_deg=TECH[tech]["overhang_deg"])
    sub = (f"{s[0]} x {s[1]} x {s[2]} mm  |  watertight: {'yes' if stats['watertight'] else 'NO'}  |  "
           f"red = overhang > {TECH[tech]['overhang_deg']:.0f} deg")
    R.overlay(img, title, sub).save(path)
    return True


def write_markdown(rep: Report, path: str) -> str:
    s = rep.stats
    L = [f"# Print prep report: {os.path.basename(rep.source)}", ""]
    L.append(f"- Size: **{s['size_mm'][0]} x {s['size_mm'][1]} x {s['size_mm'][2]} mm** (X x Y x Z)")
    L.append(f"- Watertight: **{'yes' if s['watertight'] else 'NO'}**, {s['bodies']} body(ies), {s['faces']:,} faces")
    if s.get("volume_cm3") is not None:
        L.append(f"- Volume: {s['volume_cm3']} cm3" + (f", about **{s['filament_estimate_g']} g** of {s['thresholds']['material']}" if "filament_estimate_g" in s else
                                                       f", about **{s.get('resin_estimate_ml')} ml** of resin"))
    if "printer" in s:
        L.append(f"- Printer: {s['printer']['name']}, fits: **{'yes' if s['printer']['fits'] else 'NO'}**")
    if "wall_thickness_mm" in s:
        w = s["wall_thickness_mm"]
        L.append(f"- Wall thickness: thinnest ~{w['min_p1']} mm (5th percentile {w['p5']} mm), {w['thin_area_pct']}% of the surface below the {s['thresholds']['min_wall']} mm minimum")
    o = s["overhangs"]
    L.append(f"- Overhangs > {o['limit_deg_from_vertical']:.0f} deg: {o['pct_of_surface']}% of surface; support islands: {s['support_islands']['count']}")
    if "stability" in s:
        L.append(f"- Bed contact: {s['stability']['contact_area_mm2']:.0f} mm2, centre of mass over base: {s['stability']['com_over_base']}")
    L += ["", "## Warnings", ""]
    L += [f"- **{w['code']}**: {w['message']} Fix: {w['fix']}" for w in rep.warnings] or ["- None. Ready to slice."]
    if rep.parts:
        L += ["", "## Parts (one filament each)", "", "| # | part | file | size mm | colour | AMS slot |", "|---|---|---|---|---|---|"]
        for i, p in enumerate(rep.parts, 1):
            col = p.get("color_rgb")
            slot = f"{p['slot']} ({p['slot_filament']})" if p.get("slot") else "-"
            L.append(f"| {i} | {p['name']} | {p['file']} | {' x '.join(str(x) for x in p['size_mm'])} | {('#%02x%02x%02x' % tuple(col)) if col else '-'} | {slot} |")
    L += ["", "## Steps", ""] + [f"1. {x}" for x in rep.steps]
    L += ["", "## Files", ""] + [f"- {k}: `{v}`" for k, v in rep.outputs.items()]
    text = "\n".join(L) + "\n"
    with open(path, "w") as fh:
        fh.write(text)
    return text


# --------------------------------------------------------------------------- main


def run(args) -> Report:
    rep = Report(source=args.input, settings={k: v for k, v in vars(args).items() if k != "input"})
    os.makedirs(args.out_dir, exist_ok=True)
    name = args.name or os.path.splitext(os.path.basename(args.input))[0]
    up = args.up or ("y" if args.input.lower().endswith((".glb", ".gltf")) else "z")

    parts = load_parts(args.input, up)
    rep.step(f"loaded {len(parts)} mesh part(s) from {os.path.basename(args.input)}, {'Y-up -> Z-up' if up == 'y' else 'Z-up'}")
    if args.rotate:
        rx, ry, rz = (math.radians(float(x)) for x in args.rotate.split(","))
        R = trimesh.transformations.euler_matrix(rx, ry, rz, "sxyz")
        for _, m in parts:
            m.apply_transform(R)
        rep.step(f"rotated by {args.rotate} deg (x,y,z)")

    colors = {n: part_color(m) for n, m in parts}
    measured = [c[0] for c in colors.values() if c]
    if len(parts) > 1 and measured and all(max(c) - min(c) < 12 for c in measured):
        rep.warn("no_texture_colour", "The model's texture has no colour (grayscale, e.g. an ambient-occlusion-only map), "
                 "so part colours can't be read from it.",
                 "Pass --colors with a filament per part name (see the concept image), or assign filaments in the slicer.")
    if args.colors:
        import fnmatch
        rules = [r.split("=", 1) for r in args.colors.split(",") if "=" in r]
        for pat, col in rules:
            if col.strip() not in FILAMENT_COLORS:
                raise ValueError(f"--colors: unknown filament '{col}'. Use one of: {', '.join(FILAMENT_COLORS)}")
        for n in colors:
            for pat, col in rules:  # first match wins
                if fnmatch.fnmatchcase(n, pat.strip()):
                    colors[n] = (list(FILAMENT_COLORS[col.strip()]), col.strip())
                    break
        rep.step(f"part colours set by name: {args.colors}")

    # scale to real millimetres
    whole = trimesh.util.concatenate([m for _, m in parts])
    ext = whole.extents
    if args.scale:
        s = args.scale
    elif args.height:
        s = args.height / ext[2]
    elif args.width:
        s = args.width / ext[0]
    elif args.depth:
        s = args.depth / ext[1]
    else:
        target = args.max_dim or 60.0
        if not args.max_dim:
            rep.warn("default_size", "No size given; scaled the longest side to 60 mm.", "Pass --height or --max-dim with the real size in mm.")
        s = target / ext.max()
    for _, m in parts:
        m.apply_scale(s)
    whole = trimesh.util.concatenate([m for _, m in parts])
    rep.step(f"scaled x{s:.4g} to {whole.extents[0]:.1f} x {whole.extents[1]:.1f} x {whole.extents[2]:.1f} mm")

    max_dim = whole.extents.max()
    pitch = args.voxel_pitch or max(0.2, max_dim / 300.0)

    # repair
    if args.parts:
        solids = []
        for n, m in parts:
            r = repair(m, args.repair, pitch, args.max_faces, rep, label=n)
            solids.append((n, r))
        # drop parts that are tiny AND touch nothing: they would print as loose specks
        vols = [abs(m.volume) for _, m in solids]
        kept = []
        for i, (n, m) in enumerate(solids):
            lo_i, hi_i = m.bounds
            touches = any(np.all(lo_i <= o.bounds[1] + 0.2) and np.all(hi_i >= o.bounds[0] - 0.2)
                          for j, (_, o) in enumerate(solids) if j != i)
            if vols[i] < 0.002 * max(vols) and not touches:
                rep.step(f"dropped part '{n}': a {vols[i]:.1f} mm3 speck not attached to anything")
                continue
            kept.append((n, m))
        solids = kept
    else:
        if len(parts) > 1:
            rep.step(f"merging {len(parts)} parts into one object (use --parts to keep them separate)")
        merged = trimesh.util.concatenate([m for _, m in parts])
        solids = [(name, drop_debris(repair(merged, args.repair, pitch, args.max_faces, rep, label=name), rep))]

    # rest on bed, centre on origin in XY
    allm = trimesh.util.concatenate([m for _, m in solids])
    lo, hi = allm.bounds
    shift = [-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]]
    for _, m in solids:
        m.apply_translation(shift)

    # flat base
    base = args.base
    label_mesh = plinth_mesh = None
    if args.label and base not in ("plinth",):
        base = "plinth"
        rep.step("--label given: using a plinth base")
    if base in ("auto", "flatten"):
        meshes, cut, ok = flatten_base([m for _, m in solids], rep)
        if ok or base == "flatten":
            names = [n for n, m in solids if m.bounds[1, 2] > cut]
            solids = list(zip(names, meshes))
        else:
            # undo: the cut wasn't enough for a stable footprint
            rep.step("no stable flat footprint within 6% of the height: adding a plinth instead")
            base = "plinth"
    if base == "plinth":
        moved, plinth_mesh, label_mesh = add_plinth([m for _, m in solids], args.plinth_height, args.label, rep)
        solids = [(n, m) for (n, _), m in zip(solids, moved)]
        if not args.parts:
            fused = union([solids[0][1], plinth_mesh])
            if fused is not None:
                solids = [(name, fused)]
                plinth_mesh = None
                rep.step("fused model and plinth into one solid" + (" (label kept as a 2nd object in the 3MF for a colour swap)" if label_mesh is not None else ""))
        if plinth_mesh is not None:
            solids.append(("plinth", plinth_mesh))
        if label_mesh is not None:
            solids.append(("label", label_mesh))

    # Debris removal and the base cut change the size, so fit the requested dimension exactly.
    # Sizes are for the finished print, base included.
    cur = trimesh.util.concatenate([m for _, m in solids]).extents
    want = None
    if args.height:
        want = args.height / cur[2]
    elif args.width:
        want = args.width / cur[0]
    elif args.depth:
        want = args.depth / cur[1]
    elif args.max_dim:
        want = args.max_dim / cur.max()
    if want is not None and abs(want - 1) > 1e-3:
        for _, m in solids:
            m.apply_scale(want)
        rep.step(f"re-fitted to the requested size (x{want:.4f}) after base and cleanup")
    dz = -trimesh.util.concatenate([m for _, m in solids]).bounds[0, 2]
    for _, m in solids:
        m.apply_translation([0, 0, dz])
    if args.explode and len(solids) > 1:
        layout_dir = os.path.join(args.out_dir, "print_flat")
        os.makedirs(layout_dir, exist_ok=True)
        flat = lay_flat_and_arrange(solids, rep, args.printer)
        for i, (n, m) in enumerate(flat, 1):
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in n)[:40]
            m.export(os.path.join(layout_dir, f"{name}_flat{i:02d}_{safe}.stl"))
        export_3mf(flat, os.path.join(args.out_dir, f"{name}_print_flat.3mf"), assembly_name=None)
        rep.outputs["print_flat_3mf"] = os.path.join(args.out_dir, f"{name}_print_flat.3mf")
        rep.outputs["print_flat_dir"] = layout_dir

    # One solid for the STL and the analysis: union the parts (they touch or overlap after the base step).
    if len(solids) == 1:
        final = solids[0][1]
    else:
        final = union([m for _, m in solids])
        if final is None:
            final = trimesh.util.concatenate([m for _, m in solids])
            rep.step("parts could not be unioned; the combined STL holds them as separate shells (slicers merge them)")
        else:
            rep.step(f"combined STL: {len(solids)} parts unioned into one solid")

    rep.stats = analyse(final, args.tech, args.nozzle, args.printer, args.samples, rep)

    # exports
    stl = os.path.join(args.out_dir, f"{name}.stl")
    final.export(stl)
    rep.outputs["stl"] = stl
    part_cols = []
    for n, _ in solids:
        c = colors.get(n)
        if n == "label":
            c = ([25, 25, 25], "black")
        elif n == "plinth":
            c = ([240, 240, 240], "white")
        part_cols.append(c)
    slots = assign_slots(part_cols, args.slots, rep) if len(solids) > 1 else [None] * len(solids)
    tmf = os.path.join(args.out_dir, f"{name}.3mf")
    export_3mf(solids, tmf, assembly_name=name, colors=[c[0] if c else None for c in part_cols])
    rep.outputs["3mf"] = tmf
    if args.parts or len(solids) > 1:
        pdir = os.path.join(args.out_dir, "parts")
        os.makedirs(pdir, exist_ok=True)
        for i, ((n, m), c) in enumerate(zip(solids, part_cols), 1):
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in n)[:40]
            f = os.path.join(pdir, f"{name}_part{i:02d}_{safe}.stl")
            m.export(f)
            sl = slots[i - 1]
            rep.parts.append({"name": n, "file": os.path.relpath(f, args.out_dir), "size_mm": [round(float(x), 1) for x in m.extents],
                              "watertight": bool(m.is_watertight), "color_rgb": c[0] if c else None, "filament": c[1] if c else None,
                              "slot": sl[0] if sl else None, "slot_filament": sl[1] if sl else None})
        rep.outputs["parts_dir"] = pdir
    if args.preview:
        png = os.path.join(args.out_dir, f"{name}_preview.png")
        if render_preview(final, rep.stats, png, args.tech, name):
            rep.outputs["preview"] = png
    rep.outputs["report_json"] = os.path.join(args.out_dir, "report.json")
    rep.outputs["report_md"] = os.path.join(args.out_dir, "report.md")
    with open(rep.outputs["report_json"], "w") as fh:
        json.dump({"source": rep.source, "settings": rep.settings, "stats": rep.stats, "warnings": rep.warnings,
                   "parts": rep.parts, "steps": rep.steps, "outputs": rep.outputs}, fh, indent=2, default=str)
    print(write_markdown(rep, rep.outputs["report_md"]))
    return rep


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="GLB/GLTF/OBJ/PLY/STL/3MF")
    p.add_argument("--out-dir", default="print_ready")
    p.add_argument("--name", help="output file stem (default: input name)")
    size = p.add_mutually_exclusive_group()
    size.add_argument("--height", type=float, help="final Z height in mm")
    size.add_argument("--max-dim", type=float, help="longest side in mm")
    size.add_argument("--width", type=float, help="final X width in mm")
    size.add_argument("--depth", type=float, help="final Y depth in mm")
    size.add_argument("--scale", type=float, help="raw scale factor")
    p.add_argument("--up", choices=["y", "z"], help="source up axis (default y for glTF, z otherwise)")
    p.add_argument("--rotate", help="extra rotation 'x,y,z' in degrees, applied after the up-axis fix")
    p.add_argument("--tech", choices=["fdm", "resin"], default="fdm")
    p.add_argument("--nozzle", type=float, default=0.4)
    p.add_argument("--printer", choices=sorted(PRINTERS), help="check the build-plate fit")
    p.add_argument("--base", choices=["auto", "flatten", "plinth", "none"], default="auto")
    p.add_argument("--plinth-height", type=float, default=3.0)
    p.add_argument("--label", help="raised text on a plinth, e.g. a pet's name")
    p.add_argument("--parts", action="store_true", help="keep each mesh as its own part (multi-colour / AMS)")
    p.add_argument("--explode", action="store_true",
                   help="with --parts: also write each part laid flat on its biggest flat face, arranged on one plate (print in pieces, then glue)")
    p.add_argument("--slots", type=int, default=4, help="filament slots available (AMS = 4, MMU3 = 5)")
    p.add_argument("--colors", help="filament per part by name, overriding the texture, e.g. 'Foot_*=orange,Head=brown,*=brown'. "
                                    f"Names: {', '.join(FILAMENT_COLORS)}")
    p.add_argument("--repair", choices=["auto", "voxel", "none"], default="auto")
    p.add_argument("--voxel-pitch", type=float, help="mm, default max(0.2, longest side / 300)")
    p.add_argument("--max-faces", type=int, default=300_000)
    p.add_argument("--samples", type=int, default=6000, help="ray samples for wall thickness")
    p.add_argument("--preview", action="store_true", help="also render a PNG preview (needs matplotlib)")
    a = p.parse_args(argv)
    if a.printer and a.tech == "fdm" and PRINTERS[a.printer][2] == "resin" and "--tech" not in (argv or sys.argv):
        a.tech = "resin"
    return a


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        run(args)
        return 0
    except Exception as e:  # report cleanly to the calling agent
        print(f"print_prep failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
