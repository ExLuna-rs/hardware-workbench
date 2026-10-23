"""Enchaîne : STEP carte -> boîtier -> check d'assemblage -> fichiers (impression + viewer)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import build123d as bd

from .board import load_board
from .enclosure import EnclosureParams, build_enclosure
from .interference import check_interference

# Maillage du viewer : assez fin pour juger visuellement, assez léger pour le navigateur.
VIEW_DEFLECTION = 0.05
VIEW_ANGULAR = 0.3


def _glb(shape: bd.Shape, path: Path) -> None:
    bd.export_gltf(shape, str(path), binary=True,
                   linear_deflection=VIEW_DEFLECTION, angular_deflection=VIEW_ANGULAR)


def write_manifest(out_dir: Path, extra: dict | None = None) -> dict:
    files = sorted(p.name for p in out_dir.iterdir() if p.is_file() and p.name != "manifest.json")
    manifest = {"updated": time.time(), "files": files, **(extra or {})}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def run(board_step: str | Path, out_dir: str | Path, params: dict | EnclosureParams | None = None,
        min_gap: float = 0.3) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = params if isinstance(params, EnclosureParams) else EnclosureParams.from_dict(params)

    board = load_board(board_step)
    enc = build_enclosure(board, p)
    report, overlaps = check_interference(enc, min_gap=min_gap)

    # Fichiers d'impression (repère : fond posé sur le plateau en z = 0)
    bd.export_step(enc.base, str(out / "boitier_fond.step"))
    bd.export_step(enc.lid, str(out / "boitier_couvercle.step"))
    bd.export_stl(enc.base, str(out / "boitier_fond.stl"), tolerance=0.01, angular_tolerance=0.2)
    # Couvercle retourné pour l'impression (plaque sur le plateau, lèvre vers le haut)
    lid_print = enc.lid.rotate(bd.Axis.X, 180)
    lid_print = lid_print.moved(bd.Location((0, 0, -lid_print.bounding_box().min.Z)))
    bd.export_stl(lid_print, str(out / "boitier_couvercle.stl"), tolerance=0.01, angular_tolerance=0.2)
    mesher = bd.Mesher()
    mesher.add_shape(enc.base, linear_deflection=0.01, angular_deflection=0.2, part_number="fond")
    mesher.add_shape(lid_print.moved(bd.Location((enc.dims["outer_mm"][0] + 10, 0, 0))),
                     linear_deflection=0.01, angular_deflection=0.2, part_number="couvercle")
    mesher.write(str(out / "boitier.3mf"))

    # Fichiers du viewer (repère d'assemblage)
    _glb(enc.board.as_compound(), out / "carte.glb")
    _glb(enc.base, out / "fond.glb")
    _glb(enc.lid, out / "couvercle.glb")
    collisions_glb = out / "collisions.glb"
    if overlaps is not None:
        _glb(overlaps, collisions_glb)
    elif collisions_glb.exists():
        collisions_glb.unlink()

    result = {"dims": enc.dims, "params": p.to_dict(), "interference": report}
    (out / "rapport.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    write_manifest(out, {"ok": report["ok"]})
    return result
