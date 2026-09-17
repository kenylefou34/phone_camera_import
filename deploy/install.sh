#!/usr/bin/env bash
#
# Installe (ou met à jour) le service phototheque sur le NUC.
#
# Utilisation, depuis la racine du dépôt :
#     ./deploy/install.sh
#
# Le script est IDEMPOTENT : on peut le relancer autant de fois qu'on veut,
# il remet simplement l'installation dans l'état voulu. C'est la commande à
# rejouer après chaque « git pull ».
#
# Il demande le mot de passe sudo pour les étapes qui touchent au système
# (unité systemd, fichier Avahi). Il doit donc être lancé depuis un vrai
# terminal, pas depuis un canal sans TTY.
#
# Voir docs/DEPLOIEMENT.md pour le détail de chaque étape.

set -euo pipefail

# -e : on s'arrête à la première erreur ; -u : une variable non définie est une
# erreur ; -o pipefail : une erreur au milieu d'un pipe n'est pas avalée.

PORT=8787
SERVICE=phototheque
ANCIEN_SERVICE=mediaserve          # nom d'avant le renommage du 17/09/2026
VENV="$HOME/.venv-server"
UNITE=/etc/systemd/system/${SERVICE}.service
AVAHI=/etc/avahi/services/avahi-${SERVICE}.service

etape() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info()  { printf '    %s\n' "$*"; }

# --------------------------------------------------------------------------
etape "1/7  Vérifications préalables"

racine=$(cd "$(dirname "$0")/.." && pwd)
cd "$racine"
info "dépôt : $racine"

for fichier in deploy/${SERVICE}.service deploy/avahi-${SERVICE}.service \
               requirements-server.txt ${SERVICE}/app.py; do
    if [ ! -f "$fichier" ]; then
        echo "ERREUR : $fichier est introuvable. Lancez le script depuis le dépôt." >&2
        exit 1
    fi
done
info "fichiers attendus présents"

# Le service lit la bibliothèque sur un disque externe : s'il n'est pas monté,
# autant le dire tout de suite plutôt que laisser le service échouer au boot.
if ! mountpoint -q /media/izquierdo/Famille 2>/dev/null; then
    info "ATTENTION : /media/izquierdo/Famille n'est pas monté."
    info "            Le service attendra ce montage pour démarrer"
    info "            (directive RequiresMountsFor dans l'unité systemd)."
fi

# --------------------------------------------------------------------------
etape "2/7  Environnement Python (venv)"

# PEP 668 : le Python système refuse « pip install --user », d'où le venv.
if [ ! -x "$VENV/bin/python" ]; then
    info "création de $VENV"
    python3 -m venv "$VENV"
else
    info "$VENV existe déjà"
fi

info "installation des dépendances (requirements-server.txt)"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r requirements-server.txt
info "$("$VENV/bin/python" --version)"

# --------------------------------------------------------------------------
etape "3/7  Reprise des données de l'ancien nom (mediaserve)"

# La base des appareils appairés était nommée d'après l'ancien module. Sans
# cette reprise, le service repartirait avec zéro appareil appairé et les
# téléphones déjà configurés seraient rejetés.
ancienne_base="$HOME/${ANCIEN_SERVICE}_devices.db"
nouvelle_base="$HOME/${SERVICE}_devices.db"
if [ -f "$ancienne_base" ] && [ ! -f "$nouvelle_base" ]; then
    mv "$ancienne_base" "$nouvelle_base"
    info "appairages repris : $(basename "$ancienne_base") -> $(basename "$nouvelle_base")"
elif [ -f "$nouvelle_base" ]; then
    info "$(basename "$nouvelle_base") déjà en place"
else
    info "aucune base d'appairage à reprendre (première installation)"
fi

# --------------------------------------------------------------------------
etape "4/7  Retrait de l'ancien service"

# Piège classique du renommage : sans ce retrait, l'ancienne unité reste
# active et deux services se disputent le port 8787.
if systemctl list-unit-files | grep -q "^${ANCIEN_SERVICE}.service"; then
    info "ancien service trouvé, désactivation"
    sudo systemctl disable --now ${ANCIEN_SERVICE}.service || true
    sudo rm -f /etc/systemd/system/${ANCIEN_SERVICE}.service
    sudo rm -f /etc/avahi/services/avahi-${ANCIEN_SERVICE}.service
    info "ancien service retiré"
else
    info "rien à retirer"
fi

# --------------------------------------------------------------------------
etape "5/7  Installation de l'unité systemd et de l'annonce Avahi"

sudo cp deploy/${SERVICE}.service "$UNITE"
sudo cp deploy/avahi-${SERVICE}.service "$AVAHI"
info "$UNITE"
info "$AVAHI"

sudo systemctl daemon-reload
sudo systemctl enable --now ${SERVICE}.service
sudo systemctl restart ${SERVICE}.service      # relit le code après un git pull
info "service activé (démarrage automatique au boot) et démarré"

# Avahi ne relit ses fichiers de service qu'au redémarrage du démon.
if systemctl is-active --quiet avahi-daemon; then
    sudo systemctl restart avahi-daemon
    info "avahi-daemon redémarré (annonce mDNS à jour)"
fi

# --------------------------------------------------------------------------
etape "6/7  Vérification"

# Laisser à uvicorn le temps d'ouvrir son port avant de l'interroger.
service_repond() {
    "$VENV/bin/python" - "$PORT" <<'PY' >/dev/null 2>&1
import sys, urllib.request
urllib.request.urlopen("http://127.0.0.1:%s/" % sys.argv[1], timeout=2)
PY
}

for _ in $(seq 20); do
    if service_repond; then
        break
    fi
    sleep 0.5
done

# Pas de curl sur le NUC : on interroge avec urllib.
"$VENV/bin/python" - "$PORT" <<'PY'
import sys, urllib.request, urllib.error

port = sys.argv[1]
souci = False
for chemin, attendu in (("/", 200), ("/pair", 200), ("/status", 401)):
    try:
        code = urllib.request.urlopen("http://127.0.0.1:%s%s" % (port, chemin), timeout=5).status
    except urllib.error.HTTPError as e:
        code = e.code          # /status répond 401 : c'est le comportement voulu
    except Exception as e:
        print("    %-8s ECHEC : %s" % (chemin, e)); souci = True; continue
    etat = "ok" if code == attendu else "INATTENDU (attendu %d)" % attendu
    print("    %-8s %s  %s" % (chemin, code, etat))
    souci = souci or code != attendu
raise SystemExit(1 if souci else 0)
PY

# --------------------------------------------------------------------------
etape "7/7  Terminé"

info "état      : $(systemctl is-active ${SERVICE}) / $(systemctl is-enabled ${SERVICE})"
info "version   : $(git log --oneline -1)"
info "admin     : http://$(hostname).local:${PORT}/"
info "appairage : http://$(hostname).local:${PORT}/pair"
printf '\n'
info "journal en direct : journalctl -u ${SERVICE} -f"
