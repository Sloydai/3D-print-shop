#!/usr/bin/env python3
"""Build tests/fixtures/sample_owl.glb: a deliberately messy, Y-up, multi-part GLB that looks like
what AI 3D generators return. It has the problems print_prep must fix:

- glTF units (about 0.1 m tall) and Y-up
- overlapping shells (head sunk into body), so it needs a boolean union
- a hole in the body (missing faces), so it isn't watertight
- a round bottom with almost no bed contact, so it needs a flat base
- a floating speck that isn't attached to anything
- thin ear tufts and a wing that sticks out (overhang)
- per-part colours, for the multi-colour path
"""
import os
import sys

import numpy as np
import trimesh


def colored(mesh, rgb):
    mesh.visual.face_colors = np.tile(np.array([*rgb, 255], np.uint8), (len(mesh.faces), 1))
    return mesh


def build() -> trimesh.Scene:
    body = trimesh.creation.icosphere(subdivisions=4, radius=0.035)
    body.apply_scale([1.0, 1.15, 0.9])  # Y is up in glTF
    body.apply_translation([0, 0.040, 0])
    # punch a hole: drop faces in a small patch on the back
    c = body.triangles_center
    keep = ~((c[:, 2] < -0.025) & (np.abs(c[:, 0]) < 0.006) & (np.abs(c[:, 1] - 0.045) < 0.006))
    body.update_faces(keep)
    body.remove_unreferenced_vertices()

    head = trimesh.creation.icosphere(subdivisions=4, radius=0.026)
    head.apply_translation([0, 0.088, 0.002])  # overlaps the body

    ears = []
    for sx in (-1, 1):
        ear = trimesh.creation.cone(radius=0.0045, height=0.022, sections=24)
        ear.apply_transform(trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0]))  # point +Y
        ear.apply_transform(trimesh.transformations.rotation_matrix(sx * 0.35, [0, 0, 1]))
        ear.apply_translation([sx * 0.016, 0.104, 0])
        ears.append(ear)

    eyes = []
    for sx in (-1, 1):
        eye = trimesh.creation.icosphere(subdivisions=2, radius=0.0075)
        eye.apply_translation([sx * 0.011, 0.092, 0.022])
        eyes.append(eye)

    beak = trimesh.creation.cone(radius=0.004, height=0.010, sections=16)
    beak.apply_translation([0, 0.083, 0.024])

    wing = trimesh.creation.box(extents=[0.030, 0.006, 0.020])  # sticks straight out: an overhang
    wing.apply_transform(trimesh.transformations.rotation_matrix(0.25, [0, 0, 1]))
    wing.apply_translation([0.045, 0.045, 0])

    speck = trimesh.creation.icosphere(subdivisions=1, radius=0.0012)
    speck.apply_translation([0.0, 0.135, 0.0])  # floating above the head

    scene = trimesh.Scene()
    scene.add_geometry(colored(body, (120, 80, 45)), node_name="body", geom_name="body")
    scene.add_geometry(colored(head, (150, 105, 60)), node_name="head", geom_name="head")
    for i, e in enumerate(ears):
        scene.add_geometry(colored(e, (95, 60, 35)), node_name=f"ear_{i}", geom_name=f"ear_{i}")
    for i, e in enumerate(eyes):
        scene.add_geometry(colored(e, (245, 205, 40)), node_name=f"eye_{i}", geom_name=f"eye_{i}")
    scene.add_geometry(colored(beak, (240, 120, 30)), node_name="beak", geom_name="beak")
    scene.add_geometry(colored(wing, (110, 70, 40)), node_name="wing", geom_name="wing")
    scene.add_geometry(colored(speck, (30, 30, 30)), node_name="speck", geom_name="speck")
    return scene


def main(out: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    build().export(out)
    return out


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    print(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "fixtures", "sample_owl.glb")))
