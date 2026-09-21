# Lot 1 bis — la synchronisation devient observable et pilotable

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** rendre une synchronisation visible pendant qu'elle tourne, arrêtable
à tout moment, capable de survivre à un écran éteint, et incapable d'annoncer
une panne quand elle a réussi.

**Architecture :** l'orchestrateur quitte le `viewModelScope` pour un service
de premier plan piloté par `WorkManager`, et publie un `Avancement` immuable
auquel l'écran s'abonne s'il existe. La synchronisation est découpée en paquets
d'environ 500 Mo, chacun validé par son propre `commit` — ce qui fait avancer
l'horizon en cours de route au lieu de tout jouer sur un commit final d'une
heure.

**Tech Stack :** Kotlin, Compose, Coroutines, `WorkManager`, OkHttp, JUnit 4,
MockWebServer. Côté serveur : Python 3, pytest (un seul test de contrat).

**Spec :** [`docs/superpowers/specs/2026-09-21-app-android-lot1bis-synchro-observable-design.md`](../specs/2026-09-21-app-android-lot1bis-synchro-observable-design.md)

**Issue :** #29

## Global Constraints

- **Documenter et commenter en français.** Le mainteneur débute en Python et en
  Kotlin. Un commentaire explique *pourquoi*, pas *quoi*.
- **Messages de commit sans accents** (sujet et corps).
- **TDD strict** : le test d'abord, on le voit échouer, puis le minimum pour
  qu'il passe.
- **Valider chaque test par mutation** : casser volontairement le code et
  vérifier que c'est bien ce test-là qui tombe. Plusieurs faux verts ont été
  attrapés ainsi le 18/09.
- Tests Android : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
  — ⚠️ `./gradlew test --tests` échoue, il faut `testDebugUnitTest --tests`.
- Tests serveur : `python3 -m pytest -q` à la racine du dépôt.
- **Aucune horloge réelle dans une unité testable** : l'instant est un
  paramètre, jamais `System.currentTimeMillis()` appelé au fond du code.
- Les trois dossiers sauvegardés restent **codés en dur** : le choix dans
  l'application est le lot 2.
- `minSdk = 29`, `targetSdk = 34`.

---

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `synchro/Horizons.kt` *(modifié)* | La règle de l'horizon, étendue pour traverser les paquets |
| `synchro/Paquets.kt` *(créé)* | Découpe la liste des candidats en lots bornés |
| `synchro/Debit.kt` *(créé)* | Moyenne glissante du débit et estimation du reste |
| `synchro/Avancement.kt` *(créé)* | Instantané immuable de la progression |
| `synchro/Destination.kt` *(créé)* | Chemin prévu dans la bibliothèque (affichage seul) |
| `synchro/Orchestrateur.kt` *(modifié)* | Enchaîne les paquets, publie l'avancement, obéit à l'annulation |
| `reseau/Decouverte.kt` *(modifié)* | Délais HTTP explicites |
| `reseau/ClientServeur.kt` *(modifié)* | `abandonner(session)` |
| `synchro/ServiceSynchro.kt` *(créé)* | Service de premier plan : notification, bouton Interrompre |
| `synchro/TravailSynchro.kt` *(créé)* | `CoroutineWorker` : contrainte réseau, reprise, unicité |
| `ui/Ecrans.kt` *(modifié)* | Écran d'avancement (maquette B), retour système |
| `ui/ModeleAccueil.kt` *(modifié)* | S'abonne au travail au lieu de le porter |
| `tests/test_contrat_app.py` *(modifié)* | Vérifie que `Destination` ne diverge pas du serveur |

---

### Task 1 : L'horizon survit d'un paquet à l'autre

**C'est la tâche qui protège les photos.** Elle vient en premier parce qu'une
erreur ici se paie par une perte définitive et silencieuse.

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Horizons.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/HorizonsTest.kt`

**Interfaces:**
- Consumes: `Envoi(dossier: String, instant: Double, issue: Issue)`, `Issue` — déjà présents
- Produces:
  - `data class ResultatHorizons(val horizons: Map<String, Double>, val arretes: Set<String>)`
  - `Horizons.calculer(envois: List<Envoi>, dejaArretes: Set<String> = emptySet()): ResultatHorizons`

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à la fin de `HorizonsTest.kt` (garder les tests existants ; ils
continuent d'appeler `calculer(envois)` sans second argument, ce que la valeur
par défaut permet — mais ils lisent désormais `.horizons`) :

```kotlin
    @Test fun un_dossier_deja_arrete_ne_bouge_plus_meme_si_le_paquet_reussit() {
        // Paquet 12 : DCIM/Camera a echoue. Paquet 13 : il reussit.
        // Sans memoire entre paquets, l'horizon sauterait PAR-DESSUS le
        // fichier en echec, qui ne serait PLUS JAMAIS propose par le serveur.
        val resultat = Horizons.calculer(
            listOf(Envoi("DCIM/Camera", 3000.0, Issue.CONFIRME)),
            dejaArretes = setOf("DCIM/Camera"),
        )
        assertFalse(resultat.horizons.containsKey("DCIM/Camera"))
    }

    @Test fun un_dossier_arrete_n_arrete_pas_les_autres() {
        val resultat = Horizons.calculer(
            listOf(
                Envoi("DCIM/Camera", 3000.0, Issue.CONFIRME),
                Envoi("Pictures/WhatsApp", 3000.0, Issue.CONFIRME),
            ),
            dejaArretes = setOf("DCIM/Camera"),
        )
        assertFalse(resultat.horizons.containsKey("DCIM/Camera"))
        assertEquals(3000.0, resultat.horizons["Pictures/WhatsApp"]!!, 0.0)
    }

    @Test fun les_dossiers_arretes_sont_rendus_pour_le_paquet_suivant() {
        val resultat = Horizons.calculer(
            listOf(
                Envoi("DCIM/Camera", 1000.0, Issue.CONFIRME),
                Envoi("DCIM/Camera", 2000.0, Issue.ECHEC),
            ),
        )
        assertEquals(setOf("DCIM/Camera"), resultat.arretes)
        assertEquals(1000.0, resultat.horizons["DCIM/Camera"]!!, 0.0)
    }

    @Test fun les_arretes_recus_sont_conserves_dans_le_resultat() {
        // Sans cela, l'appelant qui repasse `resultat.arretes` au paquet
        // suivant perdrait la memoire des paquets precedents des qu'un paquet
        // ne contient aucun media du dossier fautif.
        val resultat = Horizons.calculer(
            listOf(Envoi("Movies/WhatsApp", 5000.0, Issue.CONFIRME)),
            dejaArretes = setOf("DCIM/Camera"),
        )
        assertTrue(resultat.arretes.contains("DCIM/Camera"))
    }

    @Test fun un_refus_d_extension_n_arrete_toujours_pas_le_dossier() {
        // IGNORE n'est pas un echec : bloquer l'horizon dessus fermerait le
        // dossier a jamais, puisque le serveur refusera toujours ce fichier.
        val resultat = Horizons.calculer(
            listOf(
                Envoi("DCIM/Camera", 1000.0, Issue.IGNORE),
                Envoi("DCIM/Camera", 2000.0, Issue.CONFIRME),
            ),
        )
        assertEquals(2000.0, resultat.horizons["DCIM/Camera"]!!, 0.0)
        assertTrue(resultat.arretes.isEmpty())
    }
```

Adapter les tests existants du fichier : remplacer `Horizons.calculer(envois)`
par `Horizons.calculer(envois).horizons` partout où le résultat est traité
comme une `Map`.

Imports à ajouter en tête du fichier s'ils manquent :

```kotlin
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*HorizonsTest*"`
Expected: FAIL — `calculer` ne prend pas de second argument, et son résultat
n'a pas de propriété `horizons`.

- [ ] **Step 3 : Implémenter**

Remplacer le corps de `Horizons` dans `Horizons.kt` :

```kotlin
/**
 * Ce que rend [Horizons.calculer] : les horizons à transmettre, et la liste
 * des dossiers dont l'horizon est GELÉ pour le reste de la synchronisation.
 */
data class ResultatHorizons(
    val horizons: Map<String, Double>,
    val arretes: Set<String>,
)

object Horizons {

    /**
     * Horizon à transmettre pour chaque dossier : la date du dernier fichier
     * confirmé AVANT le premier échec de ce dossier.
     *
     * Pourquoi pas « la date la plus haute confirmée » : si le fichier n° 5
     * échoue et que le n° 6 réussit, retenir la plus haute ferait sauter
     * l'horizon par-dessus le n° 5, qui ne serait PLUS JAMAIS proposé par le
     * serveur — perte définitive et silencieuse.
     *
     * @param dejaArretes les dossiers gelés par les PAQUETS PRÉCÉDENTS de la
     *   même synchronisation. Sans ce paramètre, le découpage en paquets
     *   rouvrirait exactement le trou que cette fonction existe pour combler :
     *   un dossier en échec au paquet 12 verrait son horizon avancer au
     *   paquet 13, et le fichier fautif serait perdu. L'appelant repasse
     *   [ResultatHorizons.arretes] d'un paquet au suivant.
     *
     * La fonction reste pure : aucun état retenu entre deux appels.
     */
    fun calculer(
        envois: List<Envoi>,
        dejaArretes: Set<String> = emptySet(),
    ): ResultatHorizons {
        val horizons = mutableMapOf<String, Double>()
        val arretes = dejaArretes.toMutableSet()
        // Tri par date, puis ECHEC d'abord A DATE EGALE. Deux envois du meme
        // dossier peuvent porter exactement la meme date : DATE_MODIFIED n'a
        // qu'une precision d'une seconde et une rafale en produit plusieurs.
        // Sans ce second critere, `sortedBy` etant un tri STABLE, le resultat
        // dependrait de l'ordre de la liste d'entree. A egalite on retient le
        // cas prudent : l'echec arrete le dossier, quitte a reproposer
        // quelques fichiers que l'anti-doublon ecartera sans les transferer.
        for (envoi in envois.sortedWith(
            compareBy({ it.instant }, { if (it.issue == Issue.ECHEC) 0 else 1 })
        )) {
            if (envoi.dossier in arretes) continue
            when (envoi.issue) {
                Issue.ECHEC -> arretes += envoi.dossier
                Issue.CONFIRME, Issue.IGNORE -> horizons[envoi.dossier] = envoi.instant
            }
        }
        return ResultatHorizons(horizons, arretes)
    }
}
```

Laisser `Issue` et `Envoi` inchangés au-dessus.

- [ ] **Step 4 : Vérifier que tout passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*HorizonsTest*"`
Expected: PASS

- [ ] **Step 5 : Valider par mutation**

Remplacer `val arretes = dejaArretes.toMutableSet()` par
`val arretes = mutableSetOf<String>()`, relancer.
Expected: `un_dossier_deja_arrete_ne_bouge_plus_meme_si_le_paquet_reussit` et
`les_arretes_recus_sont_conserves_dans_le_resultat` **échouent**. Remettre.

- [ ] **Step 6 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Horizons.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/HorizonsTest.kt
git commit -m "feat(horizons): geler un dossier en echec pour toute la synchro, pas un paquet

Le decoupage en paquets rouvrait le trou que Horizons.calculer existe pour
combler : un dossier en echec au paquet 12 voyait son horizon avancer au
paquet 13, et le fichier fautif n'etait PLUS JAMAIS propose.

calculer() prend desormais les dossiers deja arretes et les rend enrichis ;
l'appelant les repasse d'un paquet au suivant. La fonction reste pure."
```

---

### Task 2 : Découper en paquets

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Paquets.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/PaquetsTest.kt`

**Interfaces:**
- Consumes: `fr.izquierdo.phototheque.medias.Media`
- Produces: `Paquets.decouper(medias: List<Media>, tailleMax: Long = Paquets.TAILLE_MAX_OCTETS): List<List<Media>>`, `Paquets.TAILLE_MAX_OCTETS: Long`

- [ ] **Step 1 : Écrire le test qui échoue**

