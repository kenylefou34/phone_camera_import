# Lot 1 bis — la synchronisation devient observable et pilotable

**Date :** 2026-09-21 · **État :** conception validée · **Suite de :**
[`2026-09-18-application-android-design.md`](2026-09-18-application-android-design.md)

Le contrat serveur reste celui de **[`docs/CONTRAT-APP.md`](../../CONTRAT-APP.md)**.
Ce lot ne le modifie pas : il change la façon dont l'application l'utilise, et
ce qu'elle en montre.

---

## 1. Le besoin

Le lot 1 a été essayé sur un vrai téléphone le 2026-09-21. Il a fonctionné : 971
fichiers et 14 Go sont partis du téléphone vers le NUC et s'y sont rangés
correctement. Mais l'essai a mis au jour cinq défauts qui, ensemble, rendent
l'application inutilisable pour ce à quoi elle sert — un grand rattrapage.

Le mainteneur les a formulés ainsi, pendant que la synchro tournait :

> « ça va à quelle vitesse ? j'aimerai avoir toutes ces infos sur le téléphone
> avancement vitesse nom de fichiers destination etc. »
> « je sais même pas quel dossier ça synchronise »
> « j'ai une synchro en cours là, comment je coupe ? »

Les cinq défauts, mesurés :

| # | Défaut | Mesure du 21/09 |
|---|---|---|
| 1 | **Rien ne s'affiche.** Une barre indéterminée, sans chiffre, sans nom, sans vitesse. | 40 minutes d'envoi, zéro information |
| 2 | **Une phase muette au démarrage.** Le téléphone hache tous les candidats avant de pouvoir demander un plan. Rien ne part sur le réseau pendant ce temps. | `09:53:40` → `09:55:48`, soit **2 min 08 s** |
| 3 | **On ne peut pas arrêter.** Aucun bouton. Fermer l'application abandonne tout : pas de `commit`, rien de rangé, l'horizon n'avance pas. | 14 Go auraient été perdus |
| 4 | **L'application meurt si on lâche le téléphone.** La synchro vit dans le `viewModelScope` de l'activité. Ni service de premier plan, ni `WorkManager`. | écran éteint = synchro tuée |
| 5 | **Un commit long expire, et la réussite est annoncée comme une panne.** `OkHttpClient.Builder()` est construit sans aucun délai : OkHttp applique 10 s. Le tri de 14 Go en a demandé plus de vingt minutes. | l'app a dit « échec », le serveur a tout rangé |

Le défaut 5 est le plus grave, parce qu'il est le contraire exact de ce que la
conception d'origine cherche à garantir. Le lot 1 s'était donné pour fil
conducteur que *cinq pannes produisent cinq messages distincts*. Ici, une
**réussite** produit un message de panne — et le compteur de jours reste sur
« Jamais sauvegardé » en rouge alors que tout est rangé.

## 2. Décisions prises, et pourquoi

| Décision | Choix | Raison |
|---|---|---|
| Exécution | **Service de premier plan + `WorkManager`** | « Poser le téléphone et l'oublier. » Une sauvegarde qu'il faut surveiller est une sauvegarde qu'on ne fait pas. |
| Découpage | **Validation par paquets** (~500 Mo) | Une coupure ne perd que le dernier paquet. L'horizon avance en cours de route au lieu de tout jouer sur un commit final. |
| Contrat serveur | **Inchangé pour le découpage** | Un paquet = un `plan` + ses `upload` + un `commit`. Le serveur enchaîne déjà plusieurs sessions, rien à ajouter au protocole. *(Le lot serveur y ajoute par ailleurs deux champs **optionnels** au commit, `synchro` et `bilan_app`, pour l'historique — voir sa spec §6. L'application les remplit ; un téléphone qui ne les enverrait pas continuerait de fonctionner.)* |
| Interruption | **Arrêt immédiat** | Les paquets validés sont acquis ; le paquet en cours est jeté et refait. Répondre à l'instant prime sur économiser quelques centaines de Mo. |
| Reprise après coupure subie | **Automatique**, au retour du Wi-Fi maison | Corollaire de « poser et oublier ». |
| Reprise après arrêt demandé | **Jamais automatique** | Un arrêt que l'utilisateur a demandé ne doit pas se défaire tout seul. |
| Écran pendant la synchro | **Tout à l'écran** (maquette B) | Choisi sur maquette. Voir §6. |
| Phase d'analyse | **Affichée comme une phase nommée** | Sinon elle a l'air d'un plantage. |
| Notification | **Chiffres, barre et bouton Interrompre** | C'est elle qui parle quand l'écran est éteint. |
| Temps restant | **Affiché dès la première seconde** | Choix explicite du mainteneur, malgré la réserve ci-dessous. |
| Délais HTTP | **Explicites, généreux au commit** | Défaut 5. |

