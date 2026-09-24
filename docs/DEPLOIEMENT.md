# Déploiement de `phototheque` sur le NUC

Comment installer, mettre à jour et dépanner le service d'ingestion. Tout est
en français et détaillé : l'objectif est que tu puisses rejouer l'opération
seul, en comprenant ce que fait chaque commande.

> Le module s'appelait `mediaserve` jusqu'au 17/09/2026. Si tu tombes sur ce
> nom dans un ancien document, c'est le même composant.

**Ce document couvre le serveur.** Pour l'application Android — monter la
chaîne de compilation, construire l'APK, le déposer sur le NUC, l'installer sur
un téléphone et l'appairer — voir
**[`APPLICATION-ANDROID.md`](APPLICATION-ANDROID.md)**.

---

## En une commande

Depuis la racine du dépôt, **sur le NUC, dans un vrai terminal** :

```bash
cd ~/phone_camera_import
git pull
./deploy/install.sh
```

C'est tout. Le script est **idempotent** : le relancer ne casse rien, il remet
simplement l'installation dans l'état voulu. C'est la commande à rejouer après
chaque modification du code.

Il demande ton mot de passe `sudo` : deux étapes touchent au système (l'unité
systemd et le fichier Avahi). D'où le « vrai terminal » — un canal sans TTY ne
peut pas saisir de mot de passe.

### Ce que tu dois voir

Neuf étapes numérotées, puis :

```
    /        401  ok
    /pair    401  ok
    /status  401  ok
    état      : active / enabled
    admin     : https://IZQUIERDO-NUC.local:8787/
```

`401` **partout** est le résultat correct et attendu, pas une panne : `/` et
`/pair` sont derrière le mot de passe d'administration, `/status` derrière le
jeton d'appareil, et le script de vérification ne s'authentifie nulle part. Un
`200` à cet endroit voudrait dire que la protection ne fonctionne plus.
Si le script s'arrête sur `ÉCHEC`, il dit quoi regarder.

### Le vocabulaire, en quatre phrases

- **systemd** est le chef d'orchestre des programmes qui tournent en fond sous
  Linux. Sans lui, il faudrait lancer le serveur à la main dans un terminal, et
  il s'arrêterait en le fermant.
- Un **service** (ou *unité*) est un fichier texte qui lui décrit quoi lancer,
  quand et comment. Le nôtre est `deploy/phototheque.service`.
- **`active`** veut dire « il tourne en ce moment ». **`enabled`** veut dire « il
  repartira tout seul au prochain démarrage du NUC ». Ce sont deux choses
  différentes, et on veut les deux.
- **Avahi** annonce la machine sur le réseau local sous `<nom d'hôte>.local`, ce
  qui évite de retenir une adresse IP.

---

## Ce que fait le script, étape par étape

Si tu veux le faire à la main, ou comprendre ce qui se passe, voici l'équivalent
de chaque étape.

### 1. Vérifications préalables

Le script contrôle qu'il est bien lancé depuis le dépôt et que les fichiers
attendus existent. Il prévient aussi si le disque de la bibliothèque n'est pas
monté :

```bash
mountpoint -q /media/izquierdo/Famille && echo monté || echo "NON monté"
```

Ce n'est pas bloquant : l'unité systemd contient `RequiresMountsFor`, donc le
service attendra le montage au lieu de démarrer dans le vide.

### 2. Environnement Python

```bash
python3 -m venv ~/.venv-server
~/.venv-server/bin/pip install -r requirements-server.txt
```

**Pourquoi un venv ?** Ubuntu applique la PEP 668 : le Python du système refuse
`pip install --user` pour éviter d'abîmer les paquets gérés par `apt`. On
installe donc les dépendances dans un environnement isolé, `~/.venv-server`.
C'est aussi pour ça que l'unité systemd appelle `~/.venv-server/bin/uvicorn` et
non `uvicorn` tout court.

Le trieur `mediasort`, lui, n'a besoin d'aucune dépendance : il n'utilise que la
bibliothèque standard. Seuls `exiftool` et `ffmpeg` lui sont utiles, côté système :

```bash
sudo apt-get install -y libimage-exiftool-perl ffmpeg
```

### 3. Certificat du serveur

```bash
mkdir -p ~/.config/phototheque && chmod 700 ~/.config/phototheque
IP=$(hostname -I | awk '{print $1}')      # l'adresse du NUC sur le réseau
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -subj "/CN=$(hostname).local" \
    -addext "subjectAltName=DNS:$(hostname).local,DNS:localhost,IP:127.0.0.1,IP:${IP}" \
    -keyout ~/.config/phototheque/key.pem -out ~/.config/phototheque/cert.pem
chmod 600 ~/.config/phototheque/key.pem
```

**`IP:${IP}` n'est pas facultatif** : sans ce nom alternatif, joindre le
service par son adresse IP (par exemple quand le `.local` ne résout pas)
ajoute une seconde erreur à l'avertissement du navigateur. Le script réel le
pose ; si l'adresse est introuvable, il se contente des noms plutôt que de
fabriquer un nom alternatif invalide.

