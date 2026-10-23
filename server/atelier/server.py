"""Serveur MCP de l'atelier : pilote KiCad (IPC + kicad-cli) et le module mécanique.

Lancement : python -m atelier.server   (HTTP streamable sur /mcp, viewer sur /viewer)
"""

from __future__ import annotations

import json
import secrets
from functools import partial
from pathlib import Path
from typing import Any, Literal

import anyio
import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from . import config, kicad_cli, kicad_ipc, projects
from .errors import AtelierError
from .mech import pipeline

VIEWER_HTML = Path(__file__).parent / "viewer" / "index.html"

mcp = MCPServer(
    name="atelier-pcb",
    title="Atelier PCB + boîtier 3D",
    version="0.1.0",
    instructions=(
        "Outils pour concevoir une carte KiCad et son boîtier imprimé en 3D. "
        "Les outils kicad_* et move_footprint agissent en direct sur l'éditeur PCB ouvert. "
        "run_drc, export_step et generate_enclosure travaillent sur le fichier enregistré "
        "(ils enregistrent la carte d'abord par défaut). Coordonnées KiCad en mm, Y vers le bas. "
        "Après generate_enclosure, donne à l'utilisateur le lien du viewer renvoyé."
    ),
)


async def _thread(fn, *args, **kwargs):
    try:
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))
    except AtelierError:
        raise
    except ValueError as exc:  # erreurs de géométrie / paramètres : utiles à Claude
        raise AtelierError(str(exc)) from exc


def _viewer_url(pcb: Path) -> str:
    return f"{config.PUBLIC_URL}/viewer?project={pcb.parent.name}"


async def _pcb(project: str | None) -> Path:
    open_path = None if project else await _thread(kicad_ipc.open_board_path)
    return projects.resolve_pcb(project, open_path)


async def _save_if_open(save_first: bool) -> bool:
    if not save_first:
        return False
    try:
        await _thread(kicad_ipc.save_board)
        return True
    except kicad_ipc.KiCadUnavailable:
        return False


# --------------------------------------------------------------------------- KiCad

@mcp.tool()
async def list_projects() -> list[dict]:
    """Liste les projets KiCad présents dans le dossier partagé /projects."""
    return projects.list_projects()


@mcp.tool()
async def kicad_status() -> dict:
    """Vérifie que KiCad répond et liste les cartes ouvertes dans l'éditeur PCB."""
    return await _thread(kicad_ipc.status)


@mcp.tool()
async def get_project() -> dict:
    """Résumé de la carte ouverte : contour, couches, nombre de nets, empreintes (réf, valeur, position mm, rotation, face)."""
    return await _thread(kicad_ipc.project_summary)


@mcp.tool()
async def move_footprint(ref: str, x_mm: float | None = None, y_mm: float | None = None,
                         rotation_deg: float | None = None) -> dict:
    """Déplace et/ou tourne une empreinte dans l'éditeur PCB ouvert (visible en direct, annulable par Ctrl+Z).

    Coordonnées absolues KiCad en mm (Y vers le bas). Les paramètres omis restent inchangés.
    """
    return await _thread(kicad_ipc.move_footprint, ref, x_mm, y_mm, rotation_deg)


@mcp.tool()
async def save_board() -> dict:
    """Enregistre la carte ouverte dans KiCad."""
    await _thread(kicad_ipc.save_board)
    return {"saved": True}


@mcp.tool()
async def run_drc(project: str | None = None, save_first: bool = True) -> dict:
    """Lance le DRC (avec parité schéma) via kicad-cli et résume les violations.

    project : nom du dossier dans /projects ; par défaut, la carte ouverte dans KiCad.
    """
    saved = await _save_if_open(save_first)
    pcb = await _pcb(project)
    result = await _thread(kicad_cli.run_drc, pcb, projects.out_dir(pcb))
    return {"pcb": str(pcb), "saved_before": saved, **result}


@mcp.tool()
async def export_step(project: str | None = None, save_first: bool = True) -> dict:
    """Exporte la carte avec ses composants 3D en STEP (atelier_out/carte.step)."""
    saved = await _save_if_open(save_first)
    pcb = await _pcb(project)
    step = await _thread(kicad_cli.export_step, pcb, projects.out_dir(pcb))
    return {"step": str(step), "saved_before": saved}


# --------------------------------------------------------------------------- Mécanique