### La réserve sur le temps restant

Sur ce projet, une estimation faite à partir d'un échantillon pris dans l'ordre
de la base s'est déjà trompée d'un facteur 4 : 200 médias annonçaient 1 h pour
un rattrapage de signatures qui a pris 16 min, parce que les gros fichiers
étaient groupés en tête. Le mainteneur a choisi en connaissance de cause
d'afficher l'estimation dès la première seconde.

L'estimation est donc calculée sur les **octets restants** et non sur le nombre
de fichiers — c'est le seul dénominateur qui ne se laisse pas tromper par un
lot de vidéos — et sur une moyenne glissante du débit, pas sur la moyenne depuis
le début.

## 3. Architecture

```
MainActivity ──── ModeleAccueil ─────┐
                                     │  observe
                                     ▼
                              EtatSynchro (+ Avancement)
                                     ▲
                                     │  publie
        WorkManager ── ServiceSynchro ── Orchestrateur ── Serveur
             │              │                   │
      contrainte       notification       paquets + horizons
      « réseau »       de premier plan
```

Le changement structurant : **l'orchestrateur ne vit plus dans le modèle de
vue**. Il tourne dans un service de premier plan piloté par `WorkManager`, et
publie son avancement. Le modèle de vue s'y abonne, s'il existe. L'application
peut être fermée : la synchro continue.

### Nouvelles unités

| Unité | Rôle | Dépend de |
|---|---|---|
| `Avancement` | Instantané de la progression : phase, n/total, octets faits/total, débit, média en cours, sa destination prévue, paquets validés. Immuable. | rien |
| `Debit` | Moyenne glissante des octets/seconde, et l'estimation du reste. Testable sans horloge réelle. | rien |
| `Paquets` | Découpe la liste des candidats en lots d'au plus ~500 Mo, sans jamais couper un média. | `Media` |
| `ServiceSynchro` | Service de premier plan : notification, bouton Interrompre, cycle de vie. | `Orchestrateur` |
| `TravailSynchro` | `CoroutineWorker` : contrainte réseau, reprise automatique, unicité. | `ServiceSynchro` |
| `Destination` | Calcule le chemin prévu dans la bibliothèque (`Photos/2025/09 SEPTEMBRE`). Affichage seulement. | `Dates` |

`Destination` mérite un mot : c'est la seule unité de ce lot qui **duplique** une
logique du serveur (`mediasort.config.month_folder`). Elle est purement
indicative — le serveur reste seul juge du rangement réel. Le test de contrat
existant (`tests/test_contrat_app.py`) reçoit un cas de plus qui vérifie que les
deux conventions ne divergent pas.

## 4. Le déroulé par paquets

```
horizon()                          ← une fois
  │
  ├─ lister les médias, filtrer par horizon, trier par date
  ├─ découper en paquets d'au plus 500 Mo
  │
  └─ pour chaque paquet :
       analyser   (SHA-256 des médias du paquet seulement)
       plan()     → session + empreintes réclamées
       upload()   × n
       commit()   → range, fait avancer les horizons
```

