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
etape "1/9  Vérifications préalables"

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
etape "2/9  Environnement Python (venv)"

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
etape "3/9  Certificat du serveur"

CONFIG_DIR="$HOME/.config/phototheque"
CERT="$CONFIG_DIR/cert.pem"
CLE="$CONFIG_DIR/key.pem"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if certificat_present "$CERT" "$CLE"; then
    info "certificat déjà en place, conservé"
    empreinte=$("$PYTHON" - "$racine" "$CERT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from phototheque import tls
print(tls.empreinte_certificat(sys.argv[2]))
PY
)
    info "empreinte : $empreinte"
else
    # L'adresse du NUC, pour que joindre le service par son IP n'ajoute pas
    # une seconde erreur au navigateur. Absente si le réseau n'est pas prêt :
    # on se contente alors des noms, plutôt que de fabriquer un SAN invalide.
    IP=$(hostname -I | awk '{print $1}')
    noms="DNS:$(hostname).local,DNS:localhost,IP:127.0.0.1"
    if [ -n "$IP" ]; then
        noms="$noms,IP:${IP}"
    else
        info "ATTENTION : adresse IP introuvable, le certificat ne couvrira"
        info "            que les noms. L'accès par IP avertira le navigateur."
    fi

    info "fabrication d'un certificat auto-signé (10 ans)"
    if ! erreur=$(openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=$(hostname).local" \
        -addext "subjectAltName=${noms}" \
        -keyout "$CLE" -out "$CERT" 2>&1); then
        info "$erreur"
        echec "la fabrication du certificat a échoué (message ci-dessus).
    Vérifiez qu'openssl est installé et que $CONFIG_DIR est accessible en écriture."
    fi
    chmod 600 "$CLE"
    info "certificat créé"
fi

# --------------------------------------------------------------------------
etape "4/9  Mot de passe d'administration"

ADMIN="$CONFIG_DIR/admin"
if [ -f "$ADMIN" ]; then
    info "mot de passe déjà défini, conservé"
    info "(pour en changer : rm $ADMIN puis relancer ce script)"
else
    MOT_DE_PASSE=$("$PYTHON" -c "import secrets; print(secrets.token_urlsafe(12))")
    # Le mot de passe ne doit apparaître nulle part dans une ligne de commande
    # (visible de tout utilisateur via `ps`, le temps du processus) ni dans la
    # source du script Python (visible dans un journal en cas d'erreur). Il
    # transite donc uniquement par l'entrée standard, jamais interpolé ; seul
    # $racine (non secret) passe par sys.argv, comme pour le certificat.
    #
    # Sous-shell avec umask 077 : sans cela, le fichier naîtrait avec les
    # droits par défaut le temps très court qui sépare la redirection « > »
    # du `chmod` ci-dessous. En pratique $CONFIG_DIR (0700) referme déjà
    # cette fenêtre, mais pour un fichier d'identifiants on ne veut pas
    # dépendre d'une protection posée ailleurs : avec cet umask, le fichier
    # n'existe jamais autrement qu'en 0600. Le `chmod` explicite est conservé
    # ensuite : il rend l'intention lisible et rattrape le cas d'un fichier
    # préexistant avec des droits trop larges.
    #
    # Écriture atomique : on écrit d'abord dans "$ADMIN.nouveau", jamais
    # directement sur "$ADMIN". Si Python échoue après que la redirection a
    # créé le fichier, `set -e` arrête le script AVANT le `mv` ci-dessous :
    # seul le fichier temporaire traîne, "$ADMIN" reste absent, et le
    # prochain lancement régénère normalement. Sans cela, un échec en cours
    # de calcul laisserait "$ADMIN" vide mais présent : la garde
    # `[ -f "$ADMIN" ]` du lancement suivant le prendrait pour un mot de
    # passe valide et ne le régénérerait jamais — fermant l'administration
    # en silence (verifier() refuse proprement, sans planter le serveur, donc
    # rien n'indiquerait la cause).
    (umask 077; printf '%s' "$MOT_DE_PASSE" | "$PYTHON" -c '
import sys
sys.path.insert(0, sys.argv[1])
from phototheque import adminauth
mot_de_passe = sys.stdin.read()
print(adminauth.empreinte(mot_de_passe))
' "$racine" > "$ADMIN.nouveau")
    mv "$ADMIN.nouveau" "$ADMIN"
    chmod 600 "$ADMIN"
    printf '\n\033[1m    ┌─────────────────────────────────────────────┐\033[0m\n'
    printf '\033[1m    │  Identifiants d'"'"'administration              │\033[0m\n'
    printf '\033[1m    │  utilisateur : admin                        │\033[0m\n'
    printf '\033[1m    │  mot de passe : %-27s │\033[0m\n' "$MOT_DE_PASSE"
    printf '\033[1m    └─────────────────────────────────────────────┘\033[0m\n'
    info "NOTE-LE MAINTENANT : il ne sera plus jamais affiché."
    printf '\n'
fi

# --------------------------------------------------------------------------
etape "5/9  Retrait de l'ancien service"

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
etape "6/9  Reprise des appairages"

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
etape "7/9  Le port $PORT est-il libre ?"

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
etape "8/9  Installation et démarrage"

sudo cp deploy/${SERVICE}.service "$UNITE"
info "$UNITE"

# Nom affiché par l'application dans sa liste de serveurs. « %h » est le nom
# de la machine, un nom technique ; un nom choisi (ex. « Photothèque du
# salon ») est plus parlant, et reste correct si le service change un jour
# de matériel.
NOM_AFFICHE="phototheque sur %h"
if [ -f "$CONFIG_DIR/nom" ]; then
    nom_lu=$(head -1 "$CONFIG_DIR/nom")
    # Un fichier vide ou ne contenant que des blancs veut dire « je n'ai
    # rien choisi », pas « je veux un nom vide » : un nom vide casserait la
    # découverte réseau (fichier XML refusé par Avahi, ou service annoncé
    # sans nom) sans le moindre message d'erreur. On ne retient donc le
    # contenu du fichier que s'il reste quelque chose une fois les espaces
    # retirés.
    if [ -n "$(printf '%s' "$nom_lu" | tr -d '[:space:]')" ]; then
        NOM_AFFICHE="$nom_lu"
    fi
fi
# Le nom est injecté dans un fichier XML (l'annonce Avahi) : « & », « < » et
# « > » y sont invalides tels quels. Un fichier invalide ferait qu'Avahi
# refuse de le charger — l'annonce réseau disparaîtrait sans aucun message.
# On échappe donc ces caractères en entités XML plutôt que de rejeter le nom :
# un usager non technique ne comprendrait pas pourquoi son nom serait
# refusé, et l'entité XML est de toute façon décodée à l'affichage — le nom
# apparaît intact sur le réseau.
#
# La substitution passe par Python, pas par `sed` : le nom peut contenir
# « / », « & » ou « \ », qui ont chacun un sens particulier pour `sed`
# (délimiteur habituel, référence arrière, échappement). Un remplacement
# littéral en Python n'a pas ce problème.
"$PYTHON" - "deploy/avahi-${SERVICE}.service" "$NOM_AFFICHE" <<'PY' | sudo tee "$AVAHI" >/dev/null
import sys
gabarit, nom = sys.argv[1], sys.argv[2]
nom_xml = nom.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
with open(gabarit, encoding="utf-8") as f:
    contenu = f.read()
sys.stdout.write(contenu.replace("NOM_AFFICHE", nom_xml))
PY
info "$AVAHI"
info "annoncé sur le réseau sous : ${NOM_AFFICHE}"

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
etape "9/9  Vérification"

# Laisser à uvicorn le temps d'ouvrir son port avant de l'interroger.
#
# Une réponse 401 compte comme un succès : depuis le durcissement de
# l'administration (issue #10), « / » exige le mot de passe et urlopen lève
# donc une HTTPError. Sans ce rattrapage, la fonction ne peut plus JAMAIS
# réussir : la boucle d'attente ci-dessous ferait ses 20 tours à chaque
# installation, soit 10 secondes perdues pour rien. Ici on veut seulement
# savoir si le service répond — pas ce qu'il répond.
service_repond() {
    "$PYTHON" - "$PORT" <<'PY' >/dev/null 2>&1
import ssl, sys, urllib.request, urllib.error
contexte = ssl._create_unverified_context()   # certificat auto-signé, attendu
try:
    urllib.request.urlopen("https://127.0.0.1:%s/" % sys.argv[1],
                           timeout=2, context=contexte)
except urllib.error.HTTPError:
    pass          # 401 : le service est là et répond, c'est tout ce qu'on veut
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
#
# 401 PARTOUT est le résultat CORRECT et attendu : « / » et « /pair » sont
# derrière le mot de passe d'administration (issue #10), « /status » derrière
# le jeton d'appareil, et ce script ne s'authentifie nulle part. Voir un 200
# ici signifierait que le durcissement ne fonctionne plus. L'accord entre
# cette liste et les adresses réellement protégées est verrouillé par
# tests/test_deploy.py.
"$PYTHON" - "$PORT" <<'PY' || echec "le service répond mal (voir ci-dessus)."
import ssl, sys, urllib.request, urllib.error

contexte = ssl._create_unverified_context()   # certificat auto-signé, attendu
port = sys.argv[1]
souci = False
for chemin, attendu in (("/", 401), ("/pair", 401), ("/status", 401)):
    try:
        code = urllib.request.urlopen("https://127.0.0.1:%s%s" % (port, chemin),
                                       timeout=5, context=contexte).status
    except urllib.error.HTTPError as e:
        code = e.code          # 401 attendu : authentification exigée, tant mieux
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
info "admin     : https://$(hostname).local:${PORT}/"
info "appairage : https://$(hostname).local:${PORT}/pair"
info "identifiant : admin (mot de passe affiché à sa création, étape 4/9)"
info "ATTENTION : le navigateur avertira au premier accès (certificat"
info "            auto-signé). Accepter une fois par appareil."
info "journal   : journalctl -u ${SERVICE} -f"
