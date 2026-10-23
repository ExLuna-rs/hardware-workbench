"""Configuration par variables d'environnement."""

import os
from pathlib import Path

PROJECTS_DIR = Path(os.environ.get("ATELIER_PROJECTS_DIR", "/projects"))
KICAD_CLI = os.environ.get("KICAD_CLI", "kicad-cli")
# Socket IPC de KiCad, partagé entre les conteneurs via un volume monté sur /tmp/kicad
KICAD_API_SOCKET = os.environ.get("KICAD_API_SOCKET", "ipc:///tmp/kicad/api.sock")
# Jeton d'accès au serveur (MCP + viewer). Vide = pas d'auth (réseau local uniquement !)
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
HOST = os.environ.get("ATELIER_HOST", "0.0.0.0")
PORT = int(os.environ.get("ATELIER_PORT", "8000"))
# URL publique du viewer, renvoyée à Claude dans les résultats d'outils
PUBLIC_URL = os.environ.get("ATELIER_PUBLIC_URL", f"http://localhost:{PORT}").rstrip("/")
OUT_DIRNAME = "atelier_out"
