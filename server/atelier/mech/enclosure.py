"""Génération d'un boîtier imprimable en deux pièces (fond + couvercle) autour d'une carte."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import build123d as bd

from .board import BoardModel

Side = Literal["+x", "-x", "+y", "-y"]
BOTTOM = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


@dataclass
class Cutout:
    """Découpe rectangulaire dans une paroi (connecteur USB, jack, LED...).

    offset : position le long de la paroi, depuis le centre de la carte (mm)
    z      : hauteur du centre de la découpe au-dessus de la face supérieure du PCB (mm)
    """

    side: Side
    offset: float
    z: float
    width: float
    height: float


@dataclass
class EnclosureParams:
    wall: float = 2.0             # épaisseur des parois
    floor: float = 2.0            # épaisseur du fond
    lid: float = 2.0              # épaisseur du couvercle
    xy_clearance: float = 1.0     # jeu entre le bord du PCB et la paroi intérieure
    top_clearance: float = 2.0    # jeu au-dessus du composant le plus haut
    bottom_clearance: float = 1.0 # jeu sous le point le plus bas de la carte
    standoff_height: float | None = None  # None = calcul auto
    standoff_od: float = 6.0      # diamètre extérieur des plots
    screw_hole: float = 2.5       # perçage des plots (2,5 = vis M3 autotaraudeuse)
    lid_fit: float = 0.25         # jeu d'emboîtement de la lèvre du couvercle
    lip_height: float = 3.0
    lip_width: float = 1.2
    holes: list[tuple[float, float]] = field(default_factory=list)  # trous de fixation (repère carte, mm)
    cutouts: list[Cutout] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None) -> "EnclosureParams":
        data = dict(data or {})
        data["holes"] = [tuple(h) for h in data.get("holes", [])]
        data["cutouts"] = [c if isinstance(c, Cutout) else Cutout(**c) for c in data.get("cutouts", [])]
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Enclosure:
    base: bd.Part
    lid: bd.Part
    board: BoardModel      # carte déjà positionnée dans le boîtier
    params: EnclosureParams
    dims: dict


def _corner_posts(board: BoardModel, inset: float = 2.5) -> list[tuple[float, float]]:
    hx, hy = board.size_x / 2 - inset, board.size_y / 2 - inset
    return [(hx, hy), (-hx, hy), (hx, -hy), (-hx, -hy)]


def _wall_cutout(c: Cutout, inner_x: float, inner_y: float, wall: float, z_center: float) -> bd.Part:
    depth = wall * 3  # traverse la paroi avec de la marge
    if c.side in ("+x", "-x"):
        x = (inner_x / 2 + wall / 2) * (1 if c.side == "+x" else -1)
        box = bd.Box(depth, c.width, c.height)
        return bd.Pos(x, c.offset, z_center) * box
    y = (inner_y / 2 + wall / 2) * (1 if c.side == "+y" else -1)
    box = bd.Box(c.width, depth, c.height)
    return bd.Pos(c.offset, y, z_center) * box


def build_enclosure(board: BoardModel, params: EnclosureParams | None = None) -> Enclosure:
    p = params or EnclosureParams()

    below = max(0.0, -board.z_min)                      # ce qui dépasse sous la carte
    above = max(0.0, board.z_max - board.thickness)     # ce qui dépasse au-dessus
    standoff_h = p.standoff_height if p.standoff_height is not None else max(3.0, below + p.bottom_clearance)

    inner_x = board.size_x + 2 * p.xy_clearance
    inner_y = board.size_y + 2 * p.xy_clearance
    inner_h = standoff_h + board.thickness + above + p.top_clearance
    outer_x, outer_y = inner_x + 2 * p.wall, inner_y + 2 * p.wall
    base_h = p.floor + inner_h
    board_z = p.floor + standoff_h   # face inférieure du PCB dans le boîtier

    # --- Fond : coque ouverte + plots ---
    base = bd.Box(outer_x, outer_y, base_h, align=BOTTOM)
    base -= bd.Pos(0, 0, p.floor) * bd.Box(inner_x, inner_y, inner_h + 1, align=BOTTOM)

    posts = p.holes or _corner_posts(board)
    for x, y in posts:
        post = bd.Pos(x, y, p.floor) * bd.Cylinder(p.standoff_od / 2, standoff_h, align=BOTTOM)
        base += post
        if p.holes:
            # perçage borgne depuis le haut du plot, on laisse 0,6 mm de fond
            base -= bd.Pos(x, y, 0.6) * bd.Cylinder(p.screw_hole / 2, board_z - 0.6, align=BOTTOM)

    for c in p.cutouts:
        z_center = board_z + board.thickness + c.z
        base -= _wall_cutout(c, inner_x, inner_y, p.wall, z_center)

    # --- Couvercle : plaque + lèvre d'emboîtement ---
    lid = bd.Pos(0, 0, base_h) * bd.Box(outer_x, outer_y, p.lid, align=BOTTOM)
    lip_out_x, lip_out_y = inner_x - 2 * p.lid_fit, inner_y - 2 * p.lid_fit
    lip = bd.Box(lip_out_x, lip_out_y, p.lip_height, align=BOTTOM)
    lip -= bd.Box(lip_out_x - 2 * p.lip_width, lip_out_y - 2 * p.lip_width, p.lip_height + 1, align=BOTTOM)
    lid += bd.Pos(0, 0, base_h - p.lip_height) * lip

    placed = BoardModel(
        substrate=_move(board.substrate, board_z),
        components=[_move(c, board_z) for c in board.components],
    )
    dims = {
        "outer_mm": [round(outer_x, 2), round(outer_y, 2), round(base_h + p.lid, 2)],
        "inner_mm": [round(inner_x, 2), round(inner_y, 2), round(inner_h, 2)],
        "board_mm": [round(board.size_x, 2), round(board.size_y, 2), round(board.thickness, 2)],
        "standoff_height_mm": round(standoff_h, 2),
        "board_bottom_z_mm": round(board_z, 2),
        "posts": [list(map(lambda v: round(v, 2), xy)) for xy in posts],
        "posts_are_screw_holes": bool(p.holes),
    }
    return Enclosure(base=base, lid=lid, board=placed, params=p, dims=dims)


def _move(part, dz: float):
    from .board import Part

    return Part(part.label, part.shape.moved(bd.Location((0, 0, dz))))
