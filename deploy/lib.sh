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
    # n'a pas encore de table 'devices' — ce dernier cas se produit quand la
    # base a été créée par un simple import du module (phototheque/app.py
    # instancie DeviceStore au chargement).
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
    # créée au passage par un import doit pouvoir être remplacée. À l'inverse,
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
