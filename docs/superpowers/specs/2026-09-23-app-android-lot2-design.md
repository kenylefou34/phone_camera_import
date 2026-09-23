# Lot 2 de l'application Android — dossiers, dates, synchro auto, désappairage

*Conception validée le 2026-09-23. Sous-projet 3, suite du lot 1 bis.*

---

## 1. D'où vient ce lot

Le lot 1 bis a rendu la synchronisation **observable**. Le mainteneur s'en est
servi pour de vrai, et en est ressorti avec sept remarques. Ce lot répond à
quatre d'entre elles ; les trois autres sont traitées ailleurs, voir §2.

Le fil rouge : **l'application décide tout à la place de l'utilisateur, et ne
le dit pas.** Trois dossiers sont écrits en dur (`TravailSynchro.kt:239`), la
date de reprise est choisie une fois pour toutes à l'appairage, la
synchronisation ne part que sur commande manuelle, et un appareil appairé ne
peut plus jamais l'être autrement. Chacune de ces quatre décisions doit passer
à l'utilisateur.

---

## 2. Périmètre

**Dans ce lot :**

| # | Sujet | §  |
|---|-------|----|
| 1 | Choix des dossiers à sauvegarder | §3 |
| 2 | Fenêtre de dates pilotée depuis le téléphone | §4 |
| 3 | Synchronisation automatique | §5 |
| 4 | Désappairage depuis le téléphone | §6 |

**Hors de ce lot, et pourquoi :**

- **Le scan du QR en portrait** — déjà corrigé et livré (`83115fd`).
- **Le mot de passe sur le téléchargement du QR** — tranché, il reste. Le QR ne
  contient pas qu'une adresse : il porte un **jeton d'appairage valide**
  (`url`, `token`, `certSha256`). Qui le scanne peut déposer des médias sur le
  NUC. Le mettre à portée de quiconque a le code WiFi de la maison serait un
  recul. Le mainteneur ne le saisit qu'une fois par téléphone, et
  `./deploy/identifiants.sh` lui laisse choisir un mot de passe fait pour un
  clavier tactile.