`android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/PaquetsTest.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PaquetsTest {

    private fun media(id: Long, taille: Long, instant: Double) =
        Media(id = id, dossier = "DCIM/Camera", nom = "m$id.jpg",
              taille = taille, instant = instant)

    @Test fun une_liste_vide_ne_donne_aucun_paquet() {
        assertTrue(Paquets.decouper(emptyList()).isEmpty())
    }

    @Test fun les_medias_tiennent_dans_un_seul_paquet_sous_la_limite() {
        val lot = listOf(media(1, 100, 1.0), media(2, 100, 2.0))
        assertEquals(1, Paquets.decouper(lot, tailleMax = 1000).size)
    }

    @Test fun on_change_de_paquet_quand_la_limite_serait_depassee() {
        val lot = listOf(media(1, 600, 1.0), media(2, 600, 2.0))
        val paquets = Paquets.decouper(lot, tailleMax = 1000)
        assertEquals(2, paquets.size)
        assertEquals(1L, paquets[0].single().id)
        assertEquals(2L, paquets[1].single().id)
    }

    @Test fun un_media_plus_gros_que_la_limite_fait_son_paquet_a_lui_seul() {
        // Une video de 3 Go depasse n'importe quelle taille de paquet
        // raisonnable. La refuser, ou la couper, la perdrait.
        val lot = listOf(media(1, 5000, 1.0))
        val paquets = Paquets.decouper(lot, tailleMax = 1000)
        assertEquals(1, paquets.size)
        assertEquals(1L, paquets.single().single().id)
    }

    @Test fun un_media_enorme_ne_se_melange_pas_aux_suivants() {
        val lot = listOf(media(1, 5000, 1.0), media(2, 10, 2.0))
        val paquets = Paquets.decouper(lot, tailleMax = 1000)
        assertEquals(2, paquets.size)
        assertEquals(1L, paquets[0].single().id)
    }

    @Test fun aucun_media_n_est_perdu_ni_duplique() {
        val lot = (1L..50L).map { media(it, 300, it.toDouble()) }
        val plat = Paquets.decouper(lot, tailleMax = 1000).flatten()
        assertEquals(lot.map { it.id }, plat.map { it.id })
    }

    @Test fun l_ordre_par_date_croissante_est_conserve() {
        // L'ordre chronologique est ce qui rend la regle de l'horizon juste :
        // le melanger ferait avancer un horizon par-dessus un fichier plus
        // ancien pas encore envoye.
        val lot = listOf(media(1, 10, 100.0), media(2, 10, 200.0), media(3, 10, 300.0))
        val plat = Paquets.decouper(lot, tailleMax = 25).flatten()
        assertEquals(listOf(100.0, 200.0, 300.0), plat.map { it.instant })
    }

    @Test fun la_taille_par_defaut_est_de_500_Mo() {
        assertEquals(500L * 1024 * 1024, Paquets.TAILLE_MAX_OCTETS)
    }
}
```

- [ ] **Step 2 : Vérifier qu'il échoue**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*PaquetsTest*"`
Expected: FAIL — `Paquets` n'existe pas.

- [ ] **Step 3 : Implémenter**

`android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Paquets.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media

/**
 * Découpe les candidats en lots bornés, chacun validé par son propre `commit`.
 *
 * Pourquoi : le 21/09/2026, une synchronisation de 971 fichiers et 14 Go a
 * demandé UN SEUL commit, qui a mis 1 h 02 à s'exécuter. Le téléphone avait
 * raccroché depuis longtemps, et si la synchro avait été interrompue avant,
 * les 14 Go auraient été perdus — rien n'était rangé, aucun horizon n'avait
 * bougé. Un paquet borne à la fois la perte possible et la durée d'un commit.
 */
object Paquets {

    /**
     * Point de départ, pas un résultat mesuré. Trop petit multiplie les tris
     * et les allers-retours ; trop grand rapproche du défaut qu'on corrige.
     * À réviser après le premier grand rattrapage.
     */
    const val TAILLE_MAX_OCTETS: Long = 500L * 1024 * 1024

    /**
     * @param medias déjà triés par date croissante — l'ordre est conservé tel
     *   quel, parce que c'est lui qui rend la règle de l'horizon juste.
     *
     * Un média plus gros que [tailleMax] fait son paquet à lui seul plutôt que
     * d'être refusé : une vidéo de 3 Go est un cas normal sur un téléphone, et
     * la sauter la perdrait.
     */
    fun decouper(
        medias: List<Media>,
        tailleMax: Long = TAILLE_MAX_OCTETS,
    ): List<List<Media>> {
        val paquets = mutableListOf<List<Media>>()
        var courant = mutableListOf<Media>()
        var cumul = 0L
        for (media in medias) {
            // Le test porte sur `courant.isNotEmpty()` AVANT tout : sans lui,
            // un media plus gros que la limite produirait un paquet vide puis
            // un paquet contenant ce media, et le paquet vide ferait un
            // commit inutile a chaque grosse video.
            if (courant.isNotEmpty() && cumul + media.taille > tailleMax) {
                paquets += courant
                courant = mutableListOf()
                cumul = 0L
            }
            courant += media
            cumul += media.taille
        }
        if (courant.isNotEmpty()) paquets += courant
        return paquets
    }
}
```

- [ ] **Step 4 : Vérifier que ça passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*PaquetsTest*"`
Expected: PASS

- [ ] **Step 5 : Valider par mutation**

Retirer `courant.isNotEmpty() &&` de la condition, relancer.
Expected: `un_media_plus_gros_que_la_limite_fait_son_paquet_a_lui_seul` échoue
(2 paquets au lieu de 1). Remettre.

- [ ] **Step 6 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Paquets.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/PaquetsTest.kt
git commit -m "feat(paquets): decouper une synchro en lots de 500 Mo

Le 21/09, un commit unique de 971 fichiers et 14 Go a mis 1 h 02. Une
interruption avant la fin aurait tout perdu : rien de range, aucun horizon
avance. Un paquet borne la perte possible et la duree d'un commit.

Un media plus gros que la limite fait son paquet a lui seul : une video de
3 Go est un cas normal, la sauter la perdrait."
```

---

### Task 3 : Le débit et le temps restant

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Debit.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DebitTest.kt`

**Interfaces:**
- Consumes: rien
- Produces:
  - `class Debit(fenetreMs: Long = 30_000L)`
  - `Debit.ajouter(octets: Long, instantMs: Long)`
  - `Debit.octetsParSeconde(): Double?`
  - `Debit.secondesRestantes(octetsRestants: Long): Long?`

- [ ] **Step 1 : Écrire le test qui échoue**

`android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DebitTest.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DebitTest {

    @Test fun sans_mesure_le_debit_est_inconnu() {
        // Inconnu, PAS zero : afficher « 0 Mo/s » au demarrage ferait croire
        // a un blocage.
        assertNull(Debit().octetsParSeconde(1000L))
    }

    @Test fun une_seule_mesure_ne_suffit_pas() {
        // Une mesure ne donne aucune duree : un debit calcule dessus serait
        // une division par zero, ou un nombre invente.
        val d = Debit()
        d.ajouter(1000, 0L)
        assertNull(d.octetsParSeconde(0L))
    }

    @Test fun deux_mesures_donnent_un_debit() {
        val d = Debit()
        d.ajouter(0, 0L)
        d.ajouter(2000, 2000L)          // 2000 octets en 2 s
        assertEquals(1000.0, d.octetsParSeconde(2000L)!!, 1.0)
    }

    @Test fun les_mesures_trop_vieilles_sortent_de_la_fenetre() {
        // Moyenne GLISSANTE : une video enorme envoyee il y a cinq minutes ne
        // doit plus peser sur l'estimation d'un lot de petites photos.
        val d = Debit(fenetreMs = 10_000L)
        d.ajouter(0, 0L)
        d.ajouter(1_000_000, 1_000L)    // tres rapide, puis oublie
        d.ajouter(1_000_100, 20_000L)   // tres lent, dans la fenetre
        val vu = d.octetsParSeconde(20_000L)!!
        assertTrue("debit=$vu devrait etre faible", vu < 1000.0)
    }

    @Test fun le_temps_restant_est_inconnu_sans_debit() {
        assertNull(Debit().secondesRestantes(5000, 1000L))
    }

    @Test fun le_temps_restant_se_deduit_du_debit() {
        val d = Debit()
        d.ajouter(0, 0L)
        d.ajouter(1000, 1000L)          // 1000 octets/s
        assertEquals(5L, d.secondesRestantes(5000, 1000L))
    }

    @Test fun un_reste_nul_donne_zero_seconde() {
        val d = Debit()
        d.ajouter(0, 0L)
        d.ajouter(1000, 1000L)
        assertEquals(0L, d.secondesRestantes(0, 1000L))
    }

    @Test fun un_debit_nul_ne_divise_pas_par_zero() {
        // Deux mesures au meme instant, ou aucun octet transfere : le calcul
        // rendrait Infinity, et l'ecran afficherait « ~ Infinity min ».
        val d = Debit()
        d.ajouter(500, 0L)
        d.ajouter(500, 5000L)           // zero octet en 5 s
        assertNull(d.secondesRestantes(1000, 5000L))
    }
}
```

- [ ] **Step 2 : Vérifier qu'il échoue**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*DebitTest*"`
Expected: FAIL — `Debit` n'existe pas.

- [ ] **Step 3 : Implémenter**

`android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Debit.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

/**
 * Débit moyen sur une fenêtre glissante, et estimation du temps restant.
 *
 * L'instant est TOUJOURS un paramètre, jamais lu d'une horloge : sans cela la
 * classe ne serait testable qu'avec des `Thread.sleep`, c'est-à-dire pas
 * testable du tout.
 *
 * Fenêtre glissante et non moyenne depuis le début : une vidéo de 900 Mo
 * envoyée il y a cinq minutes ne doit plus peser sur l'estimation d'un lot de
 * petites photos. C'est précisément l'erreur qui, le 17/09, a fait annoncer
 * 1 h pour un travail de 16 min.
 */
class Debit(private val fenetreMs: Long = 30_000L) {

    /** (instant, octets cumulés depuis le début de la synchronisation). */
    private val mesures = ArrayDeque<Pair<Long, Long>>()

    /** @param octets total cumulé, pas l'incrément. */
    fun ajouter(octets: Long, instantMs: Long) {
        mesures.addLast(instantMs to octets)
        while (mesures.size > 2 && instantMs - mesures.first().first > fenetreMs) {
            mesures.removeFirst()
        }
    }

    /** Octets par seconde, ou null tant qu'on ne peut rien dire d'honnête. */
    fun octetsParSeconde(instantMs: Long): Double? {
        if (mesures.size < 2) return null
        val (t0, o0) = mesures.first()
        val (t1, o1) = mesures.last()
        val duree = t1 - t0
        if (duree <= 0L) return null
        return (o1 - o0) * 1000.0 / duree
    }

    /**
     * Secondes restantes, ou null si l'estimation serait inventée.
     *
     * Un débit nul rendrait `Infinity`, et l'écran afficherait « ~ Infinity
     * min ». Mieux vaut ne rien afficher.
     */
    fun secondesRestantes(octetsRestants: Long, instantMs: Long): Long? {
        if (octetsRestants <= 0L) return 0L
        val debit = octetsParSeconde(instantMs) ?: return null
        if (debit <= 0.0) return null
        return (octetsRestants / debit).toLong()
    }
}
```

- [ ] **Step 4 : Vérifier que ça passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*DebitTest*"`
Expected: PASS

- [ ] **Step 5 : Valider par mutation**

Remplacer `if (debit <= 0.0) return null` par `if (false) return null`,
relancer.
Expected: `un_debit_nul_ne_divise_pas_par_zero` échoue. Remettre.

- [ ] **Step 6 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Debit.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DebitTest.kt
git commit -m "feat(debit): moyenne glissante et temps restant, sur horloge injectee

Fenetre glissante et non moyenne depuis le debut : une video de 900 Mo
envoyee il y a cinq minutes ne doit plus peser sur l'estimation d'un lot de
petites photos. C'est l'erreur qui, le 17/09, a fait annoncer 1 h pour un
travail de 16 min.

