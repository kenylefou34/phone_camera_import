#!/usr/bin/env bash
#
# Fonctions de décision du déploiement, isolées de install.sh pour être
# testables (voir tests/test_deploy.py). Aucune de ces fonctions ne modifie
# quoi que ce soit : elles répondent à une question, c'est tout.
#
# Règle à respecter ici : ne JAMAIS décider à partir d'un pipeline.
# Sous `set -o pipefail`, `commande | grep -q motif` renvoie 141 dès que grep
# trouve son motif tôt et ferme le tuyau (la commande amont reçoit SIGPIPE).
# La décision se retrouve inversée alors que la correspondance existait : c'est
# exactement ce qui a laissé l'ancien service tourner le 17/09/2026.

# Python utilisé pour lire les bases SQLite (le venv en production).
PYTHON_LIB="${PYTHON:-python3}"

unite_installee() {
    # Vrai si le fichier d'unité systemd passé en argument existe.
    # Un test de fichier est déterministe et ne dépend ni de systemd ni d'un
    # pipeline, contrairement à `systemctl list-unit-files | grep ...`.
    [ -f "$1" ]
}

nb_appareils() {
    # Affiche le nombre d'appareils appairés dans la base passée en argument.
    # Affiche 0 si le fichier n'existe pas, n'est pas une base lisible, ou
    # n'a pas encore de table 'devices' — ce dernier cas s'est produit quand la
    # base était créée par un simple import du module (phototheque/app.py
    # instanciait DeviceStore au chargement, jusqu'au 17/09/2026).
    local base=$1
    if [ ! -f "$base" ]; then
        echo 0
        return 0
    fi
    "$PYTHON_LIB" - "$base" <<'PY'
import sqlite3, sys
try:
    cx = sqlite3.connect(sys.argv[1])
    print(cx.execute("SELECT COUNT(*) FROM devices").fetchone()[0])
except Exception:
    print(0)
PY
}

doit_reprendre() {
    # Vrai s'il faut reprendre les appairages de l'ancienne base vers la
    # nouvelle : l'ancienne contient des appareils et la nouvelle n'en a aucun.
    #
    # Le critère est le CONTENU, pas l'existence du fichier : une base vide
    # laissée là par un outil de passage doit pouvoir être remplacée. À l'inverse,
    # une nouvelle base déjà peuplée n'est jamais écrasée.
    local ancienne=$1 nouvelle=$2
    local anciens nouveaux
    anciens=$(nb_appareils "$ancienne")
    nouveaux=$(nb_appareils "$nouvelle")
    [ "$anciens" -gt 0 ] && [ "$nouveaux" -eq 0 ]
}

occupant_du_port() {
    # Affiche la ligne du processus qui écoute sur le port, vide si libre.
    # La sortie est capturée dans une variable plutôt que filtrée par un pipe,
    # pour la raison expliquée en tête de fichier.
    ss -lptnH "sport = :$1" 2>/dev/null || true
}

certificat_present() {
    # Vrai si le certificat ET sa clé existent. L'un sans l'autre est
    # inutilisable : on considère alors qu'il n'y a pas de certificat, et
    # install.sh en fabriquera un.
    [ -f "$1" ] && [ -f "$2" ]
}

