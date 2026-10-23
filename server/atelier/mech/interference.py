"""Vérification d'assemblage : collisions (volume commun) et jeux insuffisants (distance mini)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import build123d as bd

from .board import Part
from .enclosure import Enclosure

VOLUME_EPS = 1e-3  # mm³ : en dessous, simple contact de surfaces


@dataclass
class Finding:
    kind: str          # "collision" | "tight"
    a: str
    b: str
    volume_mm3: float | None
    distance_mm: float | None
    at_mm: list[float] | None


def _bbox_overlap(a: bd.BoundBox, b: bd.BoundBox, margin: float) -> bool:
    return not (
        a.max.X + margin < b.min.X or b.max.X + margin < a.min.X
        or a.max.Y + margin < b.min.Y or b.max.Y + margin < a.min.Y
        or a.max.Z + margin < b.min.Z or b.max.Z + margin < a.min.Z
    )


def _check_pair(a: Part, b: Part, min_gap: float, check_gap: bool) -> tuple[Finding | None, bd.Shape | None]:
    if not _bbox_overlap(a.bbox, b.bbox, min_gap):
        return None, None
    common = a.shape & b.shape
    volume = float(getattr(common, "volume", 0.0) or 0.0)
    if volume > VOLUME_EPS:
        c = common.bounding_box().center()
        return Finding("collision", a.label, b.label, round(volume, 3), None,
                       [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)]), common
    if check_gap:
        d = a.shape.distance_to(b.shape)
        if 0 < d < min_gap:
            return Finding("tight", a.label, b.label, None, round(d, 3), None), None
    return None, None


def check_interference(enc: Enclosure, min_gap: float = 0.3) -> tuple[dict, bd.Compound | None]:
    """Teste fond et couvercle contre chaque solide de la carte, puis fond contre couvercle.

    Le contact plot/substrat (distance 0) est attendu et n'est pas signalé.
    """
    base = Part("boitier_fond", enc.base)
    lid = Part("boitier_couvercle", enc.lid)
    findings: list[Finding] = []
    overlaps: list[bd.Shape] = []

    for shell in (base, lid):
        for part in enc.board.all_parts():
            is_contact_expected = shell is base and part is enc.board.substrate
            f, common = _check_pair(shell, part, min_gap, check_gap=not is_contact_expected)
            if f:
                findings.append(f)
            if common is not None:
                overlaps.append(common)

    f, common = _check_pair(base, lid, min_gap, check_gap=False)
    if f:
        findings.append(f)
    if common is not None:
        overlaps.append(common)

    collisions = [f for f in findings if f.kind == "collision"]
    report = {
        "ok": not collisions,
        "min_gap_mm": min_gap,
        "collisions": len(collisions),
        "tight": len(findings) - len(collisions),
        "findings": [asdict(f) for f in findings],
    }
    return report, (bd.Compound(overlaps) if overlaps else None)
