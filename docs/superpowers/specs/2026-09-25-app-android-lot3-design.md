# Application Android — lot 3 : thème, onglet galerie, #42 et #39

**Date :** 2026-09-25 · **État :** conception validée, à relire · **Branche :** `lot3-app-galerie`
(partie de `origin/dev` à `37b9d40`, qui porte la partie serveur de la galerie)

Ce lot prépare l'application au passage de la galerie de consultation (#31) :
elle gagne un onglet qui affiche la galerie du NUC, reprend le thème de
l'interface d'administration (#43), et corrige deux défauts mineurs laissés
par le lot 2 (#42, #39).

**Contrainte d'écriture :** code, tests et documentation seulement. Rien
n'est installé sur le téléphone ni sur le NUC avant le relevé de l'étape 11
de la recette du lot 2 ; la recette de ce lot-ci vient après (§9).

---

## 1. Ce qui est demandé, et ce qui existe

| Demande | Source |
|---|---|
| Un onglet galerie en `WebView` : épinglage du certificat, authentification par le jeton d'appareil, message « pas à la maison » | spec galerie §8 (`2026-09-21-galerie-consultation-design.md`) |
| Le thème de l'admin repris dans l'application | issue #43 |
| Un arrêt subi s'écrit « terminée » dans le journal Android | issue #42 |
| Interrompre une sauvegarde manuelle repousse la passe automatique de 6 h | issue #39 |

État du code au départ :

- **Le serveur accepte déjà le jeton d'appareil pour la galerie** :
  `require_lecteur` (`phototheque/app.py:343`) prend `Authorization: Bearer`
  et retombe sinon sur le mot de passe d'administration.
- **Mais la page ne porte pas l'en-tête sur ses propres requêtes.** Toutes ses
  URL sont relatives à la racine : `<img src="/galerie/vignette/…">`,
  `<video src="/galerie/original/…">` (en `Range`), `<img src="/galerie/moyenne/…">`
  (qui répond `307` vers l'original pour une vidéo), des liens et un formulaire
  `GET` de filtres. Une `WebView` n'ajoute un en-tête qu'à la requête qu'on lui
  passe par `loadUrl` : tout le reste partirait sans authentification.
- Aucun cookie ni aucune session n'existe côté serveur.
- La galerie affiche un lien « Administration » (`/admin`, mot de passe Basic)
  et, sur la page d'un média, un lien « Télécharger » (`<a download>`) : ni l'un
  ni l'autre ne fonctionne dans une `WebView` authentifiée par jeton.
- L'application : navigation faite à la main (`enum Ecran`,
  `ui/Navigation.kt`), **aucune barre d'onglets**, `MaterialTheme { }` sans
  paramètre (violet par défaut, sans sombre), **aucun thème dans le
  manifeste**, épinglage OkHttp dans `reseau/Epinglage.kt`, découverte dans
  `Fabrique.serveur` (`reseau/Decouverte.kt`), appairage dans le `Coffre`
  chiffré.

## 2. Décisions prises

| Question | Décision | Raison |
|---|---|---|
| Organisation | **Barre d'onglets « Sauvegarde \| Galerie », ouverture sur Sauvegarde** | L'accueil dit si tout est sauvegardé, porte les alertes, et fonctionne hors de la maison ; la galerie non. |
| Authentification de la `WebView` | **Cookie de session court, obtenu par échange du jeton** (§5) | Le jeton durable ne sort jamais du coffre chiffré ; le cookie expire ; tout ce que charge la page le porte, `Range` et `307` compris. |
| Rejeté : le jeton en cookie | — | Recopierait le secret durable en clair dans la base de cookies de la `WebView`, sans expiration. |
| Rejeté : intercepter chaque requête (`shouldInterceptRequest`) | — | Obligerait à réimplémenter le streaming `206` de la vidéo à travers `WebResourceResponse` — fragile, et intestable sur JVM. |
| Couleurs | **Jetons de `web.py` recopiés, un test anti-dérive** | Onze valeurs : une génération de source unique coûterait plus d'outillage qu'elle n'éviterait d'erreurs. |
| Couleur dynamique (Material You) | **Non** | Elle ferait diverger l'application de l'admin, ce que #43 veut justement éviter. |
| Affichage bord à bord | **Non** | Pas imposé en `targetSdk` 34 ; imposerait de gérer les marges système sur chaque écran. |
| Icône du lanceur | **Inchangée** (orange) | Hors du périmètre de #43. |

## 3. Le thème (#43)

### 3.1 Les jetons

`ui/Theme.kt` déclare un objet `Jetons` : les jetons du bloc `:root` de
`STYLE` (`phototheque/web.py`), en clair et en sombre, sous leur nom CSS.

| Jeton | Clair | Sombre | Rôle |
|---|---|---|---|
| `plane` | `#f9f9f7` | `#0d0d0d` | fond de page |
| `surface` | `#fcfcfb` | `#1a1a19` | cartes |
| `ink` | `#0b0b0b` | `#ffffff` | texte |
| `ink2` (`--ink-2`) | `#52514e` | `#c3c2b7` | texte secondaire |
| `muted` | `#898781` | `#898781` | indications |
| `line` | `#e1e0d9` | `#2c2c2a` | séparateurs |
| `accent` | `#2a78d6` | `#3987e5` | le bleu (mesure, action) |
| `warning` | `#fab219` | `#fab219` (non redéfini en sombre) | attention |
| `critical` | `#d03b3b` | `#d03b3b` (non redéfini en sombre) | erreur |

`--border` (`rgba` à 10 %) est repris en `ink` à 10 % d'opacité.

**Garde-fou anti-dérive** : un test Python (`tests/test_theme_app.py`) relit le
bloc `:root` et le bloc `prefers-color-scheme: dark` de `STYLE`, puis
`Theme.kt` et les deux `colors.xml` (§3.3), et compare jeton par jeton. Il
tombe si l'un des côtés change seul.

### 3.2 Le schéma Material 3

`ThemePhototheque(content)` remplace le `MaterialTheme { }` nu de
`MainActivity`. Clair ou sombre selon `isSystemInDarkTheme()`, pas de couleur
dynamique. Le contenu est posé sur une `Surface` de couleur `background`
(l'application n'en a aucune aujourd'hui : le fond venait de la fenêtre).

**Tous les rôles sont posés**, et pas seulement ceux que cite l'issue : un
rôle laissé à sa valeur par défaut fait ressurgir le violet de Material 3 dans
un interrupteur, une case à cocher ou l'indicateur de la barre d'onglets.

| Rôle | Jeton |
|---|---|
| `primary` | accent |
| `onPrimary` | blanc (`.bouton.principal` de l'admin : `color: #fff`) |
| `primaryContainer`, `secondaryContainer` (indicateur d'onglet) | accent à faible opacité sur surface |
| `onPrimaryContainer`, `onSecondaryContainer` | ink |
| `secondary`, `tertiary` | accent |
| `background` | plane |
| `onBackground`, `onSurface` | ink |
| `surface`, `surfaceContainer*`, `surfaceBright` | surface |
| `surfaceVariant`, `surfaceDim` | plane |
| `onSurfaceVariant` | ink2 |
| `outline`, `outlineVariant` | line |
| `error` | critical |
| `onError` | blanc |
| `errorContainer` | surface |
| `onErrorContainer` | ink |
| `inverseSurface`, `inverseOnSurface`, `inversePrimary`, `scrim` | le jeton opposé du mode inverse, noir pour `scrim` |

**Pas de fond rouge.** L'admin n'en a aucun : un état critique y est un texte
ou un liseré (`.etiquette.critical`), toujours doublé d'un mot. D'où
`errorContainer` = surface : les bandeaux de l'accueil (permission refusée,
accès partiel, appareil révoqué, aucun dossier coché) deviennent des cartes à
liseré `critical` qui gardent leur texte.

**Test JVM** : aucun rôle du schéma clair ni du schéma sombre ne vaut la
valeur correspondante de `lightColorScheme()` / `darkColorScheme()` par
défaut. C'est ce test qui attrape un violet oublié. (Il suppose que
`lightColorScheme()` se construit hors d'Android : c'est une fonction pure de
`material3`, sans appel au framework. Si ce n'était pas le cas, repli : le test
porte sur la table de correspondance comme donnée pure.)

### 3.3 La fenêtre — ce qui lie #43 à la galerie

Le manifeste ne déclare aucun thème aujourd'hui. On ajoute :

- `res/values/themes.xml` : `Theme.Phototheque`, parent
  `android:Theme.Material.Light.NoActionBar` ;
- `res/values-night/themes.xml` : même nom, parent
  `android:Theme.Material.NoActionBar` ;
- `res/values/colors.xml` et `res/values-night/colors.xml` : `plane` seul
  (le reste vit dans `Theme.kt`) ;
- `android:theme="@style/Theme.Phototheque"` sur `<application>`.

Chaque thème fixe `windowBackground`, `statusBarColor` et
`navigationBarColor` sur `plane`, et `windowLightStatusBar` /
`windowLightNavigationBar` selon le mode.

Deux effets :

1. plus de flash blanc au lancement en mode sombre ;
2. **surtout** : avec `targetSdk` ≥ 33, une `WebView` ne transmet
   `prefers-color-scheme: dark` à la page que si le thème de l'activité est
   sombre (`isLightTheme` faux). Sans ce fichier, la galerie resterait claire
   dans l'application, téléphone en sombre ou pas.

### 3.4 Typographie et formes

- Police système (Roboto), comme l'admin.
- Titres d'écran (`headlineMedium`) : 26 sp, graisse 600 (l'admin est à 640,
  que Roboto non variable arrondit de toute façon), `letterSpacing` -0,015 em.
- Un composable **`Intertitre(texte)`** reprend le `h2` de l'admin : 12 sp,
  graisse 600, espacement 0,07 em, majuscules, couleur `muted`. Il remplace les
  intertitres actuels (« Dernière synchronisation », « Bilan du serveur »,
  « Fichier en cours »…).
- `shapes` : `medium` à 14 dp (les `.carte` de l'admin), `small` à 9 dp (ses
  boutons). Les cartes prennent une bordure `line`.

### 3.5 Le reste

- Notification : `setColor(accent)`.
- Règle de l'admin, **une couleur d'état n'est jamais seule** : contrôlée écran
  par écran pendant la tâche. Le seul cas où la couleur change sans texte
  propre est le compteur de jours de l'accueil qui passe en `error` : il est
  déjà accompagné du message d'alerte ; à confirmer à la relecture.

## 4. La barre d'onglets et la navigation

- Deux onglets en bas (`NavigationBar`), **« Sauvegarde »** et
  **« Galerie »**. Ouverture sur Sauvegarde.
- Deux icônes vectorielles dans `res/drawable` (`ic_onglet_sauvegarde`,
  `ic_onglet_galerie`), plutôt que `material-icons-extended` (plusieurs Mo pour
  deux pictogrammes).
- La barre n'apparaît que sur `ACCUEIL` et `GALERIE`. Réglages, Dossiers,
  Sauvegarde, Appareil et Détail restent des sous-écrans de Sauvegarde, sans
  barre, avec leur retour actuel. L'appairage n'a pas de barre.

`Navigation` reste pur et testé :

- `Ecran.GALERIE` s'ajoute à l'énumération.
- `ecranAffiche(demande, appaire, synchroEnCours)` : non appairé → `APPAIRAGE`
  (inchangé) ; **`GALERIE` demandée → `GALERIE` même si une synchro tourne**
  (sinon la passe automatique qui démarre à la mise en charge éjecterait
  l'utilisateur en pleine consultation) ; synchro en cours → `ACCUEIL` pour
  tout autre écran (inchangé) ; sinon l'écran demandé.
- `retour(GALERIE)` = `ACCUEIL`. Avant d'y arriver, le bouton retour remonte
  l'historique de la page (`WebView.goBack()`) tant qu'il y en a un, et quitte
  d'abord le plein écran vidéo s'il est actif.
- `demandeApres` inchangé : un désappairage ou une révocation mène à
  l'appairage depuis n'importe quel onglet ; le premier écran après un
  réappairage reste l'accueil (constat C3).

## 5. L'authentification de la galerie

### 5.1 L'échange

1. L'onglet s'ouvre. L'application trouve le serveur par `Fabrique.serveur`
   (la même découverte, le même repli sur l'URL du QR que la synchro).
2. Elle appelle **`POST /galerie/session`** avec son client OkHttp **déjà
   épinglé** et `Authorization: Bearer <jeton>`.
3. Le serveur (`require_device`) tire un identifiant aléatoire de 256 bits
   (`secrets.token_urlsafe(32)`), le garde **en mémoire** lié à l'appareil
   pour **12 h**, et répond :
   ```json
   {"cookie": "phototheque_galerie", "valeur": "<identifiant>", "expire_dans_s": 43200}
   ```
4. L'application dépose le cookie dans le `CookieManager` de la `WebView`,
   pour l'origine du serveur :
   `phototheque_galerie=<identifiant>; Path=/; Secure; HttpOnly; SameSite=Strict`
   (sans `Max-Age` : cookie de session). La chaîne est construite par une
   fonction pure, testée. En développement sans TLS (`cert_sha256` nul), pas
   de `Secure`.
5. Elle charge l'origine (`/`) dans la `WebView`. Toutes les requêtes de la
   page portent désormais le cookie, sans rien réécrire.

### 5.2 Côté serveur

- Un magasin `SessionsGalerie` (nouveau module `phototheque/galerie_sessions.py`) :
  dictionnaire en mémoire `sha256(identifiant) → (appareil, expiration)`,
  protégé par un verrou. On ne garde que l'empreinte de l'identifiant, comme
  pour les jetons d'appareil. Purge des sessions expirées à chaque création ;
  au plus 8 sessions vivantes par appareil (la plus ancienne tombe).
- **Le cookie n'ouvre que la galerie.** `require_lecteur` l'accepte ;
  `require_admin` et `require_device` l'ignorent. `require_lecteur` renvoie
  désormais **qui lit** : `Lecteur(nature="admin" | "appareil", appareil)`.
- **Révocation immédiate** : à chaque requête portée par le cookie, le serveur
  revérifie que l'appareil existe encore ; `Devices.revoke()` et
  `POST /sync/desappairer` purgent aussi ses sessions de galerie.
- Un redémarrage du service vide le magasin : les pages reçoivent `401`, et
  l'application refait l'échange (§6).
- Pas de limitation d'essais sur l'échange, comme pour la synchro : le jeton
  fait 256 bits, et un cookie inconnu ne coûte qu'une recherche dans un
  dictionnaire. Une requête qui **porte** le cookie et se le voit refuser
  reçoit `401` **sans** `WWW-Authenticate: Basic`, au lieu de retomber sur
  `require_admin`. Une requête sans cookie ni en-tête garde le comportement
  actuel (défi Basic, pour le navigateur du mainteneur) ; côté application,
  `onReceivedHttpAuthRequest` est surchargé pour refuser toujours
  (`handler.cancel()`), et le `401` qui en résulte est traité comme au §6.
- **Deux liens disparaissent quand le lecteur est un appareil** :
  « Administration » (en-tête de la galerie) et « Télécharger » (pages photo et
  vidéo). Sur la page vidéo, le texte de repli pour un format illisible
  devient « Ce format ne se lit pas sur le téléphone : ouvrez-le depuis un
  ordinateur. »
- `/docs`, `/redoc` et `/openapi.json` : toujours 404 (à revérifier puisqu'on
  ajoute une route).
- `docs/CONTRAT-APP.md` : nouveau §4.7 (`POST /galerie/session`), mise à jour
  du §7 (codes de retour) et du §9 (ce qui n'existe pas).

### 5.3 L'épinglage dans la `WebView`

`onReceivedSslError(vue, gestionnaire, erreur)` :

- extrait `erreur.certificate.x509Certificate` (API 29 = notre `minSdk`) ;
- calcule le SHA-256 de son encodage DER avec **la même fonction** que
  `Epinglage.empreinte` ;
- `gestionnaire.proceed()` si l'empreinte égale `cert_sha256` (comparaison en
  temps constant), `gestionnaire.cancel()` sinon — **jamais d'autre issue**.

L'erreur de nom d'hôte (on vise une IP) est ignorée : c'est l'empreinte qui
fait foi, exactement comme le `hostnameVerifier` du client OkHttp. La décision
est une fonction pure `EpinglageWebView.accepte(der, attendue)`.

### 5.4 Confinement et réglages

- `shouldOverrideUrlLoading` : seules les URL de **la même origine** (schéma,
  hôte, port) que le serveur trouvé sont chargées ; toute autre est bloquée
  (fonction pure `Confinement.autorise(url, origine)`).
- `javaScriptEnabled = true` (le seul script de la galerie est celui du lecteur
  vidéo) ; **aucune** `addJavascriptInterface` ; `allowFileAccess` et
  `allowContentAccess` à faux ; `mixedContentMode = NEVER_ALLOW` ;
  `mediaPlaybackRequiresUserGesture = false` (démarrage automatique de la
  vidéo) ; `setWebContentsDebuggingEnabled` en APK de débogage seulement.

## 6. Les états de l'onglet

Une machine d'états pure, `EtatGalerie`, aux transitions testées :

| État | Affichage | On y entre |
|---|---|---|
| `Recherche` | « Recherche du serveur… » | première ouverture de l'onglet ; « Réessayer » |
| `PasALaMaison` | « Serveur introuvable — vous n'êtes probablement pas chez vous. » (le texte de l'accueil) + bouton « Réessayer » | découverte vide ; échange en échec réseau ; erreur de la **page principale** ; certificat refusé ; second `401` d'affilée |
| `Prete` | la `WebView` | échange réussi, cookie posé |
| (révocation) | rien de propre à l'onglet | l'échange répond `401` → coffre vidé, retour à l'appairage avec le bandeau « révoqué », par le même chemin que la synchro |

Règles :

- **Jamais la page d'erreur du navigateur** : toute erreur de la page
  principale (`onReceivedError` / `onReceivedHttpError` avec
  `request.isForMainFrame`) fait basculer vers un état natif. L'erreur d'une
  ressource secondaire (une vignette) ne change rien : la page a déjà son
  image de remplacement.
- **Un `401` sur la page principale** (session expirée, service redémarré) :
  un nouvel échange puis un rechargement de la même URL. Un second `401`
  d'affilée → `PasALaMaison` et une ligne au journal : on ne boucle pas. Le
  coffre n'est **pas** vidé sur ce seul indice — seul un `401` de l'échange,
  authentifié par le jeton lui-même, prouve la révocation.
- Le certificat refusé mène à `PasALaMaison` : c'est l'une des trois causes
  que l'application ne sait pas distinguer (#23).
- La découverte et l'échange tournent hors du fil principal, dans un
  `ModeleGalerie` (`AndroidViewModel`). La révocation passe par
  `ModeleAccueil`, qui tient l'état « appairé / révoqué ».

## 7. La vie de la `WebView`

- **Une seule `WebView` par activité**, conservée d'un onglet à l'autre : y
  revenir ne recharge rien et garde le défilement.
- **Rotation** : l'activité est recréée ; l'URL courante est retenue
  (`rememberSaveable`) et rechargée. La position dans la page est perdue —
  accepté. Pas de `configChanges` dans le manifeste : ce serait contourner
  tout le cycle de vie de Compose pour un seul écran.
- Découverte et échange à l'entrée ou après une erreur, **pas à chaque retour
  sur l'onglet**. Pas de renouvellement par minuterie : le `401` s'en charge.
- À la création de la `WebView`, `CookieManager.removeSessionCookies` avant le
  premier échange : aucune session d'une exécution précédente ne traîne.
- Au désappairage (et à la révocation), les cookies de la `WebView` sont
  effacés.
- **Plein écran vidéo** : un `WebChromeClient` minimal implémente
  `onShowCustomView` / `onHideCustomView` (sans lui, le bouton plein écran de
  `<video>` ne fait rien) ; le retour quitte le plein écran.
- La page suit `prefers-color-scheme` ; le thème de la fenêtre (§3.3) le lui
  transmet.

**Journal Android** (`Phototheque`) : échange réussi / refusé, certificat
refusé, erreur de la page principale, double `401`. Le chemin seulement, sans
l'hôte ni l'empreinte d'un média.

## 8. #42 et #39

### 8.1 #42 — un arrêt subi ne s'écrit plus « terminée »

- `IssueSynchro` gagne un champ **`arretSubi`**, posé par la branche
  `catch (CancellationException)` de `TravailSynchro.doWork` quand
  `arretDemande` est faux. Il n'est **pas** affiché : l'écran reste tel quel
  (un arrêt subi ne doit pas dire « interrompue par vous »).
- `Journal.decrire` le lit en premier et écrit :
  `arrêtée par le système (contrainte perdue ou relance) : N envoyés, N refusés, N en échec, <dossiers>`.
- `pourLEcran()` devient une fonction pure `Bilan.pourLEcran(arretDemande)`,
  testable (elle est privée et lit le drapeau du companion aujourd'hui).
- `docs/APPLICATION-ANDROID.md` §11 : la note de contournement (« dossiers non
  lus signe un arrêt subi ») est remplacée par la nouvelle ligne.

### 8.2 #39 — interrompre une manuelle ne touche plus l'automatique

- Le travail qui prend `VerrouSynchro` note sa file dans un
  `@Volatile fileEnCours` du companion (`"manuelle"` ou `"auto"`), remis à
  `null` là où le verrou est rendu. Lu **sans attente** — contrairement à
  `getWorkInfosForUniqueWork`, asynchrone — ce qui compte depuis le
  `BroadcastReceiver` de la notification, qui n'a que quelques secondes de vie.
- Décision pure `Interruption.decider(fileEnCours)` :

| `fileEnCours` | File manuelle | File automatique |
|---|---|---|
| `"auto"` | annulée | annulée **et** replanifiée avec 6 h de délai (comportement actuel, nécessaire : `cancelUniqueWork` détruit la chaîne) |
| `"manuelle"` ou `null` | annulée (y compris une manuelle en attente de réseau) | **laissée intacte** |

- `arretDemande` reste posé dans tous les cas, avant l'annulation.
- Pourquoi c'est sûr : `WorkManager` exécute ses travaux dans le processus de
  l'application ; si rien n'y tient le verrou, aucune passe automatique ne
  tourne. Le cas C1 (une passe bloquée dans un appel réseau qui garde le
  verrou) donne `"auto"` : elle est bien annulée.
- **Limite assumée** : entre le démarrage d'une passe automatique et sa prise
  du verrou (quelques millisecondes), un appui sur « Interrompre » la laisse
  filer. L'accueil n'affiche « Interrompre » qu'une fois l'avancement publié,
  donc après la prise du verrou.
- `docs/APPLICATION-ANDROID.md` §8 : le paragraphe « Interrompre ne déprogramme
  pas l'automatique » décrit le nouveau comportement (critère de l'issue).

## 9. Tests et recette

### 9.1 Tests automatiques (validés par mutation)

**Serveur (pytest)**

1. `POST /galerie/session` exige un `Bearer` valide ; `401` sinon, et le mot
   de passe d'admin ne suffit pas.
2. Le cookie ouvre les cinq routes de la galerie (`/`, `/galerie/media`,
   `/galerie/vignette`, `/galerie/moyenne`, `/galerie/original` en `Range`).
3. Le cookie **n'ouvre pas** `/admin`, `/pair`, `/apk`, `/devices`,
   `/historique`, `/evenements`, `/status`, `/sync/*`, `/sync/desappairer`.
4. Refusés : cookie forgé, expiré, d'un appareil révoqué, d'un appareil
   désappairé ; la révocation purge les sessions ; un rechargement du module
   (redémarrage) les invalide. Le refus ne porte pas `WWW-Authenticate: Basic`.
5. Lecture par appareil : pas de lien « Administration » ni « Télécharger » ;
   lecture par mot de passe : les deux présents.
6. `/docs`, `/redoc`, `/openapi.json` : 404.
7. `tests/test_theme_app.py` : `web.py` contre `Theme.kt` et les deux
   `colors.xml`.

**Application (JVM, JUnit4)**

1. `Theme` : aucun rôle ne garde la valeur Material par défaut, en clair comme
   en sombre.
2. `EpinglageWebView.accepte` : empreinte attendue calculée **hors de** la
   fonction testée (leçon de la tâche 8 du lot 2), casse et espaces tolérés,
   refus d'un certificat voisin.
3. Chaîne du cookie : attributs, et pas de `Secure` sans TLS.
4. `ClientServeur.sessionGalerie` (`mockwebserver`) : `200` décodé, `401` →
   `ServeurRevoqueException`, erreur réseau.
5. `EtatGalerie` : toutes les transitions, dont le double `401` qui ne boucle
   pas et la révocation.
6. `Navigation` : la galerie survit à une synchro, retour depuis la galerie,
   barre visible sur les seuls deux onglets.
7. `Confinement.autorise` : même origine acceptée, autre hôte, autre port,
   autre schéma refusés.
8. `Journal.decrire` avec `arretSubi` (#42) ; `Bilan.pourLEcran`.
9. `Interruption.decider` (#39), les trois cas.

**Ce qu'aucun test ne couvre** : la `WebView` elle-même, les cookies réels, la
vidéo, le rendu du thème, `WorkManager`. D'où la recette.

### 9.2 Recette (après le relevé de l'étape 11 du lot 2)

Ajoutée au §9 de `docs/APPLICATION-ANDROID.md`. Préalable : mise à jour du
NUC (`install.sh`, inventaire de `incoming/` d'abord), puis installation de
l'APK.

1. **La vidéo porte le cookie** : une vidéo démarre et avance, et
   `journalctl -u phototheque` ne montre aucun `401` sur `/galerie/original`.
   C'est le point qu'aucun test ne peut trancher (le lecteur multimédia de la
   `WebView` passe par la pile réseau de Chromium, qui porte en principe les
   cookies et l'acceptation du certificat) — **à faire en premier**.
2. Les vignettes s'affichent, ainsi que la taille moyenne d'une photo (et le
   `307` d'une vidéo).
3. Hors du WiFi : « pas à la maison », jamais la page d'erreur du navigateur ;
   « Réessayer » fonctionne de retour à la maison.
4. `systemctl restart phototheque` pendant la consultation : la page suivante
   se charge sans intervention (nouvel échange).
5. Révocation depuis `/admin` : l'application revient à l'appairage, bandeau
   « révoqué ».
6. Pas de lien « Administration » ni « Télécharger » dans l'application.
7. Une synchro démarrée pendant la consultation ne fait pas quitter la galerie.
8. Rotation, retour arrière dans la page, plein écran vidéo et sortie par
   retour.
9. Thème, en clair puis en sombre, côte à côte avec `/admin` : accueil,
   galerie, réglages, notification (critère de #43).
10. #42 : débrancher pendant une passe automatique, `adb logcat -s Phototheque`
    montre « arrêtée par le système ».
11. #39 : interrompre une sauvegarde manuelle, `adb shell dumpsys jobscheduler`
    montre la passe périodique à son échéance d'origine.

L'épinglage **refusé** n'a pas de recette réelle (il faudrait un second
certificat) : il repose sur le test JVM de `EpinglageWebView.accepte`.

## 10. Ordre de réalisation

1. Thème (#43) — il conditionne le rendu sombre de la galerie.
2. #42 et #39.
3. Serveur : sessions de galerie, `require_lecteur` qui dit qui lit, liens
   masqués, contrat.
4. Application : échange, épinglage et confinement de la `WebView`,
   `EtatGalerie`, barre d'onglets.
5. Documentation (`APPLICATION-ANDROID.md` §8, §9, §11 ; `CONTRAT-APP.md` ;
   `CLAUDE.md`).

Le serveur passe avant l'application pour que l'échange ait un contrat testé
avant d'être appelé.

## 11. Hors périmètre

- Toute nouvelle fonction de la galerie (albums, recherche, modification) :
  la galerie est affichée telle que le serveur la sert.
- Le téléchargement d'un original depuis l'application.
- L'accès depuis l'extérieur de la maison.
- Les vignettes orphelines d'un média retouché (rien ne les supprime ; place
  perdue, sans autre effet) et la relance automatique des vignettes en échec
  (`--reessayer-erreurs` reste manuel) — relevés pendant cette conception, à
  suivre en issue si besoin.
- Un test d'instrumentation Android : toujours aucun dans ce projet ; la
  recette en tient lieu.