Rend null plutot qu'un chiffre invente : sans mesure, avec une seule mesure,
ou a debit nul — ce dernier cas donnerait « ~ Infinity min » a l'ecran."
```

---

### Task 4 : La destination prévue

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Destination.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DestinationTest.kt`
- Modify: `tests/test_contrat_app.py`

**Interfaces:**
- Consumes: rien
- Produces: `Destination.dossier(instantSecondes: Double, estVideo: Boolean, cheminSource: String): String`

- [ ] **Step 1 : Écrire le test Kotlin qui échoue**

`android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DestinationTest.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

class DestinationTest {

    // 2025-09-27 14:48:22 UTC
    private val septembre2025 = 1759000102.0

    @Test fun une_photo_va_dans_Photos_annee_mois() {
        assertEquals("Photos/2025/09 SEPTEMBRE",
            Destination.dossier(septembre2025, estVideo = false,
                                cheminSource = "DCIM/Camera/IMG.jpg"))
    }

    @Test fun une_video_va_dans_Videos() {
        assertEquals("Videos/2025/09 SEPTEMBRE",
            Destination.dossier(septembre2025, estVideo = true,
                                cheminSource = "DCIM/Camera/VID.mp4"))
    }

    @Test fun un_media_whatsapp_passe_sous_le_dossier_WhatsApp() {
        assertEquals("WhatsApp/Photos/2025/09 SEPTEMBRE",
            Destination.dossier(septembre2025, estVideo = false,
                                cheminSource = "Pictures/WhatsApp/IMG.jpg"))
    }

    @Test fun la_detection_whatsapp_ignore_la_casse() {
        // Le serveur teste `"whatsapp" in part.lower()` : une ROM qui ecrit
        // « whatsapp » en minuscules doit ranger au meme endroit.
        assertEquals("WhatsApp/Videos/2025/09 SEPTEMBRE",
            Destination.dossier(septembre2025, estVideo = true,
                                cheminSource = "Movies/whatsapp/VID.mp4"))
    }

    @Test fun les_mois_portent_le_nom_francais_en_majuscules() {
        // 2026-01-15 et 2026-08-16 (UTC) : janvier et aout, sans accent
        // circonflexe — le serveur ecrit « AOUT », pas « AOÛT ».
        assertEquals("Photos/2026/01 JANVIER",
            Destination.dossier(1768435200.0, false, "DCIM/Camera/a.jpg"))
        assertEquals("Photos/2026/08 AOUT",
            Destination.dossier(1786838400.0, false, "DCIM/Camera/a.jpg"))
    }
}
```

- [ ] **Step 2 : Vérifier qu'il échoue**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*DestinationTest*"`
Expected: FAIL — `Destination` n'existe pas.

- [ ] **Step 3 : Implémenter**

`android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Destination.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import java.time.Instant
import java.time.ZoneOffset

/**
 * Où le serveur rangera probablement ce média. **Affichage seulement.**
 *
 * C'est la seule unité de l'application qui duplique une logique du serveur
 * (`mediasort.classify.destination`). Le serveur reste seul juge : il lit les
 * métadonnées du fichier, que le téléphone ne relit pas, et peut donc trancher
 * une autre date. Cette estimation existe parce que « → Videos/2025/09
 * SEPTEMBRE » à l'écran vaut mieux que rien pendant une heure d'envoi.
 *
 * Un test de contrat côté Python (`tests/test_contrat_app.py`) vérifie que les
 * deux conventions ne divergent pas.
 */
object Destination {

    private val MOIS = arrayOf(
        "JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN",
        "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE",
    )

    /**
     * @param cheminSource chemin sur le téléphone, ex. `Pictures/WhatsApp/a.jpg`
     * @return chemin relatif à la bibliothèque, sans le nom du fichier
     *
     * L'instant est interprété en UTC, comme le fait le serveur : il travaille
     * sur des `datetime` naïfs issus des métadonnées.
     */
    fun dossier(instantSecondes: Double, estVideo: Boolean, cheminSource: String): String {
        val date = Instant.ofEpochSecond(instantSecondes.toLong()).atZone(ZoneOffset.UTC)
        val racine = if (estWhatsApp(cheminSource)) "WhatsApp/" else ""
        val type = if (estVideo) "Videos" else "Photos"
        val mois = String.format("%02d %s", date.monthValue, MOIS[date.monthValue - 1])
        return "$racine$type/${date.year}/$mois"
    }

    /** Même règle que `mediasort.classify.is_whatsapp` : n'importe quel
     *  segment du chemin qui contient « whatsapp », sans égard à la casse. */
    private fun estWhatsApp(chemin: String): Boolean =
        chemin.split('/').any { it.lowercase().contains("whatsapp") }
}
```

- [ ] **Step 4 : Vérifier que ça passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*DestinationTest*"`
Expected: PASS

- [ ] **Step 5 : Ajouter le test de contrat, côté serveur**

Ajouter à la fin de `tests/test_contrat_app.py` :

```python
def test_la_destination_predite_par_l_app_correspond_au_serveur(tmp_path):
    """L'écran d'avancement annonce « → Videos/2025/09 SEPTEMBRE ».

    Cette prédiction est calculée EN DOUBLE dans l'application
    (`synchro/Destination.kt`). Ce test fige la convention côté serveur : s'il
    tombe, c'est que le serveur a changé de règle et que l'application ment
    désormais à l'écran.
    """
    import datetime
    from pathlib import Path
    from mediasort import classify

    class Resultat:
        def __init__(self, d): self.date = d

    attendus = [
        ("DCIM/Camera/IMG.jpg", "photo", datetime.date(2025, 9, 27),
         "Photos/2025/09 SEPTEMBRE"),
        ("DCIM/Camera/VID.mp4", "video", datetime.date(2025, 9, 27),
         "Videos/2025/09 SEPTEMBRE"),
        ("Pictures/WhatsApp/IMG.jpg", "photo", datetime.date(2025, 9, 27),
         "WhatsApp/Photos/2025/09 SEPTEMBRE"),
        ("Movies/whatsapp/VID.mp4", "video", datetime.date(2025, 9, 27),
         "WhatsApp/Videos/2025/09 SEPTEMBRE"),
        ("DCIM/Camera/a.jpg", "photo", datetime.date(2026, 1, 15),
         "Photos/2026/01 JANVIER"),
        ("DCIM/Camera/a.jpg", "photo", datetime.date(2026, 8, 15),
         "Photos/2026/08 AOUT"),
    ]
    for relatif, mtype, jour, attendu in attendus:
        chemin = classify.destination(
            tmp_path, tmp_path / relatif, Resultat(jour), mtype)
        obtenu = str(chemin.parent.relative_to(tmp_path))
        assert obtenu == attendu, f"{relatif} -> {obtenu}, attendu {attendu}"
```

- [ ] **Step 6 : Lancer les deux suites**

Run : `python3 -m pytest tests/test_contrat_app.py -q`
Expected: PASS

- [ ] **Step 7 : Valider par mutation**

Dans `Destination.kt`, remplacer `MOIS[date.monthValue - 1]` par
`MOIS[0]`, relancer les tests Kotlin.
Expected: quatre tests échouent. Remettre.

- [ ] **Step 8 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Destination.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DestinationTest.kt \
        tests/test_contrat_app.py
git commit -m "feat(destination): predire le rangement pour l'afficher pendant l'envoi

Seule unite de l'app qui duplique une logique du serveur. Elle est
indicative : le serveur lit les metadonnees du fichier, que le telephone ne
relit pas, et peut trancher une autre date.

Un test de contrat cote Python fige la convention : s'il tombe, c'est que le
serveur a change de regle et que l'application ment a l'ecran."
```

---

### Task 5 : L'instantané d'avancement

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Avancement.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/AvancementTest.kt`

**Interfaces:**
- Consumes: rien
- Produces:
  - `enum class Phase { ANALYSE, ENVOI, RANGEMENT }`
  - `data class Avancement(...)` — champs listés ci-dessous
  - `Avancement.pourcentage: Int`

- [ ] **Step 1 : Écrire le test qui échoue**

`android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/AvancementTest.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

class AvancementTest {

    @Test fun le_pourcentage_se_calcule_sur_les_octets_pas_sur_les_fichiers() {
        // 9 petites photos et 1 grosse video : compter en fichiers annoncerait
        // 90 % alors que l'essentiel du travail reste a faire.
        val a = Avancement(phase = Phase.ENVOI, fichiersFaits = 9, fichiersTotal = 10,
                           octetsFaits = 100, octetsTotal = 1000)
        assertEquals(10, a.pourcentage)
    }

    @Test fun un_total_nul_ne_divise_pas_par_zero() {
        // Une synchro sans rien a envoyer est le cas COURANT en regime
        // permanent : elle ne doit pas faire planter l'ecran.
        val a = Avancement(phase = Phase.ENVOI, fichiersFaits = 0, fichiersTotal = 0,
                           octetsFaits = 0, octetsTotal = 0)
        assertEquals(0, a.pourcentage)
    }

    @Test fun le_pourcentage_ne_depasse_jamais_cent() {
        val a = Avancement(phase = Phase.ENVOI, fichiersFaits = 1, fichiersTotal = 1,
                           octetsFaits = 2000, octetsTotal = 1000)
        assertEquals(100, a.pourcentage)
    }

    @Test fun un_avancement_neuf_est_en_phase_d_analyse() {
        assertEquals(Phase.ANALYSE, Avancement().phase)
    }

    @Test fun les_champs_d_affichage_sont_absents_par_defaut() {
        val a = Avancement()
        assertEquals(null, a.mediaEnCours)
        assertEquals(null, a.destinationPrevue)
        assertEquals(null, a.octetsParSeconde)
        assertEquals(null, a.secondesRestantes)
    }
}
```

- [ ] **Step 2 : Vérifier qu'il échoue**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*AvancementTest*"`
Expected: FAIL — `Avancement` n'existe pas.

- [ ] **Step 3 : Implémenter**

`android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Avancement.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

/** Les trois phases d'une synchronisation, telles qu'affichées. */
enum class Phase {
    /** Le téléphone calcule les empreintes. Rien ne part sur le réseau —
     *  2 min 08 s mesurées le 21/09, pendant lesquelles l'écran semblait figé. */
    ANALYSE,
    ENVOI,
    /** Le serveur trie le paquet. Peut durer plusieurs minutes. */
    RANGEMENT,
}

/**
 * Instantané immuable de la progression, publié par l'orchestrateur et
 * consommé par l'écran comme par la notification.
 *
 * Immuable et sans référence à Android : l'écran peut disparaître et revenir,
 * l'objet reste valable, et il se teste sur la JVM.
 */
data class Avancement(
    val phase: Phase = Phase.ANALYSE,
    val fichiersFaits: Int = 0,
    val fichiersTotal: Int = 0,
    val octetsFaits: Long = 0L,
    val octetsTotal: Long = 0L,
    val octetsParSeconde: Double? = null,
    val secondesRestantes: Long? = null,
    /** Chemin sur le téléphone, ex. `DCIM/Camera/VID_20250927_164822.mp4`. */
    val mediaEnCours: String? = null,
    val tailleEnCours: Long? = null,
    /** Ex. `Videos/2025/09 SEPTEMBRE`. Estimation : voir [Destination]. */
    val destinationPrevue: String? = null,
    val paquetCourant: Int = 0,
    val paquetsValides: Int = 0,
    /** Dossiers réellement vus sur le téléphone, avec leur nombre de médias. */
    val dossiersVus: Map<String, Int> = emptyMap(),
) {
    /**
     * Calculé sur les OCTETS, jamais sur le nombre de fichiers : neuf petites
     * photos suivies d'une vidéo de 900 Mo annonceraient 90 % alors que
     * l'essentiel du travail reste à faire.
     */
    val pourcentage: Int
        get() = if (octetsTotal <= 0L) 0
                else ((octetsFaits * 100 / octetsTotal).toInt()).coerceIn(0, 100)
}
```

- [ ] **Step 4 : Vérifier que ça passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*AvancementTest*"`
Expected: PASS

- [ ] **Step 5 : Valider par mutation**

