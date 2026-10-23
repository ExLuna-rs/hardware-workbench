# Atelier PCB

Atelier perso pour concevoir une carte dans **KiCad 10** et son **boîtier imprimé en 3D**, vérifier que l'assemblage tient, et laisser **Claude** piloter le tout via un serveur **MCP**.

```
apollo (Docker)
├─ kicad : KiCad 10 desktop dans un bureau virtuel → navigateur (noVNC, :6080)
├─ mcp   : serveur MCP (:8000/mcp) + viewer 3D (:8000/viewer)
│          ├─ API IPC KiCad (kicad-python) → actions en direct dans l'éditeur PCB
│          ├─ kicad-cli → DRC, export STEP, Gerber
│          └─ build123d (OpenCascade) → boîtier, check d'interférences, STL/3MF
└─ ./projects : projets KiCad partagés par les deux conteneurs
```

## Démarrage

```bash
cp .env.example .env        # renseigne VNC_PASSWORD, MCP_TOKEN, BIND_ADDR
docker compose up -d --build
```

- **KiCad** : `http://<hôte>:6080` → « Connect », mot de passe `VNC_PASSWORD`.
- **Viewer 3D** : `http://<hôte>:8000/viewer?token=<MCP_TOKEN>`.
- Mets tes projets dans `./projects/<nom>/<nom>.kicad_pro`.

> Premier build long : KiCad + modèles 3D pèsent plusieurs Go. `WITH_3D_MODELS=0` allège l'image,
> mais l'export STEP ne contiendra alors que le circuit nu (le check d'assemblage perd son intérêt).

L'API IPC est activée d'office dans la config KiCad du conteneur. Elle sert l'**éditeur PCB** :
ouvre le `.kicad_pcb` dans KiCad pour que `get_project` / `move_footprint` fonctionnent.

## Brancher Claude

### En local (Claude Desktop)

Dans la config MCP de Claude Desktop, via le pont `mcp-remote` (Node.js requis) :

```json
{
  "mcpServers": {
    "atelier-pcb": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://apollo.lan:8000/mcp",
               "--allow-http", "--header", "Authorization:Bearer ${MCP_TOKEN}"],
      "env": { "MCP_TOKEN": "<ton jeton>" }
    }
  }
}
```

### En distant (connecteur claude.ai)

Un connecteur est appelé depuis Internet : il faut exposer **uniquement** le port 8000 (tunnel Cloudflare)
et passer à une authentification OAuth (étape 6 de `CONTEXT.md`, pas encore faite). Le port 6080 reste
réservé au réseau local / VPN.

## Outils MCP

| Outil | Rôle |
|---|---|
| `list_projects` | Projets présents dans `./projects` |
| `kicad_status` | KiCad répond-il, quelles cartes sont ouvertes |
| `get_project` | Contour, couches, nets, empreintes (réf, valeur, position, rotation, face) |
| `move_footprint` | Déplace/tourne une empreinte en direct (annulable par Ctrl+Z) |
| `save_board` | Enregistre la carte ouverte |
| `run_drc` | DRC + parité schéma via kicad-cli, résumé des violations |
| `export_step` | Carte + composants en STEP |
| `generate_enclosure` | Boîtier fond + couvercle à lèvre, plots sur les `MountingHole*`, découpes de paroi, check d'assemblage |
| `check_interference` | Réexporte et revérifie avec les derniers paramètres (après des déplacements) |
| `export_print_files` | Liens STL / 3MF / STEP du boîtier, Gerber + perçage |

Exemple de demande à Claude : *« Génère un boîtier pour la carte ouverte avec 2,5 mm de parois et une
découpe USB-C sur le côté gauche, puis dis-moi si quelque chose touche. »*

Sorties dans `projects/<nom>/atelier_out/` : `boitier_fond.stl`, `boitier_couvercle.stl` (déjà retourné
pour l'impression), `boitier.3mf` (les deux pièces), `.step`, `rapport.json`.

## Développement

```bash
cd server
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                          # tests du module mécanique (pas besoin de KiCad)
ATELIER_PROJECTS_DIR=../projects atelier-server
```

Les tests utilisent une carte synthétique ; la partie KiCad (IPC, kicad-cli) se teste avec les conteneurs.

## Limites connues (POC)

- Boîtier rectangulaire calé sur le rectangle englobant du PCB (pas encore sur le contour exact).
- Couvercle à emboîtement par lèvre, sans vis.
- Les découpes de connecteurs sont à donner à la main (Claude peut les déduire des positions d'empreintes).
- L'API IPC de KiCad couvre l'éditeur PCB ; le schéma se modifie par fichiers.
