# Sous-projet 4 — galerie de consultation

**Date :** 2026-09-21 · **État :** conception validée · **Phase :** 2 (consultation)

Premier morceau de la phase 2 du projet. Il ne modifie **aucun** fichier de la
bibliothèque : c'est de la lecture seule, de bout en bout.

---

## 1. Le besoin

> « est-ce qu'on peut faire une spec pour afficher une galerie photo / vidéo le
> tout trié par jour/mois/année avec options de tris date(début-fin) /
> type(vidéo/photo) etc. ça servirait d'écran d'accueil par exemple ? »

La bibliothèque compte 45 298 médias et 613 Go, rangés par type puis par année
et par mois. **Rien ne permet aujourd'hui de les regarder** autrement qu'en
ouvrant un explorateur de fichiers sur un disque NTFS branché au NUC. Le
mainteneur ne voit jamais ce que son système sauvegarde.

Usage retenu : **revoir ses photos**. Feuilleter, retrouver un moment, vérifier
qu'un import est bien arrivé. Consultation pure — aucune suppression, aucune
modification, aucune re-datation. Ces outils-là viendront ensuite (issues #4,
#5, #6) et se brancheront sur cette galerie ; les concevoir maintenant
alourdirait tout sans rien livrer.

## 2. Ce qui existe déjà, et ce qui manque

Le catalogue `~/mediasort_catalog.db` contient une ligne par média :

```sql
medias(empreinte PK, taille, chemin, date_prise, source_date, date_import, signature)
```

Relevé du 2026-09-21 :

| Constat | Conséquence |
|---|---|
| **45 298 lignes, toutes avec un `chemin`** | L'inventaire existe. Rien à parcourir sur le disque pour savoir ce qu'on a. |
| Le chemin porte l'année et le mois : `…/Photos/2013/05 MAI/IMG-…jpg` | **Le tri par année, par mois et par type est gratuit**, en SQL, sans toucher un seul fichier. |
| **44 665 lignes ont `date_prise` à NULL** (`source_date = 'seed'`) | Le jour exact est inconnu pour 98 % de la bibliothèque. Il faut relire les métadonnées. |
| 129 Go de photos, **484 Go de vidéos** | La vidéo pèse 79 % du volume. C'est elle qui dimensionne tout. |
| Le disque Famille plafonne à **~7 Mo/s** (NTFS via `ntfs-3g`, mesuré) | Relire 613 Go prendrait environ 24 h. Hors de question de le faire naïvement. |

## 3. Décisions prises, et pourquoi

| Décision | Choix | Raison |
|---|---|---|
| Où vit la galerie | **Serveur web du NUC**, nouvelle page d'accueil | Consultable depuis n'importe quel appareil de la maison, sans rien installer. |
| Sur le téléphone | **Un onglet `WebView`** dans l'application | Une seule galerie, deux façades. Voir §8. |
| Portée | **Lecture seule** | Rien ne peut être abîmé. C'est ce qui permet de livrer vite. |
| Vignettes | **Engendrées une fois, stockées sur le disque système du NUC** | 56 Go libres sur `/`. Jamais sur Famille : c'est le disque des médias, et il est lent. |
| Outils | **`exiftool` et `ffmpeg` seulement** | Déjà installés. Ni ImageMagick ni vips à ajouter : `ffmpeg` redimensionne aussi bien les photos que les vidéos. |
| Dates manquantes | **Récoltées pendant la passe des vignettes** | Le fichier est de toute façon ouvert. Une seule traversée sert les deux besoins. |
| Le recensement | **Tâche de fond reprenable**, jamais dans une requête HTTP | Plusieurs heures de travail. Une requête web ne doit jamais attendre ça. |

## 4. Le grand recensement

C'est le cœur du sous-projet. Tout le reste en découle.

Une passe unique sur les 45 298 médias qui, pour chacun, produit **deux choses à
la fois** :

1. **une vignette** (400 px de côté, WebP) ;
2. **la vraie date de prise de vue**, écrite dans `date_prise` du catalogue,
   comblant les 44 665 trous.

Faire les deux dans la même passe n'est pas une optimisation : c'est la seule
façon honnête de procéder, puisque le coût est **l'ouverture du fichier**, pas
le traitement.

### Ne jamais lire un fichier en entier

| Type | Méthode | Ce qui est lu |
|---|---|---|
| JPEG avec vignette EXIF | `exiftool -b -ThumbnailImage` | l'en-tête |
| JPEG sans vignette EXIF | `ffmpeg -i … -vf scale` | le fichier |
| Vidéo | `ffmpeg -ss 00:00:01 -i … -frames:v 1` | quelques secondes |

La vidéo domine le volume (484 Go) mais **pas** le coût : `ffmpeg` ne lit que le
début. Ce sont les photos sans vignette EXIF qui coûteront le plus cher, et on
ne saura combien il y en a qu'en commençant.

C'est exactement le raisonnement de l'issue **#9** — le pré-filtre par signature
rapide du trieur, qui a fait passer une vidéo de 3 Go de 28,6 s à 0,028 s. Le
même principe, appliqué à la vignette.

### Reprenable, et lent par construction

- Une table `vignettes(empreinte PK, etat, largeur, hauteur, erreur, faite_le)`
  dit ce qui est fait. La passe reprend où elle s'est arrêtée.
- **Un seul processus à la fois**, une priorité basse (`nice`), et une pause si
  une synchronisation est en cours : le NUC a 2 cœurs et 3 Go, et sa tâche
  prioritaire reste de recevoir les photos du téléphone.
- L'avancement est visible dans l'interface d'administration, à côté de
  l'historique du lot serveur.
- Un média sans vignette s'affiche avec une image de remplacement. **La galerie
  fonctionne dès la première minute**, elle se remplit au fil des heures.

### Volumétrie

45 298 vignettes de 400 px en WebP ≈ **1,1 Go**. Une taille intermédiaire de
1280 px pour l'affichage en grand serait ≈ 6,8 Go : elle est donc engendrée
**à la demande**, à la première ouverture du média, et conservée ensuite.

## 5. Le modèle de navigation

```
Années            2026  2025  2024 … 2013        (avec le nombre de médias)
  └─ Mois         09 SEPTEMBRE   08 AOUT   …
       └─ Jours   lundi 21 · mardi 15 · …        (quand la date est connue)
            └─ Grille de vignettes
                 └─ Média en grand
```

Le niveau « jours » n'apparaît que lorsque les dates sont connues pour le mois
consulté. Tant que le recensement n'y est pas passé, le mois affiche sa grille
directement — dégradation naturelle, sans message d'erreur.

### Les filtres

Disponibles à tous les niveaux, et cumulables :

- **Intervalle de dates** — du … au …
- **Type** — photos, vidéos, ou les deux
- **Origine** — appareil photo, WhatsApp (le chemin distingue déjà
  `Famille/Photos/…` de `Famille/WhatsApp/Photos/…`)

Les trois se traduisent en conditions SQL sur le catalogue. Aucun parcours de
disque.

## 6. Servir les médias

La grille ne sert que des vignettes : quelques dizaines de kilo-octets, depuis
le disque système, sans toucher à Famille.

Le média original n'est servi qu'à l'ouverture en grand, **en réponse partielle**
(`Range`). C'est indispensable pour la vidéo : sans ça, ouvrir un fichier de
900 Mo obligerait le NUC à le lire en entier avant la première image, et la
mémoire ne le permet pas — c'est la leçon de l'issue #21, où le service se
faisait tuer par le noyau pour avoir tenu un fichier entier en mémoire.

Certaines vidéos ne seront pas lisibles par le navigateur (codec non pris en
charge). On ne transcode pas : on propose le téléchargement, et on le dit.

## 7. Sécurité

La galerie est derrière `require_admin`, comme le reste de l'interface. Rien
n'est exposé hors du LAN.

Un point mérite attention : les chemins de médias viennent du catalogue, mais
une requête de la galerie porte un identifiant. **Ce n'est jamais un chemin
fourni par le client qui est ouvert** — on résout l'empreinte en chemin par le
catalogue, et on vérifie que le chemin obtenu est bien sous la bibliothèque
avant d'ouvrir quoi que ce soit. La même précaution que `sessions._chemin_sur()`,
et pour la même raison.

> **⚠️ À chaque ajout de route, revérifier `/docs`, `/redoc` et `/openapi.json`.**
> FastAPI les publie sans authentification et ils n'apparaissent nulle part dans
> le code.

## 8. L'onglet dans l'application

L'application gagne un onglet qui charge la galerie dans une `WebView`. Pas de
seconde galerie : la même page, servie par le même serveur.

Trois points propres à cette installation :

| Point | Traitement |
|---|---|
| **Certificat auto-signé** | Une `WebView` le refuse par défaut. L'application détient déjà son empreinte, reçue dans le QR : elle la vérifie dans `onReceivedSslError` et n'accepte **que** celle-là. C'est le même épinglage que le client HTTP, appliqué à la `WebView` — et l'application est le seul client de la maison qui valide ce certificat pour de bon. |
| **Authentification** | L'application n'a pas le mot de passe d'administration, elle a un jeton d'appareil. La galerie expose donc ses routes en **lecture seule** aussi sous `require_device`, et la `WebView` s'authentifie comme le reste de l'application. |
| **Pas à la maison** | L'onglet affiche le message habituel de l'application, jamais la page d'erreur du navigateur. La découverte mDNS est celle qui sert déjà à la synchronisation. |

## 9. Stratégie de test

Validation **par mutation** systématique.

1. **Année, mois et type se déduisent du chemin** — y compris pour un chemin
   WhatsApp, et y compris pour un mois écrit `05 MAI`.
2. **Un média sans `date_prise` reste visible** : il apparaît dans son mois, sans
   niveau « jour ». Le trou ne le fait pas disparaître — c'est le cas de 98 % de
   la bibliothèque, il ne peut pas être un cas dégradé.
3. **Le recensement reprend où il s'est arrêté** après une interruption.
4. **Une vignette en échec n'arrête pas la passe** et laisse une trace exploitable.
5. **On n'ouvre jamais un chemin venu du client** : le test tente une empreinte
   forgée et un chemin remontant hors de la bibliothèque.
6. **Les réponses partielles fonctionnent** : une requête `Range` sur une grande
   vidéo ne charge pas le fichier en mémoire (le piège de #21).
7. **Les routes exigent l'authentification**, et `/docs` répond toujours 404.
8. **La récolte des dates écrit bien dans `date_prise`** et n'écrase jamais une
   date déjà connue.

## 10. Hors périmètre

- **Toute modification** : supprimer, re-dater, marquer. Issues #4, #5, #6.
- **La reconnaissance de visages** : phase 3.
- **Le transcodage vidéo.** Le NUC a 2 cœurs ; il n'en est pas question.
- **Un accès depuis l'extérieur de la maison.**
- **Les albums, les favoris, la recherche par mot-clé.** À reconsidérer une fois
  la galerie utilisée pour de vrai.

## 11. Questions laissées ouvertes

- **Combien de photos n'ont pas de vignette EXIF ?** C'est la seule inconnue qui
  peut faire passer le recensement de deux heures à une nuit. Un échantillon de
  quelques centaines de fichiers, **pris au hasard et non dans l'ordre de la
  base**, répondra avant d'écrire la moindre ligne — sur ce projet, un
  échantillon pris dans l'ordre a déjà produit une estimation fausse d'un
  facteur 4.
- **Faut-il une vignette pour les médias de `_A_TRIER` ?** Il n'y en a aucun
  aujourd'hui, mais le dossier existe par conception.