ecrire_empreinte_admin() {
    # Enregistre l'empreinte du mot de passe lu sur l'ENTRÉE STANDARD.
    #   $1 fichier de destination, $2 interpréteur Python, $3 racine du dépôt
    #
    # Partagée par install.sh (mot de passe tiré au hasard à l'installation) et
    # identifiants.sh (mot de passe choisi par le mainteneur). Une seule copie :
    # les précautions ci-dessous ont chacune coûté une revue, les dupliquer
    # garantirait qu'un correctif futur n'en corrige qu'une moitié.
    local destination=$1 python=$2 racine=$3

    # Le mot de passe ne doit apparaître ni dans une ligne de commande (visible
    # de tout utilisateur via `ps`, le temps du processus) ni dans la source du
    # script Python (visible dans un journal en cas d'erreur). Il traverse donc
    # cette fonction uniquement par l'entrée standard, jamais interpolé ; seul
    # $racine (non secret) passe par sys.argv.
    #
    # Sous-shell avec umask 077 : sans cela, le fichier naîtrait avec les droits
    # par défaut le temps très court qui sépare la redirection « > » du `chmod`
    # ci-dessous. En pratique le dossier de configuration (0700) referme déjà
    # cette fenêtre, mais pour un fichier d'identifiants on ne veut pas dépendre
    # d'une protection posée ailleurs : avec cet umask, le fichier n'existe
    # jamais autrement qu'en 0600.
    #
    # Écriture atomique : on écrit d'abord dans "<destination>.nouveau", jamais
    # directement sur la destination. Deux dangers distincts, selon l'appelant :
    # pour install.sh, un échec laisserait un fichier vide que la garde du
    # lancement suivant prendrait pour un mot de passe valide, fermant
    # l'administration en silence ; pour identifiants.sh, qui écrase un fichier
    # existant, un échec détruirait le mot de passe en cours sans le remplacer,
    # et verrouillerait le mainteneur dehors. Le `mv` final ne s'exécute que si
    # Python a réussi.
    (umask 077; "$python" -c '
import sys
sys.path.insert(0, sys.argv[1])
from phototheque import adminauth
mot_de_passe = sys.stdin.read()
print(adminauth.empreinte(mot_de_passe))
' "$racine" > "$destination.nouveau")
    mv "$destination.nouveau" "$destination"
    chmod 600 "$destination"
}

version_depuis_gradle() {
    # Affiche « versionName versionCode » lus dans un build.gradle.kts.
    # Repli utilisé quand aapt2 n'est pas installé ; aapt2, lui, lit l'APK
    # réellement produit et fait autorité (voir envoyer-apk.sh).
    #
    # AUCUN pipe : `sed ... | head -1` renverrait 141 sous `set -o pipefail`
    # dès que head ferme le tuyau, et ferait avorter le script appelant. C'est
    # la règle en tête de ce fichier, et elle a déjà coûté une production.
    # On récupère donc toutes les correspondances et on garde la première par
    # expansion de paramètre.
    local fichier=$1 nom code
    if [ ! -f "$fichier" ]; then
        echo "inconnue 0"
        return 0
    fi
    nom=$(sed -n 's/.*versionName *= *"\([^"]*\)".*/\1/p' "$fichier")
    code=$(sed -n 's/.*versionCode *= *\([0-9][0-9]*\).*/\1/p' "$fichier")
    nom=${nom%%$'\n'*}
    code=${code%%$'\n'*}
    echo "${nom:-inconnue} ${code:-0}"
}

# ---------------------------------------------------------------------------
# Trouver le NUC sur le reseau
#
# Son adresse n'est PAS stable : elle a change deux fois en deux jours
# (.21 -> .31 -> ailleurs), parce que la box lui donne un bail DHCP ordinaire.
# Chaque bascule cassait tous les scripts, qui ecrivaient 192.168.1.21 en dur.
#
# L'application Android, elle, ne s'en apercoit pas : elle cherche le serveur
# en mDNS d'abord et ne retombe sur l'URL du QR qu'en secours. Les scripts font
# desormais pareil.
# ---------------------------------------------------------------------------

premiere_adresse() {
    # Affiche la premiere adresse IPv4 d'une sortie de `getent hosts`.
    #
    # IPv4 et non IPv6 : `getent` peut rendre les deux, et une adresse
    # lien-local IPv6 (fe80::...) exige un suffixe d'interface que ni ssh ni
    # scp ne recoivent ici. On saute donc tout ce qui contient un deux-points.
    #
    # Aucun pipe : une here-string, pas un pipeline (voir la regle en tete de
    # fichier).
    local sortie=$1 ligne adresse
    while IFS= read -r ligne; do
        [ -z "$ligne" ] && continue
        adresse=${ligne%% *}
        case "$adresse" in
            *:*) continue ;;
            *.*) echo "$adresse"; return 0 ;;
        esac
    done <<< "$sortie"
    return 1
}

port_ouvert() {
    # Vrai si quelque chose repond sur ce port.
    #   $1 hote, $2 port, $3 delai par essai (2 s), $4 nombre d'essais (1)
    #
    # Le code de sortie EST la decision : pas de pipeline, pas de grep.
    #
    # Sonder plutot que se fier a la seule resolution : le 23/09, `.21`
    # repondait au ping mais aucun port n'ecoutait — l'adresse etait tenue par
    # un autre appareil. Un cache mDNS perime produit le meme piege.
    #
    # PLUSIEURS essais parce que le lien du NUC BAT : mesure le 23/09,
    # ~20 s joignable puis ~35 s injoignable, en boucle. Une sonde unique est
    # alors un tirage a pile ou face, et le script renoncerait sur un creux.
    local hote=$1 port=$2 delai=${3:-2} essais=${4:-1} n=0
    while [ "$n" -lt "$essais" ]; do
        if timeout "$delai" bash -c "cat < /dev/null > /dev/tcp/$hote/$port" 2>/dev/null; then
            return 0
        fi
        n=$((n + 1))
        [ "$n" -lt "$essais" ] && sleep 3
    done
    return 1
}