Hacher paquet par paquet au lieu de tout d'avance ramène la phase muette du
défaut 2 de 2 min 08 s à quelques secondes. Le fond du problème — hacher des
fichiers que le serveur possède déjà (**issue #22**) — reste hors périmètre :
en régime normal, l'horizon limite déjà les candidats à quelques fichiers.

## 5. Le piège de l'horizon entre paquets

**C'est le point le plus dangereux de ce lot.** Il peut perdre des photos
définitivement et en silence.

`Horizons.calculer` garantit aujourd'hui qu'un dossier dont un fichier a échoué
voit son horizon s'arrêter **avant** ce fichier, pour qu'il soit reproposé. La
fonction raisonne sur une liste d'envois : **une** synchronisation.

Découpée en paquets, chaque paquet appelle `commit` avec ses propres horizons.
Si le dossier `DCIM/Camera` subit un échec au paquet 12, et que le paquet 13
contient des médias plus récents du même dossier qui réussissent, le commit du
paquet 13 fera avancer l'horizon **par-dessus** le fichier en échec. Il ne sera
plus jamais proposé par le serveur. C'est exactement la perte que
`Horizons.calculer` existe pour empêcher, réintroduite par le découpage.

**La règle :** l'ensemble des dossiers arrêtés est porté par la
**synchronisation entière**, pas par le paquet. Dès qu'un dossier connaît un
échec, aucun commit ultérieur de la même synchronisation n'a le droit de faire
avancer son horizon — même si les paquets suivants réussissent.

Concrètement, `Horizons.calculer` prend un paramètre supplémentaire : les
dossiers déjà arrêtés lors des paquets précédents. Elle renvoie, à côté des
horizons, l'ensemble arrêté mis à jour, que l'appelant repasse au paquet
suivant. La fonction reste pure et sans état.

Un dossier arrêté n'interrompt pas la synchronisation : on continue d'envoyer
ses fichiers (l'anti-doublon du serveur les écartera sans transfert s'ils sont
déjà là). Seul son **horizon** est gelé.

## 6. Ce que l'utilisateur voit

### Pendant la synchronisation

L'accueil ne renvoie pas vers un écran d'avancement : **il en devient un**. La
même page se transforme, puis redevient l'accueil avec le bilan.

```
Sauvegarde en cours
770 / 1 240
12,5 Go sur 19,8 Go
[========================------]
12,2 Mo/s              ~ 18 min

Envoi en cours
DCIM/Camera/
VID_20250927_164822.mp4
29 Mo · vidéo · 27/09/2025
→ Videos/2025/09 SEPTEMBRE

Paquet 24            [23 validés]
Dossiers : DCIM/Camera, Pictures/WhatsApp

        [ Interrompre ]
```

La ligne « Dossiers » répond à « je sais même pas quel dossier ça synchronise »
sans avoir à ouvrir un autre écran. Un dossier codé en dur mais **absent** du
téléphone y apparaît en rouge — c'est le cas de `Movies/WhatsApp` sur le
téléphone du mainteneur, constaté le 21/09 : zéro fichier reçu, et rien ne le
signalait.

### Les deux phases

La phase d'analyse a son propre libellé et sa propre progression
(« Analyse : 40 / 120 »), puis l'envoi prend le relais. Deux phases nommées :
rien n'a jamais l'air planté.

### La notification

Même contenu resserré : `Sauvegarde 770 / 1 240 · 12,2 Mo/s`, une barre, et une
action **Interrompre** directement dans la notification, sans rouvrir
l'application. Le nom du fichier en cours n'y figure pas : il change toutes les
secondes et ferait clignoter la notification en permanence.

### Navigation

Aujourd'hui `MainActivity` choisit son écran par un `when` sur l'état, et l'écran
de détail n'offre **aucun chemin de retour** : le bouton retour du système ferme
l'application et perd le bilan (issue #24, signalé comme prioritaire précisément
parce que c'est l'écran que la recette doit exploiter).

Ce lot pose une vraie pile d'écrans :

```
Appairage  ─(QR scanné)─▶  Accueil ⇄ Détail
                              │
                              └──────⇄ Historique (lot serveur)
```