Remplacer le calcul par `(fichiersFaits * 100 / fichiersTotal)`, relancer.
Expected: `le_pourcentage_se_calcule_sur_les_octets_pas_sur_les_fichiers`
échoue (90 au lieu de 10). Remettre.

- [ ] **Step 6 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Avancement.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/AvancementTest.kt
git commit -m "feat(avancement): instantane immuable de la progression

Pourcentage calcule sur les OCTETS, jamais sur le nombre de fichiers : neuf
petites photos suivies d'une video de 900 Mo annonceraient 90 % alors que
l'essentiel reste a faire.

Trois phases nommees, dont ANALYSE : les 2 min 08 s pendant lesquelles rien ne
part sur le reseau avaient l'air d'un plantage."
```

---

### Task 6 : Les délais HTTP explicites, et `abandonner`

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Decouverte.kt`
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/ClientServeur.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/FabriqueTest.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/ClientServeurTest.kt`

**Interfaces:**
- Consumes: `Fabrique.client(charge: ChargeAppairage): OkHttpClient` — existant
- Produces: `ClientServeur.abandonner(session: String)` — n'échoue jamais

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `FabriqueTest.kt` :

```kotlin
    @Test fun les_delais_sont_poses_explicitement() {
        // Sans cela, OkHttp applique 10 s de lecture. Le 21/09, le tri d'un
        // commit a demande 1 h 02 : le telephone a raccroche au bout de dix
        // secondes, affiche « echec », et laisse le compteur sur « Jamais
        // sauvegarde » pendant que le serveur rangeait 953 medias.
        val http = Fabrique.client(ChargeAppairage("https://x:8787", "jeton", null))
        assertEquals(10_000, http.connectTimeoutMillis)
        assertEquals(300_000, http.writeTimeoutMillis)
        assertEquals(1_800_000, http.readTimeoutMillis)
    }

    @Test fun les_delais_valent_aussi_pour_le_client_epingle() {
        val http = Fabrique.client(ChargeAppairage("https://x:8787", "jeton", "a".repeat(64)))
        assertEquals(1_800_000, http.readTimeoutMillis)
    }
```

Ajouter à `ClientServeurTest.kt` :

```kotlin
    @Test fun abandonner_previent_le_serveur() {
        val serveur = MockWebServer()
        serveur.enqueue(MockResponse().setBody("""{"supprimes":3,"octets":42}"""))
        serveur.start()
        val c = ClientServeur(serveur.url("/").toString().trimEnd('/'), "jeton",
                              OkHttpClient())
        c.abandonner("a".repeat(32))
        val requete = serveur.takeRequest()
        assertEquals("/sync/abandon", requete.path)
        assertEquals("POST", requete.method)
        serveur.shutdown()
    }

    @Test fun abandonner_ne_leve_jamais() {
        // La route n'existe pas encore sur le serveur (lot serveur), et quand
        // on abandonne c'est souvent PARCE QUE le reseau est tombe. Un echec
        // ici ne doit surtout pas masquer l'arret que l'utilisateur a demande.
        val serveur = MockWebServer()
        serveur.enqueue(MockResponse().setResponseCode(404))
        serveur.start()
        val c = ClientServeur(serveur.url("/").toString().trimEnd('/'), "jeton",
                              OkHttpClient())
        c.abandonner("a".repeat(32))      // ne doit pas lever
        serveur.shutdown()
    }
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*FabriqueTest*" --tests "*ClientServeurTest*"`
Expected: FAIL — les délais valent 10 000 partout, `abandonner` n'existe pas.

- [ ] **Step 3 : Poser les délais**

Dans `Decouverte.kt`, fonction `Fabrique.client`, appliquer les mêmes délais
aux **deux** constructions (avec et sans TLS). Introduire une fonction privée
pour ne pas les écrire en double :

```kotlin
    /**
     * Délais communs aux deux clients.
     *
     * OkHttp applique 10 s par défaut, y compris en lecture. Le 21/09/2026, le
     * `commit` d'une session de 971 fichiers et 14 Go a demandé 1 h 02 : le
     * téléphone a raccroché au bout de dix secondes, affiché « la sauvegarde a
     * échoué » et laissé le compteur sur « Jamais sauvegardé » — pendant que
     * le serveur rangeait tout parfaitement. Une réussite annoncée comme une
     * panne, le contraire exact de ce que la conception garantit.
     *
     * 30 min en lecture ne suffiraient PAS pour un commit monolithique : c'est
     * le découpage en paquets (`synchro.Paquets`) qui borne le travail d'un
     * commit, le délai ne fait que le protéger.
     */
    private fun OkHttpClient.Builder.avecDelais(): OkHttpClient.Builder = this
        .connectTimeout(10, TimeUnit.SECONDS)
        // Une video de 3 Go a 12 Mo/s prend plusieurs minutes a ecrire.
        .writeTimeout(5, TimeUnit.MINUTES)
        .readTimeout(30, TimeUnit.MINUTES)
```

Puis, dans `client(...)`, insérer `.avecDelais()` dans les deux chaînes, juste
avant `.build()` :

```kotlin
        val empreinte = charge.certSha256
            ?: return OkHttpClient.Builder()
                .retryOnConnectionFailure(false)
                .avecDelais()
                .build()
        ...
        return OkHttpClient.Builder()
            .sslSocketFactory(contexte.socketFactory, gestionnaire)
            .hostnameVerifier { _, _ -> true }
            .retryOnConnectionFailure(false)
            .avecDelais()
            .build()
```

Ajouter l'import `java.util.concurrent.TimeUnit` en tête de fichier s'il
manque.

- [ ] **Step 4 : Ajouter `abandonner`**

Dans `ClientServeur.kt`, à côté de `commit` :

```kotlin
    /**
     * Demande au serveur d'oublier une session abandonnée.
     *
     * **N'échoue jamais.** Deux raisons : la route n'existe pas encore côté
     * serveur (lot serveur, issue #30), et quand on abandonne c'est souvent
     * PARCE QUE le réseau est tombé. Un échec ici masquerait l'arrêt que
     * l'utilisateur vient de demander. Le filet, c'est la purge des sessions
     * de plus de 24 h côté serveur.
     */
    fun abandonner(session: String) {
        try {
            val corps = Contrat.json.encodeToString(
                RequeteAbandon.serializer(), RequeteAbandon(session))
            val requete = Request.Builder()
                .url("$base/sync/abandon")
                .header("Authorization", "Bearer $token")
                .post(corps.toRequestBody("application/json".toMediaType()))
                .build()
            http.newCall(requete).execute().close()
        } catch (e: Exception) {
            // Volontairement muet : voir la documentation ci-dessus.
        }
    }
```

Et dans `Contrat.kt`, à la suite de `RequeteCommit` :

```kotlin
/** Corps de POST /sync/abandon (lot serveur, issue #30). */
@Serializable
data class RequeteAbandon(val session: String)
```

Adapter les imports de `ClientServeur.kt` si `toRequestBody` ou `toMediaType`
n'y sont pas déjà — ils le sont pour `commit`, vérifier plutôt que d'ajouter.

- [ ] **Step 5 : Vérifier que ça passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*FabriqueTest*" --tests "*ClientServeurTest*"`
Expected: PASS

- [ ] **Step 6 : Valider par mutation**

Retirer `.avecDelais()` de la seconde chaîne (le client épinglé), relancer.
Expected: `les_delais_valent_aussi_pour_le_client_epingle` échoue. Remettre.

- [ ] **Step 7 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/ \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/reseau/
git commit -m "fix(reseau): poser des delais explicites, generosite au commit

OkHttp applique 10 s par defaut, y compris en lecture. Le 21/09, le commit
d'une session de 971 fichiers et 14 Go a demande 1 h 02 : le telephone a
raccroche au bout de dix secondes, affiche « la sauvegarde a echoue » et
laisse le compteur sur « Jamais sauvegarde » — pendant que le serveur rangeait
953 medias. Une reussite annoncee comme une panne.

30 min de lecture ne suffiraient pas pour un commit monolithique : c'est le
decoupage en paquets qui borne le travail, le delai ne fait que le proteger.

Ajoute aussi abandonner(), qui ne leve JAMAIS : la route n'existe pas encore
cote serveur, et on abandonne souvent parce que le reseau est tombe."
```

---

### Task 7 : L'orchestrateur enchaîne les paquets et rend compte

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Orchestrateur.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/OrchestrateurTest.kt`

**Interfaces:**
- Consumes: `Paquets.decouper`, `Horizons.calculer(..., dejaArretes)`, `Debit`, `Avancement`, `Phase`, `Destination.dossier`, `Serveur`
- Produces:
  - `Orchestrateur(source, serveur, horloge: () -> Long = System::currentTimeMillis, surAvancement: (Avancement) -> Unit = {})`
  - `Orchestrateur.synchroniser(dossiersChoisis: Set<String>, interrompu: () -> Boolean = { false }): Bilan`
  - `Bilan` gagne `val interrompu: Boolean`

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `OrchestrateurTest.kt` (les doubles `SourceMedias` et `Serveur` du
fichier existent déjà ; réutiliser leurs noms) :