Le service ne parle plus qu'en **HTTPS** : sans certificat, pas de démarrage.
N'ayant personne pour garantir ce certificat (pas d'autorité extérieure,
contrairement à un site public), il est **auto-signé** — d'où l'avertissement
du navigateur au premier accès, normal, détaillé plus bas.

Si le certificat existe déjà, le script le garde tel quel et affiche son
empreinte — c'est elle que l'application épingle pour reconnaître le NUC (voir
plus bas, section « Le certificat et le mot de passe »).

### 4. Mot de passe d'administration

Depuis la racine du dépôt :

```bash
MOT_DE_PASSE=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
printf 'mot de passe : %s\n' "$MOT_DE_PASSE"      # à noter tout de suite
(umask 077; printf '%s' "$MOT_DE_PASSE" | ~/.venv-server/bin/python -c '
import sys
from phototheque import adminauth
print(adminauth.empreinte(sys.stdin.read()))
' > ~/.config/phototheque/admin.nouveau)
mv ~/.config/phototheque/admin.nouveau ~/.config/phototheque/admin
chmod 600 ~/.config/phototheque/admin
```

Les trois précautions ne sont pas du décor : le mot de passe ne transite que
par l'entrée standard (jamais dans une ligne de commande, visible de tous via
`ps`), `umask 077` fait naître le fichier en `0600` dès sa création, et
l'écriture passe par un fichier temporaire — un échec en cours de route
laisserait sinon un fichier `admin` vide, que le lancement suivant prendrait
pour un mot de passe valide, fermant l'administration en silence.

Un mot de passe est tiré au hasard et son empreinte enregistrée dans
`~/.config/phototheque/admin` (jamais le mot de passe en clair). Il protège
`/`, `/pair`, `/devices` et la révocation d'un appareil.

**Il n'est affiché qu'une seule fois**, à la création :

```
    ┌─────────────────────────────────────────────┐
    │  Identifiants d'administration               │
    │  utilisateur : admin                         │
    │  mot de passe : xxxxxxxxxxxxxxxxxxxxxxxxxx   │
    └─────────────────────────────────────────────┘
```

**Note-le tout de suite.** Si le fichier `admin` existe déjà, cette étape ne
fait rien et n'affiche rien : le mot de passe en place est conservé. Pour en
changer, voir la section « Le certificat et le mot de passe » plus bas.

### 5. Retrait de l'ancien service

```bash
sudo systemctl disable --now mediaserve.service
sudo rm -f /etc/systemd/system/mediaserve.service
sudo rm -f /etc/avahi/services/avahi-mediaserve.service
sudo systemctl daemon-reload
```

**C'est le piège du renommage.** Installer le nouveau service sans retirer
l'ancien laisse deux unités actives qui se disputent le port 8787 : la seconde
échoue au démarrage, redémarre en boucle, et les journaux deviennent illisibles.

Cette étape vient **avant** la reprise des données, et ce n'est pas un détail :
déplacer une base SQLite pendant que le processus qui l'écrit tourne encore
donne un état incohérent.

> **Comment cette étape a échoué le 17/09/2026.** Le script testait la présence
> de l'ancien service avec `systemctl list-unit-files | grep -q "^mediaserve"`.
> Sous `set -o pipefail`, `grep -q` s'arrête au premier résultat et ferme le
> tuyau ; `systemctl`, qui a encore beaucoup à écrire, reçoit SIGPIPE et sort en
> 141 ; le pipeline renvoie donc 141 **alors que la correspondance existait**.
> La condition était inversée, le nettoyage sauté. La détection se fait
> maintenant sur l'existence du fichier d'unité — déterministe, sans pipeline.

### 6. Reprise des appairages

```bash
mv ~/mediaserve_devices.db ~/phototheque_devices.db
```

La base des **appareils appairés** portait l'ancien nom. Sans cette reprise, le
service redémarrerait avec zéro appareil connu et les téléphones déjà appairés
seraient rejetés — il faudrait tout réappairer au QR code.

Le script décide d'après le **contenu** des bases, pas d'après l'existence du
fichier : il reprend si l'ancienne contient des appareils et la nouvelle aucun,
et n'écrase jamais une base déjà peuplée. Une base vide rencontrée au passage
est mise de côté sous `*.vide-<horodatage>` plutôt que supprimée.

> **Pourquoi le contenu et pas l'existence.** Le 17/09/2026,
> `phototheque/app.py` instanciait `DeviceStore` au chargement du module :
> **importer l'application suffisait à créer la base, vide**. Lancer les tests
> sur le NUC créait donc `~/phototheque_devices.db`, et le test d'existence en
> a conclu à tort que la reprise avait déjà eu lieu. La base n'est désormais
> ouverte qu'à la première utilisation réelle, mais le critère reste le
> contenu : une base vide traînante ne doit jamais bloquer la reprise.

Le catalogue des médias, lui, ne change pas de nom : il s'appelle
`~/mediasort_catalog.db` d'après le trieur, qui n'a pas été renommé.

### 7. Le port est-il libre ?

```bash
ss -lptn 'sport = :8787'
```