adresse_avahi() {
    # Affiche l'adresse d'une sortie d'`avahi-resolve`, ou rien.
    #
    # Format : "nom<TAB>adresse" — l'adresse est le DERNIER champ, a l'inverse
    # de `getent hosts` ou elle est le premier. Deux analyseurs, donc, plutot
    # qu'un seul qui se tromperait sur l'un des deux.
    local sortie=$1 ligne adresse
    while IFS= read -r ligne; do
        [ -z "$ligne" ] && continue
        adresse=${ligne##*$'\t'}
        adresse=${adresse##* }
        case "$adresse" in
            *:*) continue ;;
            *.*) echo "$adresse"; return 0 ;;
        esac
    done <<< "$sortie"
    return 1
}

resoudre_mdns() {
    # Affiche l'adresse IPv4 annoncee en mDNS pour ce nom, ou rend 1.
    #
    # `avahi-resolve -4` D'ABORD, `getent` en secours. Mesure le 23/09 : dix
    # `getent hosts IZQUIERDO-NUC.local` d'affilee ont tous echoue alors
    # qu'`avahi-resolve` repondait sans broncher. La raison est dans
    # /etc/nsswitch.conf : `mdns4_minimal [NOTFOUND=return]` n'interroge que
    # l'IPv4 et coupe la chaine des qu'elle manque — or le NUC annoncait a ce
    # moment-la son IPv6 sans son IPv4. `avahi-resolve` parle au demon local
    # directement et n'a pas ce trou.
    #
    # Le `-4` n'est pas cosmetique : sans lui, avahi rend l'IPv6 en premier.
    local nom=$1 sortie adresse=""

    if command -v avahi-resolve >/dev/null 2>&1; then
        sortie=$(timeout 5 avahi-resolve -4 -n "$nom" 2>/dev/null) || sortie=""
        adresse=$(adresse_avahi "$sortie") || adresse=""
    fi

    if [ -z "$adresse" ]; then
        sortie=$(getent hosts "$nom" 2>/dev/null) || sortie=""
        adresse=$(premiere_adresse "$sortie") || adresse=""
    fi

    [ -z "$adresse" ] && return 1
    echo "$adresse"
}

adresse_nuc() {
    # Affiche l'adresse a utiliser pour joindre le NUC, ou rend 1.
    #   $1 nom mDNS, $2 adresse de repli, $3 port (22), $4 essais (1)
    #
    # La RESOLUTION est refaite a chaque essai, pas une fois pour toutes : le
    # 23/09, elle a reussi, puis echoue dix fois de suite, puis reussi de
    # nouveau. La sonder une seule fois envoyait au repli pour rien.
    #
    # Et chaque adresse est SONDEE avant d'etre retenue : resoudre ne prouve
    # pas que la machine repond. Le meme jour, `.21` repondait au ping sans
    # que rien n'y ecoute — l'adresse etait passee a un autre appareil.
    local nom=$1 repli=$2 port=${3:-22} essais=${4:-1}
    local n=0 adresse="" vu=""

    while [ "$n" -lt "$essais" ]; do
        adresse=$(resoudre_mdns "$nom") || adresse=""
        if [ -n "$adresse" ]; then
            vu=$adresse
            if port_ouvert "$adresse" "$port" 2 1; then
                echo "  $nom -> $adresse" >&2
                echo "$adresse"
                return 0
            fi
        fi
        n=$((n + 1))
        [ "$n" -lt "$essais" ] && sleep 3
    done

    if [ -n "$vu" ]; then
        echo "  $nom resout en $vu, mais $vu:$port n'a jamais repondu" >&2
    else
        echo "  $nom n'a jamais resolu (Avahi muet ?)" >&2
    fi

    if [ -n "$repli" ] && [ "$repli" != "$vu" ]; then
        echo "  essai du repli $repli" >&2
        if port_ouvert "$repli" "$port" 2 "$essais"; then
            echo "$repli"
            return 0
        fi
    fi

    return 1
}
