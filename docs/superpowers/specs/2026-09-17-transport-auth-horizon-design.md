# Spec — Transport chiffré, authentification admin, horizon de synchro

*Rédigé le 2026-09-17. Couvre les issues #3, #10 et #2. Document de conception,
en français.*

---

## 1. Pourquoi ce lot, et pourquoi maintenant

L'application Android (issue #12) va coder en dur l'adresse du serveur, le
format du QR d'appairage et la liste des endpoints. Les trois issues traitées
ici modifient précisément ces trois choses. Les faire **après** l'application
obligerait à la reprendre.

Ce lot laisse le service fonctionnellement identique. Il change comment on
l'atteint, qui a le droit de l'atteindre, et ce que l'application doit savoir
avant de synchroniser.

### Objectifs

1. **#3** — Le secret d'appairage et les médias ne circulent plus en clair sur
   le réseau local. L'application vérifie qu'elle parle bien au NUC et pas à un
   imposteur.
2. **#10** — La surface d'administration (page d'accueil, appairage, révocation)
   n'est plus ouverte à tout appareil du réseau.
3. **#2** — La première synchro d'un téléphone ne remonte pas tout son
   historique.

### Hors périmètre

- L'application Android elle-même (#12).
- L'exposition du service hors du réseau local. Le jour où ce sera au programme,
  un reverse-proxy s'ajoutera devant sans rien jeter de ce qui suit.
- La rotation automatique du certificat.
- Plusieurs comptes d'administration : il y en a un seul.

### Décisions déjà arbitrées

| Question | Décision | Raison |
|---|---|---|
| Accès à l'admin | reste joignable sur le LAN | consultée depuis le PC et parfois un téléphone |
| Durcissement | mot de passe, pas de restriction réseau | conséquence du point précédent |
| Transport | HTTPS partout, certificat auto-signé | avertissement navigateur accepté une fois par appareil |
| Architecture | tout dans le service Python | pas de reverse-proxy à maintenir pour un usage familial |
| Horizon initial | date choisie à l'appairage | prévisible, et rattrapable en mettant une date lointaine |
| Fichier témoin | respecté s'il existe, **par dossier** | reprend exactement où `run_backup.sh` s'est arrêté |

---

## 2. Volet 1 — Transport chiffré (#3)

### Le certificat

`deploy/install.sh` fabrique un certificat auto-signé **s'il n'en existe pas
déjà** :

```bash
# L'adresse du NUC sur le reseau, relevee par le script lui-meme :
IP=$(hostname -I | awk '{print $1}')

openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -subj "/CN=$(hostname).local" \
    -addext "subjectAltName=DNS:$(hostname).local,DNS:localhost,IP:${IP},IP:127.0.0.1" \
    -keyout ~/.config/phototheque/key.pem \
    -out    ~/.config/phototheque/cert.pem
```

Si l'adresse IP du NUC change (bail DHCP), le nom `.local` continue de
fonctionner ; seul l'accès par l'IP redeviendrait avertissant. Réserver une
adresse fixe sur la box est le remède, pas une régénération du certificat.

- Dossier en `0700`, clé privée en `0600`.
- Les noms alternatifs couvrent le nom `.local`, `localhost` et l'adresse IP :
  sans eux, joindre le serveur par son IP ajoute une seconde erreur au
  navigateur.
- Validité 10 ans. Les navigateurs limitent la durée des certificats **publics**
  à 398 jours, mais pas ceux qu'on accepte à la main.

**Le script ne régénère jamais un certificat existant.** Le régénérer change son
empreinte, ce qui invaliderait l'épinglage de tous les téléphones appairés : il
faudrait tous les réappairer. Régénérer est donc une action manuelle et
documentée (supprimer les deux fichiers, relancer `install.sh`, réappairer).

### Le service

L'unité systemd gagne deux arguments :

```
ExecStart=… uvicorn phototheque.app:app --host 0.0.0.0 --port 8787 \
    --ssl-keyfile /home/izquierdo/.config/phototheque/key.pem \
    --ssl-certfile /home/izquierdo/.config/phototheque/cert.pem
```

Aucune dépendance nouvelle : `uvicorn` 0.53 s'appuie sur le module `ssl` de la
bibliothèque standard. Vérifié sur le NUC.

