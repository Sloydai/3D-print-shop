"""Tests for skills/print-prep/scripts/print_prep.py on a messy sample GLB.

Run from the repo root:
    pip install -r skills/print-prep/scripts/requirements.txt pytest
    pytest tests -q
"""
import json
import os
import subprocess
import sys
import zipfile

import numpy as np
import pytest
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
TEAM = os.path.dirname(HERE)
SCRIPTS = os.path.join(TEAM, "skills", "print-prep", "scripts")
SCRIPT = os.path.join(SCRIPTS, "print_prep.py")
FIXTURE = os.path.join(HERE, "fixtures", "sample_owl.glb")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import print_prep  # noqa: E402
import make_sample_glb  # noqa: E402


@pytest.fixture(scope="session")
def sample_glb(tmp_path_factory):
    if os.path.exists(FIXTURE):
        return FIXTURE
    return make_sample_glb.main(str(tmp_path_factory.mktemp("fx") / "sample_owl.glb"))


def run_cli(*args):
    proc = subprocess.run([sys.executable, SCRIPT, *map(str, args)], capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return proc


def load_report(out):
    with open(os.path.join(out, "report.json")) as fh:
        return json.load(fh)


def test_fixture_is_actually_broken(sample_glb):
    """The sample must start out unprintable, or the other tests prove nothing."""
    scene = trimesh.load(sample_glb, force="scene")
    meshes = list(scene.geometry.values())
    assert len(meshes) >= 5
    assert not all(m.is_watertight for m in meshes), "fixture should contain an open shell"
    ext = trimesh.util.concatenate([m.copy() for m in meshes]).extents
    assert ext.max() < 1.0, "fixture should be in glTF metres, not mm"
    assert ext[1] == ext.max(), "fixture should be Y-up"


def test_glb_to_watertight_stl_and_3mf(sample_glb, tmp_path):
    out = tmp_path / "owl"
    run_cli(sample_glb, "--out-dir", out, "--height", 80, "--printer", "bambu-a1", "--preview")
    stl, tmf = out / "sample_owl.stl", out / "sample_owl.3mf"
    assert stl.exists() and tmf.exists() and (out / "report.md").exists() and (out / "sample_owl_preview.png").exists()

    m = trimesh.load(stl)
    assert m.is_watertight and m.is_winding_consistent and m.volume > 0
    assert len(m.split(only_watertight=False)) == 1, "floating speck should be removed, shells unioned"
    # scaled to real mm, Z-up, on the bed
    assert m.extents[2] == pytest.approx(80, abs=0.05)
    assert m.bounds[0, 2] == pytest.approx(0, abs=1e-6)
    assert m.extents[2] == m.extents.max()

    rep = load_report(out)
    s = rep["stats"]
    assert s["watertight"] is True
    assert s["printer"]["fits"] is True
    assert s["wall_thickness_mm"]["min_p1"] > 0
    assert "overhangs" in s and s["overhangs"]["area_mm2"] > 0  # the wing sticks out
    assert any(w["code"] == "overhangs" for w in rep["warnings"])
    assert s["filament_estimate_g"] > 0


def test_flat_base_gives_real_bed_contact(sample_glb, tmp_path):
    out = tmp_path / "flat"
    run_cli(sample_glb, "--out-dir", out, "--height", 80)
    m = trimesh.load(out / "sample_owl.stl")
    # the bottom is flat: there is a large cap of faces lying exactly on z=0, facing down
    on_bed = (np.abs(m.triangles_center[:, 2]) < 1e-4) & (m.face_normals[:, 2] < -0.99)
    assert m.area_faces[on_bed].sum() > 100  # mm2; the round-bottom original touched at a point
    assert load_report(out)["stats"]["stability"]["com_over_base"] is True


def test_3mf_is_mm_and_loads_back(sample_glb, tmp_path):
    out = tmp_path / "tmf"
    run_cli(sample_glb, "--out-dir", out, "--max-dim", 50)
    with zipfile.ZipFile(out / "sample_owl.3mf") as z:
        names = set(z.namelist())
        assert {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"} <= names
        model = z.read("3D/3dmodel.model").decode()
    assert 'unit="millimeter"' in model
    back = trimesh.load(out / "sample_owl.3mf", force="mesh")
    assert back.extents.max() == pytest.approx(50, abs=0.05)


def test_parts_mode_for_multicolour(sample_glb, tmp_path):
    out = tmp_path / "parts"
    run_cli(sample_glb, "--out-dir", out, "--height", 80, "--parts")
    rep = load_report(out)
    parts = rep["parts"]
    names = {p["name"] for p in parts}
    assert "speck" not in names, "loose speck must be dropped"
    assert {"body", "head", "beak"} <= names
    for p in parts:
        mesh = trimesh.load(out / p["file"])
        assert mesh.is_watertight, p["name"]
    beak = next(p for p in parts if p["name"] == "beak")
    assert beak["filament"] == "orange"
    eyes = [p for p in parts if p["name"].startswith("eye")]
    assert all(p["filament"] == "yellow" for p in eyes)
    # parts stay in their assembled positions: together they rebuild the full model's bounds
    allm = trimesh.util.concatenate([trimesh.load(out / p["file"]) for p in parts])
    combined = trimesh.load(out / "sample_owl.stl")
    assert np.allclose(allm.bounds, combined.bounds, atol=0.05)
    with zipfile.ZipFile(out / "sample_owl.3mf") as z:
        model = z.read("3D/3dmodel.model").decode()
    assert model.count("<component ") == len(parts)  # one object, many parts
    assert model.count("displaycolor=") == len(parts)


def test_plinth_with_name_label(sample_glb, tmp_path):
    out = tmp_path / "label"
    run_cli(sample_glb, "--out-dir", out, "--height", 90, "--label", "Hootie")
    rep = load_report(out)
    assert any(p["name"] == "label" for p in rep["parts"])
    m = trimesh.load(out / "sample_owl.stl")
    assert m.is_watertight
    assert m.extents[2] == pytest.approx(90, abs=0.05)
    label = trimesh.load(out / next(p["file"] for p in rep["parts"] if p["name"] == "label"))
    assert len(label.split()) == 6  # H O O T I E
    assert label.bounds[0, 2] < 3.5 and label.extents[2] < 1.6  # sits on the 3 mm plinth, 1 mm raised


def test_thin_walls_are_flagged(tmp_path):
    """A 0.5 mm fin must trigger the thin-wall warning for FDM (0.8 mm minimum with a 0.4 nozzle)."""
    fin = trimesh.creation.box(extents=[0.5, 30, 20])
    block = trimesh.creation.box(extents=[20, 20, 10])
    block.apply_translation([-10.25, 0, -5])
    fin.apply_translation([0, 0, 10])
    s = trimesh.Scene([block, fin])
    glb = tmp_path / "fin.glb"
    s.export(glb)
    out = tmp_path / "fin"
    run_cli(glb, "--out-dir", out, "--up", "z", "--scale", 1, "--base", "none")
    rep = load_report(out)
    assert any(w["code"] == "thin_walls" for w in rep["warnings"]), rep["warnings"]
    assert rep["stats"]["wall_thickness_mm"]["min_p1"] < 0.8


def test_too_big_for_printer_is_flagged(sample_glb, tmp_path):
    out = tmp_path / "big"
    run_cli(sample_glb, "--out-dir", out, "--height", 300, "--printer", "bambu-a1-mini")
    rep = load_report(out)
    assert rep["stats"]["printer"]["fits"] is False
    assert any(w["code"] == "too_big" for w in rep["warnings"])


def test_resin_thresholds(sample_glb, tmp_path):
    out = tmp_path / "resin"
    run_cli(sample_glb, "--out-dir", out, "--height", 60, "--printer", "elegoo-saturn-4-ultra")
    s = load_report(out)["stats"]
    assert s["tech"] == "resin"
    assert s["thresholds"]["min_wall"] == 0.4
    assert "resin_estimate_ml" in s


def test_voxel_rebuild_closes_anything(sample_glb, tmp_path):
    out = tmp_path / "vox"
    run_cli(sample_glb, "--out-dir", out, "--height", 50, "--repair", "voxel", "--voxel-pitch", 0.4)
    m = trimesh.load(out / "sample_owl.stl")
    assert m.is_watertight
    # solid, not a hollow shell: volume close to the regular repair's volume
    ref = tmp_path / "ref"
    run_cli(sample_glb, "--out-dir", ref, "--height", 50)
    assert m.volume == pytest.approx(trimesh.load(ref / "sample_owl.stl").volume, rel=0.12)


def test_open_box_gets_closed():
    box = trimesh.creation.box(extents=[10, 10, 10])
    box.update_faces(box.face_normals[:, 2] < 0.99)  # remove the whole top side
    box.remove_unreferenced_vertices()
    assert not box.is_watertight
    assert print_prep.fill_boundary_loops(box) == 1
    assert box.is_watertight and box.volume == pytest.approx(1000, rel=1e-6)


def test_ams_slots_merge_to_available_slots(sample_glb, tmp_path):
    out = tmp_path / "slots"
    run_cli(sample_glb, "--out-dir", out, "--height", 80, "--parts", "--slots", 2)
    parts = load_report(out)["parts"]
    assert {p["slot"] for p in parts} <= {1, 2}
    by_name = {p["name"]: p for p in parts}
    assert by_name["eye_0"]["slot"] == by_name["eye_1"]["slot"]  # same colour shares a slot
    assert by_name["body"]["slot"] == by_name["head"]["slot"]    # both brown


def test_explode_lays_parts_flat_on_one_plate(sample_glb, tmp_path):
    out = tmp_path / "flat"
    run_cli(sample_glb, "--out-dir", out, "--height", 80, "--parts", "--explode", "--printer", "bambu-a1")
    rep = load_report(out)
    files = sorted(os.listdir(rep["outputs"]["print_flat_dir"]))
    assert len(files) == len(rep["parts"])
    for f in files:
        m = trimesh.load(os.path.join(rep["outputs"]["print_flat_dir"], f))
        assert m.bounds[0, 2] == pytest.approx(0, abs=1e-6)
    plate = trimesh.load(rep["outputs"]["print_flat_3mf"], force="mesh")
    assert plate.extents[0] <= 256 and plate.extents[1] <= 256


def test_colors_override_by_part_name(sample_glb, tmp_path):
    out = tmp_path / "override"
    run_cli(sample_glb, "--out-dir", out, "--height", 80, "--parts", "--colors", "beak=red,eye_*=black,*=white")
    by_name = {p["name"]: p for p in load_report(out)["parts"]}
    assert by_name["beak"]["filament"] == "red"
    assert by_name["eye_0"]["filament"] == by_name["eye_1"]["filament"] == "black"
    assert by_name["body"]["filament"] == "white"
    assert len({p["slot"] for p in by_name.values()}) == 3
