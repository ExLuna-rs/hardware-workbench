"""Résolution des projets KiCad dans le dossier partagé."""

from __future__ import annotations

from pathlib import Path

from . import config
from .errors import AtelierError


class ProjectError(AtelierError):
    pass


def list_projects() -> list[dict]:
    root = config.PROJECTS_DIR
    if not root.exists():
        return []
    projects = []
    for pro in sorted(root.glob("*/*.kicad_pro")):
        pcb = pro.with_suffix(".kicad_pcb")
        projects.append({
            "name": pro.parent.name,
            "project_file": str(pro),
            "has_pcb": pcb.exists(),
        })
    return projects


def resolve_pcb(project: str | None = None, open_board_path: str | None = None) -> Path:
    """Trouve le .kicad_pcb à utiliser.

    project : nom du dossier dans /projects (prioritaire)
    open_board_path : chemin de la carte ouverte dans KiCad (via l'API IPC)
    """
    if project:
        folder = (config.PROJECTS_DIR / project).resolve()
        if config.PROJECTS_DIR.resolve() not in folder.parents:
            raise ProjectError(f"Projet hors du dossier partagé : {project}")
        pcbs = sorted(folder.glob("*.kicad_pcb"))
        if not pcbs:
            raise ProjectError(f"Aucun .kicad_pcb dans {folder}")
        return pcbs[0]
    if open_board_path:
        path = Path(open_board_path)
        if path.exists():
            return path
    raise ProjectError(
        "Aucun projet précisé et aucune carte ouverte dans KiCad. "
        "Utilise list_projects puis passe `project`."
    )


def out_dir(pcb: Path) -> Path:
    d = pcb.parent / config.OUT_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d