Le retour système fonctionne partout, l'état survit à la rotation
(`rememberSaveable` au lieu de `remember` — autre constat de #24).

## 7. Interruption et reprise

| Événement | Ce qui se passe |
|---|---|
| **Interrompre** (bouton ou notification) | Arrêt immédiat. Les paquets validés sont acquis. Le paquet en cours est abandonné : l'application prévient le serveur au mieux (`POST /sync/abandon`), sinon la purge côté serveur s'en charge. Aucune reprise automatique. |
| **Wi-Fi coupé / serveur injoignable** | Le `Worker` échoue et redemande à être relancé. `WorkManager` le rappelle dès que le réseau revient. |
| **Android tue le processus** | Le service de premier plan rend ce cas rare ; s'il survient, `WorkManager` relance le travail. |
| **Appareil révoqué** | Arrêt définitif, coffre vidé, message explicite. Pas de reprise — c'est le seul cas qui ne se réglera jamais tout seul. |

La reprise ne « reprend » pas une session : elle relance une synchronisation
normale. Les paquets déjà validés ont fait avancer l'horizon et leurs médias
sont au catalogue du serveur, donc ils ne seront ni reproposés ni retransférés.
C'est ce qui permet de ne pas ajouter d'état partagé entre le téléphone et le
serveur.

## 8. Les délais d'expiration

`Decouverte.client()` construit `OkHttpClient.Builder()` sans aucun délai, donc
avec les 10 s par défaut d'OkHttp. Valeurs retenues :

| Appel | Délai | Pourquoi |
|---|---|---|
| connexion | 10 s | Sur le LAN, au-delà c'est que le serveur n'est pas là. |
| `horizon`, `plan` | 30 s | Le serveur interroge le catalogue ; c'est rapide mais pas instantané. |
| `upload` (écriture) | 5 min par bloc | Une vidéo de 3 Go à 12 Mo/s prend plusieurs minutes. |
| `commit` (lecture) | **30 min** | Mesuré le 21/09 : trier 971 fichiers et 14 Go sur le disque NTFS a demandé plus de vingt minutes, à 5,5 Mo/s. |

Le découpage en paquets rend ce dernier délai beaucoup moins critique — un
paquet de 500 Mo se trie en moins de deux minutes — mais il doit rester généreux :
un seul fichier peut faire 900 Mo, et rien n'interdit au disque d'être occupé.

**Un commit ne doit jamais être considéré comme échoué tant qu'on n'en a pas la
preuve.** C'est la leçon du 21/09.

## 9. Stratégie de test

Le projet impose de valider chaque test **par mutation** : casser volontairement
le code et vérifier que c'est bien ce test-là qui tombe. Plusieurs faux verts
ont été attrapés ainsi le 18/09.

Tests à écrire, du plus important au moins :

1. **L'horizon gelé traverse les paquets.** Un échec au paquet 1 sur `DCIM/Camera`,
   une réussite au paquet 2 sur le même dossier : l'horizon de `DCIM/Camera`
   **ne bouge pas**. C'est le test qui protège vos photos ; il s'écrit en premier.
2. **Un dossier arrêté n'arrête pas les autres.** Les horizons des autres dossiers
   avancent normalement au paquet 2.
3. **Découpe en paquets** : jamais de média coupé en deux, un média plus gros que
   la taille de paquet fait son paquet à lui seul, ordre par date conservé.
4. **Arrêt immédiat** : les commits déjà faits restent, aucun commit n'est émis
   pour le paquet en cours, le travail ne se relance pas tout seul.
5. **Reprise automatique** : une coupure réseau produit une demande de relance,
   pas un échec définitif.
6. **Débit et estimation** : calculés sur une horloge injectée, jamais sur
   `System.currentTimeMillis()`.
7. **L'avancement est publié**, même sans écran attaché (application fermée).
8. **Les délais d'expiration sont bien posés** sur le client construit.
9. **`Destination` ne diverge pas du serveur** : cas ajouté à
   `tests/test_contrat_app.py`, côté Python.

## 10. Hors périmètre

- **Le choix des dossiers dans l'application** — c'est le lot 2. Les trois
  dossiers restent codés en dur ici. L'écran les affiche, il ne les modifie pas.
- **Issue #22** (hacher des fichiers que le serveur possède déjà) : contenue par
  l'horizon en régime normal, et fortement atténuée par le découpage en paquets.
- **Issue #23** (un certificat qui ne correspond plus est indiscernable de « pas
  à la maison ») : laissée ouverte sciemment.
- **La synchronisation automatique périodique** — lot 3. `WorkManager` est
  introduit ici, ce qui la rendra presque gratuite ensuite.
- **L'historique et la purge des sessions abandonnées** : lot serveur, spec
  séparée du même jour.

## 11. Questions laissées ouvertes

- **La taille de paquet de 500 Mo est un point de départ**, pas un résultat
  mesuré. À ajuster après le premier grand rattrapage : trop petit multiplie les
  tris et les allers-retours, trop grand rapproche du défaut qu'on corrige.
- **`POST /sync/abandon` n'existe pas encore.** Il est décrit dans la spec
  serveur. Tant qu'il n'est pas là, l'arrêt immédiat s'appuie uniquement sur la
  purge côté serveur ; l'application le tente et ignore l'échec.