Filet de sécurité avant de démarrer : même sans ancienne unité, un `uvicorn`
lancé à la main peut tenir le port. Le script s'arrête avec un message clair
plutôt que de laisser systemd boucler.

### 8. Installation de l'unité systemd et de l'annonce réseau

```bash
sudo cp deploy/phototheque.service /etc/systemd/system/
sudo cp deploy/avahi-phototheque.service /etc/avahi/services/
sudo systemctl daemon-reload
sudo systemctl enable --now phototheque.service
sudo systemctl restart avahi-daemon
```

- **`daemon-reload`** : systemd relit ses fichiers de configuration. Sans ça, il
  continue d'utiliser l'ancienne version en mémoire.
- **`enable`** : le service démarrera automatiquement à chaque boot du NUC.
- **`--now`** : et démarre aussi tout de suite.
- **`restart avahi-daemon`** : Avahi ne relit ses fichiers de service qu'au
  redémarrage. C'est lui qui permet d'écrire `https://IZQUIERDO-NUC.local:8787`
  au lieu de retenir l'adresse IP, et qui permettra à l'app Android de trouver
  le NUC seule.

> **Le nom d'hôte compte.** La machine s'annonce sous `<nom d'hôte>.local`,
> ici `IZQUIERDO-NUC.local`. `nuc.local` ne résout pas. L'URL publiée dans le
> QR d'appairage est donc déduite du nom d'hôte réel (`PUBLIC_URL` dans
> `phototheque/config.py`) et non écrite en dur — sinon l'app scannerait une
> adresse injoignable. Vérifier ce qui est réellement annoncé, depuis une
> autre machine du réseau :
> ```bash
> avahi-browse -tpr _phototheque._tcp
> ```

**Nom convivial (facultatif).** Par défaut l'annonce réseau porte
`phototheque sur <nom d'hôte>` (ex. `phototheque sur IZQUIERDO-NUC`), un nom
technique. Pour afficher autre chose (« Photothèque du salon ») :

```bash
echo "Photothèque du salon" > ~/.config/phototheque/nom
./deploy/install.sh
```

Un fichier absent, vide ou ne contenant que des espaces retombe sur le nom par
défaut — jamais sur une annonce sans nom.

`enable` et `active` sont deux choses distinctes : `active` veut dire « il tourne
en ce moment », `enabled` veut dire « il repartira au prochain démarrage ».

### 9. Vérification

Il n'y a **pas de `curl` sur le NUC** : on interroge avec Python. Le certificat
étant auto-signé, personne ne le garantit pour Python non plus : on désactive
donc la vérification pour cet appel local, avec
`ssl._create_unverified_context()`.

```bash
~/.venv-server/bin/python -c "
import ssl, urllib.request, urllib.error
contexte = ssl._create_unverified_context()
for p in ('/', '/pair', '/status'):
    try:
        code = urllib.request.urlopen('https://127.0.0.1:8787' + p, timeout=5,
                                       context=contexte).status
    except urllib.error.HTTPError as e:
        code = e.code
    print(p, code)
"
```

Résultat attendu : **`401` sur les trois adresses** — c'est le comportement
correct, pas une panne. `/` et `/pair` exigent le mot de passe
d'administration, `/status` le jeton d'un appareil appairé, et cette commande
ne s'authentifie nulle part. Le `try/except` n'est pas décoratif : sans lui,
`urlopen` lève une `HTTPError` sur le premier `401` et la commande s'arrête sur
une trace d'erreur.

Le script contrôle aussi que le service est bien `active` après démarrage : un
service en boucle de redémarrage ne doit pas passer pour une installation
réussie.

### Les décisions du script sont testées

Les deux décisions qui se sont trompées le 17/09/2026 (détecter l'ancien
service, décider de reprendre les appairages) sont isolées dans
`deploy/lib.sh`, sans effet de bord, et couvertes par `tests/test_deploy.py`.
Un test interdit par ailleurs de décider à partir d'un pipeline, la cause de la
première panne.

---

## Après une modification du code

```bash
cd ~/phone_camera_import
git pull
./deploy/install.sh
```

