# POC — Atelier PCB + boîtier 3D piloté par Claude

## Objectif
Outil perso (non distribué) pour concevoir des PCB et leurs boîtiers imprimés en 3D,
vérifier que l'assemblage tient (collisions, jeux), et laisser Claude agir directement
sur le projet via un connecteur MCP.

## Décisions prises
- **KiCad 10 desktop complet** dans un conteneur Docker, affiché dans le navigateur (noVNC ou Selkies).
  Pas de portage WASM (PCBJam) : trop expérimental et non pilotable.
- **Pilotage par Claude** via un serveur MCP distant :
  - API IPC KiCad (`kicad-python`) pour agir en direct sur l'éditeur PCB ouvert ;
  - `kicad-cli` pour DRC/ERC, export STEP, Gerber ;
  - édition de fichiers schéma (`kicad-sch-api`) + rechargement, l'API IPC couvrant surtout le PCB.
  - Base possible : mixelpixx/KiCAD-MCP-Server, étendu avec les outils mécaniques.
- **Mécanique** : worker Python build123d (OpenCascade) → boîtier paramétrique généré
  depuis les cotes du PCB (contour, trous, connecteurs).
- **Check d'assemblage** : intersection booléenne (`BRepAlgoAPI_Common`) entre chaque paire
  de solides → volume > 0 = collision ; `BRepExtrema_DistShapeShape` pour le jeu minimum
  (cible impression 3D : 0,2–0,4 mm).
- **Vue 3D d'assemblage** : petit front Three.js (STEP carte + boîtier, collisions colorées).
- **Exports impression** : STL / 3MF.
- **Hébergement** : serveur perso `apollo` (Ubuntu Server headless, Docker).

## Architecture cible
```
apollo (Docker)
├─ kicad       : KiCad 10 desktop + noVNC
├─ mcp         : serveur MCP HTTP → API IPC KiCad + kicad-cli + module méca build123d
│                + viewer Three.js d'assemblage (/viewer)
└─ volume partagé : /projects (fichiers KiCad, STEP, sorties)
Exposition : tunnel Cloudflare + authentification (le connecteur Claude doit
être joignable depuis Internet, pas seulement via le VPN).
```

## Outils MCP visés (V0)
- `get_project` — état du projet (board, empreintes, nets)
- `move_footprint` / `add_component`
- `run_drc`
- `export_step`
- `generate_enclosure` — paramètres : épaisseur paroi, jeu, type de fixation
- `check_interference` — liste des collisions et jeux insuffisants
- `export_print_files` — STL/3MF

## Étapes du POC
1. docker-compose : conteneur KiCad 10 + noVNC accessible depuis le navigateur
2. Vérifier l'API IPC depuis un script Python dans un conteneur voisin
3. Serveur MCP minimal (get_project, run_drc, export_step), testé en local depuis Claude Desktop
4. Worker build123d : boîtier simple depuis le STEP/contour du PCB + check d'interférences
5. Viewer Three.js d'assemblage
6. Exposition via tunnel Cloudflare + OAuth, ajout comme connecteur dans Claude

## Avancement
- [x] Repo, Dockerfile multi-cibles (gui / mcp), docker-compose
- [x] Serveur MCP (10 outils) en HTTP streamable, jeton partagé
- [x] Module méca : boîtier fond + couvercle, plots, découpes, collisions/jeux, STL/3MF/STEP — testé
- [x] Viewer Three.js (calques, éclaté, rapport, rafraîchissement auto)
- [ ] Premier build et test réel sur apollo (KiCad + IPC + kicad-cli)
- [ ] Exposition Cloudflare + OAuth pour le connecteur claude.ai

## Points ouverts
- noVNC retenu pour la V0 ; Selkies (WebRTC) si la fluidité ne suffit pas
- Architecture CPU d'apollo (images KiCad x86_64 vs arm64)
- Mode de fixation PCB par défaut dans le boîtier (inserts, plots, rainures)
