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
# Les décisions délicates sont dans deploy/lib.sh et couvertes par
# tests/test_deploy.py. Voir docs/DEPLOIEMENT.md pour le détail des étapes.

set -euo pipefail

PORT=8787
SERVICE=phototheque
ANCIEN_SERVICE=mediaserve          # nom d'avant le renommage du 17/09/2026
VENV="$HOME/.venv-server"
UNITE=/etc/systemd/system/${SERVICE}.service
ANCIENNE_UNITE=/etc/systemd/system/${ANCIEN_SERVICE}.service
AVAHI=/etc/avahi/services/avahi-${SERVICE}.service
ANCIEN_AVAHI=/etc/avahi/services/avahi-${ANCIEN_SERVICE}.service

racine=$(cd "$(dirname "$0")/.." && pwd)
cd "$racine"

# Les fonctions de décision lisent les bases SQLite avec ce Python.
PYTHON="$VENV/bin/python"
# shellcheck source=deploy/lib.sh
source "$racine/deploy/lib.sh"

etape() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info()  { printf '    %s\n' "$*"; }
echec() { printf '\n\033[1;31mÉCHEC : %s\033[0m\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------------------
etape "1/7  Vérifications préalables"

info "dépôt : $racine"
for fichier in deploy/${SERVICE}.service deploy/avahi-${SERVICE}.service \
               requirements-server.txt ${SERVICE}/app.py; do
    [ -f "$fichier" ] || echec "$fichier introuvable — lancez le script depuis le dépôt."
done
info "fichiers attendus présents"

# Le service lit la bibliothèque sur un disque externe : autant le dire tout
# de suite plutôt que laisser le service échouer au boot.
if ! mountpoint -q /media/izquierdo/Famille 2>/dev/null; then
    info "ATTENTION : /media/izquierdo/Famille n'est pas monté."
    info "            Le service attendra ce montage (RequiresMountsFor)."
fi

# --------------------------------------------------------------------------
etape "2/7  Environnement Python (venv)"

# PEP 668 : le Python système refuse « pip install --user », d'où le venv.
if [ ! -x "$PYTHON" ]; then
    info "création de $VENV"
    python3 -m venv "$VENV"
else
    info "$VENV existe déjà"
fi

info "installation des dépendances (requirements-server.txt)"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r requirements-server.txt
info "$("$PYTHON" --version)"

# --------------------------------------------------------------------------
etape "3/7  Retrait de l'ancien service"

# D'abord arrêter l'ancien service, AVANT de toucher à ses données : déplacer
# une base SQLite pendant que son écrivain tourne donne un état incohérent.
#
# Piège classique du renommage : sans ce retrait, l'ancienne unité reste active,
# garde le port 8787, et la nouvelle redémarre en boucle sur « address already
# in use ».
if unite_installee "$ANCIENNE_UNITE"; then
    info "ancien service $ANCIEN_SERVICE trouvé, désactivation"
    sudo systemctl disable --now ${ANCIEN_SERVICE}.service || true
    sudo rm -f "$ANCIENNE_UNITE" "$ANCIEN_AVAHI"
    sudo systemctl daemon-reload
    info "ancien service retiré"
else
    info "aucun ancien service à retirer"
fi

# --------------------------------------------------------------------------
etape "4/7  Reprise des appairages"

# La base des appareils appairés portait l'ancien nom. Sans reprise, les
# téléphones déjà configurés seraient rejetés et il faudrait tout réappairer.
#
# Le critère est le CONTENU et non l'existence du fichier : importer
# phototheque.app crée la base au passage (DeviceStore est instancié au
# chargement du module), donc un simple test d'existence peut voir un fichier
# vide et conclure à tort que la reprise a déjà eu lieu.
ancienne_base="$HOME/${ANCIEN_SERVICE}_devices.db"
nouvelle_base="$HOME/${SERVICE}_devices.db"

if doit_reprendre "$ancienne_base" "$nouvelle_base"; then
    if [ -f "$nouvelle_base" ]; then
        mv "$nouvelle_base" "$nouvelle_base.vide-$(date +%Y%m%d-%H%M%S)"
        info "base vide mise de côté"
    fi
    mv "$ancienne_base" "$nouvelle_base"
    info "appairages repris : $(nb_appareils "$nouvelle_base") appareil(s)"
else
    info "rien à reprendre ($(nb_appareils "$nouvelle_base") appareil(s) en place)"
fi

# --------------------------------------------------------------------------
etape "5/7  Le port $PORT est-il libre ?"

# Filet de sécurité : même sans ancienne unité, un processus égaré (lancement
# manuel d'uvicorn, service tiers) peut tenir le port. Autant le dire ici que
# laisser systemd boucler.
occupant=$(occupant_du_port "$PORT")
if [ -n "$occupant" ]; then
    # Le service lui-même a le droit d'y être : on le redémarrera plus bas.
    if systemctl is-active --quiet ${SERVICE}.service; then
        info "port tenu par $SERVICE lui-même (il sera redémarré)"
    else
        info "$occupant"
        echec "le port $PORT est occupé par un processus inattendu.
    Identifiez-le avec :  ss -lptn 'sport = :$PORT'
    puis arrêtez-le avant de relancer ce script."
    fi
else
    info "port libre"
fi

# --------------------------------------------------------------------------
etape "6/7  Installation et démarrage"

sudo cp deploy/${SERVICE}.service "$UNITE"
sudo cp deploy/avahi-${SERVICE}.service "$AVAHI"
info "$UNITE"
info "$AVAHI"

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE}.service
sudo systemctl restart ${SERVICE}.service      # relit le code après un git pull
info "service activé (démarrage au boot) et démarré"

# Avahi ne relit ses fichiers de service qu'au redémarrage du démon.
if systemctl is-active --quiet avahi-daemon; then
    sudo systemctl restart avahi-daemon
    info "avahi-daemon redémarré (annonce mDNS à jour)"
fi

# --------------------------------------------------------------------------
etape "7/7  Vérification"

# Laisser à uvicorn le temps d'ouvrir son port avant de l'interroger.
service_repond() {
    "$PYTHON" - "$PORT" <<'PY' >/dev/null 2>&1
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

# Un service en boucle de redémarrage ne doit pas passer pour un succès.
if ! systemctl is-active --quiet ${SERVICE}.service; then
    info "état : $(systemctl is-active ${SERVICE} || true)"
    echec "le service ne tient pas en route. Journal :
    journalctl -u ${SERVICE} -n 30 --no-pager"
fi

# Pas de curl sur le NUC : on interroge avec urllib.
"$PYTHON" - "$PORT" <<'PY' || echec "le service répond mal (voir ci-dessus)."
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

printf '\n'
info "état      : $(systemctl is-active ${SERVICE}) / $(systemctl is-enabled ${SERVICE})"
info "version   : $(git log --oneline -1)"
info "admin     : http://$(hostname).local:${PORT}/"
info "appairage : http://$(hostname).local:${PORT}/pair"
info "journal   : journalctl -u ${SERVICE} -f"
