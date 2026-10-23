"""Tests du module mécanique sur une carte synthétique (pas besoin de KiCad)."""

import json
from pathlib import Path

import build123d as bd
import pytest

from atelier.mech import EnclosureParams, build_enclosure, check_interference, load_board, run

BOTTOM = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


def make_board_step(path: Path, tall: float = 8.0, origin=(120.0, -80.0)) -> Path:
    """Carte 50x30x1,6 décentrée (comme un export KiCad), un composant haut et des broches dessous."""
    ox, oy = origin
    substrate = bd.Pos(ox, oy, 0) * bd.Box(50, 30, 1.6, align=BOTTOM)
    substrate.label = "PCB"
    tall_part = bd.Pos(ox + 10, oy, 1.6) * bd.Box(10, 10, tall, align=BOTTOM)
    tall_part.label = "U1"
    pins = bd.Pos(ox - 15, oy + 5, -2.5) * bd.Box(2, 8, 2.5, align=BOTTOM)
    pins.label = "J1_pins"
    bd.export_step(bd.Compound(children=[substrate, tall_part, pins], label="carte"), str(path))
    return path


@pytest.fixture
def board_step(tmp_path):
    return make_board_step(tmp_path / "carte.step")


def test_load_board_normalise_le_repere(board_step):
    board = load_board(board_step)
    assert board.size_x == pytest.approx(50, abs=1e-3)
    assert board.size_y == pytest.approx(30, abs=1e-3)
    assert board.thickness == pytest.approx(1.6, abs=1e-3)
    c = board.substrate.bbox.center()
    assert (c.X, c.Y) == pytest.approx((0, 0), abs=1e-3)
    assert board.z_min == pytest.approx(-2.5, abs=1e-3)
    assert board.z_max == pytest.approx(9.6, abs=1e-3)


def test_boitier_par_defaut_sans_collision(board_step):
    enc = build_enclosure(load_board(board_step), EnclosureParams(holes=[(-21, -11), (21, 11)]))
    # plot assez haut pour passer sous les broches de 2,5 mm
    assert enc.dims["standoff_height_mm"] >= 3.5
    report, overlaps = check_interference(enc)
    assert report["ok"], report
    assert overlaps is None


def test_collision_detectee_si_couvercle_trop_bas(board_step):
    params = EnclosureParams(top_clearance=-3.0)  # le couvercle écrase U1
    report, overlaps = check_interference(build_enclosure(load_board(board_step), params))
    assert not report["ok"]
    assert any(f["b"] == "U1" and f["a"] == "boitier_couvercle" for f in report["findings"])
    assert overlaps is not None


def test_jeu_insuffisant_signale(board_step):
    params = EnclosureParams(top_clearance=0.1)
    report, _ = check_interference(build_enclosure(load_board(board_step), params), min_gap=0.3)
    assert report["ok"]
    assert any(f["kind"] == "tight" and f["b"] == "U1" for f in report["findings"])


def test_pipeline_ecrit_les_fichiers(board_step, tmp_path):
    out = tmp_path / "out"
    result = run(board_step, out, {"cutouts": [{"side": "-x", "offset": 5, "z": 2, "width": 9, "height": 4}]})
    for name in ["boitier_fond.stl", "boitier_couvercle.stl", "boitier.3mf",
                 "carte.glb", "fond.glb", "couvercle.glb", "rapport.json", "manifest.json"]:
        assert (out / name).stat().st_size > 0, name
    assert result["interference"]["ok"]
    assert json.loads((out / "manifest.json").read_text())["ok"] is True
