#!/usr/bin/env bash
#
# Envoie l'APK de l'application Android vers le NUC, pour qu'il soit
# téléchargeable depuis la page d'administration (derrière le mot de passe).
#
# À LANCER DEPUIS LA MACHINE DE COMPILATION, jamais sur le NUC : celui-ci n'a
# ni JDK ni SDK Android, 2 cœurs et 3 Go de mémoire. Compiler là-bas n'est pas
# envisageable, et mettre 25 Mo de binaire dans git à chaque version non plus.
#
#   ./deploy/envoyer-apk.sh                  # compile puis envoie
#   ./deploy/envoyer-apk.sh --sans-compiler  # envoie l'APK déjà construit
#   NUC=izquierdo@192.168.1.30 ./deploy/envoyer-apk.sh   # autre machine
#
# Le service n'a PAS besoin d'être redémarré : il relit le fichier à chaque
# requête.

set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$RACINE/deploy/lib.sh"

# ----------------------------------------------------------------- réglages

NUC="${NUC:-izquierdo@192.168.1.21}"
# Doit correspondre à DATA_DIR / APK_FILE de phototheque/config.py. Si l'un
# des deux change, l'autre doit suivre — c'est le seul couplage de ce script.
DESTINATION="${DESTINATION:-.local/share/phototheque}"
APK_LOCAL="$RACINE/android/app/build/outputs/apk/debug/app-debug.apk"
GRADLE="$RACINE/android/build.gradle.kts"
JAVA_HOME_DEFAUT="$HOME/outils/jdk17"
AAPT2="$(ls "$HOME"/outils/android-sdk/build-tools/*/aapt2 2>/dev/null | head -1 || true)"

COMPILER=1
for argument in "$@"; do
    case "$argument" in
        --sans-compiler) COMPILER=0 ;;
        -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "Argument inconnu : $argument" >&2; exit 2 ;;
    esac
done

dire() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ------------------------------------------------------------- compilation

if [ "$COMPILER" -eq 1 ]; then
    dire "Compilation de l'APK de débogage"
    if [ ! -x "$RACINE/android/gradlew" ]; then
        echo "gradlew introuvable — voir docs/APPLICATION-ANDROID.md" >&2
        exit 1
    fi
    ( cd "$RACINE/android" \
      && JAVA_HOME="${JAVA_HOME:-$JAVA_HOME_DEFAUT}" ./gradlew --quiet assembleDebug )
fi

if [ ! -f "$APK_LOCAL" ]; then
    echo "Aucun APK à envoyer : $APK_LOCAL" >&2
    echo "Compilez-le d'abord, ou retirez --sans-compiler." >&2
    exit 1
fi

# --------------------------------------------------------------- étiquette

# aapt2 lit l'APK RÉELLEMENT produit : c'est lui qui fait autorité. Le repli
# sur build.gradle.kts décrit la source, ce qui diverge dès qu'on modifie la
# version sans recompiler — d'où l'avertissement.
if [ -n "$AAPT2" ]; then
    badging="$("$AAPT2" dump badging "$APK_LOCAL")"
    VERSION="$(sed -n "s/.*versionName='\([^']*\)'.*/\1/p" <<<"$badging")"
    CODE="$(sed -n "s/.*versionCode='\([^']*\)'.*/\1/p" <<<"$badging")"
    VERSION=${VERSION%%$'\n'*}
    CODE=${CODE%%$'\n'*}
else
    echo "aapt2 absent : version lue dans build.gradle.kts (peut differer de l'APK)" >&2
    read -r VERSION CODE <<<"$(version_depuis_gradle "$RACINE/android/app/build.gradle.kts")"
fi

OCTETS="$(stat -c %s "$APK_LOCAL")"
SHA="$(sha256sum "$APK_LOCAL")"
SHA=${SHA%% *}
CONSTRUIT="$(date -Iseconds -r "$APK_LOCAL")"

dire "À envoyer"
printf '  version   : %s (code %s)\n' "$VERSION" "$CODE"
printf '  taille    : %s octets\n' "$OCTETS"
printf '  empreinte : %s\n' "$SHA"
printf '  vers      : %s:%s\n' "$NUC" "$DESTINATION"

# ------------------------------------------------------------------ envoi

dire "Envoi"
ssh "$NUC" "mkdir -p '$DESTINATION'"

# On téléverse sous un nom temporaire. Écrire directement sur app.apk
# laisserait, le temps du transfert, un binaire tronqué que la page d'admin
# proposerait joyeusement au téléchargement — et qu'Android refuserait
# d'installer sans expliquer pourquoi.
scp -q "$APK_LOCAL" "$NUC:$DESTINATION/app.apk.envoi"

dire "Vérification sur le NUC"
# L'empreinte est recalculée À L'ARRIVÉE. Un transfert abîmé est rare mais
# silencieux : sans ce contrôle, on ne le découvrirait qu'au moment où
# l'installation échoue sur le téléphone, loin de sa cause.
distant="$(ssh "$NUC" "sha256sum '$DESTINATION/app.apk.envoi'")"
distant=${distant%% *}
if [ "$distant" != "$SHA" ]; then
    echo "ÉCHEC : l'empreinte ne correspond pas après transfert." >&2
    echo "  attendue : $SHA" >&2
    echo "  reçue    : $distant" >&2
    ssh "$NUC" "rm -f '$DESTINATION/app.apk.envoi'"
    exit 1
fi
echo "  empreinte identique après transfert"

# Mise en place. Le `mv` est atomique (même système de fichiers) : à aucun
# instant le serveur ne voit un fichier à moitié écrit.
#
# L'ordre compte : l'APK d'abord, l'étiquette ensuite. Entre les deux, pendant
# quelques millisecondes, la page annonce l'ancienne version pour le nouveau
# binaire. L'inverse serait pire — annoncer la nouvelle version pour l'ancien
# binaire ferait installer le mauvais APK en croyant le bon. La taille, elle,
# n'est jamais fausse : le serveur la relit toujours sur le disque.
ssh "$NUC" "mv '$DESTINATION/app.apk.envoi' '$DESTINATION/app.apk'"
ssh "$NUC" "cat > '$DESTINATION/app.apk.infos.json'" <<FIN
{
  "version": "$VERSION",
  "version_code": $CODE,
  "construit_le": "$CONSTRUIT",
  "sha256": "$SHA",
  "octets": $OCTETS
}
FIN

dire "Terminé"
echo "  L'application est téléchargeable sur la page d'administration."
echo "  Le service n'a pas besoin d'être redémarré."
echo
echo "  Depuis le téléphone, ouvrez cette page et appuyez sur"
echo "  « Télécharger l'application » :"
echo "      https://IZQUIERDO-NUC.local:8787/"