**Le code n'est jamais rechargé tout seul.** `uvicorn` tourne sans `--reload` en
production : tant qu'on ne redémarre pas le service, il continue d'exécuter la
version chargée en mémoire au démarrage. Le script s'en charge (`systemctl
restart`), mais si tu veux juste redémarrer sans rien réinstaller :

```bash
sudo systemctl restart phototheque
```

---

## Le certificat et le mot de passe

`install.sh` fabrique les deux à la première installation, dans
`~/.config/phototheque/` :

| Fichier | Rôle | Si tu le supprimes |
|---|---|---|
| `cert.pem`, `key.pem` | certificat du serveur | un nouveau est fabriqué — **tous les téléphones appairés sont rejetés** et doivent être réappairés |
| `admin` | empreinte du mot de passe | un nouveau mot de passe est tiré et affiché |
| `nom` | nom affiché sur le réseau (facultatif) | retour à « phototheque sur <machine> » |

**Ne supprime jamais le certificat sans raison.** L'application épingle son
empreinte : la changer revient à changer d'identité aux yeux des téléphones.

**Changer les identifiants (en choisir) :**

```bash
~/phone_camera_import/deploy/identifiants.sh
```

Le script change **l'identifiant et le mot de passe**. Il affiche d'abord
l'identifiant actuel ; le laisser vide le conserve. Puis il demande le nouveau
mot de passe **deux fois**, sans jamais l'afficher
— ni à l'écran, ni dans l'historique du terminal. La confirmation n'est pas une
formalité : une coquille dans un mot de passe qu'on ne voit pas s'écrire ne se
découvrirait qu'à la connexion suivante, sans moyen de savoir ce qui a été tapé.

Il ne demande pas `sudo` et **ne redémarre rien** : le service relit le fichier
à chaque requête, le nouveau mot de passe est donc actif immédiatement.

En dessous de 12 caractères, il **avertit sans refuser** — c'est ton réseau et
ton arbitrage. Le serveur ralentit désormais les essais répétés (voir
ci-dessous), mais un mot de passe très court se devine avant même que cette
limitation n'entre en jeu.

> **Pour vérifier, ouvre une fenêtre de navigation privée.** Tant qu'un
> navigateur reste ouvert, il continue d'envoyer les anciens identifiants sans
> les redemander — c'est le propre de l'authentification HTTP Basic, et ça donne
> l'impression trompeuse que le changement n'a pas pris.

**À propos de l'identifiant.** Il valait `admin` jusqu'au 18/09/2026, en dur
dans le code. En changer écarte le bruit de fond des balayages automatiques, qui
essaient `admin`, `root` et `administrator` avant tout le reste. Mais soyons
clairs sur ce que ça vaut : **ce n'est pas un secret** — il n'est pas haché,
contrairement au mot de passe, et il est stocké en clair dans
`~/.config/phototheque/utilisateur`. C'est une gêne pour un attaquant, pas une
protection. Ce qui protège reste le mot de passe.

Un `:` y est refusé : l'authentification transmet `utilisateur:mot de passe` et
le serveur découpe sur le premier deux-points, donc un tel nom ne pourrait
jamais être reconnu.

**Le serveur ralentit les essais répétés.** Après 5 mots de passe erronés
depuis une même machine, il refuse pendant un délai qui **double** à chaque
nouvel essai (2 s, 4 s, 8 s…), plafonné à une minute. Le refus est alors
immédiat : le serveur ne calcule même plus l'empreinte. C'est le point
important — cette vérification coûte environ 100 ms des deux cœurs du NUC, dans
le processus qui range aussi tes photos ; sans cette limite, s'acharner sur le
mot de passe ralentissait l'import.

Trois choses à savoir :

- Le décompte est **par machine**. Quelqu'un qui s'acharne depuis un autre
  appareil ne te bloque pas.
- Une connexion réussie **efface l'ardoise**.
- Naviguer normalement ne compte pas : seul un mot de passe réellement erroné
  est décompté.

Si tu es toi-même bloqué, il suffit d'**attendre une minute**. En cas d'urgence,
`sudo systemctl restart phototheque` remet le décompte à zéro (il vit en
mémoire, il ne survit pas au redémarrage).

**Identifiant oublié :**

```bash
rm ~/.config/phototheque/utilisateur
```

Le fichier absent vaut `admin` — c'est le filet, et c'est aussi pourquoi un
fichier vide ou abîmé ne verrouille personne dehors.

**Mot de passe perdu :**

```bash
rm ~/.config/phototheque/admin
./deploy/install.sh
```

Le script relance la fabrication (étape 4/9) et affiche un mot de passe tiré au
hasard — **une seule fois**. Note-le immédiatement. Utilise plutôt
`identifiants.sh` ci-dessus si tu veux en choisir un.

### Migrer vers une autre machine

Le téléphone retrouve le serveur par le réseau, pas par son adresse : il cherche
le service `_phototheque._tcp` et reconnaît le bon au certificat. Deux façons de
déménager :

**Garder les appairages** — copier la configuration et les données :

```bash
scp -r ~/.config/phototheque nouvelle-machine:~/.config/
scp ~/mediasort_catalog.db ~/phototheque_devices.db ~/phototheque_journal.db \
    nouvelle-machine:~/
