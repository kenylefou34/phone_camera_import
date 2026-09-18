#!/usr/bin/env bash
#
# Change le mot de passe d'administration de phototheque.
#
# Utilisation, depuis n'importe où sur le NUC :
#     ~/phone_camera_import/deploy/motdepasse.sh
#
# À la différence d'install.sh — qui en TIRE un au hasard à la première
# installation et refuse ensuite d'y toucher — ce script permet d'en CHOISIR
# un, et d'en changer autant de fois qu'on veut.
#
# Aucun privilège particulier : il n'écrit qu'un fichier dans le dossier de
# configuration de l'utilisateur. Pas de sudo, pas de redémarrage du service.
#
# Les précautions d'écriture sont dans ecrire_empreinte_admin (deploy/lib.sh),
# partagée avec install.sh et couverte par tests/test_deploy.py.

set -euo pipefail

racine=${RACINE:-$(cd "$(dirname "$0")/.." && pwd)}
CONFIG_DIR=${CONFIG_DIR:-$HOME/.config/phototheque}
PYTHON=${PYTHON:-$HOME/.venv-server/bin/python}
ADMIN="$CONFIG_DIR/admin"

# shellcheck source=deploy/lib.sh
source "$racine/deploy/lib.sh"

info()  { printf '    %s\n' "$*"; }
echec() { printf '\n\033[1;31mÉCHEC : %s\033[0m\n' "$*" >&2; exit 1; }

printf '\n\033[1m==> Changement du mot de passe d'"'"'administration\033[0m\n'

# Vérifié AVANT de demander quoi que ce soit : découvrir que Python manque
# après avoir tapé deux fois son mot de passe serait vexant, et surtout
# l'échec surviendrait en pleine écriture du fichier.
# `command -v` plutôt que `[ -x ]` : il accepte aussi bien un chemin complet
# (le cas réel, $HOME/.venv-server/bin/python) qu'un nom de commande à chercher
# dans le PATH, et vérifie l'exécutabilité dans les deux cas.
command -v "$PYTHON" >/dev/null 2>&1 || echec "Python introuvable : $PYTHON
    Le venv du serveur n'est pas installé. Lancez d'abord ./deploy/install.sh"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

# -r : un antislash dans le mot de passe est un caractère comme un autre, pas
# une échappée. -s : rien ne s'affiche, donc rien ne reste à l'écran ni dans
# l'historique du terminal. Le printf final remet la ligne que -s a mangée.
printf '    Nouveau mot de passe : '
read -rs premier || true
printf '\n    Confirmation         : '
read -rs second || true
printf '\n\n'

[ -n "$premier" ] || echec "mot de passe vide — rien n'a été changé.
    Un mot de passe vide fermerait l'administration sans le dire."

[ "$premier" = "$second" ] || echec "les deux saisies ne sont pas identiques — rien n'a été changé.
    C'est justement le rôle de la confirmation : sans elle, une coquille dans
    un mot de passe qu'on ne voit pas s'afficher ne se découvre qu'à la
    connexion suivante."

# Averti, pas interdit : c'est un réseau local et c'est l'arbitrage du
# mainteneur. Mais tant que rien ne limite les essais côté serveur (issue #19),
# la longueur du mot de passe est la seule barrière réelle — autant le dire.
if [ "${#premier}" -lt 12 ]; then
    printf '\033[1;33m    ATTENTION : mot de passe court (%d caractères).\033[0m\n' "${#premier}"
    info "Rien ne limite encore le nombre d'essais côté serveur : un mot de"
    info "passe court se devine. 12 caractères ou plus sont conseillés."
    printf '\n'
fi

printf '%s' "$premier" | ecrire_empreinte_admin "$ADMIN" "$PYTHON" "$racine"

info "mot de passe changé."
printf '\n'
info "Actif IMMÉDIATEMENT : le service relit ce fichier à chaque requête,"
info "il n'y a rien à redémarrer."
printf '\n'
info "Pour le vérifier, ouvre une fenêtre de navigation PRIVÉE : tant qu'un"
info "navigateur reste ouvert, il continue d'envoyer l'ancien mot de passe"
info "sans le redemander (c'est le propre de l'authentification HTTP Basic)."
printf '\n'