### L'empreinte transmise à l'application

`pairing.pairing_payload()` possède depuis l'origine un champ `cert_sha256`,
toujours resté à `None`. Il porte désormais le **SHA-256 du certificat au format
DER**, en hexadécimal minuscule — la forme standard de l'épinglage :

```python
hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
```

`ssl` et `hashlib` sont dans la bibliothèque standard : le module `cryptography`
reste inutile (il est absent du venv, vérifié).

L'application compare cette empreinte à celle du serveur qu'elle joint. Un
appareil du réseau qui usurperait le nom `.local` serait rejeté même en
présentant un certificat par ailleurs valide. C'est une garantie **plus forte**
qu'un certificat public classique.

### Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `CERT_FILE` | `~/.config/phototheque/cert.pem` | certificat servi |
| `KEY_FILE` | `~/.config/phototheque/key.pem` | clé privée |
| `PUBLIC_URL` | `https://<nom d'hôte>.local:<PORT>` | adresse publiée dans le QR |

Seul le schéma de `PUBLIC_URL` change : `http` devient `https`.

### Défaut assumé

`http://IZQUIERDO-NUC.local:8787/` cessera de répondre, avec un message peu
explicite du navigateur. Un même port ne peut pas servir les deux protocoles, et
aucune redirection n'est possible. Mitigation : `install.sh` affiche l'adresse
`https://` à la fin, le README et `docs/DEPLOIEMENT.md` l'annoncent en tête.

---

## 3. Volet 2 — Authentification de l'administration (#10)

### Le mécanisme

**Authentification HTTP « Basic », par-dessus HTTPS.** Le navigateur affiche sa
propre fenêtre de connexion et retient les identifiants.

Retenu parce qu'il n'y a aucun code de session à écrire : pas de cookie, pas de
jeton anti-CSRF, pas d'expiration — donc aucun bug de session possible.
Fonctionne à l'identique sur PC et sur téléphone. Défaut réel : pas de bouton de
déconnexion, il faut fermer le navigateur. En clair ce serait inacceptable ; le
volet 1 chiffre tout.

Implémenté comme une dépendance FastAPI `require_admin`, sur le modèle de
l'actuelle `require_device`. Réponse en cas d'échec : `401` avec l'en-tête
`WWW-Authenticate: Basic realm="phototheque"`, sans lequel le navigateur
n'affiche pas sa fenêtre.

### Le mot de passe

`install.sh` en tire un au hasard à la première installation, **l'affiche une
seule fois**, et n'enregistre que son empreinte dans `~/.config/phototheque/admin`
(`0600`), au format :

```
pbkdf2_sha256$<itérations>$<sel hex>$<empreinte hex>
```

- `hashlib.pbkdf2_hmac` : bibliothèque standard, aucune dépendance.
- Nombre d'itérations choisi à l'implémentation pour qu'une vérification coûte
  **environ 100 ms sur le NUC** — mesuré, pas estimé. Assez pour rendre une
  attaque par essais successifs inopérante sur un LAN, assez peu pour ne pas
  gêner la navigation (une page d'admin = une requête, tout est en ligne dans la
  page).
- Comparaison avec `hmac.compare_digest`, en temps constant.
- Le nom d'utilisateur est `admin`, fixe.
- Pour changer le mot de passe : supprimer le fichier et relancer `install.sh`.

Variable `ADMIN_FILE` pour surcharger le chemin (utile aux tests).

### Surface protégée

| Adresse | Aujourd'hui | Après |
|---|---|---|
| `GET /` | ouverte | **mot de passe admin** |
| `GET /pair`, `POST /pair` | ouverte | **mot de passe admin** |
| `GET /devices` | ouverte | **mot de passe admin** |
| `POST /devices/{id}/revoke` | ouverte | **mot de passe admin** |
| `GET /status` | jeton d'appareil | jeton d'appareil |
| `POST /sync/plan`, `/sync/upload`, `/sync/commit` | jeton d'appareil | jeton d'appareil |
| `GET /sync/horizon` *(nouveau)* | — | jeton d'appareil |

Le cœur de #10 : aujourd'hui, n'importe quel appareil du WiFi peut ouvrir
`/pair` et repartir avec un jeton donnant accès en écriture à la bibliothèque.