```kotlin
    @Test fun chaque_paquet_est_valide_par_son_propre_commit() {
        // Trois medias de 400 octets, paquets de 1000 : 2 paquets, 2 commits.
        // (a 600 octets on obtiendrait TROIS paquets, 600+600 depassant deja 1000.)
        val medias = (1L..3L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 400, it.toDouble() * 1000)
        }
        val serveur = ServeurEspion()
        val bilan = Orchestrateur(SourceFausse(medias), serveur,
                                  taillePaquet = 1000)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(2, serveur.commits.size)
        assertEquals(3, bilan.envoyes)
    }

    @Test fun un_echec_au_premier_paquet_gele_le_dossier_pour_les_suivants() {
        // LE test qui protege les photos. Le media 1 echoue a l'envoi ; les
        // medias 2 et 3, dans un paquet suivant, reussissent. L'horizon de
        // DCIM/Camera ne doit JAMAIS etre transmis, sinon le media 1 ne sera
        // plus jamais propose par le serveur.
        val medias = (1L..3L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = ServeurEspion(echouerSur = setOf("DCIM/Camera/m1.jpg"))
        val bilan = Orchestrateur(SourceFausse(medias), serveur, taillePaquet = 1000)
            .synchroniser(setOf("DCIM/Camera"))
        assertTrue("aucun commit ne doit porter d'horizon pour ce dossier",
            serveur.commits.none { it.containsKey("DCIM/Camera") })
        // Sans cette ligne, le test passerait aussi si le code arretait TOUTE
        // la synchro au premier echec — or un dossier gele ne doit rien
        // interrompre, seul son horizon est fige.
        assertEquals(2, bilan.envoyes)
    }

    @Test fun un_dossier_sain_avance_malgre_l_echec_d_un_autre() {
        val medias = listOf(
            Media(1, "DCIM/Camera", "m1.jpg", 600, 1000.0),
            Media(2, "Pictures/WhatsApp", "w2.jpg", 600, 2000.0),
        )
        val serveur = ServeurEspion(echouerSur = setOf("DCIM/Camera/m1.jpg"))
        Orchestrateur(SourceFausse(medias), serveur, taillePaquet = 1000)
            .synchroniser(setOf("DCIM/Camera", "Pictures/WhatsApp"))
        assertTrue(serveur.commits.any { it.containsKey("Pictures/WhatsApp") })
    }

    @Test fun une_interruption_arrete_net_et_garde_les_paquets_valides() {
        val medias = (1L..4L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = ServeurEspion()
        var appels = 0
        val bilan = Orchestrateur(SourceFausse(medias), serveur, taillePaquet = 1000)
            // Seuil 3 et non 2 : interrompu() est appele une fois en tete de
            // chaque paquet PUIS une fois par media. A 2, l'arret tomberait en
            // tete du paquet 2, sans jamais entrer dans la boucle d'envoi —
            // donc sans abandon a constater par le test suivant.
            .synchroniser(setOf("DCIM/Camera"), interrompu = { appels++ >= 3 })
        assertTrue(bilan.interrompu)
        // Le compte exact, et pas `isNotEmpty()` : ce dernier passerait aussi
        // si le paquet abandonne etait commite lui aussi.
        assertEquals(1, serveur.commits.size)
    }

    @Test fun une_interruption_previent_le_serveur_du_paquet_abandonne() {
        val medias = (1L..4L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = ServeurEspion()
        var appels = 0
        Orchestrateur(SourceFausse(medias), serveur, taillePaquet = 1000)
            .synchroniser(setOf("DCIM/Camera"), interrompu = { appels++ >= 3 })
        assertTrue(serveur.abandons.isNotEmpty())
    }

    @Test fun l_avancement_est_publie_avec_la_destination_prevue() {
        val medias = listOf(
            Media(1, "DCIM/Camera", "v.mp4", 600, 1759000102.0, estVideo = true))
        val vus = mutableListOf<Avancement>()
        Orchestrateur(SourceFausse(medias), ServeurEspion(), taillePaquet = 1000,
                      surAvancement = { vus += it })
            .synchroniser(setOf("DCIM/Camera"))
        assertTrue("une phase d'analyse doit etre publiee",
                   vus.any { it.phase == Phase.ANALYSE })
        assertTrue("la destination prevue doit apparaitre",
            vus.any { it.destinationPrevue == "Videos/2025/09 SEPTEMBRE" })
    }

    @Test fun l_avancement_final_annonce_le_total_en_octets() {
        val medias = (1L..3L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val vus = mutableListOf<Avancement>()
        Orchestrateur(SourceFausse(medias), ServeurEspion(), taillePaquet = 1000,
                      surAvancement = { vus += it })
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(1800L, vus.last().octetsTotal)
        // octetsTotal est calcule une fois et ne bouge jamais : sans cette
        // seconde assertion, le test passerait meme si la progression n'etait
        // jamais incrementee.
        assertEquals(1800L, vus.last().octetsFaits)
    }

    @Test fun une_revocation_n_est_pas_une_interruption_demandee() {
        // Couvre la sortie de TETE de boucle. Une revocation doit donner
        // revoque=true et interrompu=false, quel que soit le paquet ou elle
        // tombe.
        val medias = (1L..4L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val bilan = Orchestrateur(
            SourceFausse(medias),
            ServeurEspion(revoquerSur = setOf("DCIM/Camera/m1.jpg")),
            taillePaquet = 1000,
        ).synchroniser(setOf("DCIM/Camera"))
        assertTrue(bilan.revoque)
        assertFalse("une revocation n'est pas un arret demande par l'utilisateur",
                    bilan.interrompu)
    }

    @Test fun le_bilan_serveur_cumule_tous_les_paquets() {
        // Un paquet qui echoue au rangement ne doit pas etre efface par un
        // paquet suivant qui reussit.
        val medias = (1L..2L).map {
            Media(it, "DCIM/Camera", "m$it.jpg", 600, it.toDouble() * 1000)
        }
        val serveur = ServeurEspion(erreursParCommit = listOf(1.0, 0.0))
        val bilan = Orchestrateur(SourceFausse(medias), serveur, taillePaquet = 1000)
            .synchroniser(setOf("DCIM/Camera"))
        assertEquals(1.0, bilan.bilanServeur["errors"]!!, 0.0)
    }
```

Ajouter en haut du fichier les doubles manquants, s'ils n'y sont pas déjà sous
ces noms — sinon adapter les tests aux noms existants :

```kotlin
private class SourceFausse(private val medias: List<Media>) : SourceMedias {
    override fun lister() = medias
    override fun ouvrir(media: Media) =
        java.io.ByteArrayInputStream(ByteArray(media.taille.toInt()))
}

private class ServeurEspion(
    private val echouerSur: Set<String> = emptySet(),
    private val revoquerSur: Set<String> = emptySet(),
    /** Valeur de `errors` rendue par le 1er commit, le 2e, etc. */
    private val erreursParCommit: List<Double> = emptyList(),
) : Serveur {
    val commits = mutableListOf<Map<String, Double>>()
    val abandons = mutableListOf<String>()
    private var n = 0

    override fun horizon() = ReponseHorizon(depuis = null, dossiers = emptyMap())
    override fun plan(fichiers: List<FichierPlan>) =
        ReponsePlan(session = "%032x".format(++n), needed = fichiers.map { it.hash })
    override fun envoyer(session: String, chemin: String, flux: java.io.InputStream,
                         taille: Long, empreinteAttendue: String) = when (chemin) {
        in revoquerSur -> ResultatEnvoi.REVOQUE
        in echouerSur -> ResultatEnvoi.ECHEC
        else -> ResultatEnvoi.OK
    }
    override fun commit(session: String, horizons: Map<String, Double>):
            Map<String, Double> {
        val erreurs = erreursParCommit.getOrElse(commits.size) { 0.0 }
        commits += horizons
        return mapOf("sorted" to 1.0, "errors" to erreurs)
    }
    override fun abandonner(session: String) { abandons += session }
}
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*OrchestrateurTest*"`
Expected: FAIL — `taillePaquet`, `surAvancement`, `interrompu`,
`Bilan.interrompu` et `Serveur.abandonner` n'existent pas.

- [ ] **Step 3 : Étendre l'interface `Serveur` et `Bilan`**

Dans `Orchestrateur.kt` :

```kotlin
interface Serveur {
    fun horizon(): ReponseHorizon
    fun plan(fichiers: List<FichierPlan>): ReponsePlan
    fun envoyer(session: String, chemin: String, flux: InputStream, taille: Long,
                empreinteAttendue: String): ResultatEnvoi
    fun commit(session: String, horizons: Map<String, Double>): Map<String, Double>
    /** Oublie une session abandonnée. N'échoue jamais — voir ClientServeur. */
    fun abandonner(session: String)
}

data class Bilan(
    val envoyes: Int,
    val refuses: Int,
    val echecs: Int,
    val revoque: Boolean,
    val bilanServeur: Map<String, Double>,
    /** L'utilisateur a demandé l'arrêt. Ce n'est PAS un échec, et ça ne doit
     *  ni déclencher d'alerte ni provoquer de reprise automatique. */
    val interrompu: Boolean = false,
)
```

Compléter `Adaptateur` dans `Decouverte.kt` :

```kotlin
    override fun abandonner(session: String) = c.abandonner(session)
```

- [ ] **Step 4 : Réécrire `synchroniser`**

Remplacer le corps de la classe `Orchestrateur` :

```kotlin
class Orchestrateur(
    private val source: SourceMedias,
    private val serveur: Serveur,
    private val taillePaquet: Long = Paquets.TAILLE_MAX_OCTETS,
    private val horloge: () -> Long = System::currentTimeMillis,
    private val surAvancement: (Avancement) -> Unit = {},
) {
    fun synchroniser(
        dossiersChoisis: Set<String>,
        interrompu: () -> Boolean = { false },
    ): Bilan {
        val etat = serveur.horizon()
        val depuis = etat.depuis?.let { jourVersSecondes(it) }
        val tous = source.lister()
        val candidats = Selection.candidats(tous, dossiersChoisis, etat.dossiers, depuis)
        val lots = Paquets.decouper(candidats, taillePaquet)

        val octetsTotal = candidats.sumOf { it.taille }
        val dossiersVus = tous.groupingBy { it.dossier }.eachCount()
        val debit = Debit()
        debit.ajouter(0L, horloge())

        var envoyes = 0; var refuses = 0; var echecs = 0
        var revoque = false; var arrete = false
        var octetsFaits = 0L; var fichiersFaits = 0
        // L'ensemble des dossiers geles traverse TOUS les paquets. Le remettre
        // a zero a chaque paquet ferait avancer l'horizon par-dessus un
        // fichier en echec du paquet precedent : perte definitive.
        var arretes = emptySet<String>()
        var bilanServeur = emptyMap<String, Double>()
        var paquetsValides = 0

        fun publier(phase: Phase, media: Media? = null) {
            surAvancement(Avancement(
                phase = phase,
                fichiersFaits = fichiersFaits, fichiersTotal = candidats.size,
                octetsFaits = octetsFaits, octetsTotal = octetsTotal,
                octetsParSeconde = debit.octetsParSeconde(),
                secondesRestantes = debit.secondesRestantes(octetsTotal - octetsFaits),
                mediaEnCours = media?.chemin,
                tailleEnCours = media?.taille,
                destinationPrevue = media?.let {
                    Destination.dossier(it.instant, it.estVideo, it.chemin)
                },
                paquetCourant = paquetsValides + 1,
                paquetsValides = paquetsValides,
                dossiersVus = dossiersVus,
            ))
        }

        publier(Phase.ANALYSE)

        for (lot in lots) {
            // Les deux sorties sont SEPAREES. Les confondre ferait declarer
            // `interrompu` une revocation — et de facon non deterministe, selon
            // qu'elle tombe ou non sur le dernier paquet. Le lot promet cinq
            // pannes et cinq messages distincts ; un ecran qui teste
            // `interrompu` avant `revoque` annoncerait « arret demande » pour
            // un appareil revoque.
            if (revoque) break
            if (interrompu()) { arrete = true; break }

            // --- analyse : empreintes du paquet SEULEMENT ---
            val envois = mutableListOf<Envoi>()
            val empreintes = mutableMapOf<Media, String>()
            val lisibles = mutableListOf<Media>()
            for (media in lot) {
                publier(Phase.ANALYSE, media)
                try {
                    empreintes[media] = Empreintes.sha256(source.ouvrir(media))
                    lisibles += media
                } catch (e: Exception) {
                    // Ecarte du lot, mais INSCRIT comme echec : sans cette
                    // entree, Horizons.calculer ne le verrait pas, l'horizon
                    // sauterait par-dessus lui, et il serait perdu.
                    echecs++
                    envois += Envoi(media.dossier, media.instant, Issue.ECHEC)
                    // La progression avance MEME sur un echec de lecture : sans
                    // cela la barre se bloquerait sous 100 % sans jamais
                    // l'atteindre, alors qu'un media disparu entre le listing et
                    // l'envoi est un cas banal sur un telephone.
                    fichiersFaits++; octetsFaits += media.taille
                }
            }

            val reponse = serveur.plan(lisibles.map {
                FichierPlan(it.chemin, it.taille, empreintes.getValue(it))
            })
            val reclamees = reponse.needed.toSet()

            // --- envoi ---
            var abandonne = false
            for (media in lisibles) {
                if (interrompu()) { abandonne = true; arrete = true; break }
                publier(Phase.ENVOI, media)
                val empreinte = empreintes.getValue(media)
                if (empreinte !in reclamees) {
                    envois += Envoi(media.dossier, media.instant, Issue.CONFIRME)
                    fichiersFaits++; octetsFaits += media.taille
                    debit.ajouter(octetsFaits, horloge())
                    continue
                }
                val issue = try {
                    when (serveur.envoyer(reponse.session, media.chemin,
                                          source.ouvrir(media), media.taille, empreinte)) {
                        ResultatEnvoi.OK -> { envoyes++; Issue.CONFIRME }
                        ResultatEnvoi.EXTENSION_REFUSEE -> { refuses++; Issue.IGNORE }
                        ResultatEnvoi.ECHEC -> { echecs++; Issue.ECHEC }
                        ResultatEnvoi.REVOQUE -> { revoque = true; null }
                    }
                } catch (e: Exception) {
                    echecs++
                    Issue.ECHEC
                }
                if (issue == null) break          // revoque : on arrete la boucle
                envois += Envoi(media.dossier, media.instant, issue)
                fichiersFaits++; octetsFaits += media.taille
                debit.ajouter(octetsFaits, horloge())
            }

            if (abandonne) {
                // Arret immediat : le paquet en cours est jete. On previent au
                // mieux ; la purge des 24 h cote serveur est le filet.
                serveur.abandonner(reponse.session)
                break
            }

            // --- rangement ---
            publier(Phase.RANGEMENT)
            val resultat = Horizons.calculer(envois, arretes)
            arretes = resultat.arretes
            val rendu = serveur.commit(reponse.session, resultat.horizons)
            // CUMULE, jamais ecrase. Avec N commits, ne garder que le dernier
            // ferait declarer reussie une synchro dont le 3e paquet a echoue au
            // rangement : EtatSynchro.estUneReussite lit `errors` et avancerait
            // le compteur de jours, la banniere « le serveur n'a pas reussi a
            // ranger N medias » ne s'afficherait jamais, et l'ecran de detail
            // montrerait le chiffre du dernier paquet au lieu du total.
            bilanServeur = (bilanServeur.keys + rendu.keys).associateWith {
                (bilanServeur[it] ?: 0.0) + (rendu[it] ?: 0.0)
            }
            paquetsValides++
        }

        publier(Phase.RANGEMENT)
        return Bilan(envoyes, refuses, echecs, revoque, bilanServeur, arrete)
    }

    /**
     * « 2026-09-01 » → secondes. Le champ `depuis` du contrat est une DATE ISO
     * nue, sans fuseau : il faut donc choisir a quel instant elle commence.
     *
     * On l'ancre a UTC+14, c'est-a-dire l'instant le plus PRECOCE auquel cette
     * date calendaire commence ou que ce soit sur Terre. Interpreter la date
     * dans le fuseau courant du telephone paraitrait plus naturel, mais un
     * changement de fuseau entre l'appairage et la synchro decalerait le
     * plancher — et vers l'ouest il reculerait trop tard, sautant en silence
     * des medias autour de la date d'appairage. Le sens choisi ici ne peut que
     * reproposer quelques heures de trop, que l'anti-doublon ecarte sans les
     * transferer.
     */
    private fun jourVersSecondes(jour: String): Double =
        java.time.LocalDate.parse(jour)
            .atStartOfDay(java.time.ZoneOffset.ofHours(14))
            .toEpochSecond().toDouble()
}
```

