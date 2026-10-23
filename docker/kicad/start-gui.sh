#!/bin/sh
# Prépare la config KiCad et le mot de passe VNC, puis lance le bureau virtuel.
set -eu

CFG=/home/ubuntu/.config/kicad/10.0
mkdir -p "$CFG" /home/ubuntu/.vnc /tmp/kicad

# Première exécution : API IPC activée + tables de bibliothèques par défaut
# (évite l'assistant de configuration au premier lancement).
[ -f "$CFG/kicad_common.json" ] || cp /opt/atelier/kicad_common.json "$CFG/kicad_common.json"
for table in sym-lib-table fp-lib-table; do
  if [ ! -f "$CFG/$table" ] && [ -f "/usr/share/kicad/template/$table" ]; then
    cp "/usr/share/kicad/template/$table" "$CFG/$table"
  fi
done

if [ -z "${VNC_PASSWORD:-}" ]; then
  echo "VNC_PASSWORD doit être défini (voir .env)." >&2
  exit 1
fi
x11vnc -storepasswd "$VNC_PASSWORD" /home/ubuntu/.vnc/passwd >/dev/null

chown -R ubuntu:ubuntu /home/ubuntu /tmp/kicad
chmod 775 /tmp/kicad

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/atelier.conf
