#!/usr/bin/env bash
#
# Change les identifiants d'administration de phototheque : le nom d'utilisateur
# et le mot de passe.
#
# Utilisation, depuis n'importe où sur le NUC :
#     ~/phone_camera_import/deploy/identifiants.sh
#
# À la différence d'install.sh — qui TIRE un mot de passe au hasard à la
# première installation, sous le nom « admin », et refuse ensuite d'y toucher —
# ce script permet de CHOISIR les deux, et d'en changer autant qu'on veut.
#
# Aucun privilège particulier : il n'écrit que dans le dossier de configuration
# de l'utilisateur. Pas de sudo, pas de redémarrage du service.
#
# Les précautions d'écriture du mot de passe sont dans ecrire_empreinte_admin
# (deploy/lib.sh), partagée avec install.sh et couverte par tests/test_deploy.py.

set -euo pipefail

racine=${RACINE:-$(cd "$(dirname "$0")/.." && pwd)}
CONFIG_DIR=${CONFIG_DIR:-$HOME/.config/phototheque}
PYTHON=${PYTHON:-$HOME/.venv-server/bin/python}
ADMIN="$CONFIG_DIR/admin"
UTILISATEUR="$CONFIG_DIR/utilisateur"

# shellcheck source=deploy/lib.sh
source "$racine/deploy/lib.sh"

info()  { printf '    %s\n' "$*"; }
echec() { printf '\n\033[1;31mÉCHEC : %s\033[0m\n' "$*" >&2; exit 1; }

printf '\n\033[1m==> Changement des identifiants d'"'"'administration\033[0m\n'

# Vérifié AVANT de demander quoi que ce soit : découvrir que Python manque
# après avoir tapé deux fois son mot de passe serait vexant, et surtout
# l'échec surviendrait en pleine écriture du fichier.
command -v "$PYTHON" >/dev/null 2>&1 || echec "Python introuvable : $PYTHON
    Le venv du serveur n'est pas installé. Lancez d'abord ./deploy/install.sh"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

# Fichier absent = « admin », exactement comme le lit le serveur
# (adminauth.utilisateur). On l'AFFICHE : ce n'est pas un secret — il n'est pas
# haché, contrairement au mot de passe — et sans cet affichage, un identifiant
# oublié ne serait récupérable que par un accès SSH à la machine.
# Rogner UNIQUEMENT les extrémités, exactement comme le serveur
# (adminauth.utilisateur fait un .strip()). Supprimer aussi les espaces
# intérieurs afficherait « kenizq » là où il faut taper « ken izq », et le
# mainteneur chercherait longtemps pourquoi son identifiant est refusé.
rogner() { sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'; }

actuel="admin"
if [ -r "$UTILISATEUR" ]; then
    lu=$(rogner < "$UTILISATEUR" || true)
    if [ -n "$lu" ]; then
        actuel="$lu"
    fi
fi
info "Identifiant actuel : $actuel"
printf '    Nouvel identifiant (vide = garder « %s ») : ' "$actuel"
read -r saisi || true
# Rogné aussi à la saisie : une ligne d'espaces vaut alors « ne rien changer »,
# plutôt que d'enregistrer un nom que le serveur relira comme vide — donc comme
# « admin » — sans que personne n'ait demandé ça.
nouvel_identifiant=$(printf '%s' "$saisi" | rogner)

# -r : un antislash dans le mot de passe est un caractère comme un autre, pas
# une échappée. -s : rien ne s'affiche, donc rien ne reste à l'écran ni dans
# l'historique du terminal. Le printf final remet la ligne que -s a mangée.
printf '    Nouveau mot de passe : '
read -rs premier || true
printf '\n    Confirmation         : '
read -rs second || true
printf '\n\n'

# --- TOUT est validé avant la moindre écriture ------------------------------
# Un refus survenant après avoir écrit le mot de passe laisserait une
# installation à moitié changée, sans que le message d'erreur le dise.

case "$nouvel_identifiant" in
    *:*) echec "l'identifiant ne peut pas contenir « : » — rien n'a été changé.
    L'authentification du navigateur transmet « utilisateur:mot de passe » et le
    serveur découpe sur le PREMIER deux-points : un nom qui en contient un ne
    pourrait jamais être reconnu, et plus personne n'aurait accès à
    l'administration." ;;
esac

[ -n "$premier" ] || echec "mot de passe vide — rien n'a été changé.
    Un mot de passe vide fermerait l'administration sans le dire."

[ "$premier" = "$second" ] || echec "les deux saisies ne sont pas identiques — rien n'a été changé.
    C'est justement le rôle de la confirmation : sans elle, une coquille dans
    un mot de passe qu'on ne voit pas s'afficher ne se découvre qu'à la
    connexion suivante."

# Averti, pas interdit : c'est un réseau local et c'est l'arbitrage du
# mainteneur. Le serveur limite désormais les essais (issue #19), ce qui rend
# l'acharnement très coûteux — mais un mot de passe vraiment court reste
# devinable en quelques essais, avant même que la limitation n'entre en jeu.
if [ "${#premier}" -lt 12 ]; then
    printf '\033[1;33m    ATTENTION : mot de passe court (%d caractères).\033[0m\n' "${#premier}"
    info "Le serveur ralentit les essais répétés, mais un mot de passe très"
    info "court se devine avant que cela ne serve. 12 caractères ou plus."
    printf '\n'
fi

# --- écritures ---------------------------------------------------------------
printf '%s' "$premier" | ecrire_empreinte_admin "$ADMIN" "$PYTHON" "$racine"

# L'identifiant en dernier : si cette écriture échouait, le nouveau mot de passe
# serait déjà en place sous l'ancien identifiant — gênant, mais on reste dehors
# de rien. L'inverse laisserait un identifiant neuf avec un mot de passe ancien.
if [ -n "$nouvel_identifiant" ]; then
    (umask 077; printf '%s' "$nouvel_identifiant" > "$UTILISATEUR.nouveau")
    mv "$UTILISATEUR.nouveau" "$UTILISATEUR"
    chmod 600 "$UTILISATEUR"
    retenu=$nouvel_identifiant
else
    retenu=$actuel
fi

info "identifiants changés."
printf '\n'
info "Identifiant : $retenu"
info "Mot de passe : celui que tu viens de taper (il n'est stocké nulle part en clair)."
printf '\n'
info "Actif IMMÉDIATEMENT : le service relit ces fichiers à chaque requête,"
info "il n'y a rien à redémarrer."
printf '\n'
info "Pour le vérifier, ouvre une fenêtre de navigation PRIVÉE : tant qu'un"
info "navigateur reste ouvert, il continue d'envoyer les anciens identifiants"
info "sans les redemander (c'est le propre de l'authentification HTTP Basic)."
printf '\n'
info "Identifiant oublié ? « rm $UTILISATEUR » le ramène à « admin »."
printf '\n'