Ajouter les imports nécessaires en tête de `Orchestrateur.kt` :
`import fr.izquierdo.phototheque.medias.Empreintes`,
`import fr.izquierdo.phototheque.medias.Media`.

- [ ] **Step 5 : Vérifier que tout passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`
Expected: PASS — y compris les tests d'orchestrateur déjà présents. Si l'un
d'eux échoue parce que son double `Serveur` n'implémente pas `abandonner`, lui
ajouter `override fun abandonner(session: String) {}`.

- [ ] **Step 6 : Valider par mutation**

Remplacer `Horizons.calculer(envois, arretes)` par `Horizons.calculer(envois)`,
relancer.
Expected: `un_echec_au_premier_paquet_gele_le_dossier_pour_les_suivants`
échoue. **C'est le test le plus important du lot** : s'il ne tombe pas, c'est
qu'il ne teste rien. Remettre.

- [ ] **Step 7 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Orchestrateur.kt \
        android/app/src/main/kotlin/fr/izquierdo/phototheque/reseau/Decouverte.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/OrchestrateurTest.kt
git commit -m "feat(orchestrateur): enchainer les paquets, publier l'avancement, obeir a l'arret

Un paquet = un plan, ses envois, un commit. L'horizon avance donc en cours de
route au lieu de tout jouer sur un commit final — 1 h 02 le 21/09.

Le point sensible : l'ensemble des dossiers geles traverse TOUS les paquets.
Le remettre a zero a chaque paquet ferait avancer l'horizon par-dessus un
fichier en echec du paquet precedent, qui ne serait plus jamais propose. Perte
definitive et silencieuse. Un test dedie le verrouille.

L'arret est immediat : le paquet en cours est jete et le serveur prevenu au
mieux. Les paquets deja valides restent acquis."
```

---

### Task 8 : Le service de premier plan et le travail planifié

C'est la tâche la moins testable en unitaire : elle est surtout de la plomberie
Android. On teste ce qui se teste — la décision de reprise — et on valide le
reste sur le téléphone (tâche 10).

**Files:**
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/ServiceSynchro.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/TravailSynchro.kt`
- Create: `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Reprise.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/RepriseTest.kt`
- Modify: `android/app/build.gradle.kts`
- Modify: `android/app/src/main/AndroidManifest.xml`

**Interfaces:**
- Consumes: `Orchestrateur`, `Avancement`, `Bilan`
- Produces:
  - `Reprise.faut_il_relancer(bilan: Bilan): Boolean`
  - `TravailSynchro.lancer(context: Context)`, `TravailSynchro.interrompre(context: Context)`
  - `TravailSynchro.avancement: StateFlow<Avancement?>`

- [ ] **Step 1 : Écrire le test de la décision de reprise**

`android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/RepriseTest.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RepriseTest {

    private fun bilan(echecs: Int = 0, revoque: Boolean = false,
                      interrompu: Boolean = false) =
        Bilan(envoyes = 0, refuses = 0, echecs = echecs, revoque = revoque,
              bilanServeur = emptyMap(), interrompu = interrompu)

    @Test fun une_synchro_reussie_ne_se_relance_pas() {
        assertFalse(Reprise.fautIlRelancer(bilan()))
    }

    @Test fun un_echec_reseau_se_relance() {
        assertTrue(Reprise.fautIlRelancer(bilan(echecs = 3)))
    }

    @Test fun un_arret_demande_ne_se_relance_JAMAIS() {
        // Un arret que l'utilisateur a demande ne doit pas se defaire tout
        // seul : ce serait le contraire de ce qu'il vient de demander.
        assertFalse(Reprise.fautIlRelancer(bilan(echecs = 5, interrompu = true)))
    }

    @Test fun une_revocation_ne_se_relance_pas() {
        // Seul un nouveau QR debloque : relancer tournerait en boucle.
        assertFalse(Reprise.fautIlRelancer(bilan(echecs = 2, revoque = true)))
    }
}
```

- [ ] **Step 2 : Vérifier qu'il échoue**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*RepriseTest*"`
Expected: FAIL — `Reprise` n'existe pas.

- [ ] **Step 3 : Implémenter la décision**

`android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Reprise.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

/**
 * Faut-il demander à Android de relancer la synchronisation plus tard ?
 *
 * Isolé du `Worker` pour être testable sur la JVM : la logique tient en trois
 * lignes, mais se tromper ici donne soit une boucle infinie, soit une
 * sauvegarde qui reste en plan pendant des semaines.
 */
object Reprise {

    fun fautIlRelancer(bilan: Bilan): Boolean = when {
        // L'utilisateur a demande l'arret. Le defaire tout seul serait le
        // contraire de ce qu'il vient de demander.
        bilan.interrompu -> false
        // Seul un nouveau QR debloque : relancer tournerait en boucle.
        bilan.revoque -> false
        else -> bilan.echecs > 0
    }
}
```

- [ ] **Step 4 : Vérifier que ça passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*RepriseTest*"`
Expected: PASS

- [ ] **Step 5 : Ajouter les dépendances et les permissions**

Dans `android/app/build.gradle.kts`, à la suite des `implementation` :

```kotlin
    implementation("androidx.work:work-runtime-ktx:2.9.0")
```

Dans `android/app/src/main/AndroidManifest.xml`, avant `<application>` :

```xml
    <!-- Sans ce service, la synchro vit dans le viewModelScope de l'activite :
         ecran eteint, Android la tue, aucun commit n'est emis et les Go deja
         montes restent dans le depot temporaire du NUC sans etre ranges.
         Constate le 21/09/2026. -->
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
    <!-- Android 13+ : sans elle, la notification d'avancement n'apparait pas,
         et l'utilisateur n'a plus AUCUN moyen de voir ou d'arreter une synchro
         qui tourne ecran eteint. -->
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
```

**Ne PAS déclarer de `<service>` dans le manifeste.** `ServiceSynchro` est un
`object` qui fabrique une notification, pas une `Service` Android : c'est
`WorkManager` qui porte le service de premier plan, avec le sien
(`SystemForegroundService`), déjà déclaré par la bibliothèque. Ajouter une
entrée `<service android:name=".synchro.ServiceSynchro">` ferait échouer
l'installation ou le lancement.

- [ ] **Step 6 : Écrire le service et le travail**

`android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/TravailSynchro.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import android.content.Context
import androidx.work.*
import fr.izquierdo.phototheque.appairage.Coffre
import fr.izquierdo.phototheque.medias.Depot
import fr.izquierdo.phototheque.reseau.Fabrique
import fr.izquierdo.phototheque.reseau.ServeurRevoqueException
import fr.izquierdo.phototheque.ui.Memoire
import fr.izquierdo.phototheque.ui.EtatSynchro
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * La synchronisation, exécutée par Android et non par l'écran.
 *
 * `WorkManager` garantit trois choses que le `viewModelScope` ne donnait pas :
 * le travail survit à la fermeture de l'application, il n'est lancé que
 * lorsqu'un réseau est disponible, et il est relancé tout seul après une
 * coupure subie.
 */
class TravailSynchro(
    context: Context,
    parametres: WorkerParameters,
) : CoroutineWorker(context, parametres) {

    override suspend fun doWork(): Result {
        val contexte = applicationContext
        val charge = Coffre(contexte).charge() ?: return Result.success()
        val depot = Depot(contexte)

        setForeground(ServiceSynchro.information(contexte, Avancement()))

        val serveur = try {
            Fabrique.serveur(contexte, charge)
        } catch (e: ServeurRevoqueException) {
            Coffre(contexte).oublier()
            _avancement.value = null
            return Result.success()
        } ?: run {
            // Pas a la maison : ce n'est PAS une panne. On ne reessaie pas en
            // boucle, la contrainte reseau de WorkManager s'en charge.
            _avancement.value = null
            return Result.success()
        }

        val bilan = try {
            Orchestrateur(
                depot, serveur,
                surAvancement = { vu ->
                    _avancement.value = vu
                    setForegroundAsync(ServiceSynchro.information(contexte, vu))
                },
            ).synchroniser(DOSSIERS_SAUVEGARDES, interrompu = { isStopped })
        } catch (e: ServeurRevoqueException) {
            Coffre(contexte).oublier()
            _avancement.value = null
            return Result.success()
        } catch (e: Exception) {
            _avancement.value = null
            return Result.retry()
        }

        if (EtatSynchro.estUneReussite(bilan, depot.accesRefuse())) {
            Memoire(contexte).enregistrerReussite(System.currentTimeMillis())
        }
        _dernierBilan.value = bilan
        _avancement.value = null
        return if (Reprise.fautIlRelancer(bilan)) Result.retry() else Result.success()
    }

    companion object {
        /** Lot 1 : dossiers en dur. L'écran de choix arrive au lot 2. */
        val DOSSIERS_SAUVEGARDES =
            setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp")

        private const val NOM = "synchro"

        private val _avancement = MutableStateFlow<Avancement?>(null)
        /** null quand aucune synchronisation ne tourne. */
        val avancement = _avancement.asStateFlow()

        private val _dernierBilan = MutableStateFlow<Bilan?>(null)
        val dernierBilan = _dernierBilan.asStateFlow()

        fun lancer(context: Context) {
            val demande = OneTimeWorkRequestBuilder<TravailSynchro>()
                .setConstraints(Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL,
                                    WorkRequest.MIN_BACKOFF_MILLIS,
                                    java.util.concurrent.TimeUnit.MILLISECONDS)
                .build()
            // KEEP et non REPLACE : deux appuis sur le bouton ne doivent pas
            // faire tourner deux synchros en parallele sur la meme
            // bibliotheque.
            WorkManager.getInstance(context)
                .enqueueUniqueWork(NOM, ExistingWorkPolicy.KEEP, demande)
        }

        fun interrompre(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(NOM)
        }
    }
}
```

`android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/ServiceSynchro.kt` :

