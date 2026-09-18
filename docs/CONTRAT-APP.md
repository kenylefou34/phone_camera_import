# Contrat serveur — ce que l'application Android doit implémenter

**À qui s'adresse ce document :** à qui code l'application (issue #12), sans
avoir à ouvrir une seule ligne de Python.

**Tous les exemples de ce document ont été capturés sur un échange réel** avec
le serveur, le 2026-09-18, et non rédigés de mémoire. C'est la seule façon
d'éviter qu'ils divergent du code.

> Ce document décrit le contrat **figé** par le lot des issues #3, #10 et #2. Il
> ne bougera plus sans une raison écrite. La conception d'ensemble est dans
> `docs/superpowers/specs/2026-09-17-transport-auth-horizon-design.md`.

---

## 1. Vue d'ensemble

Une synchronisation complète, dans l'ordre :

```
   (une seule fois)   scanner le QR affiché par /pair
                      → url, token, cert_sha256

   (à chaque synchro) 1. GET  /sync/horizon   « depuis quand dois-je remonter ? »
                      2. scanner les dossiers du téléphone
                      3. POST /sync/plan      « voici ce que j'ai, que te faut-il ? »
                      4. POST /sync/upload    (une fois par fichier réclamé)
                      5. POST /sync/commit    « j'ai fini, range et note où j'en suis »
```

Tous les appels sauf l'appairage portent l'en-tête :

```
Authorization: Bearer <token>
```

---

## 2. L'appairage : ce que contient le QR

Le QR affiché par `https://<serveur>:8787/pair` encode un objet JSON de
**trois champs, et pas un de plus** :

```json
{
  "url": "https://IZQUIERDO-NUC.local:8787",
  "token": "SLgiMxHinPOYVMZMEO_jEAYT9vQIbxkXMFfm5BgixTw",
  "cert_sha256": "02f00ed30b8e621f38681b89ae14dd69d4936b180a0bd88318344157cf3a05fb"
}
```

| Champ | Ce que c'est | Ce que l'application en fait |
|---|---|---|
| `url` | Où joindre le serveur. Schéma **`https`**. | Amorçage, et secours si le `.local` ne résout pas. |
| `token` | Le secret. **Montré une seule fois.** | À conserver durablement ; sert à tous les appels. |
| `cert_sha256` | SHA-256 du certificat, en hexadécimal minuscule. | **L'identité du serveur.** Voir section 3. |

`cert_sha256` peut valoir **`null`** : le serveur tourne alors sans certificat
(lancement manuel en HTTP pour du développement, ou variante Docker). L'app doit
le supporter et savoir qu'elle ne peut alors pas épingler.

---

## 3. Retrouver le serveur, et vérifier que c'est bien lui

**L'identité du serveur, c'est son certificat — pas son adresse.** Une adresse
IP change, un nom `.local` peut être usurpé sur un réseau local ; l'empreinte du
certificat, non.

1. Parcourir le service mDNS **`_phototheque._tcp`** sur le réseau.
2. Pour chaque candidat, ouvrir la connexion TLS et comparer le SHA-256 du
   certificat (format DER) à `cert_sha256`.
3. Celui qui correspond est le bon. Aucun autre ne doit être accepté.
4. Si rien n'est trouvé en mDNS, se rabattre sur l'`url` du QR — **en épinglant
   toujours**.

Le certificat est **auto-signé** : la validation habituelle par autorité de
certification échouera toujours, c'est normal et attendu. C'est l'épinglage qui
remplace cette validation, pas qui s'y ajoute.

---

## 4. Les quatre appels

### 4.1 `GET /sync/horizon` — depuis quand remonter

**Réponse (200)**, capturée à la première synchro d'un appareil appairé :

```json
{
  "depuis": "2026-09-01",
  "dossiers": {}
}
```

Et après une première synchro réussie :

```json
{
  "depuis": "2026-09-01",
  "dossiers": {
    "DCIM/Camera": 1789000000.0,
    "Pictures/WhatsApp": 1788900000.0
  }
}
```

> ⚠️ **Deux unités différentes dans la même réponse.** `depuis` est une **date
> ISO** `AAAA-MM-JJ` ; les valeurs de `dossiers` sont des **timestamps Unix en
> secondes, flottants**. Ce n'est pas une coquille du document.

- `depuis` : la date choisie à l'appairage. Sert de plancher pour un dossier
  **absent** de `dossiers`. Peut valoir **`null`** — cela signifie *aucune
  limite* (appareil repris d'une base antérieure à ce réglage), pas « rien à
  envoyer ».
- `dossiers` : jusqu'où chaque dossier a déjà été remonté.

**Règle pour un dossier donné :** s'il figure dans `dossiers`, remonter les
médias **plus récents** que ce timestamp. Sinon, utiliser `depuis`.

### 4.2 `POST /sync/plan` — que te faut-il ?

**Requête** — les trois champs sont **obligatoires** :

```json
{
  "files": [
    {
      "path": "DCIM/Camera/IMG_20260912_143000.jpg",
      "size": 954,
      "hash": "c777d42e972fefb334f506835d77ad0ab12500b5a4db7fe29fe995faf8df80f7"
    },
    {
      "path": "DCIM/Camera/VID_20260913_101500.mp4",
      "size": 3812,
      "hash": "621cb302b024ebded4eb571e0ba50151d129b8aad8daa067403a6f7361e80773"
    }
  ]
}
```

`hash` est le **SHA-256 du contenu du fichier**, en hexadécimal minuscule.

**Réponse (200) :**

```json
{
  "session": "4bad0393fe5f4fd69635802c39699ce1",
  "needed": [
    "c777d42e972fefb334f506835d77ad0ab12500b5a4db7fe29fe995faf8df80f7",
    "621cb302b024ebded4eb571e0ba50151d129b8aad8daa067403a6f7361e80773"
  ]
}
```

> ### ⚠️ Trois pièges, tous vérifiés
>
> **1. `needed` contient des EMPREINTES, pas des chemins.** L'application doit
> garder elle-même la correspondance empreinte → fichier pour savoir quoi
> envoyer.
>
> **2. `path` et `size` sont obligatoires mais JAMAIS LUS.** Les omettre donne
> un `422` ; les renseigner ne change rien au résultat. Seul `hash` est
> exploité. Conséquence lourde pour le téléphone : il doit calculer un SHA-256
> **complet** de chaque fichier candidat avant même de savoir s'il est utile.
> Sur une vidéo de 3 Go, c'est une lecture intégrale pour rien si le serveur
> l'a déjà.
>
> *Pourquoi ces deux champs restent quand même dans le contrat* : ils ne
> coûtent rien au téléphone (le chemin et la taille sont connus sans lire le
> fichier), ils rendent la requête lisible en cas de diagnostic, et surtout ils
> laissent la porte ouverte au correctif évident de ce piège — un pré-filtre
> serveur sur `(taille, chemin)` avant d'exiger l'empreinte complète, dans
> l'esprit de ce que l'issue #9 a fait côté trieur. Les retirer aujourd'hui
> obligerait à refaire évoluer le contrat demain. Suivi en **#22**.
>
> **3. Chaque appel fabrique une NOUVELLE session.** Redemander un plan
> abandonne silencieusement la session précédente et les fichiers déjà envoyés
> dedans. N'appeler `/sync/plan` qu'une fois par synchronisation.

### 4.3 `POST /sync/upload` — envoyer un fichier

**Ce n'est pas du JSON** mais un `multipart/form-data` à trois champs :

| Champ | Contenu |
|---|---|
| `session` | L'identifiant renvoyé par `/sync/plan` |
| `path` | Le chemin **relatif** du fichier sur le téléphone, ex. `DCIM/Camera/IMG_20260912_143000.jpg` |
| `file` | Le fichier lui-même |

**Réponse (200) :**

```json
{ "ok": true, "hash": "c777d42e972fefb334f506835d77ad0ab12500b5a4db7fe29fe995faf8df80f7" }
```

L'empreinte renvoyée est celle du fichier **tel que reçu**. L'application
devrait la comparer à celle qu'elle avait calculée : une différence signale un
transfert abîmé.

Le serveur écrit par blocs et ne tient jamais le fichier entier en mémoire
(issue #21) : il n'y a pas de taille maximale à respecter côté application.

### 4.4 `POST /sync/commit` — valider

**Requête :**

```json
{
  "session": "4bad0393fe5f4fd69635802c39699ce1",
  "horizons": {
    "DCIM/Camera": 1789000000.0,
    "Pictures/WhatsApp": 1788900000.0
  }
}
```

`horizons` est **facultatif** ; un client qui ne l'envoie pas fonctionne, mais
son horizon n'avancera jamais. Les valeurs sont des **timestamps Unix flottants**.

**Réponse (200)** — le bilan détaillé du rangement :

```json
{
  "sorted": 1,
  "duplicates": 0,
  "to_triage": 0,
  "skipped": 0,
  "errors": 0,
  "photos": 1,
  "videos": 0,
  "whatsapp": 0,
  "octets_ranges": 954,
  "par_source_date": { "filename": 1 },
  "par_annee_mois": { "2026/09 SEPTEMBRE": 1 }
}
```

`errors` mérite l'attention : **si `errors > 0`, le serveur n'a fait avancer
aucun horizon.** Les médias concernés seront reproposés à la synchro suivante,
et l'anti-doublon écartera sans les transférer ceux qui étaient déjà rangés.

---

## 5. ⚠️ Le piège le plus dangereux : l'horizon

**C'est l'application qui décide des horizons. Le serveur ne fait que les
enregistrer** (en les bornant à l'instant présent). Il ne vérifie pas qu'ils
correspondent à ce qui a réellement été envoyé.

Conséquence, vérifiée sur l'échange capturé plus haut : deux fichiers avaient
été réclamés, **un seul a été envoyé**, et le `commit` a quand même fait avancer
l'horizon des deux dossiers. Le fichier jamais envoyé **ne sera plus jamais
proposé**. Il reste sur le téléphone, mais il n'entrera jamais dans la
bibliothèque, et rien ne le signalera.

**La règle à respecter :** pour chaque dossier, n'avancer son horizon que
**jusqu'à la date du dernier fichier réellement envoyé avec succès**. En cas
d'envoi interrompu, laisser l'horizon du dossier là où il était.

Deux corollaires :

- un horizon qui **recule** est bénin : des fichiers déjà connus sont
  reproposés, l'anti-doublon les écarte sans les transférer ;
- un horizon qui **avance trop** est définitif et silencieux.

Dans le doute, avancer moins.

---

## 6. Les extensions acceptées

Le serveur **n'accepte que ce que le trieur sait ranger** :

- **photos** : `.png` `.jpg` `.jpeg` `.bmp` `.dng` `.heic` `.webp`
- **vidéos** : `.mp4` `.mkv` `.avi` `.mov` `.m4v` `.wmv` `.3gp`

Toute autre extension — `.webm`, `.gif`, `.tiff`, `.avif`, `.jfif`, `.mts`,
`.mpg`, les formats bruts `.raw` `.cr2` `.nef` `.arw`… — reçoit un **`400`** et
le fichier n'est **jamais écrit** sur le NUC :

```json
{ "detail": "extension non prise en charge : « .webm » — le serveur n'accepte que les photos et vidéos qu'il sait ranger" }
```

**Ce que l'application doit en faire : poursuivre la synchronisation
normalement.** Un refus n'est pas une panne : il ne doit ni interrompre la
session, ni empêcher le `commit`.

**Dit franchement : ce média ne sera jamais importé.** Le fichier reste intact
sur le téléphone, mais l'horizon du dossier passera au-dessus de lui. C'est un
choix assumé : bloquer l'horizon créerait un blocage **permanent** du dossier,
sacrifiant tous les médias suivants pour un seul.

---

## 7. Codes de retour et conduite à tenir

| Code | Quand | Ce que fait l'application |
|---|---|---|
| `200` | Succès | Continuer. |
| `400` | Extension non prise en charge (`/sync/upload`) | **Passer au fichier suivant.** Ne pas interrompre la session. |
| `401` | Jeton absent, invalide, ou **appareil révoqué depuis la page d'administration** | Effacer l'appairage local et demander un nouveau QR. Ne pas réessayer en boucle : le jeton ne redeviendra jamais valable. |
| `404` | `session` mal formée sur `/sync/commit` | Bug de l'application : la session doit être reprise telle quelle de `/sync/plan`. |
| `422` | Champ obligatoire manquant | Bug de l'application. Le détail indique le champ. |
| `429` | Uniquement sur les pages d'administration | Ne concerne pas l'application. |
| `5xx` | Panne serveur | Réessayer plus tard. **Ne pas faire avancer l'horizon.** |

Réponses réelles, capturées :

```
sans jeton           401  { "detail": "jeton invalide" }
jeton révoqué        401  { "detail": "jeton invalide" }
session mal formée   404  { "detail": "session inconnue" }
```

---

## 8. Cas particuliers à ne pas manquer

**Une synchronisation sans rien à envoyer est normale**, et même le cas
courant une fois la bibliothèque à jour. Il faut quand même appeler `/sync/plan`
(avec `files: []` si besoin) puis `/sync/commit` : c'est le `commit` qui fait
avancer les horizons. Capturé :

```
POST /sync/plan   { "files": [] }        → 200  { "session": "...", "needed": [] }
POST /sync/commit { "session": "...", "horizons": {} }
                                          → 200  { "sorted": 0, ..., "errors": 0 }
```

**`GET /status`** existe et renvoie l'état du disque et le nombre de médias.
Utile pour un écran d'information, pas nécessaire à la synchronisation :

```json
{
  "ok": true,
  "library": "/media/izquierdo/Famille",
  "catalog_count": 44669,
  "disque": { "total": 488557658112, "utilise": 395502030848,
              "libre": 68163063808, "pourcentage_utilise": 81 },
  "medias": { "photos": 40000, "videos": 4669 }
}
```

**Un horodatage aberrant est ignoré en silence.** Un horizon `NaN` ou `-inf` est
écarté pour ce dossier seulement ; le reste de la synchronisation aboutit. Un
horizon dans le futur est ramené à l'instant présent — sans quoi il fermerait
définitivement le dossier.

**Il n'y a pas de reprise d'envoi interrompu.** Un fichier dont l'envoi est
coupé doit être renvoyé en entier. Le serveur ne laisse aucun fragment
exploitable (écriture dans un fichier temporaire renommé à la fin).

---

## 9. Ce qui n'existe pas

Pour éviter de le chercher :

- pas de pagination sur `/sync/plan` — l'application envoie toute sa liste ;
- pas de reprise d'envoi partiel (voir ci-dessus) ;
- pas d'envoi groupé : un appel `/sync/upload` par fichier ;
- pas de notification du serveur vers le téléphone : c'est l'application qui
  décide quand synchroniser ;
- pas de suppression : le serveur ne renvoie jamais d'ordre d'effacement au
  téléphone.
