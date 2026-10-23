# syntax=docker/dockerfile:1
# Une seule image de base KiCad 10, deux cibles :
#   - gui : KiCad desktop dans un bureau virtuel, affiché dans le navigateur (noVNC)
#   - mcp : serveur MCP + module mécanique (kicad-cli, kicad-python, build123d)
# Les deux cibles partagent les couches KiCad : pas de double occupation disque.

FROM ubuntu:24.04 AS kicad-base
ARG WITH_3D_MODELS=1
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=Europe/Paris

RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common gpg-agent ca-certificates \
 && add-apt-repository --yes ppa:kicad/kicad-10.0-releases \
 && apt-get update \
 && if [ "$WITH_3D_MODELS" = "1" ]; then \
      apt-get install -y --install-recommends kicad ; \
    else \
      apt-get install -y --no-install-recommends kicad kicad-symbols kicad-footprints kicad-templates ; \
    fi \
 && apt-get install -y --no-install-recommends python3 python3-venv tini \
 && rm -rf /var/lib/apt/lists/*

# L'utilisateur "ubuntu" (uid 1000) existe déjà dans l'image : on l'utilise partout
# pour que le socket IPC de KiCad soit accessible depuis l'autre conteneur.
ENV HOME=/home/ubuntu
WORKDIR /home/ubuntu


# ---------------------------------------------------------------- GUI (navigateur)
FROM kicad-base AS gui
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      xvfb x11vnc openbox novnc websockify supervisor x11-xserver-utils \
      fonts-dejavu fonts-liberation xterm dbus-x11 libgl1-mesa-dri \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html

COPY docker/kicad/supervisord.conf /etc/supervisor/conf.d/atelier.conf
COPY docker/kicad/start-gui.sh /usr/local/bin/start-gui.sh
COPY docker/kicad/kicad_common.json /opt/atelier/kicad_common.json
RUN chmod +x /usr/local/bin/start-gui.sh

ENV DISPLAY=:1 RESOLUTION=1920x1080 KICAD_PROJECT=""
EXPOSE 6080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/start-gui.sh"]


# ---------------------------------------------------------------- Serveur MCP
FROM kicad-base AS mcp
RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
COPY server/pyproject.toml /opt/atelier/server/pyproject.toml
COPY server/atelier /opt/atelier/server/atelier
RUN pip install --no-cache-dir /opt/atelier/server
USER ubuntu
ENV ATELIER_PROJECTS_DIR=/projects KICAD_API_SOCKET=ipc:///tmp/kicad/api.sock
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["atelier-server"]