@mcp.tool()
async def generate_enclosure(
    project: str | None = None,
    wall: float = 2.0,
    floor: float = 2.0,
    lid: float = 2.0,
    xy_clearance: float = 1.0,
    top_clearance: float = 2.0,
    standoff_height: float | None = None,
    standoff_od: float = 6.0,
    screw_hole: float = 2.5,
    lid_fit: float = 0.25,
    cutouts: list[dict[str, Any]] | None = None,
    use_mounting_holes: bool = True,
    refresh_step: bool = True,
    min_gap: float = 0.3,
) -> dict:
    """Génère un boîtier imprimable (fond + couvercle à lèvre) autour de la carte et vérifie l'assemblage.

    - Plots vissés sur les empreintes MountingHole* si use_mounting_holes, sinon 4 plots d'appui aux coins.
    - cutouts : découpes de paroi, ex. [{"side": "-x", "offset": 5, "z": 1.5, "width": 9.5, "height": 3.8}]
      side ∈ +x/-x/+y/-y (repère carte, Y vers le HAUT), offset le long de la paroi depuis le centre
      de la carte, z = centre de la découpe au-dessus de la face supérieure du PCB (mm).
    - Renvoie les dimensions, le rapport de collisions/jeux et l'URL du viewer 3D.
    Fichiers : boitier_fond.stl, boitier_couvercle.stl (déjà orienté pour l'impression), boitier.3mf, .step.
    """
    if refresh_step:
        await _save_if_open(True)
    pcb = await _pcb(project)
    out = projects.out_dir(pcb)
    step = out / "carte.step"
    if refresh_step or not step.exists():
        step = await _thread(kicad_cli.export_step, pcb, out)

    holes: list[tuple[float, float]] = []
    if use_mounting_holes:
        try:
            holes = await _thread(kicad_ipc.mounting_holes_relative)
        except kicad_ipc.KiCadUnavailable:
            holes = []

    params = {
        "wall": wall, "floor": floor, "lid": lid, "xy_clearance": xy_clearance,
        "top_clearance": top_clearance, "standoff_height": standoff_height,
        "standoff_od": standoff_od, "screw_hole": screw_hole, "lid_fit": lid_fit,
        "holes": holes, "cutouts": cutouts or [],
    }
    result = await _thread(pipeline.run, step, out, params, min_gap)
    return {
        "viewer_url": _viewer_url(pcb),
        "dims": result["dims"],
        "interference": result["interference"],
        "files": sorted(p.name for p in out.glob("boitier*")),
    }


@mcp.tool()
async def check_interference(project: str | None = None, min_gap: float = 0.3, refresh_step: bool = True) -> dict:
    """Réexporte la carte et revérifie l'assemblage avec les derniers paramètres de boîtier utilisés.

    À appeler après avoir déplacé des composants, pour voir si tout rentre toujours.
    """
    pcb = await _pcb(project)
    out = projects.out_dir(pcb)
    report_file = out / "rapport.json"
    if not report_file.exists():
        raise AtelierError("Aucun boîtier généré pour ce projet : appelle d'abord generate_enclosure.")
    params = json.loads(report_file.read_text())["params"]
    if refresh_step:
        await _save_if_open(True)
        await _thread(kicad_cli.export_step, pcb, out)
    result = await _thread(pipeline.run, out / "carte.step", out, params, min_gap)
    return {"viewer_url": _viewer_url(pcb), "interference": result["interference"]}


@mcp.tool()
async def export_print_files(project: str | None = None,
                             include: list[Literal["stl", "3mf", "step", "gerbers"]] | None = None) -> dict:
    """Liste (et produit si besoin) les fichiers de fabrication : STL/3MF/STEP du boîtier, Gerber + perçage de la carte."""
    include = include or ["stl", "3mf"]
    pcb = await _pcb(project)
    out = projects.out_dir(pcb)
    files: list[str] = []
    for ext in ("stl", "3mf", "step"):
        if ext in include:
            files += [p.name for p in sorted(out.glob(f"boitier*.{ext}"))]
    if "gerbers" in include:
        gdir = await _thread(kicad_cli.export_gerbers, pcb, out)
        files += [f"gerbers/{p.name}" for p in sorted(gdir.iterdir())]
    if not files:
        raise AtelierError("Aucun fichier : appelle d'abord generate_enclosure.")
    base = f"{config.PUBLIC_URL}/files/{pcb.parent.name}"
    return {"folder": str(out), "downloads": {f: f"{base}/{f}" for f in files}}


# --------------------------------------------------------------------------- HTTP (viewer)

@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/viewer", methods=["GET"])
async def viewer(_: Request) -> Response:
    return FileResponse(VIEWER_HTML, media_type="text/html")


@mcp.custom_route("/api/projects", methods=["GET"])
async def api_projects(_: Request) -> Response:
    return JSONResponse(projects.list_projects())


@mcp.custom_route("/files/{project}/{path:path}", methods=["GET"])
async def files(request: Request) -> Response:
    project = request.path_params["project"]
    rel = request.path_params["path"]
    base = (config.PROJECTS_DIR / project / config.OUT_DIRNAME).resolve()
    target = (base / rel).resolve()
    if base not in target.parents or not target.is_file():
        return JSONResponse({"error": "introuvable"}, status_code=404)
    headers = {"Cache-Control": "no-store"}
    return FileResponse(target, headers=headers)


class TokenAuth:
    """Jeton partagé : en-tête Authorization: Bearer, ?token= ou cookie. /health reste public."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token or scope["path"] == "/health":
            return await self.app(scope, receive, send)
        request = Request(scope)
        provided = (
            request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            or request.query_params.get("token", "")
            or request.cookies.get("atelier_token", "")
        )
        if not secrets.compare_digest(provided, self.token):
            return await JSONResponse({"error": "non autorisé"}, status_code=401)(scope, receive, send)
        return await self.app(scope, receive, send)


def create_app():
    app = mcp.streamable_http_app(
        host=config.HOST,
        # Derrière un tunnel/proxy, le Host public n'est pas localhost : la protection
        # anti DNS-rebinding est remplacée par le jeton.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return TokenAuth(app, config.MCP_TOKEN)


def main() -> None:
    if not config.MCP_TOKEN:
        print("⚠️  MCP_TOKEN vide : serveur sans authentification, à n'exposer que sur le réseau local.")
    uvicorn.run(create_app(), host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
