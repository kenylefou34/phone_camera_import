# Sous-projet 3 — application Android de sauvegarde

**Issue :** #12 · **Date :** 2026-09-18 · **État :** conception validée

Le contrat serveur que cette application doit implémenter est déjà écrit et figé :
**[`docs/CONTRAT-APP.md`](../../CONTRAT-APP.md)** (issue #15). Le présent document
ne le répète pas ; il décrit l'application qui le consomme.

---

## 1. Le besoin

Les photos et vidéos du téléphone doivent rejoindre la bibliothèque familiale du
NUC **sans que le mainteneur ait à y penser**, et sans qu'un arrêt silencieux
puisse passer inaperçu.

Le mainteneur a été explicite sur un point qui pèse sur toute la conception :
il ne surveillera pas le système. Une panne qui ne se signale pas d'elle-même
est donc une panne qui durera des mois.

## 2. Décisions prises, et pourquoi

| Décision | Choix | Raison |
|---|---|---|
| Technologie | **Kotlin natif** (Compose) | Seule voie qui traite correctement l'arrière-plan, l'accès aux médias et les notifications. Le mainteneur connaît déjà un peu Kotlin. |
| Déclenchement | **Automatique, plus un bouton** | Le bouton est livré d'abord (lot 1), l'automatique ensuite (lot 3). |
| Dossiers sauvegardés | **Choisis dans l'application** | S'adapte aux autres téléphones de la famille. `DCIM/Camera`, `Pictures/WhatsApp`, `Movies/WhatsApp` pré-cochés. |
| Alerte | **Notification + compteur de jours** | Une notification seule ne se déclenche pas quand *rien* ne se passe. Voir §7. |
| Portée réseau | **Maison uniquement** | Rien n'est exposé sur Internet. Un accès distant éventuel passera par un VPN, pas par une ouverture de port. |
| Emplacement du code | **`android/` dans ce dépôt** | Le contrat et son implémentation côte à côte : une évolution du serveur et l'adaptation de l'app tiennent dans le même commit. |
| Batterie | **Pas de condition de charge** | Réseau non facturé au volume et batterie pas au plus bas suffisent. |
| Versions | `minSdk 29`, `targetSdk 34` | Le téléphone du mainteneur est en Android 14. `minSdk 29` couvre sans surcoût un téléphone familial plus ancien, et garantit `RELATIVE_PATH`. |

### Le principe directeur : l'application reste bête

Toute décision métier reste au serveur. L'application ne sait pas ce qu'est un
doublon, ne date aucun média, ne range rien. Elle **liste, demande, envoie,
valide**. L'intelligence reste en Python, où le mainteneur est à l'aise ; le
Kotlin se limite à ce que seul Android sait faire.

## 3. Architecture

| Module | Rôle |
|---|---|
| `mediastore` | Énumération des photos et vidéos, découverte des dossiers |
| `empreintes` | SHA-256 et cache local (Room) |
| `reseau` | Client HTTP (OkHttp), épinglage, les quatre appels du contrat |
| `synchro` | Orchestration — **la règle de l'horizon vit ici** |
| `travail` | `WorkManager` : déclenchement automatique |
| `ui` | Compose : quatre écrans |

`synchro` est le seul module qui peut détruire des données. Il est écrit en
**Kotlin pur**, sans dépendance à Android ni au réseau, pour être testable sur
la JVM en millisecondes. Ce n'est pas un détail d'organisation : c'est ce qui
rend ses tests possibles.

## 4. Accès aux médias

On interroge `MediaStore.Images` et `MediaStore.Video` — colonnes `_ID`,
`RELATIVE_PATH`, `SIZE`, `DATE_TAKEN`, `DATE_MODIFIED`, `DISPLAY_NAME`.
`RELATIVE_PATH` fournit directement la liste des dossiers de l'écran de
sélection, sans parcourir le système de fichiers.

Les fichiers sont lus par `ContentResolver.openInputStream()` et envoyés **en
flux**, jamais chargés entièrement en mémoire — même raison que côté serveur
(issue #21), et mêmes conséquences sur une vidéo de plusieurs gigaoctets.

### Permissions

`READ_MEDIA_IMAGES` + `READ_MEDIA_VIDEO` (API 33+), `READ_EXTERNAL_STORAGE` en
dessous. **`MANAGE_EXTERNAL_STORAGE` est exclue** : bien plus large que
nécessaire, et elle interdirait toute publication ultérieure.

### Le piège de l'accès partiel (Android 14)

Depuis Android 14, l'utilisateur peut n'accorder l'accès qu'à *quelques* photos
choisies (`READ_MEDIA_VISUAL_USER_SELECTED`). L'application fonctionnerait alors
normalement **en ne sauvegardant que celles-là** — un échec parfaitement
silencieux, c'est-à-dire exactement le mode de panne qu'on cherche à éliminer.

Ce cas doit être détecté et affiché en permanence, pas seulement au premier
lancement.

### Les unités de date

Trois unités pour la même notion, et c'est une source d'erreur à 1000× :

| Source | Unité |
|---|---|
| `DATE_TAKEN` (MediaStore) | millisecondes — **parfois absent** |
| `DATE_MODIFIED` (MediaStore) | secondes |
| Horizons (contrat serveur) | secondes, flottant |

Règle : `DATE_TAKEN` si présent et non nul, sinon `DATE_MODIFIED × 1000`.
**Une seule fonction de conversion dans tout le projet**, testée par table de
valeurs. Aucun calcul de date ailleurs.

## 5. La règle de l'horizon

C'est le cœur de l'application, et le seul endroit où un bug perd des photos
définitivement. Rappel du contrat (§5) : **l'application décide de l'horizon, le
serveur l'enregistre sans vérifier qu'il correspond à ce qui a été envoyé.**

Pour chaque dossier :

1. Trier les fichiers en attente par **date croissante**.
2. Les envoyer dans cet ordre.
3. L'horizon du dossier vaut la date du dernier fichier confirmé **avant le
   premier échec**.

### Pourquoi « avant le premier échec » et non « le plus récent confirmé »

Si le fichier n° 5 échoue et que le n° 6 réussit, retenir la date la plus haute
confirmée ferait sauter l'horizon **par-dessus le n° 5**, qui ne serait plus
jamais proposé. On s'arrête donc au premier échec du dossier, même si la suite
passe.

Si le **premier** fichier d'un dossier échoue, rien n'est confirmé : l'horizon de
ce dossier reste **inchangé**, et n'est donc pas envoyé dans le `commit`.

L'envoi par date croissante n'est pas cosmétique : c'est ce qui donne un sens à
« le dernier confirmé ».

### La comparaison à la frontière : `>=`, pas `>`

L'horizon d'un dossier vaut la date d'un fichier réellement envoyé. À la synchro
suivante, on pourrait croire qu'il faut reprendre **strictement après** cette
date. C'est un piège.

`DATE_TAKEN` est en millisecondes, mais son repli `DATE_MODIFIED` est en
**secondes** : deux photos d'une même rafale peuvent porter exactement la même
valeur. Avec une comparaison stricte, la seconde serait écartée à jamais.

On filtre donc avec **`>=`**, en acceptant de reproposer le fichier frontière.
Le contrat est formel sur l'asymétrie : un horizon qui recule est bénin —
l'anti-doublon écarte sans transférer — tandis qu'un horizon qui avance trop est
définitif et silencieux. Dans le doute, reproposer.

### L'exception unique

Un `400` « extension non prise en charge » **n'est pas un échec**. Le contrat
l'établit : bloquer l'horizon dessus créerait un blocage *permanent* du dossier,
sacrifiant tous les médias suivants pour un seul. Ce fichier est sauté et
l'horizon continue par-dessus.

Tout le reste — coupure réseau, `5xx`, erreur locale — arrête l'avancement du
dossier concerné, et de lui seul.

### Toujours valider

Une session abandonnée sans `commit` laisse indéfiniment les fichiers déjà reçus
dans le dépôt temporaire du NUC, sans que rien ne les range.

L'application appelle donc **toujours `/sync/commit`**, y compris après une
interruption, avec les horizons conservateurs ci-dessus. Ce qui est arrivé est
rangé ; le reste sera reproposé.

## 6. Déroulé d'une synchronisation

```
1. Trouver le serveur     mDNS _phototheque._tcp, puis épinglage du certificat
2. GET  /sync/horizon     depuis + horizons par dossier
3. MediaStore             candidats des dossiers cochés, postérieurs à l'horizon
4. Empreintes             cache local d'abord, calcul seulement si nécessaire
5. POST /sync/plan        session + empreintes réclamées
6. Envois                 par dossier, par date croissante
7. POST /sync/commit      horizons conservateurs (§5)
```

### Trouver le serveur, et l'épinglage

`NsdManager` parcourt `_phototheque._tcp`. L'`url` du QR sert de secours si le
mDNS ne répond pas.

**Attention à l'épinglage :** le QR transmet le SHA-256 du **certificat** (format
DER). Le `CertificatePinner` d'OkHttp, lui, épingle la **clé publique** (SPKI) —
ce n'est pas la même chose et il ne convient pas ici. Il faut un
`X509TrustManager` qui compare le SHA-256 du certificat présenté à celui du QR.
Le certificat étant auto-signé, la validation par autorité échoue toujours : cet
épinglage la **remplace**, il ne s'y ajoute pas.

### « Serveur introuvable » n'est pas une panne

Quand le téléphone n'est pas à la maison, le serveur est injoignable. C'est le
quotidien, pas un incident.

Traiter ce cas comme un échec déclencherait une notification chaque fois que le
mainteneur sort de chez lui. Il les désactiverait en une semaine, et la vraie
alerte passerait inaperçue le jour où elle compte. Donc : **replanification
silencieuse**, sans notification et sans toucher au compteur de jours.

### Déclenchement automatique

`WorkManager`, tâche périodique **unique** (jamais deux synchros en parallèle),
conditions : réseau non facturé au volume, batterie pas au plus bas. Les envois
volumineux passent en service de premier plan avec notification de progression,
sans quoi Android interrompt le travail en cours.

Le bouton « sauvegarder maintenant » exécute le même code, sans les conditions.

### Le cache d'empreintes

Le contrat oblige à calculer l'empreinte de chaque candidat avant de savoir s'il
est utile (issue #22) — coûteux sur un téléphone. L'empreinte est donc conservée
en base locale, indexée par `(_ID, taille, date de modification)`. Si ces trois
valeurs n'ont pas bougé, le fichier n'est pas relu.

Cela ne change rien au protocole et rend quasi gratuites la deuxième synchro et
les suivantes — c'est-à-dire le cas courant.

## 7. Ce que l'utilisateur voit

### Quatre écrans

1. **Appairage** — au premier lancement. Scan du QR, jeton rangé dans
   `EncryptedSharedPreferences`, jamais en clair.
2. **Accueil** — une seule information en grand : *« Sauvegardé il y a 2 heures,
   1 847 médias en sécurité »*, ou l'avertissement, et le bouton.
3. **Dossiers** — dossiers découverts, nombre de médias, cases à cocher.
4. **Détail** — journal des synchros : envoyés, déjà connus, refusés et pourquoi.

Le **lot 1 livre les écrans 1, 2 et 4** ; l'écran « Dossiers » arrive au lot 2,
les dossiers étant d'abord codés en dur.

L'écran de détail fait partie du premier lot, à la demande du mainteneur : au
début on n'a pas encore confiance dans le système, et sans visibilité cette
confiance ne peut pas se construire.

### Le compteur de jours est l'alerte principale

Une notification d'échec ne se déclenche que s'il y a un échec. Or les pires
pannes sont celles où **rien ne se passe** : permission révoquée, application
tuée par l'économiseur de batterie, tâche périodique jamais planifiée.

Le compteur part de la dernière synchro **réussie**, pas de la dernière
tentative : il ne peut pas mentir par omission. Seuil : **7 jours**, modifiable.
Une vérification périodique indépendante de la synchro notifie au franchissement
— y compris si la synchro ne tourne plus du tout.

### Catalogue des erreurs

| Situation | Affichage | Notification |
|---|---|---|
| Serveur introuvable | rien | non |
| Réseau coupé en cours d'envoi | « reprise à la prochaine occasion » | non |
| `400` extension non gérée | listé dans le détail | non |
| `401` appareil révoqué | écran d'appairage, message explicite | **oui** |
| Accès partiel aux photos | bandeau permanent | **oui** |
| Permission retirée | bandeau permanent + bouton | **oui** |
| `5xx` serveur | compté comme échec | après 2 de suite |
| Seuil de 7 jours franchi | accueil en avertissement | **oui** |

Principe : **notifier ce qui exige une action**, se taire sur ce qui se répare
seul. Une notification qu'on apprend à ignorer ne protège de rien.

### Ce que l'application ne fait jamais

Elle ne supprime rien sur le téléphone, et le serveur ne lui en donne jamais
l'ordre. La bibliothèque est une copie, pas un déplacement.

## 8. Stratégie de test

| Quoi | Comment | Pourquoi |
|---|---|---|
| **Règle de l'horizon** | Kotlin pur, JVM | Le seul code qui peut perdre des photos |
| Conversion des dates | fonction pure, table de valeurs | Le piège à 1000× |
| Épinglage du certificat | mauvais certificat → connexion refusée | Une sécurité non testée n'existe pas |
| Client réseau | `MockWebServer`, alimenté par les réponses **réellement capturées** en écrivant #15 | Pas d'exemples inventés |
| Cache d'empreintes | Room, Robolectric | Une empreinte périmée enverrait un mauvais fichier |

Cas obligatoires de la règle de l'horizon :

- échec au milieu → l'horizon s'arrête **avant**, même si les suivants passent ;
- `400` extension → l'horizon passe **par-dessus** ;
- tout réussit → horizon = date du dernier fichier ;
- dossier vide → horizon inchangé ;
- session interrompue → `commit` quand même appelé.

### Un test de contrat, côté serveur

Ajouter dans le dépôt **Python** un test qui rejoue la séquence complète et
vérifie que les réponses correspondent toujours à ce que décrit
`docs/CONTRAT-APP.md`.

La dérive du contrat serait ainsi détectée **là où elle naît** — au moment où
quelqu'un modifie un endpoint — et non trois mois plus tard sur un téléphone qui
ne synchronise plus.

## 9. Découpage en lots

| Lot | Ce qui devient possible |
|---|---|
| **1** | Scanner le QR, appuyer sur un bouton, voir les photos arriver. Dossiers par défaut en dur. Accueil + détail. |
| **2** | Choisir les dossiers. |
| **3** | Ne plus y penser : automatique, notifications, compteur de 7 jours. |
| **4** | Synchros suivantes quasi instantanées (cache d'empreintes). |

Le lot 1 est le vrai jalon : la chaîne complète fonctionne pour de bon. Le reste
est du confort ajouté sans rien casser.

**Le plan d'implémentation qui suivra ce document ne couvrira que le lot 1.**
Les lots suivants auront chacun le leur, écrit une fois le précédent livré et
éprouvé sur un vrai téléphone.

## 10. Outillage

JDK 17, outils en ligne de commande du SDK Android, wrapper Gradle fourni par le
projet. **Pas d'émulateur** : les essais se font sur le téléphone du mainteneur
par USB — plus fidèle, et ~8 Go économisés sur un disque déjà à 86 %.

Rien n'est installé avant que ce document ne soit validé.

## 11. Hors périmètre

- **Sauvegarde hors du domicile.** Conception faite pour la maison, sans fermer
  la porte à un VPN ultérieur. Aucune ouverture de port.
- **Publication sur un magasin d'applications.** L'APK sera téléchargeable depuis
  la page du serveur (voir le commentaire du 18/09 sur #12).
- **Suppression de médias sur le téléphone.**
- **iOS.**

## 12. Questions laissées ouvertes

- **Le pré-filtre du plan (#22).** Le cache d'empreintes atténue le coût sans
  changer le protocole. La vraie correction — un pré-filtre serveur sur la
  taille — sera décidée quand on aura mesuré le coût réel sur un téléphone.
- **Lecteur de QR.** ZXing (léger, sans dépendance aux services Google) plutôt
  que ML Kit, l'application étant installée hors magasin. À confirmer à
  l'implémentation.
- **Plusieurs téléphones familiaux.** Le serveur le permet déjà (horizons par
  appareil). L'application n'a rien de spécial à prévoir ; seule la distribution
  de l'APK reste à traiter.