### Conséquence assumée

Appairer un téléphone demandera de saisir le mot de passe admin sur l'appareil
qui affiche le QR. C'est exactement ce qui empêche un inconnu de s'appairer.

---

## 4. Volet 3 — Horizon de synchro (#2)

### Où vit l'horizon

La table `synchros(dossier, dernier_ts)` du catalogue est clé **par dossier
seulement** : deux téléphones partageraient le même horizon, ce qui est faux dès
le second appareil. Elle n'a par ailleurs jamais été appelée, hors de ses tests.

L'horizon déménage côté appareils, clé par **(appareil, dossier)**, et la version
inutilisée du catalogue est retirée — plutôt que de laisser une troisième
tuyauterie morte dans le dépôt (après `quick_signature` et `get_last_sync`).

### Modèle de données

Dans la base des appareils (`~/phototheque_devices.db`) :

```sql
-- colonne ajoutée à la table existante
ALTER TABLE devices ADD COLUMN horizon_initial TEXT;   -- date ISO, ex. 2026-09-17

-- nouvelle table
CREATE TABLE horizons (
    appareil   TEXT NOT NULL,
    dossier    TEXT NOT NULL,
    dernier_ts REAL NOT NULL,
    PRIMARY KEY (appareil, dossier)
);
```

Migration : la colonne est ajoutée aux bases existantes, comme l'a été
`confirmed_at`. Les appareils déjà appairés reçoivent `horizon_initial = NULL`,
interprété comme « pas de limite » — on ne restreint pas rétroactivement ce qu'un
appareil existant avait le droit d'envoyer.

Dans `mediasort/catalog.py` : `get_last_sync`, `set_last_sync` et la création de
la table `synchros` sont supprimés. Une table `synchros` déjà présente dans un
catalogue est laissée telle quelle (vide, sans effet) ; la supprimer n'apporterait
rien et toucherait une base de 44 669 lignes sans raison.

### Le protocole, en trois temps

**1. À l'appairage.** La page `/pair` propose un champ « importer à partir du »,
par défaut la date du jour. Le formulaire envoie un `POST /pair`, qui enregistre
la date comme `horizon_initial` de l'appairage en cours et réaffiche la page.

`GET /pair` conserve le comportement mis en place le 17/09 : il réaffiche
l'appairage en attente tant qu'il est valable, et n'en crée un nouveau que
s'il n'y en a aucun. Recharger la page ne fabrique donc pas d'identifiant
supplémentaire — c'est idempotent, et non pas dénué d'effet.

**2. Au début d'une synchro.** L'application appelle `GET /sync/horizon` :

```json
{
  "depuis": "2026-09-17",
  "dossiers": { "DCIM/Camera": 1726574400.0 }
}
```

- `depuis` : la date d'appairage, valeur de repli. `null` si `horizon_initial`
  est `NULL`.
- `dossiers` : les horizons déjà atteints, par dossier. Vide à la première
  synchro.

Pour chaque dossier à synchroniser, l'application choisit dans cet ordre :

1. l'horizon renvoyé par le serveur pour ce dossier, s'il existe ;
2. sinon le `.flagfile_timestamp` **de ce dossier** sur le téléphone, s'il existe
   — c'est lui qui reprend exactement là où `run_backup.sh` s'est arrêté ;
3. sinon `depuis` ;
4. sinon, aucune limite.

**3. Après un commit réussi.** `POST /sync/commit` accepte un champ
supplémentaire :

```json
{ "session": "…", "horizons": { "DCIM/Camera": 1726660800.0 } }
```

Le serveur ne l'enregistre **qu'après un tri réussi**. Champ facultatif : son
absence laisse les horizons inchangés, ce qui garde les clients existants
compatibles.

### Pourquoi l'horizon n'avance qu'après un commit réussi

Si une synchro échoue à mi-parcours, l'horizon ne bouge pas : la suivante reprend
depuis le dernier point sûr. On peut re-proposer deux fois les mêmes fichiers —
l'anti-doublon les écarte au `sync/plan`, sans transfert — mais on ne peut jamais
en perdre. Le sens de ce compromis est délibéré : du travail refait plutôt que
des photos manquantes.

### Pourquoi la date n'est pas dans le QR

