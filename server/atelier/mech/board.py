"""Chargement du STEP exporté par KiCad et normalisation du repère.

Convention du module mécanique (indépendante de l'origine choisie à l'export) :
- X/Y : centre du substrat PCB en (0, 0), Y vers le haut (repère STEP, pas KiCad) ;
- Z   : face inférieure du substrat en z = 0, face supérieure en z = épaisseur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import build123d as bd

# Un substrat PCB fait en pratique entre 0,4 et 3,2 mm d'épaisseur.
SUBSTRATE_MIN_THICKNESS = 0.3
SUBSTRATE_MAX_THICKNESS = 3.5


@dataclass
class Part:
    label: str
    shape: bd.Shape

    @property
    def bbox(self) -> bd.BoundBox:
        return self.shape.bounding_box()


@dataclass
class BoardModel:
    substrate: Part
    components: list[Part] = field(default_factory=list)

    @property
    def thickness(self) -> float:
        return self.substrate.bbox.size.Z

    @property
    def size_x(self) -> float:
        return self.substrate.bbox.size.X

    @property
    def size_y(self) -> float:
        return self.substrate.bbox.size.Y

    @property
    def z_min(self) -> float:
        """Point le plus bas (broches traversantes, composants face arrière)."""
        return min([self.substrate.bbox.min.Z] + [c.bbox.min.Z for c in self.components])

    @property
    def z_max(self) -> float:
        """Point le plus haut (composant le plus grand côté face avant)."""
        return max([self.substrate.bbox.max.Z] + [c.bbox.max.Z for c in self.components])

    def all_parts(self) -> list[Part]:
        return [self.substrate, *self.components]

    def as_compound(self) -> bd.Compound:
        return bd.Compound([p.shape for p in self.all_parts()])


def _solid_labels(root: bd.Shape) -> list[str]:
    """Nom de chaque solide, dans l'ordre de root.solids().

    Les feuilles de l'arbre STEP sont en coordonnées locales, mais leur ordre en
    profondeur est le même que celui de root.solids() (coordonnées globales) : on
    ne garde que les noms. Pour un export KiCad, le chemin ressemble à
    [carte, R1, R_0603_...] : on retient le premier nom sous la racine (la référence).
    """
    root_label = (root.label or "").strip()
    labels: list[str] = []

    def walk(shape: bd.Shape, path: list[str]) -> None:
        children = list(getattr(shape, "children", None) or [])
        here = path + [(shape.label or "").strip()]
        if not children:
            meaningful = [l for l in here if l and l != root_label]
            name = meaningful[0] if meaningful else ""
            labels.extend([name] * len(shape.solids()))
            return
        for child in children:
            walk(child, here)

    walk(root, [])
    total = len(root.solids())
    if len(labels) != total:
        return [f"solid_{i}" for i in range(total)]
    # Noms uniques pour le rapport (R1, R1#2...)
    seen: dict[str, int] = {}
    unique = []
    for i, name in enumerate(labels):
        name = name or f"solid_{i}"
        seen[name] = seen.get(name, 0) + 1
        unique.append(name if seen[name] == 1 else f"{name}#{seen[name]}")
    return unique


def _pick_substrate(parts: list[Part]) -> Part:
    candidates = [
        p for p in parts
        if SUBSTRATE_MIN_THICKNESS <= p.bbox.size.Z <= SUBSTRATE_MAX_THICKNESS
    ]
    if not candidates:
        raise ValueError(
            "Impossible d'identifier le substrat PCB dans le STEP "
            "(aucun solide plat d'épaisseur 0,3–3,5 mm)."
        )
    return max(candidates, key=lambda p: p.bbox.size.X * p.bbox.size.Y)


def load_board(step_path: str | Path) -> BoardModel:
    """Charge le STEP d'une carte et le ramène dans le repère normalisé."""
    compound = bd.import_step(str(step_path))
    solids = compound.solids()
    if not solids:
        raise ValueError(f"Aucun solide trouvé dans {step_path}")

    parts = [Part(label, s) for label, s in zip(_solid_labels(compound), solids)]
    substrate = _pick_substrate(parts)

    bb = substrate.bbox
    offset = bd.Location((-bb.center().X, -bb.center().Y, -bb.min.Z))
    moved = [Part(p.label, p.shape.moved(offset)) for p in parts]
    new_substrate = next(m for m, p in zip(moved, parts) if p is substrate)
    components = [m for m, p in zip(moved, parts) if p is not substrate]
    return BoardModel(substrate=new_substrate, components=components)