```

Puis `./deploy/install.sh` sur la nouvelle machine. Les téléphones continuent de
fonctionner sans rien faire. Réserve : le certificat copié porte les noms de
l'ancienne machine, donc le navigateur redeviendra avertissant.

**Repartir propre** — ne rien copier, lancer `./deploy/install.sh`, puis
réappairer chaque téléphone avec un nouveau QR.

---

## Consulter et dépanner

```bash
systemctl status phototheque         # état détaillé (lecture : pas besoin de sudo)
journalctl -u phototheque -f         # journal en direct
journalctl -u phototheque -n 50      # les 50 dernières lignes
journalctl -u phototheque -b         # depuis le dernier démarrage du NUC
```

| Symptôme | Cause probable | Quoi faire |
|---|---|---|
| Le service ne démarre pas au boot | Disque `Famille` non monté | `mountpoint -q /media/izquierdo/Famille` ; l'unité l'attend via `RequiresMountsFor`, il suffit de monter le disque |
| `Address already in use` | Ancien service encore actif | `systemctl list-unit-files \| grep -E 'mediaserve\|phototheque'` puis retirer l'ancien (étape 5) |
| L'adresse `.local` est inaccessible, l'IP fonctionne | Annonce mDNS absente, ou mauvais nom d'hôte | `sudo systemctl restart avahi-daemon` ; vérifier le nom réel avec `hostname` et ce qui est annoncé avec `avahi-browse -tpr _phototheque._tcp` depuis une autre machine |
| `http://IZQUIERDO-NUC.local:8787/` ne répond plus, message peu explicite du navigateur | Le service ne parle plus qu'en HTTPS : un même port ne sert pas les deux protocoles | Taper `https://IZQUIERDO-NUC.local:8787/` |
| Le navigateur affiche un avertissement de sécurité en `https://` | Certificat auto-signé — normal, personne d'extérieur ne le garantit | Cliquer « Paramètres avancés » puis « Continuer » ; une fois par appareil |
| Identifiant ou mot de passe d'administration à changer | — | `./deploy/identifiants.sh` : il te les fait choisir, sans sudo ni redémarrage |
| Identifiant d'administration oublié | — | `rm ~/.config/phototheque/utilisateur` : le fichier absent vaut `admin` |
| `429` / « trop d'essais » sur l'administration | 5 mots de passe erronés depuis cette machine (issue #19) | Attendre une minute ; en urgence `sudo systemctl restart phototheque` remet le décompte à zéro |
| Mot de passe d'administration perdu | — | `rm ~/.config/phototheque/admin && ./deploy/install.sh` : un nouveau est tiré et affiché |
| Le mot de passe changé n'est pas pris en compte | Le navigateur renvoie l'ancien tant qu'il n'est pas fermé (HTTP Basic) | Réessayer dans une fenêtre de navigation privée |
| Téléphones soudain non reconnus | Base d'appairage perdue | Vérifier `~/phototheque_devices.db` ; l'ancienne était `~/mediaserve_devices.db` (étape 6) |
| Le QR d'appairage reste blanc | Page servie par une version antérieure au correctif | Relancer `git pull && ./deploy/install.sh` : le code n'est pas rechargé tout seul |
| `database is locked` | Écriture concurrente sur le catalogue | Vérifier qu'un `--backfill-signatures` ne tourne pas : `pgrep -af "python3 -m mediasort"` |

### Revenir en arrière

Les unités systemd sont de simples fichiers texte, la marche arrière est directe :

```bash
sudo systemctl disable --now phototheque
sudo rm /etc/systemd/system/phototheque.service
sudo rm /etc/avahi/services/avahi-phototheque.service
sudo systemctl daemon-reload
```

Pour revenir à une version antérieure du code : `git log --oneline` pour trouver
le commit, `git checkout <commit>`, puis `./deploy/install.sh`.

Le catalogue est sauvegardé avant les opérations lourdes. Pour le restaurer :

```bash
sudo systemctl stop phototheque
cp ~/mediasort_catalog.db.avant-signatures ~/mediasort_catalog.db
sudo systemctl start phototheque
```

### Les médias que le serveur n'a pas su ranger

Un fichier reçu que le trieur n'arrive pas à ranger — disque plein, média
illisible, source modifiée pendant la copie — n'est **pas détruit**. Il est
déplacé dans :

```
<INCOMING_DIR>/_echecs/<chemin envoyé par le téléphone>
```

soit, avec les réglages par défaut,
`/media/izquierdo/Famille/incoming/_echecs/`. Chaque média y est accompagné
d'un petit fichier `<nom>.motif` qui porte la raison de l'échec et sa date.

**Avant l'issue #16, ces fichiers étaient supprimés.** Le nettoyage de fin de
synchro effaçait le dossier de session sans regarder le bilan, et un fichier en
échec y restait. L'horizon n'avançait pas, donc le téléphone reproposait le
média — mais cette garantie reposait entièrement sur lui. Si l'application
libérait la place après envoi, ou si le DCIM était vidé à la main, l'unique
copie restante venait d'être détruite par le serveur.

**Où les voir.** Sur la page d'administration, un bloc « Médias non rangés »
apparaît dès qu'il y en a — et seulement dans ce cas. Il liste chaque fichier,
sa raison, sa taille et sa date.

**Comment ça se vide.** *Jamais tout seul.* Il n'y a **aucune purge
automatique**, et c'est délibéré : une purge à l'ancienneté redeviendrait
exactement le défaut qu'on vient de corriger, avec un délai. Le bouton
« Vider la quarantaine » de la page d'administration est le seul moyen, et il
demande confirmation.

**Ce dossier ne grossit que quand quelque chose ne va pas.** Qu'il grossisse est
un signal, pas un déchet. Traitez la cause avant de vider — sinon le téléphone
renverra le même fichier à la prochaine synchro, il échouera pareil, et il
reviendra. La boucle est bornée : un média identique au même chemin n'occupe
qu'une place, ce n'est pas la quarantaine qui remplira le disque.

En ligne de commande, si la page d'administration n'est pas accessible :

```bash
ls -R /media/izquierdo/Famille/incoming/_echecs/     # voir
rm -rf /media/izquierdo/Famille/incoming/_echecs/    # vider (irréversible)
```

### Le journal des synchronisations (issue #30)

Le service tient un journal de tout ce qui se passe, dans une base séparée :

```
~/phototheque_journal.db
```

**Créée au premier usage**, comme `phototheque_devices.db` : importer le module
ne suffit pas à la faire apparaître, il faut qu'une synchronisation, un
appairage ou un démarrage ait réellement eu lieu. Surchargeable par
`JOURNAL_DB` (voir Paramétrage ci-dessous).

Elle contient trois choses : une ligne par synchronisation (`synchros`), une
ligne par fichier reçu avec son sort — rangé, doublon, à trier, refusé, exclu,
erreur — (`mouvements`), et une ligne par événement ponctuel — démarrage,
purge, appairage, confirmation, révocation, échec d'authentification —
(`evenements`).

**Quatre pages, toutes derrière le mot de passe d'administration :**

| Page | Contenu |
|---|---|
| `/historique` | Les synchronisations, la plus récente en haut : appareil, date, nombre de fichiers, état (« sans erreur » / « en erreur »). Chaque ligne mène au détail. |
| `/historique/<id>` | Le détail d'une synchronisation : ses mouvements, origine sur le téléphone → destination dans la bibliothèque. |
| `/historique/recherche?q=` | Retrouver un média par nom (partiel) ou par empreinte exacte, à travers toutes les synchronisations — la réponse à « où est passée cette photo ». |
| `/evenements` | Démarrages, appairages, révocations, échecs d'authentification — tout ce qui n'est pas une synchronisation. |

Des liens vers `/historique` et `/evenements` sont sur la page d'administration
(`/`).

**Une panne du journal ne fait jamais échouer une route.** Toute écriture y
passe par une fonction qui attrape l'exception et se contente de la
journaliser dans `journalctl -u phototheque` : un disque plein ou une base
verrouillée ne doit jamais empêcher un commit d'aboutir, sous peine de bloquer
l'avancée de l'horizon pour une simple trace.

**À inclure dans toute sauvegarde du NUC**, au même titre que le catalogue et
la base des appareils :

```bash
~/mediasort_catalog.db
~/phototheque_devices.db
~/phototheque_journal.db
```

### La purge des sessions abandonnées (issue #30)

Un dossier de réception (`INCOMING_DIR/<session>/`) dont **rien n'a été
modifié depuis plus de 24 heures** — fichier le plus récent de toute
l'arborescence, pas seulement le dossier lui-même — est supprimé
automatiquement, **au démarrage du service ET après chaque commit**. Pas de
tâche planifiée à installer ni à surveiller. Chaque session emportée laisse un
événement `purge` dans le journal, visible sur `/evenements`, avec le nombre
de fichiers et les octets récupérés.

**La quarantaine `INCOMING_DIR/_echecs/` n'est jamais touchée par cette
purge** : la purge ne considère que les dossiers dont le nom a la forme d'un
identifiant de session (32 caractères hexadécimaux) ; `_echecs` n'a pas cette
forme et en est donc écarté par construction, sans qu'il ait fallu l'exclure
explicitement nulle part dans le code. La purger reviendrait à réintroduire
l'issue #16 — les médias non rangés détruits — avec un simple délai au lieu
d'un vrai correctif.

Le téléphone peut aussi demander la suppression immédiate de sa session en
cours (bouton « Interrompre ») par `POST /sync/abandon` — voir
`docs/CONTRAT-APP.md` §4.6. Sans surprise si cet appel échoue : la purge de
24 h sert de filet.

---

## Paramétrage

Tout est surchargeable par variables d'environnement (voir
`phototheque/config.py`), à déclarer dans l'unité systemd avec `Environment=` :