Elle pourrait y voyager, mais la changer imposerait alors de réappairer. Une
seule source de vérité, côté serveur, modifiable après coup.

---

## 5. Le contrat vu par l'application Android

Ce que #12 devra implémenter, et qui ne bougera plus après ce lot :

| Étape | Appel | Auth |
|---|---|---|
| Appairage | scan du QR : `{url, token, cert_sha256}` | — |
| Vérification du serveur | épingler `cert_sha256` sur la connexion TLS | — |
| Horizon | `GET /sync/horizon` | `Authorization: Bearer <token>` |
| Quoi envoyer | `POST /sync/plan` | idem |
| Envoi | `POST /sync/upload` | idem |
| Validation | `POST /sync/commit` avec `horizons` | idem |

Le champ `url` du QR porte désormais un schéma `https`.

---

## 6. Stratégie de test

Développement piloté par les tests, volet par volet.

**Volet 1.** Empreinte calculée sur un certificat de test fabriqué dans le
répertoire temporaire du test ; vérification qu'elle correspond bien au SHA-256
du DER. `pairing_payload` transporte l'empreinte. `PUBLIC_URL` est en `https`.
Non testé automatiquement : la poignée de main TLS réelle — vérifiée à la main
sur le NUC après déploiement, et par le test de fumée de `install.sh`.

**Volet 2.** Un bon mot de passe passe, un mauvais échoue, l'absence d'en-tête
renvoie `401` avec `WWW-Authenticate`. Chaque adresse d'administration est
refusée sans authentification — un test par adresse, pour qu'ajouter une route
non protégée casse la suite. Le format du fichier d'empreinte est relu
correctement. Les adresses `/sync/*` restent sur le jeton d'appareil.

**Volet 3.** Horizon par (appareil, dossier) : deux appareils ne se marchent pas
dessus. `GET /sync/horizon` renvoie la date d'appairage quand aucun dossier n'est
connu. `POST /sync/commit` n'avance l'horizon qu'en cas de succès — test de
non-régression : un tri en échec laisse l'horizon inchangé. Migration d'une base
d'appareils sans la colonne ni la table.

**Vérification visuelle.** Le QR contiendra 64 caractères de plus (l'empreinte).
Il deviendra plus dense : rendu et relu à la taille affichée, taille augmentée si
nécessaire. Ce défaut ne se voit qu'en regardant.

---

## 7. Déploiement et retour en arrière

`./deploy/install.sh` reste la commande unique et idempotente. Il gagne deux
étapes : fabrication du certificat s'il manque, génération du mot de passe admin
s'il manque. Son test de fumée passe en `https` sans vérifier le certificat
(auto-signé).

Aucun réappairage n'est nécessaire : les appareils déjà enregistrés gardent leur
jeton. La liste est de toute façon vide au moment d'écrire ces lignes.

Retour en arrière : retirer les deux arguments `--ssl-*` de l'unité et relancer
`systemctl daemon-reload`. Le service repart en HTTP, les jetons restent valides.

---

## 8. Risques et compromis acceptés

| Risque | Portée | Ce qu'on fait |
|---|---|---|
| L'adresse `http://…` cesse de répondre | confort quotidien | annoncé dans le README, `DEPLOIEMENT.md` et en fin d'installation |
| Avertissement du navigateur | une fois par appareil | expliqué pas à pas dans la doc |
| Régénérer le certificat casse l'épinglage | réappairage de tous les téléphones | le script ne régénère jamais ; procédure manuelle documentée |
| Pas de déconnexion en Basic auth | admin familiale | assumé ; fermer le navigateur |
| QR plus dense | lisibilité du scan | vérifié visuellement, taille ajustée |
| Mot de passe affiché une seule fois | perte possible | procédure de réinitialisation documentée (supprimer le fichier, relancer) |

---

## 9. Points volontairement laissés ouverts

- **Rotation du certificat** : manuelle. Une rotation automatique n'a de sens
  qu'avec un mécanisme de réappairage assisté, qui suppose l'application (#12).
- **Limitation du nombre d'essais sur le mot de passe** : le coût de 100 ms par
  vérification suffit sur un LAN. À revoir si le service est un jour exposé.
- **Plusieurs administrateurs** : un seul compte, pas de besoin identifié.