- **La galerie en WebView** — la galerie côté serveur n'existe pas encore
  (issue #31, spec écrite le 21/09, rien d'implémenté). Un onglet WebView
  afficherait aujourd'hui une page blanche. Il se greffera après #31, pour très
  peu de travail. La raison de ne pas l'empiler ici n'est pas sa taille : **le
  lot 1 bis n'a toujours jamais tourné sur un appareil.** Poser une deuxième
  couche non éprouvée sur une première non éprouvée prépare une séance de
  débogage où l'on ne saura plus laquelle des deux ment.
- **Un déclenchement « en direct »** (à chaque photo prise) — demande un
  observateur permanent sur MediaStore. Peu cher à ajouter une fois l'auto en
  place ; inutile avant d'avoir vu l'auto vivre.

**Ce que le serveur change : presque rien.** L'horizon monotone, qu'on
croyait devoir lui imposer, se règle entièrement côté application (§4.4). Il ne
reste que deux retouches, toutes deux au service du désappairage (§6.4) : une
route authentifiée par le jeton d'appareil, et une suppression d'horizons
oubliée.

---

## 3. Choix des dossiers à sauvegarder

### 3.1 Ce qui existe déjà

- `TravailSynchro.DOSSIERS_SAUVEGARDES` (`TravailSynchro.kt:239`) —
  `{"DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"}`, en dur.
- `Selection.candidats(medias, dossiersChoisis, horizons, depuisSecondes)`
  prend **déjà** un ensemble de dossiers en paramètre. La plomberie est là ;
  seules l'interface et la persistance manquent.
- `EtatSynchro.dossiersVus: Map<String, Int>?` donne déjà, pour chaque dossier
  réellement présent sur le téléphone, son nombre de médias. C'est la source de
  l'arborescence : `Media.dossier` vient de `RELATIVE_PATH` de MediaStore.

### 3.2 Une arborescence parcourable, pas une liste à plat

Le mainteneur a posé l'exigence ainsi : *« ça serait bien de pouvoir cocher
mais pouvoir rentrer dedans voir ce qu'il y a pour cocher »*, et
*« du moment qu'on voit ce qu'il y a dans les dossiers quand on parcourt, ça me
gêne pas de naviguer, au moins on n'oublie rien »*.

L'écran présente donc un **arbre**, avec fil d'Ariane et navigation par niveau,
construit en découpant les chemins de `dossiersVus` sur `/`.

### 3.3 Le mode de coche

**Une seule case par ligne. Un appui déplie trois choix explicites :**

```
○ Ce dossier seulement
● Ce dossier et ses sous-dossiers
○ Ne pas sauvegarder
```

Deux autres formes ont été maquettées et écartées : deux cases par ligne
(« dossier » / « + dedans ») — trop chargé, et deux cibles voisines au pouce se
ratent ; et une case accompagnée d'un bouton « tout » — un clic de moins, mais
un vocabulaire à apprendre. Le clic supplémentaire de la forme retenue n'est
payé que sur les dossiers réellement cochés, une poignée, une fois.

**État intermédiaire.** Une case à moitié pleine quand seuls certains
sous-dossiers sont pris. Sans elle, on croit un dossier entièrement pris alors
qu'il ne l'est qu'à moitié.

### 3.4 Ce qu'une ligne montre du contenu

Des **chiffres qui parlent**, pas des images :

- le nombre de médias ;
- la période couverte (« du 04/2024 au 19/09/2026 ») ;
- les noms des sous-dossiers ;
- un indice de nature quand il tranche — « tous < 50 Ko » démasque
  `.thumbnails` sans avoir à l'ouvrir.

Tout cela vient d'une requête MediaStore et reste instantané sur des dizaines
de milliers de médias.

**Et un bouton « voir »** qui déplie une grille d'aperçu **pour ce dossier
seul**. Trois vignettes sur chaque ligne ont été envisagées puis écartées :
chaque ligne visible déclencherait trois décodages d'image, avec cache et
annulation au défilement, et c'est la seule variante dont la lenteur se
verrait. Le besoin exprimé est un besoin de **vérification**, pas de
contemplation : on ne doute pas de `DCIM/Camera`, on doute de deux ou trois
dossiers obscurs. L'aperçu à la demande met l'image exactement là, sans la
faire payer aux quarante autres lignes — et il se retire sans rien casser s'il
s'avère inutile à l'usage.

### 3.5 Repli des chaînes

`Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images` fait six niveaux
dont les cinq premiers ne contiennent **aucun média** et n'ont qu'un enfant
chacun. Une chaîne de dossiers sans média et à enfant unique est **repliée en
une seule ligne**, affichant le chemin complet. Descendre marche par marche
dans des dossiers vides n'apprend rien et coûte cinq appuis.

### 3.6 Le filet : les dossiers nouveaux

Après chaque synchronisation, l'application affiche la **liste des dossiers
entrés depuis la dernière fois par une case récursive**. Une coche récursive
est une délégation dans le temps : elle prendra demain des dossiers qui
n'existent pas aujourd'hui. Sans ce rappel, le mainteneur devrait surveiller ;
avec, il est prévenu.

### 3.7 Permissions et persistance

`Android/media/` est indexé par MediaStore (contrairement à `Android/data/`) :
`READ_MEDIA_IMAGES` et `READ_MEDIA_VIDEO`, déjà demandées, suffisent. **Aucun
recours à SAF n'est nécessaire**, ce qui évite un sélecteur système qui ne
sait pas cocher récursivement.

La sélection est persistée sur le téléphone. `DOSSIERS_SAUVEGARDES` devient sa
valeur par défaut au premier lancement, pour qu'une mise à jour ne change rien
sans prévenir.

### 3.8 Réalité constatée sur le téléphone du mainteneur

`Pictures/Messages` **existe et contient des médias à sauvegarder** ;
`Android/` aussi. `Messenger` et `Download` n'existent pas. Tout est
atteignable par MediaStore.

---

## 4. La fenêtre de dates

### 4.1 Deux régimes, une seule fonction

Les dates et la synchronisation automatique ne sont pas deux fonctionnalités :

- **Rattrapage** — une fenêtre (début, éventuellement fin), lancée à la main.
  C'est le mode pour aller chercher 2019.
- **Régime établi** — plus de borne haute, déclenchement automatique, reprise
  depuis l'horizon.

Le bouton « synchro auto » ne fait que basculer de l'un à l'autre.

### 4.2 Trois règles

1. **Cocher « auto » efface la date de fin**, et le dit. C'est la seule
   protection fiable contre la date de fin oubliée : un compteur « 342 médias
   hors fenêtre » se remarque une semaine, pas six mois. Le but déclaré étant
   de finir en automatique, autant que le geste qui y mène nettoie derrière
   lui.
2. **La date de début reste**, et elle a deux rôles qu'il faut distinguer.
   Elle est le **plancher des dossiers sans horizon** — cocher
   `Pictures/Messages` pour la première fois ne doit pas remonter à 2012 ;
   c'est déjà ce que fait `Selection.candidats` avec `depuisSecondes` quand un
   dossier est absent de `horizons`. Et **la baisser est un ordre de reprise**
   (§4.3). Elle ne bloque jamais rien de nouveau : sur un dossier déjà connu,
   c'est l'horizon qui commande.

   **Correction apportée par la relecture finale (2026-09-24).** La dernière
   phrase décrivait une intention, pas le code : la fenêtre est un filtre, et
   sa borne basse s'applique *après* la sélection, donc elle **peut** amputer
   un dossier déjà connu — précisément quand son horizon est *sous* la date de
   début, c'est-à-dire après avoir **remonté** cette date. La tranche
   `[horizon, début[` est alors écartée, et si l'horizon avançait quand même
   sur les médias envoyés, elle passerait dessous : perdue pour toujours, sans
   qu'un compteur bouge. L'application **gèle donc l'horizon de tout dossier
   dont la borne basse a écarté un candidat** (même mécanisme que les dossiers
   en échec, `Horizons.calculer`). Ce que l'écran promet reste vrai — « les
   autres ne seront pas repris tant que vous ne baissez pas la date de
   début » — et c'est le gel qui le rend tenable : la tranche redevient
   proposable dès que la date redescend. Son coût est réel et assumé : tant
   que la fenêtre coupe quelque chose par le bas, l'horizon de ce dossier
   n'avance plus, donc ses médias sont réempreintés à chaque passe.
3. **En automatique, la fenêtre est grisée, pas cachée.** On doit pouvoir lire
   *pourquoi* la borne haute a disparu.

Et, en toutes circonstances, **l'application affiche combien de médias sont
hors fenêtre**. Une fenêtre est un filtre, et un filtre muet est une panne
silencieuse.

### 4.3 Ce que veut dire baisser la date de début

**La date de début est un ordre, pas un plancher.** La baisser fixe, pour la
synchronisation qui suit et pour elle seule, un plancher de **sélection** à
cette date : `Selection.candidats` propose de nouveau tout ce qui se trouve
entre cette date et l'horizon déjà connu de chaque dossier coché, comme si ce
dossier n'avait jamais été synchronisé. Ce n'est **pas** une réécriture de
l'horizon serveur — celui-ci reste entièrement gouverné par la monotonie
(§4.4), qui l'empêche de reculer.

C'est ce qui permet à la date de remplacer le désappairage comme moyen de tout
reprendre (§6). La lecture concurrente — « plancher permanent », plancher réel
= `max(date, horizon)` **en permanence** — a été écartée : l'horizon
commanderait toujours, et baisser la date ne reproposerait jamais rien.

**Seule une BAISSE est un ordre de reprise**, et la relecture finale
(2026-09-24) a dû le faire respecter au code : `repriseADemander` traitait
tout changement comme un ordre, y compris **remonter** la date. Or remonter la
date est le geste de qui veut *alléger* — passer de 2019 à 2024 — et une
reprise repropose et réempreinte (SHA-256 intégral) des dizaines de milliers
de fichiers. Le geste obtenait l'exact contraire de ce qu'il demandait.

**Son coût a disparu avec la monotonie de la tâche 6 (§4.4).** L'horizon
transmis à chaque `commit` est `max(horizon calculé sur ce paquet, horizon
déjà connu du serveur)`, ce dernier lu une seule fois au début de la
synchronisation. Un rattrapage 2019–2020 sur un dossier déjà remonté à
septembre 2026 calcule donc un horizon de fin 2020 sur ce paquet, le compare à
septembre 2026, et transmet `max(2020, 2026) = 2026` : la mémoire de septembre
2026 survit intacte au rattrapage. Rien n'est relu ensuite — la sauvegarde
suivante repart exactement là où elle en était avant le rattrapage, pas de la
fin de la fenêtre fermée. L'ordre de reprise se réduit ainsi à un plancher de
**sélection**, ponctuel, sans jamais toucher à ce que le serveur retient.

### 4.4 L'horizon devient monotone — côté application

**Le défaut.** L'horizon est décidé par l'application ; `set_horizon`
(`phototheque/devices.py:189`) écrit tel quel ce qu'elle envoie, et la boucle
de commit (`phototheque/app.py:257-278`) ne le borne que par le haut
(`min(ts, maintenant)`). Rien n'empêche l'horizon de **reculer**.

**Le scénario qui fait mal.** Le téléphone a tout jusqu'à septembre 2026. Une
fenêtre 2019–2020 est posée pour rattraper du vieux. À la validation,
l'application envoie l'horizon du lot — fin 2020 — et le serveur **écrase** la
mémoire de septembre 2026. La nuit suivante, six ans de médias sont reproposés.
Rien n'est perdu ni renvoyé deux fois, mais le téléphone relit tout, à chaque
fois.

**Le correctif.** L'application envoie `max(nouvel horizon, horizon connu)`.
Elle lit déjà l'horizon au début de chaque synchronisation
(`GET /sync/horizon`, qui rend `{depuis, dossiers}`). Monotone, **sans toucher
au serveur ni au contrat**.

L'ordre de reprise du §4.3 est la seule exception, et il est délibéré : il
écrit l'horizon bas une fois, au moment où l'utilisateur change la date.

---

## 5. Synchronisation automatique

### 5.1 Déclenchement

`PeriodicWorkRequest`, période de 6 h, contraintes **réseau non facturé + en
charge**. « Synchroniser maintenant » reste disponible à tout moment et ignore
les contraintes.

**Ce que la relecture finale (2026-09-24) a dû corriger pour que cette
dernière phrase soit vraie.** Un `PeriodicWorkRequest` n'atteint jamais d'état
terminal : entre deux passes il reste `ENQUEUED`. L'écran, qui dérivait son
état de « une exécution n'est pas terminée », lisait donc une attente
permanente dès que l'interrupteur était coché — bouton « Sauvegarder
maintenant » **grisé pour toujours**, barre de progression et « En attente
d'un réseau… » affichés en continu. La file périodique ne contribue plus qu'à
l'état « en cours » ; l'attente et la nouvelle tentative ne se lisent que sur
la file manuelle. Et « Interrompre », qui annule les deux files,
**reprogramme** la file périodique derrière lui (avec six heures de délai,
sinon il relancerait aussitôt ce qu'il vient d'arrêter) : `cancelUniqueWork`
ne suspend pas une passe, il détruit la chaîne.

### 5.2 Ce que « toutes les 6 h » veut dire

Ce n'est **pas un réveil à heure fixe**, et la spec le dit pour que personne
n'en attende ça :

- au plus une fois par tranche de 6 h, dès que les conditions sont réunies ;
- Android regroupe ces réveils (mode Doze) : le délai peut glisser à 7 ou 8 h
  si le téléphone dort, **jamais se déclencher plus tôt** ;
- les conditions priment sur l'horloge : sans réseau non facturé **et** sans
  charge, l'échéance passe sans rien faire ;
- 15 minutes est le minimum autorisé par la plate-forme.

En pratique : **une passe par nuit, au branchement du téléphone à la maison.**

### 5.3 Le revers, et la règle qui en découle

Trois jours sans brancher le téléphone sur le WiFi de la maison, et rien ne
tourne — sans que rien ne le dise. L'automatique deviendrait un silence qu'on
prend pour un succès : exactement le piège de la date de fin oubliée sous un
autre habit.

L'accueil affiche donc en permanence **« dernière sauvegarde : il y a N
jours »**, et passe en avertissement visible **au-delà de 3 jours quand
l'automatique est actif**. Le seuil manuel existant
(`EtatSynchro.SEUIL_ALERTE_JOURS = 7`) reste inchangé pour le mode manuel :
sept jours sans geste volontaire n'ont rien d'anormal, trois nuits sans passe
automatique, si.

---

## 6. Désappairage depuis le téléphone

### 6.1 Ce n'est pas le moyen de tout reprendre

La date de début fait ce travail (§4.3), sans rescanner de QR et de façon
réversible. Le désappairage est donc libéré pour ne faire qu'une chose :
**couper le lien**.

### 6.2 Pourquoi il doit exister — le blocage définitif, vérifié dans le code

1. `oublier()` (`appairage/Appairage.kt:67`) n'est atteignable **que sur un
   401** (`TravailSynchro.kt:163` et `:180`), c'est-à-dire seulement quand
   l'administrateur révoque l'appareil.
2. Une fois appairé, l'écran de scan est **inatteignable** :
   `MainActivity.kt:74` ne l'affiche que si `!etat.appaire`.
3. Le certificat est **épinglé par empreinte**, et cet épinglage **remplace**
   la validation habituelle (`reseau/Epinglage.kt`). Si le certificat du NUC
   change — réinstallation du disque, `~/.config/phototheque` effacé, autre
   machine — le TLS échoue **avant** le HTTP.

Conséquence : plus de connexion, donc jamais de 401, donc la révocation depuis
la page d'admin **ne peut pas atteindre le téléphone**. L'application est
bloquée définitivement ; la seule sortie est d'effacer ses données ou de la
réinstaller. Même impasse pour pointer le téléphone vers un autre serveur.

### 6.3 La forme retenue

Le vrai métier du désappairage est **se dépanner et changer de serveur**. Or au
moment précis où on en a besoin, le serveur est injoignable par définition. La
conception en découle :

- **L'effacement local est inconditionnel** et réussit toujours. C'est lui qui
  débloque.
- **Le serveur est prévenu au mieux**, avec un délai court. Son échec est
  signalé — « le serveur n'a pas pu être prévenu, l'appareil restera dans la
  liste d'admin jusqu'à ce que vous l'y révoquiez » — et **jamais bloquant**.
- La confirmation annonce la conséquence en clair plutôt qu'un « êtes-vous
  sûr ? » :

  > « Vous devrez rescanner un QR. Le prochain appairage relira vos N médias
  > (≈ M min). Rien ne sera envoyé deux fois. »

### 6.4 Les deux retouches du serveur

**Une route de désappairage authentifiée par le jeton d'appareil.** Le seul
chemin de révocation existant est `POST /devices/{device_id}/revoke`
(`app.py:305-307`), protégé par `require_admin`, c'est-à-dire par le **mot de
passe d'administration**. Le téléphone ne détient qu'un jeton d'appareil : il
ne peut pas l'appeler. Il faut donc une route que l'appareil puisse emprunter
pour se retirer **lui-même**, sous `require_device`.

Le risque est mesuré : un jeton volé permettrait de révoquer le téléphone
légitime, qui se réappairerait. C'est un désagrément, à comparer à ce que le
même jeton volé permet déjà — déposer des médias.

**La suppression des horizons.** `Devices.revoke()` (`devices.py:163`) exécute
`DELETE FROM devices WHERE id=?` et rien d'autre. La table `horizons` n'a
**ni clé étrangère ni `ON DELETE CASCADE`**, et `PRAGMA foreign_keys` n'est
jamais activé (SQLite le laisse inactif par défaut). Chaque révocation laisse
donc ses lignes d'horizon orphelines, définitivement.

Ce n'est pas un défaut de correction — l'identifiant d'appareil est un
`uuid.uuid4().hex` tiré à chaque appairage (`devices.py:86`), donc un téléphone
réappairé ne retombera jamais sur les orphelins. C'est une fuite lente, qui
s'aggrave avec ce lot : une sélection par arborescence produit bien plus d'une
ligne d'horizon par appareil que les trois dossiers en dur d'aujourd'hui. La
suppression tient en une requête, au même endroit.

---

## 7. Écrans et navigation

Le lot 1 bis a laissé quatre écrans, choisis par un `when` dans
`MainActivity` : appairage, avancement, détail, accueil. Ce lot en ajoute
trois, atteints depuis un point d'entrée **« Réglages »** sur l'accueil :

| Écran | Contenu |
|-------|---------|
| Dossiers | l'arbre du §3 |
| Sauvegarde | fenêtre de dates, bouton « synchro auto », médias hors fenêtre |
| Appareil | état de l'appairage, bouton « Désappairer ce téléphone » |

Le `when` de `MainActivity` atteint ici sa limite : sept destinations, un
bouton retour à gérer par écran, et un état de navigation à préserver à la
rotation (`rememberSaveable`, déjà nécessaire au lot 1 bis — issue #24). La
navigation passe donc dans **un état de navigation explicite**, testable sur la
JVM, plutôt que dans une cascade de booléens.

---

## 8. Tests

Le projet n'a **aucun test d'instrumentation Android**, et ce lot n'en
introduit pas : ce serait un chantier en soi. La conséquence est assumée et
doit être dite — tout ce qui suit est couvert par lecture et par recette
manuelle, pas par exécution automatique : Compose, la navigation, le
`PeriodicWorkRequest` et ses contraintes.

**Ce qui est couvert par des tests JVM**, et doit l'être :

- construction de l'arbre depuis une liste de chemins plats, y compris le repli
  des chaînes (§3.5) et les cas dégénérés (chemin vide, dossier racine) ;
- propagation des trois modes de coche, et calcul de l'état intermédiaire ;
- `Selection.candidats` avec un ordre de reprise (§4.3) ;
- **la monotonie de l'horizon** (§4.4) : c'est le test le plus important du
  lot, celui qui garde la mémoire de septembre 2026 pendant un rattrapage 2019 ;
- l'effacement de la date de fin au passage en automatique ;
- le comptage des médias hors fenêtre ;
- le désappairage quand le serveur ne répond pas : l'état local est vidé, et
  l'échec est rapporté.

**Côté serveur (pytest, §6.4) :**

- la route de désappairage retire l'appareil quand elle est appelée avec un
  jeton d'appareil valide, et la refuse sans jeton ou avec un jeton révoqué ;
- elle **ne doit pas** être accessible avec le seul mot de passe d'admin par
  inadvertance, ni l'inverse ;
- après un retrait, `get_horizons()` ne rend plus rien pour cet appareil.

Les documents interactifs (`/docs`, `/redoc`, `/openapi.json`) restent fermés
sans rien faire de particulier : ils sont coupés à la construction de
l'application (`app.py:27-29`), globalement, et non route par route. La règle
du dépôt — « y repenser à chaque ajout de route » — est donc satisfaite par
construction ici, mais l'ajout d'une route reste le moment de le vérifier.

**Chaque test est validé par mutation**, selon la règle du dépôt : casser
volontairement le code et vérifier que c'est bien ce test-là qui tombe. Un test
qui passe du premier coup ne prouve rien — plusieurs faux verts ont été
attrapés ainsi le 18/09.

---

## 9. Risques et limites assumées

1. **Le lot 1 bis n'a jamais tourné sur un appareil.** Ce lot s'appuie dessus.
   La recette du lot 1 bis (18 étapes) reste à dérouler, et le lien WiFi
   battant du NUC (constaté le 23/09 : ~20 s joignable, ~35 s injoignable) la
   rend aujourd'hui impraticable. **La correction est physique : un câble
   ethernet.**
2. **Les deux limites reportées du lot 1 bis** (issue #33) restent : interrompre
   pendant l'envoi d'une grosse vidéo n'arrête pas le téléversement en cours,
   et l'écran reste figé pendant ce temps. Ce lot ne les traite pas.
3. **L'issue #16 n'est pas traitée ici** : le serveur détruit toujours les
   médias qu'il n'a pas su ranger (`sessions.cleanup()` avant le test sur
   `errors`). La ceinture posée au lot 1 bis — geler l'horizon de tout le
   paquet — tient toujours, mais le fichier, lui, reste perdu. **Un rattrapage
   de grande ampleur augmente mécaniquement l'exposition à ce défaut** : c'est
   un argument pour traiter #16 avant, et non après, le premier gros usage de
   la fenêtre de dates.
4. **La relecture après une fenêtre fermée** (§4.3) est un coût réel, accepté
   faute de preuve qu'il gêne.