```kotlin
package fr.izquierdo.phototheque.synchro

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.ForegroundInfo
import fr.izquierdo.phototheque.MainActivity
import fr.izquierdo.phototheque.R

/**
 * La notification qui accompagne une synchronisation en arrière-plan.
 *
 * Android l'exige pour un service de premier plan, mais elle a ici un vrai
 * rôle : écran éteint, c'est le SEUL endroit où l'avancement est visible, et
 * le seul endroit d'où l'on peut arrêter sans rouvrir l'application.
 *
 * Le nom du fichier en cours n'y figure pas : il change toutes les secondes et
 * ferait clignoter la notification en permanence.
 */
object ServiceSynchro {

    private const val CANAL = "synchro"
    private const val ID = 1

    const val ACTION_INTERROMPRE = "fr.izquierdo.phototheque.INTERROMPRE"

    fun information(context: Context, avancement: Avancement): ForegroundInfo {
        creerCanal(context)

        val titre = when (avancement.phase) {
            Phase.ANALYSE -> "Analyse ${avancement.fichiersFaits} / ${avancement.fichiersTotal}"
            Phase.ENVOI -> "Sauvegarde ${avancement.fichiersFaits} / ${avancement.fichiersTotal}"
            Phase.RANGEMENT -> "Rangement sur le serveur…"
        }
        val vitesse = avancement.octetsParSeconde
            ?.let { " · %.1f Mo/s".format(it / 1_048_576.0) } ?: ""

        // getBroadcast et NON getActivity : la conception veut qu'on puisse
        // arreter sans rouvrir l'application, et un PendingIntent d'activite
        // ne delivre meme pas son intent quand la tache existe deja en
        // arriere-plan — le systeme se contente de la ramener au premier plan.
        val arret = PendingIntent.getBroadcast(
            context, 0,
            Intent(context, RecepteurInterruption::class.java)
                .setAction(ACTION_INTERROMPRE),
            PendingIntent.FLAG_IMMUTABLE)

        val notification = NotificationCompat.Builder(context, CANAL)
            .setContentTitle(titre)
            .setContentText("${avancement.pourcentage} %$vitesse")
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setOngoing(true)
            .setProgress(100, avancement.pourcentage, avancement.octetsTotal == 0L)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel,
                       "Interrompre", arret)
            .build()

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q)
            ForegroundInfo(ID, notification,
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else ForegroundInfo(ID, notification)
    }

    private fun creerCanal(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val gestionnaire = context.getSystemService(NotificationManager::class.java)
        // IMPORTANCE_LOW : visible et persistante, mais sans son ni vibration.
        // Une sauvegarde d'une heure qui sonne serait desinstallee le jour meme.
        gestionnaire.createNotificationChannel(NotificationChannel(
            CANAL, "Sauvegarde en cours", NotificationManager.IMPORTANCE_LOW))
    }
}
```

Retirer l'import `fr.izquierdo.phototheque.R` s'il n'est pas utilisé (aucune
ressource propre n'est référencée ici, les icônes viennent de `android.R`).

- [ ] **Step 7 : Vérifier que tout compile et que les tests passent**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 8 : Valider par mutation**

Dans `Reprise.fautIlRelancer`, remplacer `bilan.interrompu -> false` par
`bilan.interrompu -> true`, relancer.
Expected: `un_arret_demande_ne_se_relance_JAMAIS` échoue. Remettre.

- [ ] **Step 9 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/ \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/RepriseTest.kt \
        android/app/build.gradle.kts android/app/src/main/AndroidManifest.xml
git commit -m "feat(synchro): service de premier plan et WorkManager, poser le telephone et l'oublier

La synchro vivait dans le viewModelScope de l'activite : ecran eteint, Android
la tuait, aucun commit n'etait emis, et les Go deja montes restaient dans le
depot temporaire du NUC sans etre ranges ni purges.

Notification persistante avec chiffres, barre et bouton Interrompre : ecran
eteint, c'est le seul endroit ou l'avancement est visible et le seul d'ou l'on
peut arreter. IMPORTANCE_LOW — une sauvegarde d'une heure qui sonne serait
desinstallee le jour meme.

Reprise automatique apres une coupure subie, JAMAIS apres un arret demande ni
apres une revocation, qui tournerait en boucle. La decision est isolee dans
Reprise pour etre testable."
```

---

### Task 9 : L'écran d'avancement et la navigation

**Files:**
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Ecrans.kt`
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/ModeleAccueil.kt`
- Modify: `android/app/src/main/kotlin/fr/izquierdo/phototheque/MainActivity.kt`
- Test: `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/LisibleTest.kt` *(créé)*

**Interfaces:**
- Consumes: `Avancement`, `Phase`, `TravailSynchro.avancement`
- Produces: `Lisible.octets(n: Long): String`, `Lisible.duree(secondes: Long): String`, `EcranAvancement(avancement: Avancement, surInterrompre: () -> Unit)`

- [ ] **Step 1 : Écrire le test des formats qui échoue**

`android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/LisibleTest.kt` :

```kotlin
package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class LisibleTest {

    @Test fun les_octets_se_lisent_en_francais() {
        assertEquals("512 o", Lisible.octets(512))
        assertEquals("1,0 Ko", Lisible.octets(1024))
        assertEquals("29,0 Mo", Lisible.octets(29L * 1024 * 1024))
        assertEquals("12,5 Go", Lisible.octets((12.5 * 1024 * 1024 * 1024).toLong()))
    }

    @Test fun une_duree_courte_se_dit_en_secondes() {
        assertEquals("45 s", Lisible.duree(45))
    }

    @Test fun une_duree_moyenne_se_dit_en_minutes() {
        assertEquals("18 min", Lisible.duree(18 * 60 + 20))
    }

    @Test fun une_duree_longue_se_dit_en_heures_et_minutes() {
        // Le 21/09, le rangement a pris 1 h 02 : « 62 min » serait illisible.
        assertEquals("1 h 02", Lisible.duree(62 * 60))
    }

    @Test fun une_duree_nulle_ne_dit_pas_zero_seconde() {
        assertEquals("moins d'une minute", Lisible.duree(0))
    }
}
```

- [ ] **Step 2 : Vérifier qu'il échoue**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*LisibleTest*"`
Expected: FAIL — `Lisible` n'existe pas.

- [ ] **Step 3 : Implémenter les formats**

Créer `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Lisible.kt` :

```kotlin
package fr.izquierdo.phototheque.ui

/**
 * Mise en forme des nombres pour l'écran. Séparée des composables pour être
 * testable sur la JVM : un « ~ Infinity min » affiché en production ne se
 * rattrape pas.
 */
object Lisible {

    fun octets(n: Long): String {
        if (n < 1024) return "$n o"
        var x = n.toDouble()
        for (unite in listOf("Ko", "Mo", "Go", "To")) {
            x /= 1024.0
            if (x < 1024.0) return String.format("%.1f %s", x, unite).replace('.', ',')
        }
        return String.format("%.1f Po", x).replace('.', ',')
    }

    fun duree(secondes: Long): String = when {
        secondes < 60 -> if (secondes <= 0) "moins d'une minute" else "$secondes s"
        secondes < 3600 -> "${secondes / 60} min"
        else -> String.format("%d h %02d", secondes / 3600, (secondes % 3600) / 60)
    }
}
```

- [ ] **Step 4 : Vérifier que ça passe**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*LisibleTest*"`
Expected: PASS

Note sur la virgule : `String.format` suit la locale de la machine. Sur une
JVM française il produit déjà « 1,0 », sur une JVM anglaise « 1.0 » — le
`.replace('.', ',')` rend le résultat identique dans les deux cas, et c'est
voulu : sans lui, le test passerait sur le poste du mainteneur et tomberait
sur une autre machine.

- [ ] **Step 5 : Écrire l'écran d'avancement**

Ajouter à `Ecrans.kt` :

```kotlin
/**
 * L'écran pendant une synchronisation — maquette B, « tout à l'écran ».
 *
 * L'accueil ne renvoie pas vers cet écran : il en DEVIENT un. Aucune
 * navigation à faire pour voir ce qui se passe.
 */
@Composable
fun EcranAvancement(avancement: Avancement, surInterrompre: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
           horizontalAlignment = Alignment.CenterHorizontally) {

        Text(when (avancement.phase) {
                 Phase.ANALYSE -> "Analyse en cours"
                 Phase.ENVOI -> "Sauvegarde en cours"
                 Phase.RANGEMENT -> "Rangement sur le serveur"
             },
             style = MaterialTheme.typography.titleLarge)

        Spacer(Modifier.height(12.dp))
        Text("${avancement.fichiersFaits} / ${avancement.fichiersTotal}",
             style = MaterialTheme.typography.headlineMedium)
        Text("${Lisible.octets(avancement.octetsFaits)} sur " +
             Lisible.octets(avancement.octetsTotal),
             style = MaterialTheme.typography.bodyMedium)

        Spacer(Modifier.height(12.dp))
        // Barre DETERMINEE des qu'on connait le total : une barre qui tourne
        // sans fin pendant une heure ne dit rien.
        if (avancement.octetsTotal > 0L)
            LinearProgressIndicator(progress = { avancement.pourcentage / 100f },
                                    modifier = Modifier.fillMaxWidth())
        else LinearProgressIndicator(Modifier.fillMaxWidth())

        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(avancement.octetsParSeconde
                     ?.let { "${Lisible.octets(it.toLong())}/s" } ?: "—")
            Text(avancement.secondesRestantes?.let { "~ ${Lisible.duree(it)}" } ?: "—")
        }

        avancement.mediaEnCours?.let { chemin ->
            Spacer(Modifier.height(20.dp))
            Text("Fichier en cours", style = MaterialTheme.typography.labelMedium)
            Text(chemin, style = MaterialTheme.typography.bodySmall)
            avancement.tailleEnCours?.let {
                Text(Lisible.octets(it), style = MaterialTheme.typography.bodySmall)
            }
            avancement.destinationPrevue?.let {
                Text("→ $it", style = MaterialTheme.typography.bodySmall)
            }
        }

        Spacer(Modifier.height(20.dp))
        Text("Paquet ${avancement.paquetCourant} · " +
             "${avancement.paquetsValides} validés",
             style = MaterialTheme.typography.labelMedium)

        // Repond a « je sais meme pas quel dossier ca synchronise », sans
        // avoir a ouvrir un autre ecran.
        Spacer(Modifier.height(8.dp))
        Text("Dossiers : " + TravailSynchro.DOSSIERS_SAUVEGARDES.joinToString(", "),
             style = MaterialTheme.typography.bodySmall)
        // Pas de garde sur `isNotEmpty()` : elle ne protegerait de rien —
        // l'orchestrateur calcule la carte AVANT la premiere publication, donc
        // tout Avancement publie a deja regarde — et elle masquerait le cas ou
        // les trois dossiers suivis sont absents.
        val absents = TravailSynchro.DOSSIERS_SAUVEGARDES - avancement.dossiersVus.keys
        if (absents.isNotEmpty()) {
            Text("Introuvables sur ce téléphone : ${absents.joinToString(", ")}",
                 color = MaterialTheme.colorScheme.error,
                 style = MaterialTheme.typography.bodySmall)
        }

        Spacer(Modifier.height(24.dp))
        OutlinedButton(onClick = surInterrompre) { Text("Interrompre") }
    }
}
```

Ajouter en tête de `Ecrans.kt` les imports manquants :
`androidx.compose.foundation.layout.Arrangement`,
`androidx.compose.foundation.layout.Row`,
`androidx.compose.foundation.rememberScrollState`,
`androidx.compose.foundation.verticalScroll`,
`androidx.compose.material3.OutlinedButton`,
`fr.izquierdo.phototheque.synchro.Avancement`,
`fr.izquierdo.phototheque.synchro.Phase`,
`fr.izquierdo.phototheque.synchro.TravailSynchro`.

- [ ] **Step 6 : Brancher le modèle sur le travail**

Dans `ModeleAccueil.kt`, remplacer `synchroniser()` par un simple appel au
travail, et exposer l'avancement :

```kotlin
    /** L'avancement publié par le travail de fond, null quand rien ne tourne. */
    val avancement = TravailSynchro.avancement

    /**
     * Demande une synchronisation à Android. Le travail lui survit : ce modèle
     * de vue ne l'exécute plus, il l'observe.
     */
    fun synchroniser() {
        if (coffre.charge() == null) return
        rafraichirPermissions()
        TravailSynchro.lancer(getApplication())
    }

    fun interrompre() {
        TravailSynchro.interrompre(getApplication())
    }
```

**Supprimer aussi `ModeleAccueil.dossiersSauvegardes`** : la liste vit désormais
dans `TravailSynchro.DOSSIERS_SAUVEGARDES`, et deux sources de vérité pour les
dossiers suivis finiraient par diverger — l'écran afficherait alors une liste
que la synchronisation n'utilise pas.