| Variable | Défaut | Rôle |
|---|---|---|
| `PORT` | `8787` | Port d'écoute |
| `LIBRARY_DIR` | `/media/izquierdo/Famille` | Bibliothèque de destination |
| `CATALOG_DB` | `~/mediasort_catalog.db` | Catalogue anti-doublon |
| `INCOMING_DIR` | `<LIBRARY_DIR>/incoming` | Dépôt temporaire des envois |
| `DEVICES_DB` | `~/phototheque_devices.db` | Appareils appairés |
| `JOURNAL_DB` | `~/phototheque_journal.db` | Journal des synchronisations, mouvements et événements (issue #30) |
| `CONFIG_DIR` | `~/.config/phototheque` | Dossier du certificat, du mot de passe et du nom convivial |
| `ADMIN_FILE` | `<CONFIG_DIR>/admin` | Empreinte du mot de passe d'administration |
| `ADMIN_USER_FILE` | `<CONFIG_DIR>/utilisateur` | Identifiant d'administration. **Absent = `admin`.** |
| `PUBLIC_URL` | `https://<nom d'hôte>.local:<PORT>` | Adresse publiée dans le QR d'appairage |
| `DOCS_PUBLIQUES` | *(vide)* | `1` rouvre `/docs`, `/redoc` et `/openapi.json`. **À laisser vide en service.** |

> **`DOCS_PUBLIQUES` : à laisser vide.** FastAPI publie par défaut trois pages
> — `/docs`, `/redoc` et `/openapi.json` — **sans aucun mot de passe**. Elles
> décrivent toute l'API et `/docs` permet même de l'essayer depuis le
> navigateur. Constaté ouvert sur le NUC le 18/09/2026, et refermé depuis :
> elles répondent maintenant `404`. Ne mets `DOCS_PUBLIQUES=1` que sur une
> machine de développement, jamais sur le NUC.

> **`CERT_FILE` et `KEY_FILE` ne sont volontairement pas dans ce tableau.**
> L'unité systemd passe les chemins du certificat en dur à `uvicorn`
> (`--ssl-certfile`, `--ssl-keyfile`) : ce sont eux qui décident du certificat
> **réellement servi**. Les variables, elles, ne décident que du certificat
> dont le service calcule l'empreinte pour le QR d'appairage. Les surcharger
> seules donne donc la pire panne possible du lot : uvicorn sert le certificat
> A, le QR annonce l'empreinte du certificat B, l'application épingle B, se
> connecte à A et échoue sans message compréhensible — alors que tout le reste
> fonctionne. Si tu déplaces le certificat, modifie **aussi** les deux
> arguments `--ssl-*` dans `deploy/phototheque.service`, et garde une seule
> vérité sur son emplacement.

---

## Variante Docker

Cette section est écrite pour être suivie sans rien connaître à Docker. Tout ce
qui suit a été exécuté et vérifié, pas seulement rédigé.

### Faut-il l'utiliser ?

**Sur le NUC, non.** Le déploiement recommandé reste `./deploy/install.sh`
(section précédente) : c'est lui qui est en service et qui gère le montage du
disque, le démarrage au boot et l'annonce réseau.

Docker sert à **faire tourner le service sur une autre machine sans y installer
quoi que ce soit** : essayer sur un portable, migrer vers un autre ordinateur,
ou repartir de zéro si le NUC rend l'âme. Tout ce dont l'application a besoin
(Python, exiftool, ffmpeg) est enfermé dans une boîte, et la machine hôte reste
propre.

### Le vocabulaire, en trois phrases

- Une **image**, c'est un modèle figé : l'application et tous ses outils,
  empaquetés. On la fabrique une fois.
- Un **conteneur**, c'est une image qu'on fait tourner. On peut l'arrêter, le
  supprimer et le recréer sans rien perdre, à condition que les données soient
  dans des volumes (voir plus bas).
- Un **volume**, c'est un dossier qui survit au conteneur. C'est là que vivent
  tes photos et le catalogue.

### 1. Installer Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker "$USER"
```

La dernière ligne t'évite de taper `sudo` devant chaque commande Docker.
**Elle ne prend effet qu'après une déconnexion/reconnexion** — ferme ta session
et rouvre-la, sinon tu auras « permission denied ».

Vérifie que tout répond :

```bash
docker run --rm hello-world
docker compose version
```

> **Attention au piège « compose ».** Il existe deux versions.
> La moderne s'écrit **`docker compose`** (avec une **espace**), fournie par le
> paquet `docker-compose-plugin`. L'ancienne s'écrit `docker-compose` (avec un
> **tiret**) : elle n'est plus maintenue et **plante avec les versions récentes
> de Docker**, sur une erreur incompréhensible du type
> `HTTPConnection.request() got an unexpected keyword argument 'chunked'`.
> Si tu vois cette erreur, c'est que tu utilises l'ancienne : installe
> `docker-compose-plugin` et remets l'espace.

### 2. Indiquer où sont les photos

Ouvre `deploy/docker-compose.yml` et adapte **une seule ligne**, celle du
dossier de la bibliothèque sur ta machine :

```yaml
    volumes:
      # À ADAPTER : dossier de la bibliothèque sur la machine hôte.
      - /media/izquierdo/Famille:/data/library
```

À gauche des deux-points, le chemin **sur ta machine**. À droite, le chemin
**vu par l'application** : celui-là ne change jamais. Sur un portable, ce serait
par exemple `/home/ken/Photos:/data/library`.

Le dossier doit exister avant de démarrer, sinon Docker en crée un vide et tu
croiras la bibliothèque perdue.

### 3. Démarrer

Depuis la racine du dépôt :

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

- `--build` fabrique l'image. **La première fois prend plusieurs minutes** (il
  télécharge Python, exiftool et ffmpeg) ; les fois suivantes sont rapides.
- `-d` (*detached*) rend la main : le service tourne en arrière-plan.

### 4. Vérifier

```bash
docker compose -f deploy/docker-compose.yml ps        # doit afficher « running »
```

Puis ouvre `http://localhost:8787/` dans un navigateur. **Tu obtiendras une
demande de mot de passe à laquelle rien ne répond** : voir « Les limites, dites
franchement » ci-dessous — dans cette variante, l'administration et l'appairage
ne sont pas accessibles. Le conteneur, lui, tourne bien : les journaux
ci-dessous le confirment.

En cas de doute, lis ce que dit l'application :

```bash
docker compose -f deploy/docker-compose.yml logs -f   # Ctrl-C pour sortir
```

### 5. Les commandes du quotidien

| Ce que tu veux | La commande (depuis la racine du dépôt) |
|---|---|
| Voir les journaux | `docker compose -f deploy/docker-compose.yml logs -f` |
| Arrêter | `docker compose -f deploy/docker-compose.yml stop` |
| Redémarrer | `docker compose -f deploy/docker-compose.yml restart` |
| Mettre à jour après un `git pull` | `docker compose -f deploy/docker-compose.yml up -d --build` |
| Tout arrêter et supprimer le conteneur | `docker compose -f deploy/docker-compose.yml down` |

`down` supprime le conteneur mais **garde les données**. Redémarrer ensuite
retrouve le catalogue et les appareils appairés.

### Où sont les données, et comment les sauvegarder

Deux endroits, à ne pas confondre :

| Donnée | Où elle vit | Perdue si… |
|---|---|---|
| **Tes photos et vidéos** | sur ta machine, dans le dossier que tu as indiqué à l'étape 2 | jamais par Docker — c'est ton dossier |
| **Catalogue + appareils appairés** | dans un volume Docker nommé `phototheque-data` | seulement si tu le supprimes explicitement |

Pour sauvegarder le catalogue, commence par **relever le nom exact du volume** :
Docker le préfixe par le nom du projet, qui dépend du dossier depuis lequel tu
lances la commande. Ne le devine pas, demande-le :

```bash
docker volume ls | grep phototheque-data
```

Reporte le nom affiché à la place de `<VOLUME>` ci-dessous :

```bash
docker compose -f deploy/docker-compose.yml stop
docker run --rm -v <VOLUME>:/data -v "$PWD":/sauvegarde \
    alpine tar czf /sauvegarde/catalogue-phototheque.tgz -C /data .
docker compose -f deploy/docker-compose.yml start
```

Tu obtiens un fichier `catalogue-phototheque.tgz` dans le dossier courant.

### Les limites, dites franchement

- **La découverte réseau (mDNS) ne fonctionne pas** dans cette variante.
  L'adresse `IZQUIERDO-NUC.local` est annoncée par Avahi, un service de la
  machine hôte, et l'application ne fait aucune annonce elle-même. En Docker, il
  faut donc utiliser `http://localhost:8787` en local, ou l'adresse IP de la
  machine depuis un téléphone. Pour retrouver le nom `.local`, installe le
  fichier d'annonce sur l'hôte comme à l'étape 8 de la section systemd.
  Pense alors à renseigner `PUBLIC_URL` (tableau du paramétrage ci-dessus) pour
  que le QR code affiche une adresse joignable depuis le téléphone.
- **L'administration et l'appairage ne sont pas accessibles.** `/`, `/pair` et
  `/devices` répondent `401` **pour toujours**, et il n'y a donc aucun moyen
  d'appairer un téléphone dans cette variante. La raison : le mot de passe
  d'administration est fabriqué par `install.sh`, que Docker n'utilise pas. Le
  `Dockerfile` ne définit ni `CONFIG_DIR` ni `ADMIN_FILE`, et le
  `docker-compose.yml` ne monte aucun volume de configuration : le fichier
  d'empreinte est donc absent, et un fichier absent ferme l'administration —
  c'est volontaire, mieux vaut refuser que laisser la surface ouverte. La
  variante Docker sert donc à **faire tourner et essayer le service**, pas à
  l'exploiter avec un téléphone. Corriger cela demanderait d'y porter le
  certificat et le mot de passe, ce qui n'est pas au programme de ce lot.
- **Le conteneur sert en HTTP, pas en HTTPS.** Le certificat est fabriqué par
  `install.sh`, que la variante Docker n'utilise pas. Conséquence à connaître :
  l'adresse publiée dans le QR d'appairage vaut `https://…` par défaut, alors
  que le conteneur ne répond qu'en `http://`. L'application ne pourrait pas se
  connecter. Si tu utilises cette variante avec un téléphone, force l'adresse :
  `PUBLIC_URL=http://<adresse-de-la-machine>:8787` dans `docker-compose.yml`.
  Pour un simple essai depuis un navigateur, il n'y a rien à faire.
- **Les fichiers créés par le conteneur appartiennent à `root`** sur ta machine
  (le conteneur tourne en root). C'est sans gravité, mais ça surprend quand on
  essaie de les effacer sans `sudo`.
- Le port 8787 doit être libre. S'il est déjà pris (par exemple par le service
  systemd sur le NUC), Docker refusera de démarrer.

### Tout supprimer

```bash
docker compose -f deploy/docker-compose.yml down -v   # -v supprime AUSSI les données
docker image prune -a                                  # libère les images inutilisées
```

⚠️ `-v` efface le volume, donc le catalogue et les appareils appairés. **Tes
photos ne sont pas touchées** : elles sont dans ton dossier, pas dans le volume.
