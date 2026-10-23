"""Accès à l'instance KiCad ouverte via l'API IPC (kicad-python).

L'API IPC doit être activée dans KiCad (Préférences > Plugins > Enable KiCad API) ;
l'image Docker fournie l'active d'office. Elle agit sur l'éditeur PCB ouvert :
les modifications apparaissent en direct dans la fenêtre KiCad.
"""

from __future__ import annotations

from pathlib import Path

from kipy import KiCad
from kipy.geometry import Angle, Vector2
from kipy.proto.board.board_types_pb2 import BoardLayer
from kipy.proto.common.types.base_types_pb2 import DocumentType

from . import config
from .errors import AtelierError

NM_PER_MM = 1_000_000


class KiCadUnavailable(AtelierError):
    pass


def _mm(v: int | float) -> float:
    return round(v / NM_PER_MM, 4)


def connect() -> KiCad:
    try:
        kicad = KiCad(socket_path=config.KICAD_API_SOCKET, client_name="atelier-pcb", timeout_ms=5000)
        kicad.ping()
        return kicad
    except Exception as exc:  # noqa: BLE001 - message clair pour Claude
        raise KiCadUnavailable(
            f"KiCad injoignable sur {config.KICAD_API_SOCKET} ({exc}). "
            "Vérifie que KiCad tourne et que l'éditeur PCB est ouvert."
        ) from exc


def status() -> dict:
    kicad = connect()
    boards = kicad.get_open_documents(DocumentType.DOCTYPE_PCB)
    return {
        "kicad_version": str(kicad.get_version()),
        "open_boards": [
            str(Path(d.project.path) / d.board_filename) for d in boards
        ],
    }


def get_board():
    kicad = connect()
    try:
        return kicad.get_board()
    except Exception as exc:  # noqa: BLE001
        raise KiCadUnavailable(
            "Aucune carte ouverte dans l'éditeur PCB de KiCad. Ouvre le .kicad_pcb dans la fenêtre KiCad."
        ) from exc


def open_board_path() -> str | None:
    try:
        board = get_board()
    except KiCadUnavailable:
        return None
    doc = board.document
    return str(Path(doc.project.path) / doc.board_filename)


def _ref(fp) -> str:
    return fp.reference_field.text.value


def _footprint_info(fp) -> dict:
    pos = fp.position
    lib = fp.definition.id
    return {
        "ref": _ref(fp),
        "value": fp.value_field.text.value,
        "footprint": f"{lib.library}:{lib.name}",
        "x_mm": _mm(pos.x),
        "y_mm": _mm(pos.y),
        "rotation_deg": round(fp.orientation.degrees, 2),
        "side": "back" if fp.layer == BoardLayer.BL_B_Cu else "front",
        "locked": bool(fp.locked),
    }


def board_outline(board) -> dict | None:
    """Rectangle englobant du contour (Edge.Cuts), en mm, repère KiCad (Y vers le bas)."""
    edges = [s for s in board.get_shapes() if s.layer == BoardLayer.BL_Edge_Cuts]
    if not edges:
        return None
    raw = board.get_item_bounding_box(edges)
    boxes = [b for b in (raw if isinstance(raw, list) else [raw]) if b is not None]
    if not boxes:
        return None
    box = boxes[0]
    for b in boxes[1:]:
        box.merge(b)
    c = box.center()
    return {
        "min_mm": [_mm(box.pos.x), _mm(box.pos.y)],
        "size_mm": [_mm(box.size.x), _mm(box.size.y)],
        "center_mm": [_mm(c.x), _mm(c.y)],
    }


def project_summary() -> dict:
    board = get_board()
    footprints = [_footprint_info(fp) for fp in board.get_footprints()]
    return {
        "board_file": open_board_path(),
        "outline": board_outline(board),
        "copper_layers": board.get_copper_layer_count(),
        "nets": len(board.get_nets()),
        "footprints": footprints,
    }


def mounting_holes_relative() -> list[tuple[float, float]]:
    """Trous de fixation (empreintes MountingHole*) relatifs au centre de la carte, Y vers le haut.

    C'est le repère attendu par le module mécanique, indépendant de l'origine d'export STEP.
    """
    board = get_board()
    outline = board_outline(board)
    if not outline:
        return []
    cx, cy = outline["center_mm"]
    holes = []
    for fp in board.get_footprints():
        lib = fp.definition.id
        if "mountinghole" in f"{lib.library}{lib.name}".lower():
            holes.append((round(_mm(fp.position.x) - cx, 3), round(-(_mm(fp.position.y) - cy), 3)))
    return holes


def move_footprint(ref: str, x_mm: float | None = None, y_mm: float | None = None,
                   rotation_deg: float | None = None) -> dict:
    board = get_board()
    matches = [fp for fp in board.get_footprints() if _ref(fp) == ref]
    if not matches:
        raise AtelierError(f"Empreinte {ref} introuvable sur la carte.")
    fp = matches[0]
    if fp.locked:
        raise AtelierError(f"{ref} est verrouillée dans KiCad.")
    pos = fp.position
    commit = board.begin_commit()
    try:
        fp.position = Vector2.from_xy(
            int(round(x_mm * NM_PER_MM)) if x_mm is not None else pos.x,
            int(round(y_mm * NM_PER_MM)) if y_mm is not None else pos.y,
        )
        if rotation_deg is not None:
            fp.orientation = Angle.from_degrees(rotation_deg)
        board.update_items([fp])
        board.push_commit(commit, f"Claude : déplacement de {ref}")
    except Exception:
        board.drop_commit(commit)
        raise
    updated = next(f for f in board.get_footprints() if _ref(f) == ref)
    return _footprint_info(updated)


def save_board() -> None:
    get_board().save()