Supprimer de `ModeleAccueil` l'ancien bloc `viewModelScope.launch { … }` et les
imports devenus inutiles (`Dispatchers`, `launch`, `Orchestrateur`, `Fabrique`,
`ServeurRevoqueException`). Ajouter, dans le bloc `init`, une observation du
dernier bilan :

```kotlin
        viewModelScope.launch {
            TravailSynchro.derniereIssue.collect { issue ->
                if (issue == null) return@collect
                // Les CINQ pannes passent par ici. Ne lire que `bilan`
                // laisserait trois d'entre elles sans message : un serveur
                // introuvable, une revocation levee avant tout bilan, et une
                // panne generique sortent toutes AVANT qu'un bilan existe.
                val base = issue.bilan?.let {
                    _etat.value.apresSynchro(
                        it,
                        accesPartiel = depot.accesPartiel(),
                        accesRefuse = depot.accesRefuse(),
                        derniereReussiteMs = memoire.derniereReussiteMs(),
                    )
                } ?: _etat.value.copy(
                    // Relues ici aussi : sans elles, une permission retiree en
                    // pleine synchro sortirait en panne generique alors qu'un
                    // message juste existe pour elle.
                    permissionRefusee = depot.accesRefuse(),
                    accesPartiel = depot.accesPartiel(),
                )
                _etat.value = base.copy(
                    serveurIntrouvable = issue.serveurIntrouvable,
                    erreur = issue.erreur,
                    // Meme source de verite qu'`appaire`, et pour la meme
                    // raison : lire `issue.revoque` seul rejouerait une
                    // revocation perimee apres un rescan de QR, et afficherait
                    // le bandeau « revoque » sur un telephone fraichement
                    // reappaire. Une revocation reelle vide le coffre AVANT de
                    // publier l'issue, donc coffre vide = revocation en cours.
                    revoque = issue.revoque && coffre.charge() == null,
                    // La verite vient du COFFRE, pas de l'issue. `derniereIssue`
                    // est un StateFlow de companion object : apres un rescan de
                    // QR suivi d'une reouverture de l'application, le nouveau
                    // collecteur recevrait l'ancienne issue et renverrait a
                    // l'appairage avec « revoque » alors que le coffre est
                    // plein. Un message de panne FAUX coute aussi cher qu'un
                    // message manquant.
                    appaire = coffre.charge() != null,
                    // Conserve APRES la synchro : c'est la seule liste qui
                    // revele un dossier suivi mais absent du telephone, et
                    // l'avancement qui la portait vient d'etre efface.
                    // `?:` et NON `ifEmpty` : EtatSynchro distingue exprès
                    // `null` (« pas encore regarde ») de la carte VIDE
                    // (« regarde, MediaStore n'a rien rendu »), et documente
                    // le second comme le cas le plus grave de tous. Aplatir
                    // les deux rendait le message « Aucun dossier trouve »
                    // definitivement injoignable.
                    dossiersVus = issue.dossiersVus ?: _etat.value.dossiersVus,
                )
            }
        }
```

Conserver `viewModelScope` et `launch` dans les imports pour ce bloc.

- [ ] **Step 7 : Demander la permission de notifier**

Depuis Android 13, `POST_NOTIFICATIONS` est une permission **à demander à
l'exécution**. La déclarer au manifeste, comme le fait la tâche 8, ne suffit
pas : sans la demande, la notification n'apparaît jamais — donc plus aucun
avancement écran éteint, ni bouton pour arrêter. C'est-à-dire toute la valeur
du service de premier plan.

Dans `MainActivity.onCreate`, remplacer l'appel existant :

```kotlin
        permissions.launch(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
                // POST_NOTIFICATIONS est demandee ICI et pas ailleurs : sans
                // elle, le service de premier plan demarre mais sa
                // notification reste invisible, et l'utilisateur n'a plus
                // aucun moyen de voir ou d'arreter une synchro en cours.
                arrayOf(android.Manifest.permission.READ_MEDIA_IMAGES,
                        android.Manifest.permission.READ_MEDIA_VIDEO,
                        android.Manifest.permission.POST_NOTIFICATIONS)
            else
                arrayOf(android.Manifest.permission.READ_EXTERNAL_STORAGE))
```

Un refus de `POST_NOTIFICATIONS` ne doit **rien** empêcher d'autre : la
synchronisation continue, seul l'affichage en arrière-plan est perdu.
`rafraichirPermissions()` ne s'occupe que de l'accès aux médias et n'a pas à
en tenir compte.

- [ ] **Step 8 : Navigation avec retour**

Dans `MainActivity.kt`, remplacer le bloc `setContent` :

```kotlin
        setContent {
            MaterialTheme {
                val etat by modele.etat.collectAsStateWithLifecycle()
                val avancement by modele.avancement.collectAsStateWithLifecycle()
                // rememberSaveable et non remember : l'ecran de detail
                // retombait sur l'accueil a chaque rotation (issue #24).
                var detail by rememberSaveable { mutableStateOf(false) }

                // Sans ce BackHandler, le bouton retour du systeme FERMAIT
                // l'application depuis l'ecran de detail, en perdant le
                // dernier bilan (issue #24).
                // `avancement == null` en plus de `detail` : arme pendant
                // l'ecran d'avancement, le premier retour eteindrait `detail`
                // en coulisse sans rien changer a l'ecran, et le second
                // fermerait l'application.
                BackHandler(enabled = detail && avancement == null) { detail = false }

                when {
                    !etat.appaire -> EcranAppairage(
                        qrInvalide = etat.qrInvalide,
                        revoque = etat.revoque,
                        surScanner = {
                            scanner.launch(ScanOptions().setPrompt(
                                "Scannez le QR affiché sur la page du serveur"))
                        })
                    avancement != null -> EcranAvancement(
                        avancement!!, surInterrompre = modele::interrompre)
                    detail -> EcranDetail(etat, TravailSynchro.DOSSIERS_SAUVEGARDES)
                    else -> EcranAccueil(etat, System.currentTimeMillis(),
                        surSynchroniser = modele::synchroniser,
                        surVoirDetail = { detail = true })
                }
            }
        }
```

Ajouter les imports `androidx.activity.compose.BackHandler`,
`androidx.compose.runtime.saveable.rememberSaveable`,
`fr.izquierdo.phototheque.synchro.TravailSynchro`.

**Ne rien ajouter pour le bouton « Interrompre » de la notification.** Une
version antérieure de ce plan faisait traiter son action dans `onCreate` ; la
tâche 8 l'a remplacée par un `BroadcastReceiver`, précisément parce qu'un
`PendingIntent` d'activité ne délivre pas son intent quand la tâche de
l'application existe déjà en arrière-plan — le traitement n'aurait jamais
tourné. L'interruption ne passe plus par l'activité.

- [ ] **Step 9 : Vérifier que tout compile et que les tests passent**

Run : `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 10 : Valider par mutation**

Dans `Lisible.duree`, remplacer `else -> String.format("%d h %02d", …)` par
`else -> "${secondes / 60} min"`, relancer.
Expected: `une_duree_longue_se_dit_en_heures_et_minutes` échoue. Remettre.

- [ ] **Step 11 : Commit**

```bash
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/ \
        android/app/src/main/kotlin/fr/izquierdo/phototheque/MainActivity.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/LisibleTest.kt
git commit -m "feat(ui): ecran d'avancement complet, et le bouton retour ne ferme plus l'app

L'accueil ne renvoie pas vers un ecran d'avancement : il en DEVIENT un.
Aucune navigation a faire pour voir ce qui se passe.

Affiche n/total, les octets, la vitesse, le temps restant, le fichier en cours
avec sa taille et SA DESTINATION prevue dans la bibliotheque, le paquet en
cours, et les dossiers suivis — avec en rouge ceux qui sont introuvables sur
ce telephone. Repond a « je sais meme pas quel dossier ca synchronise ».

Barre determinee des que le total est connu : une barre qui tourne sans fin
pendant une heure ne dit rien.

Corrige aussi deux constats de #24 : le bouton retour du systeme fermait
l'application depuis l'ecran de detail, et cet ecran retombait sur l'accueil a
chaque rotation."
```

---

### Task 10 : Recette sur un vrai téléphone

**Files:** aucun — c'est la validation du lot.

- [ ] **Step 1 : Construire et installer**

```bash
cd ~/dev/phone_camera_import
./deploy/envoyer-apk.sh
```

Puis, sur le téléphone, page d'administration → « Télécharger l'application ».
Voir `docs/APPLICATION-ANDROID.md` §6 si l'installation coince.

- [ ] **Step 2 : L'écran dit enfin quelque chose**

Appuyer sur « Sauvegarder maintenant ». Attendu, **dès les premières
secondes** : « Analyse en cours », un compteur qui bouge, puis « Sauvegarde en
cours » avec une vitesse et une destination.

**Ce qu'il ne doit PAS y avoir** : une barre qui tourne sans chiffre.

- [ ] **Step 3 : Poser le téléphone**

Éteindre l'écran, attendre cinq minutes, le rallumer. Attendu : la
synchronisation a **continué**, et la notification affiche l'avancement.

Vérifier côté NUC que ça monte toujours :

```bash
ssh izquierdo@192.168.1.21 'find /media/izquierdo/Famille/incoming -type f | wc -l'
```

- [ ] **Step 4 : L'horizon avance en cours de route**

Pendant la synchro, après quelques paquets :

```bash
ssh izquierdo@192.168.1.21 'python3 -c "
import sqlite3, os, datetime
c = sqlite3.connect(os.path.expanduser(\"~/phototheque_devices.db\"))
for _, d, t in c.execute(\"select * from horizons\"):
    print(d, datetime.datetime.fromtimestamp(t))
"'
```

Attendu : des horizons **déjà écrits**, alors que la synchro tourne encore.
C'est la preuve que le découpage en paquets fonctionne — avant ce lot, rien
n'apparaissait avant la toute fin.

- [ ] **Step 5 : Interrompre**

Appuyer sur « Interrompre » dans la notification. Attendu : arrêt **immédiat**,
et les paquets déjà validés restent rangés. Rien ne se relance tout seul.

Vérifier qu'aucune session n'est restée en plan :

```bash
ssh izquierdo@192.168.1.21 'ls /media/izquierdo/Famille/incoming/'
```

Attendu : vide. Tant que le lot serveur (issue #30) n'est pas fait,
`POST /sync/abandon` répond 404 et le dossier **reste** — c'est normal, le
noter et le supprimer à la main.

- [ ] **Step 6 : Le commit long ne ment plus**

Relancer une grosse synchro et la laisser finir. Attendu : **aucun message
d'échec**, et l'accueil affiche « Sauvegardé aujourd'hui ». C'est le défaut
n° 5, celui qui a motivé tout ce lot.

- [ ] **Step 7 : Couper le Wi-Fi en pleine synchro**

Attendu : la synchronisation s'arrête sans alerte rouge, et **repart toute
seule** quand le Wi-Fi revient (laisser quelques minutes : `WorkManager`
applique un délai croissant).

- [ ] **Step 8 : Le bouton retour**

Depuis « Voir le détail », appuyer sur retour. Attendu : on revient à
l'accueil. **L'application ne se ferme pas.**

- [ ] **Step 9 : Commit de clôture**

```bash
git commit --allow-empty -m "chore(android): lot 1 bis valide de bout en bout sur telephone reel"
```

---

## Ce que ce plan ne fait pas

- **Le choix des dossiers dans l'application** : lot 2. Ils restent codés en
  dur, dans `TravailSynchro.DOSSIERS_SAUVEGARDES`.
- **Issue #22** (hacher des fichiers que le serveur possède déjà) : atténuée
  par les paquets, pas résolue.
- **Issue #23** (certificat changé indiscernable de « pas à la maison »).
- **`POST /sync/abandon` côté serveur** : issue #30. L'application l'appelle
  déjà et ignore le 404.
- **La synchronisation automatique périodique** : lot 3. `WorkManager` est
  introduit ici, ce qui la rendra presque gratuite.
