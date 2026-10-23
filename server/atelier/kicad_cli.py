"""Appels à kicad-cli (DRC, exports). Agit sur le fichier enregistré, pas sur l'éditeur ouvert."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import config
from .errors import AtelierError


class KiCadCliError(AtelierError):
    pass


def _run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    cmd = [config.KICAD_CLI, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise KiCadCliError(f"kicad-cli introuvable ({config.KICAD_CLI})") from exc
    if proc.returncode not in (0, 5):  # 5 = violations DRC trouvées avec --exit-code-violations
        raise KiCadCliError(f"{' '.join(cmd)} a échoué ({proc.returncode}) : {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def run_drc(pcb: Path, out_dir: Path) -> dict:
    report = out_dir / "drc.json"
    _run(["pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity",
          "--units", "mm", "-o", str(report), str(pcb)])
    data = json.loads(report.read_text())
    violations = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])
    parity = data.get("schematic_parity", [])

    def short(v: dict) -> dict:
        return {
            "type": v.get("type"),
            "severity": v.get("severity"),
            "description": v.get("description"),
            "items": [i.get("description") for i in v.get("items", [])][:4],
        }

    return {
        "errors": sum(1 for v in violations if v.get("severity") == "error"),
        "warnings": sum(1 for v in violations if v.get("severity") == "warning"),
        "unconnected": len(unconnected),
        "schematic_parity_issues": len(parity),
        "violations": [short(v) for v in violations[:50]],
        "unconnected_items": [short(v) for v in unconnected[:30]],
        "report_file": str(report),
    }


def export_step(pcb: Path, out_dir: Path) -> Path:
    step = out_dir / "carte.step"
    _run(["pcb", "export", "step", "--subst-models", "--force", "--no-dnp", "-o", str(step), str(pcb)])
    if not step.exists():
        raise KiCadCliError("Export STEP terminé sans fichier de sortie.")
    return step


def export_gerbers(pcb: Path, out_dir: Path) -> Path:
    gerber_dir = out_dir / "gerbers"
    gerber_dir.mkdir(exist_ok=True)
    _run(["pcb", "export", "gerbers", "-o", str(gerber_dir) + "/", str(pcb)])
    _run(["pcb", "export", "drill", "-o", str(gerber_dir) + "/", str(pcb)])
    return gerber_dir
