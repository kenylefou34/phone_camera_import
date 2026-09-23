# Lot 2 de l'application Android — plan d'implémentation

> **Pour les agents :** SOUS-SKILL REQUISE — utiliser `superpowers:subagent-driven-development`
> (recommandée) ou `superpowers:executing-plans` pour dérouler ce plan tâche par
> tâche. Les étapes sont des cases à cocher (`- [ ]`).

**But :** rendre à l'utilisateur les quatre décisions que l'application prenait à
sa place en silence — quels dossiers sauvegarder, sur quelle fenêtre de dates,
quand se déclencher, et comment se désappairer.

**Architecture :** la logique pure (arbre de dossiers, résolution des coches,
monotonie de l'horizon, réglages) vit dans des objets Kotlin sans dépendance
Android, testables sur la JVM. Compose et `WorkManager` ne reçoivent que du
câblage. Côté serveur, deux retouches seulement, toutes deux au service du
désappairage.

**Pile technique :** Kotlin, Compose (BOM 2024.06.00), `androidx.work` 2.9.0,
`kotlinx-serialization-json` 1.6.3, JUnit 4. Serveur : FastAPI + pytest.

**Spec :** `docs/superpowers/specs/2026-09-23-app-android-lot2-design.md`

## Contraintes globales

- **Documenter et commenter en français, avec les accents.** Seuls les
  **messages de commit** sont sans accents (convention du dépôt).
- **Messages de commit toujours par heredoc à délimiteur quoté** :
  `git commit -F - <<'FIN'`. Jamais `git commit -m "..."` — bash mange les
  accents graves et laisse des phrases à trous (arrivé sur `836e447`).
- **Tests Android :** `cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest`.
  ⚠️ `./gradlew test --tests` **échoue** : toujours `testDebugUnitTest --tests`.
- **Tests serveur :** `python3 -m pytest -q` à la racine du dépôt.
- **Chaque test est validé par mutation** : casser volontairement le code et
  vérifier que c'est bien ce test-là qui tombe. Un test qui passe du premier
  coup ne prouve rien. Une mutation qui provoque une **erreur de syntaxe** ne
  prouve rien non plus — la mutation doit rester compilable.
- **Aucun test d'instrumentation Android n'existe dans ce projet** et ce lot
  n'en introduit pas. Compose, la navigation et `WorkManager` ne sont couverts
  que par lecture et recette manuelle (tâche 12).
- Ne jamais lancer `./gradlew clean` : cela **supprime l'APK** déjà construit.

## Points de vigilance

Cinq classes d'entrée que la spec implique sans qu'aucune tâche ne les exerce
naturellement. Chacune a son test, rattaché ci-dessous à la tâche qui possède le
code.

1. **Un dossier coché puis disparu du téléphone** (WhatsApp désinstallé). La
   sélection contient un chemin que MediaStore ne rend plus : l'arbre ne doit
   pas le perdre silencieusement ni planter. → tâche 3.
2. **Un chemin de dossier qui est le préfixe d'un autre sans en être le parent**
   (`Pictures/WhatsApp` et `Pictures/WhatsAppBusiness`). Une coche récursive sur
   le premier ne doit **pas** embarquer le second. → tâche 3.
3. **Fenêtre de dates inversée** (début après fin). Doit donner zéro média et le
   dire, jamais un comportement indéfini. → tâche 8.
4. **Horizon connu absent pour un dossier** (premier passage). La règle de
   monotonie ne doit pas inventer de plancher. → tâche 6.
5. **Désappairage alors que le serveur est injoignable.** C'est le cas
   NORMAL d'usage de cette fonction : l'effacement local doit réussir quand
   même. → tâche 11.

---

## Structure des fichiers

**Créés :**

| Fichier | Responsabilité |
|---|---|
| `android/.../ui/Reglages.kt` | réglages persistés : dossiers, dates, auto (données + sérialisation, pur) |
| `android/.../ui/MagasinReglages.kt` | lecture/écriture SharedPreferences (mince, non testé sur JVM) |
| `android/.../synchro/Arbre.kt` | construction de l'arborescence à partir des chemins plats (pur) |
| `android/.../synchro/Choix.kt` | résolution des coches en ensemble de dossiers, et état d'une coche (pur) |
| `android/.../synchro/Fenetre.kt` | bornes de dates, et comptage du hors-fenêtre (pur) |
| `android/.../synchro/Desappairage.kt` | ordre des opérations du désappairage (pur) |
| `android/.../ui/Navigation.kt` | état de navigation explicite (pur) |
| `android/.../ui/EcranDossiers.kt` | Compose : l'arbre et ses coches |
| `android/.../ui/EcranSauvegarde.kt` | Compose : dates, auto, médias hors fenêtre |
| `android/.../ui/EcranAppareil.kt` | Compose : état d'appairage, bouton de désappairage |

> `synchro/Destination.kt` existe déjà (calcul de la destination serveur) : ne
> pas le confondre avec un écran. Et `Orchestrateur.kt` contient déjà un
> `jourVersSecondes` privé — la tâche 8 le **déplace** dans `Fenetre` et fait
> appeler l'orchestrateur, plutôt que d'en avoir deux qui divergeront.

**Modifiés :**

| Fichier | Changement |
|---|---|
| `android/.../synchro/Horizons.kt` | ajout de `monotone()` |
| `android/.../synchro/Selection.kt` | plancher de reprise qui prime sur l'horizon |
| `android/.../synchro/Orchestrateur.kt` | applique la monotonie, prend les réglages |
| `android/.../synchro/TravailSynchro.kt` | lit les réglages, planification périodique |
| `android/.../ui/ModeleAccueil.kt` | expose et modifie les réglages, désappairage |
| `android/.../ui/EtatSynchro.kt` | seuil d'alerte à 3 jours quand l'auto est actif |
| `android/.../MainActivity.kt` | navigation explicite |
| `android/.../appairage/Appairage.kt` | rien (l'effacement existe déjà) |
| `phototheque/app.py` | route `POST /sync/desappairer` |
| `phototheque/devices.py` | `revoke()` supprime aussi les horizons |
| `docs/CONTRAT-APP.md` | la nouvelle route, la monotonie |
| `docs/APPLICATION-ANDROID.md` | les nouveaux écrans |
| `CLAUDE.md` | état d'avancement |

---

## Tâche 1 : les réglages persistés

**Fichiers :**
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Reglages.kt`
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/MagasinReglages.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/ReglagesTest.kt`

**Interfaces :**
- Consomme : rien.
- Produit : `data class Reglages(dossiersSeuls: Set<String>, dossiersRecursifs: Set<String>, debutJour: String?, finJour: String?, debutApplique: String?, auto: Boolean)`,
  `Reglages.enAuto(): Reglages`, `Reglages.versJson(): String`,
  `Reglages.depuisJson(String?): Reglages`, `Reglages.DEFAUT`,
  `Reglages.dossiersConnus: Set<String>`.
  Classe `MagasinReglages(context)` avec `lire(): Reglages` et `ecrire(Reglages)`.

- [ ] **Étape 1 : écrire le test qui échoue**

Fichier `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/ReglagesTest.kt` :

```kotlin
package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ReglagesTest {

    @Test
    fun `cocher auto efface la date de fin`() {
        // C'est la seule protection fiable contre la date de fin oubliee : un
        // compteur « 342 medias hors fenetre » se remarque une semaine, pas
        // six mois.
        val avant = Reglages(debutJour = "2019-01-01", finJour = "2020-12-31")

        val apres = avant.enAuto()

        assertTrue(apres.auto)
        assertNull(apres.finJour)
        assertEquals("2019-01-01", apres.debutJour)   // la borne basse reste
    }

    @Test
    fun `les reglages survivent a un aller-retour par json`() {
        val reglages = Reglages(
            dossiersSeuls = setOf("DCIM/Camera"),
            dossiersRecursifs = setOf("Pictures"),
            debutJour = "2026-09-15", finJour = null,
            debutApplique = "2026-09-15", auto = true)

        assertEquals(reglages, Reglages.depuisJson(reglages.versJson()))
    }

    @Test
    fun `un json absent donne les trois dossiers historiques`() {
        // Une mise a jour de l'application ne doit RIEN changer a ce qui est
        // sauvegarde tant que l'utilisateur n'a rien choisi.
        assertEquals(Reglages.DEFAUT, Reglages.depuisJson(null))
        assertEquals(
            setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"),
            Reglages.DEFAUT.dossiersSeuls)
    }

    @Test
    fun `un json illisible ne fait pas planter et retombe sur le defaut`() {
        // Preferences corrompues, retrogradage de version : lever ici fermerait
        // l'application a CHAQUE lancement, definitivement.
        assertEquals(Reglages.DEFAUT, Reglages.depuisJson("{ceci n'est pas du json"))
    }
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*ReglagesTest*"
```

Attendu : ÉCHEC de compilation, `Unresolved reference: Reglages`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

Fichier `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Reglages.kt` :

```kotlin
package fr.izquierdo.phototheque.ui

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Ce que l'utilisateur a choisi : quoi sauvegarder, sur quelle période, et si
 * la sauvegarde se déclenche seule.
 *
 * Les dates sont des jours ISO (« 2026-09-15 ») et non des instants : une borne
 * saisie par un humain porte sur un jour entier, et stocker un instant ferait
 * dépendre le résultat du fuseau au moment de la saisie.
 *
 * [debutApplique] n'est pas un réglage mais une trace : il retient la valeur de
 * [debutJour] dont la reprise a déjà été menée à son terme. C'est lui qui fait
 * qu'abaisser la date de début repropose les vieux médias **une fois** et non
 * chaque nuit.
 */
@Serializable
data class Reglages(
    val dossiersSeuls: Set<String> = emptySet(),
    val dossiersRecursifs: Set<String> = emptySet(),
    val debutJour: String? = null,
    val finJour: String? = null,
    val debutApplique: String? = null,
    val auto: Boolean = false,
    /**
     * Les dossiers déjà VUS sur le téléphone à la dernière synchronisation.
     * Sert uniquement à signaler ceux qui sont apparus depuis : une coche
     * récursive est une délégation dans le temps, elle prendra demain des
     * dossiers qui n'existent pas aujourd'hui.
     */
    val dossiersConnus: Set<String> = emptySet(),
) {
    /**
     * Passage en automatique. Efface la date de fin, délibérément.
     *
     * Une borne haute oubliée bloquerait en silence toutes les photos à venir.
     * Le but déclaré de l'automatique étant de synchroniser depuis la dernière
     * date, la borne haute n'y a aucun sens : autant que le geste qui y mène
     * nettoie derrière lui. L'écran doit le DIRE au moment où on coche.
     */
    fun enAuto(): Reglages = copy(auto = true, finJour = null)

    fun versJson(): String = FORMAT.encodeToString(serializer(), this)

    companion object {
        /**
         * Ce qui était codé en dur au lot 1. Sert de valeur initiale pour que
         * la mise à jour de l'application ne change rien à ce qui est
         * sauvegardé tant que l'utilisateur n'a rien choisi.
         */
        val DEFAUT = Reglages(
            dossiersSeuls = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"))

        private val FORMAT = Json { ignoreUnknownKeys = true }

        /**
         * Relit des réglages, et survit à tout ce qui peut arriver au fichier.
         *
         * Préférences corrompues, rétrogradage de version, champ disparu : lever
         * ici depuis un initialiseur de ViewModel fermerait l'application à
         * CHAQUE lancement, définitivement. C'est exactement la panne que
         * `Coffre` a déjà rencontrée avec le Keystore.
         */
        fun depuisJson(json: String?): Reglages =
            if (json == null) DEFAUT
            else try { FORMAT.decodeFromString(serializer(), json) }
                 catch (e: Exception) { DEFAUT }
    }
}
```

Fichier `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/MagasinReglages.kt` :

```kotlin
package fr.izquierdo.phototheque.ui

import android.content.Context

/**
 * Persistance des réglages.
 *
 * Des préférences ordinaires, pas le coffre chiffré : une liste de dossiers
 * n'est pas un secret, et la chiffrer exposerait ce réglage à la panne de
 * Keystore décrite dans `Coffre`. Toute la logique est dans [Reglages], qui se
 * teste sur la JVM ; cette classe ne fait que lire et écrire une chaîne.
 */
class MagasinReglages(context: Context) {

    private val prefs = context.getSharedPreferences("reglages", Context.MODE_PRIVATE)

    fun lire(): Reglages = Reglages.depuisJson(prefs.getString(CLE, null))

    fun ecrire(reglages: Reglages) {
        prefs.edit().putString(CLE, reglages.versJson()).apply()
    }

    private companion object { const val CLE = "reglages" }
}
```

- [ ] **Étape 4 : lancer le test et vérifier qu'il passe**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*ReglagesTest*"
```

Attendu : SUCCÈS, 4 tests.

- [ ] **Étape 5 : valider par mutation**

Remplacer dans `enAuto()` : `copy(auto = true, finJour = null)` par
`copy(auto = true)`. Relancer : seul
`cocher auto efface la date de fin` doit tomber. Restaurer.

Remplacer dans `depuisJson` : `catch (e: Exception) { DEFAUT }` par
`catch (e: Exception) { Reglages() }`. Relancer : seul
`un json illisible ne fait pas planter et retombe sur le defaut` doit tomber.
Restaurer.

- [ ] **Étape 6 : commettre**

```bash
cd /home/invisart/dev/phone_camera_import
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Reglages.kt \
        android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/MagasinReglages.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/ReglagesTest.kt
git commit -F - <<'FIN'
feat(app): reglages persistes - dossiers, fenetre de dates, auto

Cocher l'automatique efface la date de fin, deliberement : une borne
haute oubliee bloquerait en silence toutes les photos a venir, et un
compteur « hors fenetre » se remarque une semaine, pas six mois.

Un json illisible retombe sur le defaut au lieu de lever : depuis un
initialiseur de ViewModel, lever fermerait l'application a chaque
lancement, comme le Keystore l'avait deja fait avec Coffre.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 2 : l'arborescence des dossiers

**Fichiers :**
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Arbre.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/ArbreTest.kt`

**Interfaces :**
- Consomme : rien.
- Produit : `data class Noeud(chemin: String, libelle: String, medias: Int, mediasTotal: Int, enfants: List<Noeud>)`
  et `Arbre.construire(dossiers: Map<String, Int>): List<Noeud>`.
  L'entrée est exactement `EtatSynchro.dossiersVus`.

- [ ] **Étape 1 : écrire le test qui échoue**

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

class ArbreTest {

    @Test
    fun `les chemins plats deviennent un arbre`() {
        val arbre = Arbre.construire(mapOf(
            "DCIM/Camera" to 1200,
            "Pictures/WhatsApp" to 300,
            "Pictures/Messages" to 38))

        // « DCIM » se replie avec son unique enfant : il ne contient aucun
        // média et n'a qu'un sous-dossier, donc y entrer n'apprendrait rien.
        // « Pictures » en a deux, il reste donc un niveau à part entière.
        assertEquals(listOf("DCIM/Camera", "Pictures"), arbre.map { it.libelle })
        val pictures = arbre.first { it.libelle == "Pictures" }
        assertEquals(listOf("Messages", "WhatsApp"), pictures.enfants.map { it.libelle })
        assertEquals("Pictures/Messages", pictures.enfants.first().chemin)
    }

    @Test
    fun `le total remonte les medias des sous-dossiers`() {
        val arbre = Arbre.construire(mapOf(
            "Pictures/WhatsApp" to 300,
            "Pictures/Messages" to 38))

        val pictures = arbre.single()
        assertEquals(0, pictures.medias)         // rien DIRECTEMENT dans Pictures
        assertEquals(338, pictures.mediasTotal)  // mais 338 en dessous
    }

    @Test
    fun `une chaine sans media et a enfant unique est repliee`() {
        // Android/media/com.whatsapp/WhatsApp/Media fait cinq niveaux dont
        // aucun ne contient de media : descendre marche par marche dans des
        // dossiers vides n'apprend rien et coute cinq appuis.
        val arbre = Arbre.construire(mapOf(
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images" to 900))

        val racine = arbre.single()
        assertEquals(
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images",
            racine.libelle)
        assertEquals(
            "Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images",
            racine.chemin)
        assertEquals(900, racine.medias)
        assertEquals(emptyList<Noeud>(), racine.enfants)
    }

    @Test
    fun `un dossier qui contient des medias n'est jamais replie`() {
        // Meme avec un enfant unique : on doit pouvoir cocher le parent seul.
        val arbre = Arbre.construire(mapOf(
            "DCIM" to 12,
            "DCIM/Camera" to 1200))

        val dcim = arbre.single()
        assertEquals("DCIM", dcim.libelle)
        assertEquals(12, dcim.medias)
        assertEquals(listOf("Camera"), dcim.enfants.map { it.libelle })
    }

    @Test
    fun `une chaine a enfants multiples n'est pas repliee`() {
        val arbre = Arbre.construire(mapOf(
            "Android/media/a" to 1,
            "Android/media/b" to 1))

        // « Android/media » se replie (un seul enfant, aucun media), mais
        // s'arrete la : deux enfants.
        val racine = arbre.single()
        assertEquals("Android/media", racine.libelle)
        assertEquals(listOf("a", "b"), racine.enfants.map { it.libelle })
        assertEquals("Android/media/a", racine.enfants.first().chemin)
    }

    @Test
    fun `une liste vide donne un arbre vide`() {
        assertEquals(emptyList<Noeud>(), Arbre.construire(emptyMap()))
    }
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*ArbreTest*"
```

Attendu : ÉCHEC de compilation, `Unresolved reference: Arbre`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

```kotlin
package fr.izquierdo.phototheque.synchro

/**
 * Un dossier de l'arborescence présentée à l'utilisateur.
 *
 * [chemin] est le chemin RÉEL, celui que porte `Media.dossier` et qui sert de
 * clé d'horizon côté serveur. [libelle] est ce qu'on affiche : il peut contenir
 * des « / » quand une chaîne de dossiers vides a été repliée.
 */
data class Noeud(
    val chemin: String,
    val libelle: String,
    /** Médias DIRECTEMENT dans ce dossier, sans les sous-dossiers. */
    val medias: Int,
    /** Médias de ce dossier ET de toute sa descendance. */
    val mediasTotal: Int,
    val enfants: List<Noeud>,
)

/**
 * Construction de l'arborescence à partir des chemins plats de MediaStore.
 *
 * MediaStore ne connaît pas d'arbre : `RELATIVE_PATH` rend « Pictures/WhatsApp »
 * sans dire que « Pictures » existe. C'est ici qu'on le reconstitue.
 */
object Arbre {

    fun construire(dossiers: Map<String, Int>): List<Noeud> {
        val racine = Brouillon("")
        for ((chemin, nombre) in dossiers) {
            var courant = racine
            for (segment in chemin.split("/").filter { it.isNotEmpty() }) {
                courant = courant.enfants.getOrPut(segment) { Brouillon(segment) }
            }
            courant.medias += nombre
        }
        return racine.enfants.values.map { figer(it, "") }.sortedBy { it.libelle }
    }

    private class Brouillon(val segment: String) {
        val enfants = linkedMapOf<String, Brouillon>()
        var medias = 0
    }

    private fun figer(depart: Brouillon, prefixe: String): Noeud {
        var noeud = depart
        var libelle = depart.segment
        var chemin = if (prefixe.isEmpty()) depart.segment else "$prefixe/${depart.segment}"
        // Repli : un dossier SANS média et à enfant UNIQUE n'apprend rien et
        // coûte un appui. Les deux conditions comptent — un dossier qui
        // contient des médias doit rester cochable pour lui-même.
        while (noeud.medias == 0 && noeud.enfants.size == 1) {
            val unique = noeud.enfants.values.first()
            libelle += "/${unique.segment}"
            chemin += "/${unique.segment}"
            noeud = unique
        }
        val enfants = noeud.enfants.values.map { figer(it, chemin) }.sortedBy { it.libelle }
        return Noeud(
            chemin = chemin,
            libelle = libelle,
            medias = noeud.medias,
            mediasTotal = noeud.medias + enfants.sumOf { it.mediasTotal },
            enfants = enfants)
    }
}
```

- [ ] **Étape 4 : lancer le test et vérifier qu'il passe**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*ArbreTest*"
```

Attendu : SUCCÈS, 6 tests.

- [ ] **Étape 5 : valider par mutation**

Remplacer la condition de repli `noeud.medias == 0 && noeud.enfants.size == 1`
par `noeud.enfants.size == 1`. Relancer : seul
`un dossier qui contient des medias n'est jamais replie` doit tomber. Restaurer.

Remplacer `noeud.medias + enfants.sumOf { it.mediasTotal }` par `noeud.medias`.
Relancer : seul `le total remonte les medias des sous-dossiers` doit tomber.
Restaurer.

- [ ] **Étape 6 : commettre**

```bash
cd /home/invisart/dev/phone_camera_import
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Arbre.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/ArbreTest.kt
git commit -F - <<'FIN'
feat(app): reconstituer l'arborescence des dossiers depuis MediaStore

MediaStore ne connait pas d'arbre : RELATIVE_PATH rend
« Pictures/WhatsApp » sans dire que « Pictures » existe.

Les chaines de dossiers SANS media et a enfant unique sont repliees en
une seule ligne : Android/media/com.whatsapp/WhatsApp/Media fait cinq
niveaux dont aucun ne contient quoi que ce soit, et descendre marche par
marche dans des dossiers vides n'apprend rien. Un dossier qui contient
des medias n'est jamais replie - il doit rester cochable pour lui-meme.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 3 : résolution des coches

**Fichiers :**
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Choix.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/ChoixTest.kt`

**Interfaces :**
- Consomme : `Reglages.dossiersSeuls`, `Reglages.dossiersRecursifs` (tâche 1).
- Produit : `enum class Coche { AUCUNE, PARTIELLE, DOSSIER, RECURSIVE }`,
  `Choix.resoudre(tous: Set<String>, seuls: Set<String>, recursifs: Set<String>): Set<String>`,
  `Choix.etat(noeud: Noeud, seuls: Set<String>, recursifs: Set<String>): Coche`,
  `Choix.nouveauxParRecursivite(tous: Set<String>, connus: Set<String>, recursifs: Set<String>): Set<String>`.

- [ ] **Étape 1 : écrire le test qui échoue**

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertEquals
import org.junit.Test

class ChoixTest {

    @Test
    fun `une coche simple ne prend que le dossier lui-meme`() {
        val resolus = Choix.resoudre(
            tous = setOf("Pictures", "Pictures/WhatsApp"),
            seuls = setOf("Pictures"), recursifs = emptySet())

        assertEquals(setOf("Pictures"), resolus)
    }

    @Test
    fun `une coche recursive prend toute la descendance`() {
        val resolus = Choix.resoudre(
            tous = setOf("Pictures", "Pictures/WhatsApp", "Pictures/WhatsApp/Sent", "DCIM"),
            seuls = emptySet(), recursifs = setOf("Pictures"))

        assertEquals(setOf("Pictures", "Pictures/WhatsApp", "Pictures/WhatsApp/Sent"), resolus)
    }

    @Test
    fun `une coche recursive n'embarque pas un homonyme voisin`() {
        // « Pictures/WhatsApp » est un PREFIXE de « Pictures/WhatsAppBusiness »
        // sans en etre le parent. Comparer les chaines sans le separateur
        // sauvegarderait un dossier que l'utilisateur n'a jamais coche.
        val resolus = Choix.resoudre(
            tous = setOf("Pictures/WhatsApp", "Pictures/WhatsAppBusiness"),
            seuls = emptySet(), recursifs = setOf("Pictures/WhatsApp"))

        assertEquals(setOf("Pictures/WhatsApp"), resolus)
    }

    @Test
    fun `un dossier coche puis disparu du telephone ne casse rien`() {
        // WhatsApp desinstalle : le reglage garde un chemin que MediaStore ne
        // rend plus. On ne le propose pas, et on ne leve pas.
        val resolus = Choix.resoudre(
            tous = setOf("DCIM/Camera"),
            seuls = setOf("DCIM/Camera", "Pictures/WhatsApp"), recursifs = emptySet())

        assertEquals(setOf("DCIM/Camera"), resolus)
    }

    @Test
    fun `les dossiers entres par recursivite depuis la derniere fois sont signales`() {
        // Une coche recursive est une delegation dans le temps : elle prendra
        // demain des dossiers qui n'existent pas aujourd'hui. Sans ce rappel,
        // il faudrait surveiller ; avec, on est prevenu.
        val nouveaux = Choix.nouveauxParRecursivite(
            tous = setOf("Pictures/WhatsApp", "Pictures/Telegram", "DCIM/Camera"),
            connus = setOf("Pictures/WhatsApp", "DCIM/Camera"),
            recursifs = setOf("Pictures"))

        assertEquals(setOf("Pictures/Telegram"), nouveaux)
    }

    @Test
    fun `un dossier neuf hors de toute coche recursive n'est pas signale`() {
        // Il n'est pas sauvegarde : l'annoncer ferait croire le contraire.
        val nouveaux = Choix.nouveauxParRecursivite(
            tous = setOf("Download/Nouveau", "DCIM/Camera"),
            connus = setOf("DCIM/Camera"),
            recursifs = setOf("Pictures"))

        assertEquals(emptySet<String>(), nouveaux)
    }

    @Test
    fun `l'etat d'une coche distingue les quatre cas`() {
        val feuille = Noeud("Pictures/WhatsApp", "WhatsApp", 10, 10, emptyList())
        val parent = Noeud("Pictures", "Pictures", 0, 10, listOf(feuille))

        assertEquals(Coche.AUCUNE, Choix.etat(parent, emptySet(), emptySet()))
        assertEquals(Coche.DOSSIER, Choix.etat(parent, setOf("Pictures"), emptySet()))
        assertEquals(Coche.RECURSIVE, Choix.etat(parent, emptySet(), setOf("Pictures")))
        // Seul l'enfant est coche : le parent doit le DIRE, sinon on croit le
        // dossier entierement pris alors qu'il ne l'est qu'a moitie.
        assertEquals(Coche.PARTIELLE,
                     Choix.etat(parent, setOf("Pictures/WhatsApp"), emptySet()))
    }
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*ChoixTest*"
```

Attendu : ÉCHEC de compilation, `Unresolved reference: Choix`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

```kotlin
package fr.izquierdo.phototheque.synchro

/** Ce qu'affiche la case d'une ligne de l'arborescence. */
enum class Coche {
    AUCUNE,
    /** Seuls certains sous-dossiers sont pris : case à moitié pleine. */
    PARTIELLE,
    /** Ce dossier seulement. */
    DOSSIER,
    /** Ce dossier et toute sa descendance. */
    RECURSIVE,
}

object Choix {

    /**
     * Les dossiers réellement sauvegardés, une fois la récursivité déployée.
     *
     * Filtré sur [tous], c'est-à-dire sur ce que MediaStore rend AUJOURD'HUI :
     * un dossier coché puis disparu du téléphone (application désinstallée)
     * reste dans le réglage — on ne le supprime pas dans le dos de
     * l'utilisateur — mais il n'est pas proposé.
     */
    fun resoudre(tous: Set<String>, seuls: Set<String>, recursifs: Set<String>): Set<String> =
        tous.filterTo(mutableSetOf()) { dossier ->
            dossier in seuls || recursifs.any { sousArbre(dossier, it) }
        }

    /**
     * Vrai si [dossier] est [racine] ou se trouve dessous.
     *
     * Le « / » n'est pas décoratif : sans lui, « Pictures/WhatsApp » embarquerait
     * « Pictures/WhatsAppBusiness », qui n'est pas son enfant. On sauvegarderait
     * un dossier que personne n'a coché.
     */
    private fun sousArbre(dossier: String, racine: String): Boolean =
        dossier == racine || dossier.startsWith("$racine/")

    /**
     * Ce que la case de ce nœud doit montrer.
     *
     * L'état PARTIELLE existe pour empêcher une erreur de lecture : sans lui,
     * un dossier dont un seul sous-dossier est pris se lirait comme entièrement
     * pris.
     */
    fun etat(noeud: Noeud, seuls: Set<String>, recursifs: Set<String>): Coche = when {
        noeud.chemin in recursifs -> Coche.RECURSIVE
        noeud.chemin in seuls -> Coche.DOSSIER
        descendanceCochee(noeud, seuls, recursifs) -> Coche.PARTIELLE
        else -> Coche.AUCUNE
    }

    private fun descendanceCochee(
        noeud: Noeud, seuls: Set<String>, recursifs: Set<String>,
    ): Boolean = noeud.enfants.any {
        it.chemin in seuls || it.chemin in recursifs || descendanceCochee(it, seuls, recursifs)
    }

    /**
     * Les dossiers qu'une coche récursive vient d'embarquer sans qu'on les ait
     * choisis un par un.
     *
     * C'est le filet de la récursivité : elle prendra demain des dossiers qui
     * n'existent pas aujourd'hui — une application installée, un nouveau
     * répertoire de captures. Sans ce rappel après chaque synchronisation, il
     * faudrait surveiller.
     *
     * Seuls ceux effectivement SAUVEGARDÉS sont signalés : annoncer un dossier
     * neuf hors de toute coche récursive ferait croire qu'il est pris.
     */
    fun nouveauxParRecursivite(
        tous: Set<String>, connus: Set<String>, recursifs: Set<String>,
    ): Set<String> = resoudre(tous - connus, emptySet(), recursifs)
}
```

- [ ] **Étape 4 : lancer le test et vérifier qu'il passe**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*ChoixTest*"
```

Attendu : SUCCÈS, 7 tests.

- [ ] **Étape 5 : valider par mutation**

Remplacer dans `sousArbre` : `dossier.startsWith("$racine/")` par
`dossier.startsWith(racine)`. Relancer : seul
`une coche recursive n'embarque pas un homonyme voisin` doit tomber. Restaurer.

Remplacer dans `resoudre` : `tous.filterTo(...)` par
`(seuls + recursifs).toSet()`. Relancer :
`un dossier coche puis disparu du telephone ne casse rien` et
`une coche recursive prend toute la descendance` doivent tomber. Restaurer.

Remplacer dans `nouveauxParRecursivite` : `tous - connus` par `tous`. Relancer :
seul `les dossiers entres par recursivite depuis la derniere fois sont signales`
doit tomber. Restaurer.

- [ ] **Étape 6 : commettre**

```bash
cd /home/invisart/dev/phone_camera_import
git add android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Choix.kt \
        android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/ChoixTest.kt
git commit -F - <<'FIN'
feat(app): resoudre les coches en ensemble de dossiers a sauvegarder

Deux pieges traites explicitement.

Le separateur dans le test de sous-arbre n'est pas decoratif : sans lui
« Pictures/WhatsApp » embarquerait « Pictures/WhatsAppBusiness », qui
n'est pas son enfant, et on sauvegarderait un dossier que personne n'a
coche.

Le resultat est filtre sur ce que MediaStore rend AUJOURD'HUI : un
dossier coche puis disparu (application desinstallee) reste dans le
reglage - on ne touche pas au choix de l'utilisateur dans son dos - mais
il n'est pas propose.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 4 : navigation explicite

**Fichiers :**
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/Navigation.kt`
- Modifier : `android/app/src/main/kotlin/fr/izquierdo/phototheque/MainActivity.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/NavigationTest.kt`

**Interfaces :**
- Consomme : `EtatSynchro.appaire`, `Avancement` (existant).
- Produit : `enum class Ecran { APPAIRAGE, ACCUEIL, DETAIL, REGLAGES, DOSSIERS, SAUVEGARDE, APPAREIL }`,
  `Navigation.ecranAffiche(demande: Ecran, appaire: Boolean, synchroEnCours: Boolean): Ecran`,
  `Navigation.retour(depuis: Ecran): Ecran?`.

- [ ] **Étape 1 : écrire le test qui échoue**

```kotlin
package fr.izquierdo.phototheque.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NavigationTest {

    @Test
    fun `sans appairage aucun autre ecran n'est atteignable`() {
        // Le lot 1 le garantissait par un `when` ; il faut que ca reste vrai
        // maintenant que sept destinations existent.
        for (demande in Ecran.values()) {
            assertEquals(Ecran.APPAIRAGE,
                Navigation.ecranAffiche(demande, appaire = false, synchroEnCours = false))
        }
    }

    @Test
    fun `une synchro en cours prend le pas sur l'ecran demande`() {
        assertEquals(Ecran.ACCUEIL,
            Navigation.ecranAffiche(Ecran.DOSSIERS, appaire = true, synchroEnCours = true))
    }

    @Test
    fun une_synchro_en_cours_ne_maintient_pas_un_appareil_revoque_sur_l_accueil() {
        // Cet état est ATTEIGNABLE, contrairement à ce qu'on croirait : une
        // révocation en pleine synchro fait appeler Coffre.oublier() par
        // TravailSynchro (TravailSynchro.kt:163), donc `appaire` retombe à
        // faux pendant que l'avancement n'est pas encore effacé. Si l'ordre
        // des deux gardes s'inversait, l'application afficherait l'accueil
        // d'un appareil qui n'a plus de jeton, au lieu de l'écran de scan.
        // C'est ce test, et lui seul, qui verrouille cet ordre.
        assertEquals(Ecran.APPAIRAGE,
            Navigation.ecranAffiche(Ecran.ACCUEIL, appaire = false, synchroEnCours = true))
    }

    @Test
    fun `l'ecran demande est affiche quand rien ne s'y oppose`() {
        assertEquals(Ecran.DOSSIERS,
            Navigation.ecranAffiche(Ecran.DOSSIERS, appaire = true, synchroEnCours = false))
    }

    @Test
    fun `les trois ecrans de reglages reviennent aux reglages`() {
        assertEquals(Ecran.REGLAGES, Navigation.retour(Ecran.DOSSIERS))
        assertEquals(Ecran.REGLAGES, Navigation.retour(Ecran.SAUVEGARDE))
        assertEquals(Ecran.REGLAGES, Navigation.retour(Ecran.APPAREIL))
    }

    @Test
    fun `l'accueil n'a pas de retour et ferme l'application`() {
        // null = on laisse le systeme fermer l'application. Renvoyer ACCUEIL
        // ici rendrait le bouton retour inoperant, ce qui se signale en
        // magasin d'applications comme un defaut.
        assertNull(Navigation.retour(Ecran.ACCUEIL))
        assertNull(Navigation.retour(Ecran.APPAIRAGE))
    }
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*NavigationTest*"
```

Attendu : ÉCHEC de compilation, `Unresolved reference: Navigation`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

```kotlin
package fr.izquierdo.phototheque.ui

/** Les destinations de l'application. */
enum class Ecran { APPAIRAGE, ACCUEIL, DETAIL, REGLAGES, DOSSIERS, SAUVEGARDE, APPAREIL }

/**
 * Navigation, séparée de Compose pour être vérifiable sur la JVM.
 *
 * Le lot 1 choisissait l'écran par une cascade de `when` sur des booléens. À
 * quatre destinations ça tenait ; à sept, chaque nouveau drapeau croise tous
 * les autres et les cas impossibles deviennent atteignables sans qu'aucun test
 * ne puisse le dire.
 */
object Navigation {

    /**
     * L'écran réellement affiché, qui n'est pas toujours celui demandé.
     *
     * Deux règles priment sur la demande, et toutes deux existaient déjà au lot
     * 1 : sans appairage rien n'est atteignable, et une synchronisation en
     * cours doit rester visible.
     */
    fun ecranAffiche(demande: Ecran, appaire: Boolean, synchroEnCours: Boolean): Ecran = when {
        !appaire -> Ecran.APPAIRAGE
        synchroEnCours -> Ecran.ACCUEIL
        else -> demande
    }

    /**
     * Où mène le bouton retour du système, ou `null` pour laisser le système
     * fermer l'application.
     *
     * Renvoyer l'écran courant plutôt que `null` rendrait le bouton retour
     * inopérant depuis l'accueil — un défaut visible et signalé comme tel.
     */
    fun retour(depuis: Ecran): Ecran? = when (depuis) {
        Ecran.APPAIRAGE, Ecran.ACCUEIL -> null
        Ecran.DETAIL, Ecran.REGLAGES -> Ecran.ACCUEIL
        Ecran.DOSSIERS, Ecran.SAUVEGARDE, Ecran.APPAREIL -> Ecran.REGLAGES
    }
}
```

- [ ] **Étape 4 : lancer le test et vérifier qu'il passe**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*NavigationTest*"
```

Attendu : SUCCÈS, 5 tests.

- [ ] **Étape 5 : valider par mutation**

Intervertir les deux premières branches de `ecranAffiche` (mettre
`synchroEnCours -> Ecran.ACCUEIL` en premier). Relancer : seul
`une_synchro_en_cours_ne_maintient_pas_un_appareil_revoque_sur_l_accueil`
doit tomber. Restaurer.

> Cette prédiction a été corrigée en cours d'exécution : elle désignait d'abord
> le test qui boucle avec `synchroEnCours = false`, lequel ne peut donc **pas**
> distinguer l'ordre des deux gardes. La mutation ne tuait aucun test — l'ordre
> n'était pas vérifié. Le test ci-dessus a été ajouté pour ça.

Remplacer `Ecran.APPAIRAGE, Ecran.ACCUEIL -> null` par
`Ecran.APPAIRAGE, Ecran.ACCUEIL -> Ecran.ACCUEIL`. Relancer : seul
`l'accueil n'a pas de retour et ferme l'application` doit tomber. Restaurer.

- [ ] **Étape 6 : câbler `MainActivity`**

Remplacer le bloc `when { ... }` de `MainActivity.onCreate` par un état de
navigation. Les écrans des tâches 5, 8 et 11 n'existent pas encore : les
brancher au fur et à mesure. Pour l'instant, seules les destinations déjà
écrites sont atteignables.

```kotlin
var demande by rememberSaveable { mutableStateOf(Ecran.ACCUEIL) }
val affiche = Navigation.ecranAffiche(
    demande, appaire = etat.appaire, synchroEnCours = avancement != null)

// Le retour est calculé, plus deviné : à sept destinations, la cascade de
// booléens du lot 1 laissait des états inatteignables par le bouton retour.
BackHandler(enabled = Navigation.retour(affiche) != null) {
    Navigation.retour(affiche)?.let { demande = it }
}

when (affiche) {
    Ecran.APPAIRAGE -> EcranAppairage(
        qrInvalide = etat.qrInvalide, revoque = etat.revoque,
        surScanner = { /* inchangé */ })
    Ecran.ACCUEIL ->
        if (avancement != null) EcranAvancement(avancement!!, modele::interrompre)
        else EcranAccueil(etat, reglages, System.currentTimeMillis(),
                          surSynchroniser = modele::synchroniser,
                          surInterrompre = modele::interrompre,
                          surVoirDetail = { demande = Ecran.DETAIL },
                          surReglages = { demande = Ecran.REGLAGES })
    Ecran.DETAIL -> EcranDetail(etat, TravailSynchro.DOSSIERS_SAUVEGARDES)
    Ecran.REGLAGES -> EcranReglages(
        surDossiers = { demande = Ecran.DOSSIERS },
        surSauvegarde = { demande = Ecran.SAUVEGARDE },
        surAppareil = { demande = Ecran.APPAREIL })
    // Écrits aux tâches 5, 8 et 11.
    Ecran.DOSSIERS, Ecran.SAUVEGARDE, Ecran.APPAREIL -> EcranReglages(
        surDossiers = {}, surSauvegarde = {}, surAppareil = {})
}
```

Ajouter dans `ui/Ecrans.kt` le menu, et le bouton d'entrée sur l'accueil :

```kotlin
/** Menu des réglages : trois portes, rien d'autre. */
@Composable
fun EcranReglages(surDossiers: () -> Unit, surSauvegarde: () -> Unit,
                  surAppareil: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp),
           verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Réglages", style = MaterialTheme.typography.headlineMedium)
        Button(onClick = surDossiers, modifier = Modifier.fillMaxWidth()) {
            Text("Dossiers à sauvegarder")
        }
        Button(onClick = surSauvegarde, modifier = Modifier.fillMaxWidth()) {
            Text("Quand sauvegarder")
        }
        Button(onClick = surAppareil, modifier = Modifier.fillMaxWidth()) {
            Text("Cet appareil")
        }
    }
}
```

Ajouter à `EcranAccueil` deux paramètres — `surReglages: () -> Unit` et
`reglages: Reglages` — plus un bouton « Réglages » sous le bouton principal.
`reglages` sert dès la tâche 9 à choisir le seuil d'alerte ; le passer
maintenant évite de retoucher la signature deux fois.

```kotlin
@Composable
fun EcranAccueil(etat: EtatSynchro, reglages: Reglages, maintenantMs: Long,
                 surSynchroniser: () -> Unit, surInterrompre: () -> Unit,
                 surVoirDetail: () -> Unit, surReglages: () -> Unit) {
    val jours = EtatSynchro.joursDepuis(maintenantMs, etat.derniereReussiteMs)
    // Tache 9 : le seuil descend a 3 jours quand l'automatique est actif.
    val alerte = jours == null || jours >= EtatSynchro.seuilAlerteJours(reglages.auto)
    ...
}
```

> `seuilAlerteJours` n'existe qu'à la tâche 9. Jusque-là, garder
> `EtatSynchro.SEUIL_ALERTE_JOURS` et ne changer que cette ligne à la tâche 9.

- [ ] **Étape 7 : compiler et lancer TOUTE la suite**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest
```

Attendu : SUCCÈS, aucun test en échec.

- [ ] **Étape 8 : commettre**

```bash
cd /home/invisart/dev/phone_camera_import
git add android/
git commit -F - <<'FIN'
refactor(app): navigation explicite a la place de la cascade de booleens

Le lot 1 choisissait l'ecran par un `when` sur des drapeaux. A quatre
destinations ca tenait ; ce lot en ajoute trois, et chaque nouveau
drapeau croise tous les autres - les cas impossibles deviennent
atteignables sans qu'aucun test ne puisse le dire.

L'etat de navigation est desormais une valeur, et le bouton retour est
CALCULE au lieu d'etre devine. Le tout se verifie sur la JVM, ce qui
compte dans un projet sans aucun test d'instrumentation.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 5 : l'écran des dossiers, et la synchro qui les lit

**Fichiers :**
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/EcranDossiers.kt`
- Modifier : `android/.../ui/ModeleAccueil.kt`, `android/.../synchro/TravailSynchro.kt`,
  `android/.../MainActivity.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/TravailSynchroReglagesTest.kt`

**Interfaces :**
- Consomme : `Arbre.construire`, `Choix.resoudre`, `Choix.etat`, `Reglages`,
  `MagasinReglages`.
- Produit : `ModeleAccueil.reglages: StateFlow<Reglages>`,
  `ModeleAccueil.changerCoche(chemin: String, coche: Coche)`,
  `@Composable EcranDossiers(arbre, reglages, surCoche, surEntrer, surRemonter, chemin)`.

- [ ] **Étape 1 : écrire le test qui échoue**

Le point testable sur la JVM est que la synchronisation lise bien les réglages
au lieu de la constante. On extrait cette décision dans une fonction pure.

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.ui.Reglages
import org.junit.Assert.assertEquals
import org.junit.Test

class TravailSynchroReglagesTest {

    @Test
    fun `les dossiers synchronises viennent des reglages et non de la constante`() {
        val reglages = Reglages(dossiersSeuls = setOf("Pictures/Messages"))

        val choisis = TravailSynchro.dossiersASauvegarder(
            reglages, tous = setOf("Pictures/Messages", "DCIM/Camera"))

        assertEquals(setOf("Pictures/Messages"), choisis)
    }

    @Test
    fun `des reglages vierges sauvegardent les trois dossiers historiques`() {
        // Une mise a jour ne doit RIEN changer tant que l'utilisateur n'a pas
        // ouvert l'ecran.
        val choisis = TravailSynchro.dossiersASauvegarder(
            Reglages.DEFAUT,
            tous = setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp", "Download"))

        assertEquals(setOf("DCIM/Camera", "Pictures/WhatsApp", "Movies/WhatsApp"), choisis)
    }
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*TravailSynchroReglagesTest*"
```

Attendu : ÉCHEC, `Unresolved reference: dossiersASauvegarder`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

Dans le `companion object` de `TravailSynchro`, à la place de
`DOSSIERS_SAUVEGARDES` :

```kotlin
/**
 * Les dossiers à proposer au serveur, d'après ce que l'utilisateur a coché.
 *
 * Fonction séparée, et pure, pour être vérifiable sur la JVM : c'est le point
 * où le lot 1 décidait à la place de l'utilisateur, et sa régression serait
 * muette — la synchronisation réussirait en ne sauvegardant pas les bons
 * dossiers.
 */
fun dossiersASauvegarder(reglages: Reglages, tous: Set<String>): Set<String> =
    Choix.resoudre(tous, reglages.dossiersSeuls, reglages.dossiersRecursifs)
```

Conserver `DOSSIERS_SAUVEGARDES` : elle reste la valeur par défaut de
`Reglages.DEFAUT` et l'argument de `EcranDetail`.

Dans `doWork()`, remplacer l'appel :

```kotlin
val reglages = MagasinReglages(contexte).lire()
...
).synchroniser(reglages, interrompu = { isStopped })
```

et faire calculer `dossiersASauvegarder` par `Orchestrateur`, qui seul connaît
`source.lister()`. Modifier la signature :

```kotlin
fun synchroniser(
    reglages: Reglages,
    interrompu: () -> Boolean = { false },
): Bilan {
    val etat = serveur.horizon()
    val tous = source.lister()
    val dossiersChoisis = TravailSynchro.dossiersASauvegarder(
        reglages, tous.map { it.dossier }.toSet())
    ...
}
```

Mettre à jour `OrchestrateurTest` : remplacer chaque
`synchroniser(setOf("A"))` par `synchroniser(Reglages(dossiersSeuls = setOf("A")))`.

- [ ] **Étape 4 : lancer TOUTE la suite**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest
```

Attendu : SUCCÈS. Si `OrchestrateurTest` échoue, c'est l'adaptation de
signature — corriger les appels, pas les assertions.

- [ ] **Étape 5 : valider par mutation**

Remplacer le corps de `dossiersASauvegarder` par `DOSSIERS_SAUVEGARDES`.
Relancer : seul
`les dossiers synchronises viennent des reglages et non de la constante` doit
tomber. Restaurer.

- [ ] **Étape 6 : écrire l'écran**

Fichier `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/EcranDossiers.kt`.
Une ligne par nœud : la case, le libellé, le compte et la période, le bouton
« voir », le chevron. Un appui sur la case déplie les trois choix.

```kotlin
package fr.izquierdo.phototheque.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import fr.izquierdo.phototheque.synchro.Choix
import fr.izquierdo.phototheque.synchro.Coche
import fr.izquierdo.phototheque.synchro.Noeud

/**
 * Choix des dossiers à sauvegarder.
 *
 * Une case par ligne : un appui déplie trois choix explicites. Deux autres
 * formes ont été maquettées puis écartées — deux cases par ligne (deux cibles
 * voisines au pouce se ratent) et une case plus un bouton « tout » (un clic de
 * moins, mais un vocabulaire à apprendre).
 */
@Composable
fun EcranDossiers(
    racine: List<Noeud>,
    reglages: Reglages,
    surCoche: (String, Coche) -> Unit,
    surApercu: (String) -> Unit,
) {
    // Le chemin où l'on se trouve : la navigation DANS l'arbre est un état
    // local à cet écran, distinct de la navigation entre écrans.
    var chemin by rememberSaveable { mutableStateOf(listOf<String>()) }
    var deplie by rememberSaveable { mutableStateOf<String?>(null) }

    val courants = chemin.fold(racine) { niveau, libelle ->
        niveau.firstOrNull { it.libelle == libelle }?.enfants ?: emptyList()
    }

    Column(Modifier.fillMaxSize()) {
        // Fil d'Ariane : sans lui, on ne sait plus où l'on est passé six
        // niveaux plus bas.
        Text("📁 / " + chemin.joinToString(" / "),
             Modifier.padding(16.dp, 8.dp),
             style = MaterialTheme.typography.bodySmall)
        if (chemin.isNotEmpty()) {
            TextButton(onClick = { chemin = chemin.dropLast(1) }) { Text("← Remonter") }
        }
        LazyColumn(Modifier.weight(1f)) {
            items(courants, key = { it.chemin }) { noeud ->
                LigneDossier(
                    noeud = noeud,
                    coche = Choix.etat(noeud, reglages.dossiersSeuls,
                                       reglages.dossiersRecursifs),
                    deplie = deplie == noeud.chemin,
                    surDeplier = { deplie = if (deplie == noeud.chemin) null else noeud.chemin },
                    surChoix = { surCoche(noeud.chemin, it); deplie = null },
                    surEntrer = { chemin = chemin + noeud.libelle },
                    surApercu = { surApercu(noeud.chemin) })
            }
        }
    }
}

@Composable
private fun LigneDossier(
    noeud: Noeud, coche: Coche, deplie: Boolean,
    surDeplier: () -> Unit, surChoix: (Coche) -> Unit,
    surEntrer: () -> Unit, surApercu: () -> Unit,
) {
    Column {
        Row(Modifier.fillMaxWidth().padding(16.dp, 10.dp),
            verticalAlignment = Alignment.CenterVertically) {
            TriCase(coche, surDeplier)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f).clickable(enabled = noeud.enfants.isNotEmpty()) { surEntrer() }) {
                Text(noeud.libelle, style = MaterialTheme.typography.bodyLarge)
                Text(sousTitre(noeud), style = MaterialTheme.typography.bodySmall)
            }
            if (noeud.mediasTotal > 0) {
                TextButton(onClick = surApercu) { Text("voir") }
            }
            if (noeud.enfants.isNotEmpty()) {
                TextButton(onClick = surEntrer) { Text("›") }
            }
        }
        if (deplie) {
            // Les trois choix en clair. Le vocabulaire est la moitie de
            // l'affaire : « recursivement » ne veut rien dire pour personne.
            Column(Modifier.padding(start = 52.dp, bottom = 8.dp)) {
                ChoixLigne("Ce dossier seulement", coche == Coche.DOSSIER) { surChoix(Coche.DOSSIER) }
                ChoixLigne("Ce dossier et ses sous-dossiers", coche == Coche.RECURSIVE) { surChoix(Coche.RECURSIVE) }
                ChoixLigne("Ne pas sauvegarder", coche == Coche.AUCUNE) { surChoix(Coche.AUCUNE) }
            }
        }
    }
}

@Composable
private fun ChoixLigne(texte: String, actif: Boolean, surClic: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable { surClic() }.padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = actif, onClick = surClic)
        Text(texte)
    }
}

@Composable
private fun TriCase(coche: Coche, surClic: () -> Unit) {
    // TriStateCheckbox et non Checkbox : l'etat PARTIELLE doit se VOIR, sinon
    // on croit un dossier entierement pris alors qu'il ne l'est qu'a moitie.
    TriStateCheckbox(
        state = when (coche) {
            Coche.AUCUNE -> androidx.compose.ui.state.ToggleableState.Off
            Coche.PARTIELLE -> androidx.compose.ui.state.ToggleableState.Indeterminate
            Coche.DOSSIER, Coche.RECURSIVE -> androidx.compose.ui.state.ToggleableState.On
        },
        onClick = surClic)
}

/**
 * Les chiffres qui parlent : c'est eux, et non des vignettes, qui font
 * reconnaître un dossier. « tous < 50 Ko » démasque `.thumbnails` sans avoir à
 * l'ouvrir.
 */
private fun sousTitre(noeud: Noeud): String = buildString {
    append("${noeud.mediasTotal} média(s)")
    if (noeud.enfants.isNotEmpty()) append(" · ${noeud.enfants.size} sous-dossier(s)")
}
```

Dans `ModeleAccueil` :

```kotlin
private val magasin = MagasinReglages(application)
private val _reglages = MutableStateFlow(magasin.lire())
val reglages = _reglages.asStateFlow()

fun changerCoche(chemin: String, coche: Coche) {
    val r = _reglages.value
    val nouveau = r.copy(
        dossiersSeuls = if (coche == Coche.DOSSIER) r.dossiersSeuls + chemin
                        else r.dossiersSeuls - chemin,
        dossiersRecursifs = if (coche == Coche.RECURSIVE) r.dossiersRecursifs + chemin
                            else r.dossiersRecursifs - chemin)
    _reglages.value = nouveau
    magasin.ecrire(nouveau)
}
```

Brancher `Ecran.DOSSIERS` dans `MainActivity` sur `EcranDossiers`, alimenté par
`Arbre.construire(etat.dossiersVus ?: emptyMap())`.

- [ ] **Étape 7 : l'aperçu à la demande**

Le bouton « voir » de chaque ligne ouvre une grille pour **ce dossier seul**.
Trois vignettes sur chaque ligne ont été écartées : chaque ligne visible
déclencherait trois décodages d'image, avec cache et annulation au défilement,
et c'est la seule variante dont la lenteur se verrait. Ici, on ne décode que ce
qu'on demande.

Ajouter à `Depot` :

```kotlin
/**
 * Les premiers médias d'un dossier, pour l'aperçu.
 *
 * [limite] est bas et volontaire : l'aperçu sert à VÉRIFIER qu'on a bien
 * coché le bon dossier, pas à contempler. Charger davantage ferait payer un
 * décodage d'image à une question qui se tranche en un coup d'œil.
 */
fun apercu(dossier: String, limite: Int = 8): List<Media> =
    lister().filter { it.dossier == dossier }.sortedByDescending { it.instant }.take(limite)

/**
 * La vignette d'un média, ou `null` si elle est illisible.
 *
 * Un `null` n'est pas une anomalie : un fichier supprimé entre la requête
 * MediaStore et l'affichage est parfaitement ordinaire. Lever ici ferait
 * planter l'aperçu sur un dossier par ailleurs sain.
 */
fun vignette(media: Media, cote: Int = 256): android.graphics.Bitmap? = try {
    val base = if (media.estVideo) MediaStore.Video.Media.EXTERNAL_CONTENT_URI
               else MediaStore.Images.Media.EXTERNAL_CONTENT_URI
    context.contentResolver.loadThumbnail(
        ContentUris.withAppendedId(base, media.id),
        android.util.Size(cote, cote), null)
} catch (e: Exception) { null }
```

> `loadThumbnail` exige Android 10 (API 29). Vérifier le `minSdk` de
> `app/build.gradle.kts` : s'il est plus bas, encadrer par
> `Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q` et ne pas proposer le bouton
> « voir » en dessous, plutôt que d'afficher une grille vide.

Dans `EcranDossiers`, `surApercu` ouvre un `AlertDialog` contenant une
`LazyVerticalGrid` de quatre colonnes, alimentée par `depot.apercu(chemin)`, avec
le décodage fait hors du fil principal (`LaunchedEffect` + `Dispatchers.IO`) et
un pied de boîte qui dit « 8 premiers de N ».

- [ ] **Étape 8 : signaler les dossiers entrés par récursivité**

`Choix.nouveauxParRecursivite` existe depuis la tâche 3 mais rien ne l'affiche.
Dans `TravailSynchro`, à la fin d'une synchronisation réussie :

```kotlin
val vus = dossiersVus?.keys.orEmpty()
val magasin = MagasinReglages(contexte)
val avant = magasin.lire()
val nouveaux = Choix.nouveauxParRecursivite(
    vus, avant.dossiersConnus, avant.dossiersRecursifs)
// `dossiersConnus` est rangé DANS LE MÊME geste : sans cela, les mêmes
// dossiers seraient annoncés « nouveaux » à chaque synchronisation, et
// l'avertissement deviendrait un bruit qu'on apprend à ignorer.
magasin.ecrire(avant.copy(dossiersConnus = vus))
_derniereIssue.value = IssueSynchro(..., dossiersNouveaux = nouveaux)
```

Ajouter `dossiersNouveaux: Set<String> = emptySet()` à `IssueSynchro` et à
`EtatSynchro`, et l'afficher dans `EcranDetail` :

```kotlin
if (etat.dossiersNouveaux.isNotEmpty()) {
    Text("Nouveaux dossiers pris par une coche « et ses sous-dossiers » :")
    etat.dossiersNouveaux.sorted().forEach { Text("• $it") }
}
```

> **Attention au premier lancement.** `dossiersConnus` est vide par défaut :
> sans précaution, la toute première synchronisation annoncerait comme
> « nouveaux » TOUS les dossiers récursifs. Ne rien afficher quand
> `avant.dossiersConnus` est vide — se contenter de le remplir.

- [ ] **Étape 9 : lancer TOUTE la suite, puis commettre**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest
cd /home/invisart/dev/phone_camera_import && git add android/
git commit -F - <<'FIN'
feat(app): ecran de choix des dossiers, et synchro qui le lit

Les trois dossiers en dur de TravailSynchro deviennent la valeur par
defaut d'un reglage. dossiersASauvegarder() est extraite et pure : c'est
le point ou le lot 1 decidait a la place de l'utilisateur, et sa
regression serait MUETTE - la synchro reussirait en ne sauvegardant pas
les bons dossiers.

L'ecran presente une arborescence parcourable. Une case par ligne, qui
deplie trois choix en clair ; TriStateCheckbox pour que l'etat partiel
se VOIE, sinon on croit un dossier entierement pris alors qu'il ne l'est
qu'a moitie.

Les lignes portent des chiffres, pas des vignettes : trois vignettes par
ligne feraient decoder trois images a chaque ligne visible, et c'est la
seule variante dont la lenteur se verrait. L'apercu est a la demande,
pour le seul dossier dont on doute.

Les dossiers entres par une coche recursive depuis la derniere synchro
sont signales. Une coche recursive est une delegation dans le temps :
elle prendra demain des dossiers qui n'existent pas aujourd'hui.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 6 : l'horizon devient monotone

**C'est le test le plus important du lot.**

**Fichiers :**
- Modifier : `android/.../synchro/Horizons.kt`, `android/.../synchro/Orchestrateur.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/HorizonsTest.kt`

**Interfaces :**
- Consomme : `ResultatHorizons` (existant).
- Produit : `Horizons.monotone(nouveaux: Map<String, Double>, connus: Map<String, Double>): Map<String, Double>`.

- [ ] **Étape 1 : écrire le test qui échoue**

À ajouter dans `HorizonsTest.kt` :

```kotlin
@Test
fun `un horizon ne recule jamais`() {
    // Le telephone a tout jusqu'en septembre 2026. Une fenetre 2019-2020 est
    // posee pour rattraper du vieux. Sans cette regle, le commit envoie
    // « fin 2020 » et le serveur ECRASE la memoire de 2026 : la nuit suivante,
    // six ans de medias sont reproposes. Rien n'est perdu ni renvoye deux
    // fois, mais le telephone relit tout, a chaque fois.
    val nouveaux = mapOf("DCIM/Camera" to 1_609_459_200.0)   // 01/01/2021
    val connus = mapOf("DCIM/Camera" to 1_789_000_000.0)     // 2026

    assertEquals(mapOf("DCIM/Camera" to 1_789_000_000.0),
                 Horizons.monotone(nouveaux, connus))
}

@Test
fun `un horizon avance normalement quand il progresse`() {
    val nouveaux = mapOf("DCIM/Camera" to 1_789_000_000.0)
    val connus = mapOf("DCIM/Camera" to 1_609_459_200.0)

    assertEquals(mapOf("DCIM/Camera" to 1_789_000_000.0),
                 Horizons.monotone(nouveaux, connus))
}

@Test
fun `un dossier sans horizon connu garde sa valeur neuve`() {
    // Premier passage sur un dossier qu'on vient de cocher : il n'y a pas de
    // plancher a respecter, et en inventer un sauterait des medias.
    assertEquals(mapOf("Pictures/Messages" to 42.0),
                 Horizons.monotone(mapOf("Pictures/Messages" to 42.0), emptyMap()))
}

@Test
fun `un dossier connu mais absent du lot n'est pas reenvoye`() {
    // On ne transmet QUE ce que ce paquet a touche : renvoyer les autres
    // ferait ecrire au serveur des horizons qu'aucun envoi ne justifie.
    assertEquals(emptyMap<String, Double>(),
                 Horizons.monotone(emptyMap(), mapOf("DCIM/Camera" to 1.0)))
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*HorizonsTest*"
```

Attendu : ÉCHEC, `Unresolved reference: monotone`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

Dans `object Horizons` :

```kotlin
/**
 * Les horizons à transmettre, bornés par ceux que le serveur connaît déjà.
 *
 * L'horizon signifie « tout ce qui est plus récent que cette date a été
 * proposé ». Reproposer du plus ancien ne le rend pas faux : il ne doit donc
 * JAMAIS reculer tout seul.
 *
 * Sans cette borne, une fenêtre de rattrapage 2019-2020 posée sur un téléphone
 * déjà synchronisé jusqu'en septembre 2026 ferait écrire « fin 2020 » au
 * serveur — `set_horizon` (`phototheque/devices.py:189`) écrit tel quel ce
 * qu'on lui envoie, et la boucle de commit ne borne que par le haut. La
 * mémoire de 2026 serait effacée et six ans de médias reproposés chaque nuit.
 *
 * Seuls les dossiers présents dans [nouveaux] ressortent : transmettre les
 * autres ferait écrire au serveur des horizons qu'aucun envoi ne justifie.
 */
fun monotone(
    nouveaux: Map<String, Double>,
    connus: Map<String, Double>,
): Map<String, Double> =
    nouveaux.mapValues { (dossier, valeur) -> maxOf(valeur, connus[dossier] ?: valeur) }
```

Dans `Orchestrateur.synchroniser`, au moment du commit de chaque paquet,
remplacer `resultat.horizons` par sa version bornée :

```kotlin
val aTransmettre = Horizons.monotone(resultat.horizons, etat.dossiers)
val bilanPaquet = serveur.commit(reponse.session, aTransmettre)
```

- [ ] **Étape 4 : lancer le test et vérifier qu'il passe**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*HorizonsTest*"
```

Attendu : SUCCÈS.

- [ ] **Étape 5 : valider par mutation**

Remplacer `maxOf(valeur, connus[dossier] ?: valeur)` par `valeur`. Relancer :
seul `un horizon ne recule jamais` doit tomber. Restaurer.

Remplacer `connus[dossier] ?: valeur` par `connus[dossier] ?: 0.0`. Relancer :
`un dossier sans horizon connu garde sa valeur neuve` doit **passer** (0.0 est
plus petit) — ce n'est donc pas une mutation utile. Utiliser plutôt
`connus[dossier] ?: Double.MAX_VALUE` : ce test-là doit tomber. Restaurer.

### ⚠️ Le câblage dans `Orchestrateur` n'est PAS couvrable à cette tâche

Ne cherche pas à écrire un test bout-en-bout ici, et ne t'inquiète pas si
remettre `resultat.horizons` à la place de `aTransmettre` ne fait tomber aucun
test : **c'est attendu, et démontrable.**

Le plancher de sélection d'un média vaut `horizons[dossier] ?: depuis`
(`Selection.kt`). Un média retenu a donc toujours `instant >= horizon connu`, et
l'horizon calculé par `Horizons.calculer` — la date du dernier fichier confirmé
— est forcément supérieur ou égal à celui-là. `monotone` ne peut donc jamais
mordre tant que rien ne permet de descendre **sous** l'horizon connu.

Ce qui le permet, c'est l'**ordre de reprise** de la tâche 7 (`plancherReprise`).
C'est donc la tâche 7 qui porte le test bout-en-bout, et elle le fait.

À cette tâche, la couverture est celle des quatre tests unitaires de
`Horizons.monotone` ci-dessus. Le câblage d'une seule ligne dans `Orchestrateur`
est relu, pas exécuté — et c'est assumé.

- [ ] **Étape 6 : commettre**

```bash
cd /home/invisart/dev/phone_camera_import && git add android/
git commit -F - <<'FIN'
fix(app): l'horizon ne recule plus tout seul

L'horizon signifie « tout ce qui est plus recent que cette date a ete
propose ». Reproposer du plus ancien ne le rend pas faux : il ne doit
donc jamais reculer.

Sans cette borne, une fenetre 2019-2020 posee sur un telephone deja
synchronise jusqu'en septembre 2026 faisait ecrire « fin 2020 » au
serveur - set_horizon ecrit tel quel ce qu'on lui envoie, et la boucle
de commit ne borne que par le haut. La memoire de 2026 etait effacee et
six ans de medias reproposes chaque nuit. Rien n'etait perdu ni renvoye
deux fois, mais le telephone relisait tout.

Corrige entierement cote application : le serveur et le contrat ne
changent pas.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 7 : l'ordre de reprise

**Fichiers :**
- Modifier : `android/.../synchro/Selection.kt`, `android/.../synchro/Orchestrateur.kt`,
  `android/.../ui/Reglages.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/SelectionTest.kt`

**Interfaces :**
- Consomme : `Reglages.debutJour`, `Reglages.debutApplique` (tâche 1),
  `Selection.candidats` (existant).
- Produit : `Selection.candidats(..., planchierReprise: Double?)` — paramètre
  supplémentaire ; `Reglages.repriseADemander(): Boolean`.

> **Note sur la spec.** La spec §4.3 décrit l'ordre de reprise comme une
> réécriture de l'horizon serveur, et en tire un coût : « une fenêtre fermée
> laisse l'horizon à la fin de la fenêtre, donc la sauvegarde suivante relit
> tout ». **Avec la monotonie de la tâche 6, ce coût disparaît** : le commit
> transmet `max(2020, 2026) = 2026`, la mémoire de 2026 survit au rattrapage, et
> rien n'est relu ensuite. L'ordre de reprise n'a donc pas besoin de toucher à
> l'horizon serveur — il suffit d'abaisser le plancher de SÉLECTION pour une
> synchronisation. C'est plus simple, et supérieur au comportement spécifié.
> Mettre la spec à jour à la tâche 12.

- [ ] **Étape 1 : écrire le test qui échoue**

À ajouter dans `SelectionTest.kt` :

```kotlin
@Test
fun `un ordre de reprise passe sous l'horizon connu`() {
    // Abaisser la date de debut doit REPROPOSER les vieux medias. Sans ce
    // plancher, `horizons[dossier] ?: depuis` fait toujours gagner l'horizon
    // et la date de debut ne peut rien reprendre du tout.
    val vieux = Media(1, "DCIM/Camera", "a.jpg", 10, instant = 100.0)
    val recent = Media(2, "DCIM/Camera", "b.jpg", 10, instant = 900.0)

    val candidats = Selection.candidats(
        medias = listOf(vieux, recent),
        dossiersChoisis = setOf("DCIM/Camera"),
        horizons = mapOf("DCIM/Camera" to 500.0),
        depuisSecondes = null,
        plancherReprise = 50.0)

    assertEquals(listOf(vieux, recent), candidats)
}

@Test
fun `sans ordre de reprise l'horizon commande toujours`() {
    val vieux = Media(1, "DCIM/Camera", "a.jpg", 10, instant = 100.0)
    val recent = Media(2, "DCIM/Camera", "b.jpg", 10, instant = 900.0)

    val candidats = Selection.candidats(
        medias = listOf(vieux, recent),
        dossiersChoisis = setOf("DCIM/Camera"),
        horizons = mapOf("DCIM/Camera" to 500.0),
        depuisSecondes = null,
        plancherReprise = null)

    assertEquals(listOf(recent), candidats)
}

@Test
fun `un ordre de reprise plus haut que l'horizon ne saute aucun media`() {
    // Reprendre « depuis 2020 » sur un dossier dont l'horizon est a 2019 ne
    // doit pas fermer la fenetre 2019-2020 : la reprise ABAISSE le plancher,
    // elle ne le remonte jamais.
    val media = Media(1, "DCIM/Camera", "a.jpg", 10, instant = 300.0)

    val candidats = Selection.candidats(
        medias = listOf(media),
        dossiersChoisis = setOf("DCIM/Camera"),
        horizons = mapOf("DCIM/Camera" to 200.0),
        depuisSecondes = null,
        plancherReprise = 500.0)

    assertEquals(listOf(media), candidats)
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*SelectionTest*"
```

Attendu : ÉCHEC de compilation, paramètre `plancherReprise` inconnu.

- [ ] **Étape 3 : écrire l'implémentation minimale**

Dans `Selection.candidats`, ajouter le paramètre et abaisser le plancher :

```kotlin
/**
 * @param plancherReprise ordre ponctuel d'aller rechercher du plus ancien.
 *   `null` en régime normal. Quand il vaut quelque chose, il ABAISSE le
 *   plancher de chaque dossier — il ne le remonte jamais, sinon reprendre
 *   « depuis 2020 » fermerait la fenêtre 2019-2020 d'un dossier dont
 *   l'horizon est à 2019.
 *
 *   C'est ce paramètre, et non une réécriture d'horizon côté serveur, qui fait
 *   qu'abaisser la date de début repropose les vieux médias. La monotonie
 *   (voir [Horizons.monotone]) garantit que le rattrapage ne fera pas
 *   redescendre l'horizon enregistré.
 */
fun candidats(
    medias: List<Media>,
    dossiersChoisis: Set<String>,
    horizons: Map<String, Double>,
    depuisSecondes: Double?,
    plancherReprise: Double? = null,
): List<Media> = medias
    .filter { it.dossier in dossiersChoisis }
    .filter { media ->
        val normal = horizons[media.dossier] ?: depuisSecondes
        val plancher = when {
            plancherReprise == null -> normal
            normal == null -> plancherReprise
            else -> minOf(normal, plancherReprise)
        }
        plancher == null || media.instant >= plancher
    }
    .sortedBy { it.instant }
```

Dans `Reglages` :

```kotlin
/**
 * Vrai si la date de début a changé depuis la dernière reprise menée à son
 * terme. C'est ce qui fait qu'abaisser la date repropose les vieux médias
 * UNE FOIS et non chaque nuit.
 */
fun repriseADemander(): Boolean = debutJour != null && debutJour != debutApplique
```

Dans `Orchestrateur.synchroniser`, calculer le plancher et le passer :

```kotlin
val plancherReprise =
    if (reglages.repriseADemander()) reglages.debutJour?.let { jourVersSecondes(it) }
    else null
val candidats = Selection.candidats(
    tous, dossiersChoisis, etat.dossiers, depuis, plancherReprise)
```

Le rangement de `debutApplique = debutJour` appartient à `TravailSynchro`, à la
seule condition d'une synchronisation **complète et réussie** — une reprise
coupée en deux doit se rejouer :

```kotlin
if (!bilan.interrompu && EtatSynchro.estUneReussite(bilan, depot.accesRefuse())) {
    Memoire(contexte).enregistrerReussite(System.currentTimeMillis())
    val magasin = MagasinReglages(contexte)
    magasin.ecrire(magasin.lire().copy(debutApplique = reglages.debutJour))
}
```

- [ ] **Étape 4 : lancer TOUTE la suite**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest
```

Attendu : SUCCÈS.

- [ ] **Étape 5 : valider par mutation**

Remplacer `minOf(normal, plancherReprise)` par `maxOf(normal, plancherReprise)`.
Relancer : `un ordre de reprise passe sous l'horizon connu` doit tomber.
Restaurer.

Remplacer `plancherReprise == null -> normal` par
`plancherReprise == null -> plancherReprise`. Relancer :
`sans ordre de reprise l'horizon commande toujours` doit tomber. Restaurer.

**Et le test bout-en-bout de la monotonie, qui n'était pas écrivable à la tâche
6.** C'est seulement maintenant qu'un média peut être retenu *sous* l'horizon
connu, donc seulement maintenant que `Horizons.monotone` peut mordre. Ajouter à
`OrchestrateurTest.kt` — les doublures `FauxServeur` et `FausseSource`, ainsi que
l'aide `media(instant, nom)`, existent déjà dans ce fichier :

```kotlin
    @Test fun un_rattrapage_ancien_n_efface_pas_la_memoire_des_synchros_recentes() {
        // Le serveur connait deja septembre 2026 ; le rattrapage ne contient
        // que du 2021. Sans la monotonie (tache 6), le commit renverrait 2021
        // et le serveur ECRASERAIT la memoire de 2026 : la nuit suivante,
        // cinq ans de medias seraient reproposes, relus, et rejetes un par un
        // par l'anti-doublon.
        val vieux = media(1_609_459_200.0)                 // 01/01/2021
        val serveur = FauxServeur(horizons = mapOf("DCIM/Camera" to 1_789_000_000.0))

        Orchestrateur(FausseSource(listOf(vieux)), serveur).synchroniser(
            Reglages(dossiersSeuls = setOf("DCIM/Camera"), debutJour = "2020-01-01"))

        assertEquals(1_789_000_000.0,
                     serveur.commits.last().getValue("DCIM/Camera"), 0.001)
    }
```

Le valider par mutation : remettre `resultat.horizons` à la place de
`aTransmettre` dans `Orchestrateur` (le câblage de la tâche 6). **Ce test doit
tomber** — c'est lui, et lui seul, qui prouve que la monotonie est branchée.
Restaurer.

- [ ] **Étape 6 : commettre**

```bash
cd /home/invisart/dev/phone_camera_import && git add android/
git commit -F - <<'FIN'
feat(app): abaisser la date de debut repropose les vieux medias

C'est un ORDRE, pas un plancher permanent : sans ce parametre,
`horizons[dossier] ?: depuis` fait toujours gagner l'horizon et la date
de debut ne peut rien reprendre du tout.

Il abaisse le plancher, jamais ne le remonte : reprendre « depuis 2020 »
sur un dossier dont l'horizon est a 2019 ne doit pas fermer la fenetre
2019-2020.

Il ne s'applique QU'UNE FOIS : debutApplique n'est range qu'apres une
synchro complete et reussie, donc une reprise coupee en deux se rejoue.

La spec prevoyait de reecrire l'horizon serveur, et en tirait un cout de
relecture apres une fenetre fermee. La monotonie rend cela inutile : le
commit transmet max(2020, 2026), la memoire de 2026 survit, et rien
n'est relu ensuite. Spec corrigee.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 8 : l'écran de sauvegarde (dates, auto, hors fenêtre)

**Fichiers :**
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/EcranSauvegarde.kt`
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Fenetre.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/FenetreTest.kt`

**Interfaces :**
- Consomme : `Reglages`, `Media`.
- Produit : `Fenetre.dansLaFenetre(media: Media, debut: String?, fin: String?): Boolean`,
  `Fenetre.horsFenetre(medias: List<Media>, debut: String?, fin: String?): Int`.

- [ ] **Étape 1 : écrire le test qui échoue**

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import java.time.LocalDateTime
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FenetreTest {

    private fun media(instant: Double) = Media(1, "DCIM/Camera", "a.jpg", 10, instant)

    /** Un instant reel, construit hors de Fenetre : c'est ce qui empeche ces
     *  tests d'etre auto-coherents et donc vides de sens. */
    private fun instantLocal(quand: String, fuseau: String): Double =
        LocalDateTime.parse(quand).atZone(ZoneId.of(fuseau)).toEpochSecond().toDouble()

    @Test fun sans_bornes_tout_est_dans_la_fenetre() {
        assertTrue(Fenetre.dansLaFenetre(media(0.0), null, null))
        assertTrue(Fenetre.dansLaFenetre(media(9e9), null, null))
    }

    @Test fun la_borne_de_fin_couvre_la_soiree_du_dernier_jour_partout() {
        // LE test de cette tache. Une photo prise le 15 a 23 h doit rester
        // DANS une fenetre qui finit le 15 — a Paris comme a Tokyo comme a
        // Los Angeles. Une borne calee sur minuit UTC, ou pire sur le debut de
        // jour + 24 h, couperait l'apres-midi et la soiree du dernier jour
        // sans un mot.
        for (fuseau in listOf("Europe/Paris", "Asia/Tokyo", "America/Los_Angeles")) {
            val tard = instantLocal("2026-09-15T23:00", fuseau)
            assertTrue(fuseau, Fenetre.dansLaFenetre(media(tard), null, "2026-09-15"))
        }
    }

    @Test fun la_borne_de_debut_couvre_le_petit_matin_du_premier_jour_partout() {
        for (fuseau in listOf("Europe/Paris", "Asia/Tokyo", "America/Los_Angeles")) {
            val tot = instantLocal("2026-09-15T00:30", fuseau)
            assertTrue(fuseau, Fenetre.dansLaFenetre(media(tot), "2026-09-15", null))
        }
    }

    @Test fun la_borne_de_fin_ecarte_bien_les_jours_suivants() {
        // La contrepartie : trop large ne veut pas dire sans borne.
        val bienApres = instantLocal("2026-09-20T12:00", "Europe/Paris")
        assertFalse(Fenetre.dansLaFenetre(media(bienApres), null, "2026-09-15"))
    }

    @Test fun une_fenetre_inversee_ne_retient_rien_et_ne_leve_pas() {
        // Debut apres fin : l'utilisateur s'est trompe. Zero media, et
        // l'ecran doit le DIRE - pas un comportement indefini.
        val m = media(instantLocal("2026-06-01T12:00", "Europe/Paris"))
        assertFalse(Fenetre.dansLaFenetre(m, debut = "2026-09-01", fin = "2026-01-01"))
    }

    @Test fun hors_fenetre_compte_ce_que_la_fenetre_laisse_dehors() {
        val medias = listOf(
            media(instantLocal("2019-01-01T12:00", "Europe/Paris")),
            media(instantLocal("2026-09-20T12:00", "Europe/Paris")),
            media(instantLocal("2026-09-21T12:00", "Europe/Paris")))

        assertEquals(2, Fenetre.horsFenetre(medias, debut = null, fin = "2026-01-01"))
    }
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*FenetreTest*"
```

Attendu : ÉCHEC, `Unresolved reference: Fenetre`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

```kotlin
package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.medias.Media
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * La fenêtre de dates choisie par l'utilisateur.
 *
 * Les bornes sont des jours ISO, pas des instants : une date saisie par un
 * humain porte sur un jour entier.
 *
 * **Chaque borne est élargie dans SON sens**, et c'est délibéré. Le téléphone
 * ne sait pas dans quel fuseau une photo a été prise : `instant` est un
 * horodatage absolu, et « le 15 septembre » ne désigne pas le même intervalle
 * à Paris, à Tokyo et à Los Angeles. Une borne trop étroite écarterait des
 * médias en silence — une borne trop large en repropose quelques heures de
 * trop, que l'anti-doublon du serveur écarte sans les transférer. Le choix
 * est donc toujours le même : **reproposer plutôt que sauter.**
 */
object Fenetre {

    /**
     * Le tout premier instant qui peut appartenir à ce jour, où que ce soit :
     * minuit au fuseau le plus en avance (UTC+14).
     *
     * Même raisonnement, et même valeur, que la fonction qu'`Orchestrateur`
     * utilisait pour l'horizon : vers l'est, la borne ne peut qu'être trop
     * généreuse ; vers l'ouest, elle sauterait des médias.
     */
    fun debutDuJour(jour: String): Double =
        LocalDate.parse(jour).atStartOfDay(ZoneOffset.ofHours(14)).toEpochSecond().toDouble()

    /**
     * Le premier instant qui n'appartient PLUS à ce jour, où que ce soit :
     * minuit du lendemain au fuseau le plus en retard (UTC-12). Borne
     * **exclusive**.
     *
     * Réutiliser [debutDuJour] en y ajoutant 24 h serait le piège : la fenêtre
     * s'arrêterait à midi UTC le jour choisi, c'est-à-dire **vers 14 h à
     * Paris**. Toutes les photos de l'après-midi et de la soirée du dernier
     * jour disparaîtraient, sans un mot.
     */
    fun finDuJour(jour: String): Double =
        LocalDate.parse(jour).plusDays(1)
            .atStartOfDay(ZoneOffset.ofHours(-12)).toEpochSecond().toDouble()

    fun dansLaFenetre(media: Media, debut: String?, fin: String?): Boolean {
        if (debut != null && media.instant < debutDuJour(debut)) return false
        if (fin != null && media.instant >= finDuJour(fin)) return false
        return true
    }

    /**
     * Combien de médias la fenêtre laisse dehors.
     *
     * Ce nombre doit être affiché EN PERMANENCE. Une fenêtre est un filtre, et
     * un filtre muet est une panne silencieuse : c'est exactement le piège de
     * la date de fin oubliée.
     */
    fun horsFenetre(medias: List<Media>, debut: String?, fin: String?): Int =
        medias.count { !dansLaFenetre(it, debut, fin) }
}
```

Brancher la fenêtre dans `Orchestrateur.synchroniser`, après `Selection.candidats` :

```kotlin
val candidats = Selection.candidats(tous, dossiersChoisis, etat.dossiers, depuis, plancherReprise)
    .filter { Fenetre.dansLaFenetre(it, reglages.debutJour, reglages.finJour) }
```

- [ ] **Étape 4 : lancer le test et vérifier qu'il passe**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*FenetreTest*"
```

Attendu : SUCCÈS, 4 tests.

- [ ] **Étape 5 : valider par mutation**

Remplacer `finDuJour` par `debutDuJour(jour) + 86_400.0` — le piège exact.
Relancer : `la_borne_de_fin_couvre_la_soiree_du_dernier_jour_partout` doit
tomber. Restaurer.

Puis remplacer l'ancrage de `debutDuJour` par `ZoneOffset.UTC`. Relancer :
`la_borne_de_debut_couvre_le_petit_matin_du_premier_jour_partout` doit tomber
(sur les fuseaux à l'est). Restaurer.

- [ ] **Étape 6 : écrire l'écran**

`EcranSauvegarde` affiche : les deux sélecteurs de date, l'interrupteur
« Sauvegarder automatiquement », et **en permanence** le compte de médias hors
fenêtre. Cocher l'automatique appelle `Reglages.enAuto()` et affiche le message
qui dit que la date de fin a été effacée. Quand l'automatique est actif, la date
de fin est **grisée et visible**, pas cachée.

```kotlin
if (reglages.auto) {
    Text("La date de fin a été retirée : en automatique, la sauvegarde " +
         "reprend depuis la dernière date et ne s'arrête plus.",
         style = MaterialTheme.typography.bodySmall)
}
if (horsFenetre > 0) {
    // En permanence, et pas seulement en cas de probleme : c'est le seul
    // garde-fou contre une borne oubliee.
    Text("$horsFenetre média(s) sont hors de cette fenêtre et ne seront pas " +
         "sauvegardés.", style = MaterialTheme.typography.bodyMedium)
}
```

- [ ] **Étape 7 : lancer TOUTE la suite, puis commettre**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest
cd /home/invisart/dev/phone_camera_import && git add android/
git commit -F - <<'FIN'
feat(app): fenetre de dates pilotee depuis le telephone

La borne haute inclut son jour : comparer a minuit ferait disparaitre
toutes les photos du dernier jour de la fenetre, et personne ne
comprendrait pourquoi.

Le nombre de medias HORS fenetre est affiche en permanence. Une fenetre
est un filtre, et un filtre muet est une panne silencieuse - c'est
exactement le piege de la date de fin oubliee.

Une fenetre inversee retient zero media et le dit, au lieu d'un
comportement indefini.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 9 : la synchronisation automatique

**Fichiers :**
- Modifier : `android/.../synchro/TravailSynchro.kt`, `android/.../ui/EtatSynchro.kt`,
  `android/.../ui/ModeleAccueil.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/ui/EtatSynchroTest.kt`

**Interfaces :**
- Consomme : `Reglages.auto`.
- Produit : `TravailSynchro.planifier(context, actif: Boolean)`,
  `EtatSynchro.seuilAlerteJours(auto: Boolean): Long`.

- [ ] **Étape 1 : écrire le test qui échoue**

À ajouter dans `EtatSynchroTest.kt` :

```kotlin
@Test
fun `le seuil d'alerte descend a trois jours en automatique`() {
    // Sept jours sans geste volontaire n'ont rien d'anormal ; trois nuits
    // sans passe automatique, si. Sans ce seuil, l'automatique devient un
    // silence qu'on prend pour un succes - le piege de la date de fin
    // oubliee, sous un autre habit.
    assertEquals(3L, EtatSynchro.seuilAlerteJours(auto = true))
    assertEquals(7L, EtatSynchro.seuilAlerteJours(auto = false))
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*EtatSynchroTest*"
```

Attendu : ÉCHEC, `Unresolved reference: seuilAlerteJours`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

Dans le `companion object` de `EtatSynchro` :

```kotlin
/** Au-delà, l'accueil passe en avertissement (mode manuel). */
const val SEUIL_ALERTE_JOURS = 7L

/** Au-delà, l'accueil passe en avertissement quand l'automatique est actif. */
const val SEUIL_ALERTE_AUTO_JOURS = 3L

/**
 * Le seuil qui s'applique.
 *
 * En automatique, la passe a lieu chaque nuit au branchement du téléphone :
 * trois jours de silence sont déjà une anomalie. En manuel, sept jours sans
 * geste volontaire n'ont rien d'étonnant. Garder sept dans les deux cas
 * laisserait une panne d'automatique invisible une semaine entière.
 */
fun seuilAlerteJours(auto: Boolean): Long =
    if (auto) SEUIL_ALERTE_AUTO_JOURS else SEUIL_ALERTE_JOURS
```

Dans `EcranAccueil`, remplacer l'unique `EtatSynchro.SEUIL_ALERTE_JOURS` par
`EtatSynchro.seuilAlerteJours(reglages.auto)` — le paramètre `reglages` a été
ajouté à la tâche 4 précisément pour ça.

Dans le `companion object` de `TravailSynchro` :

```kotlin
private const val NOM_PERIODIQUE = "synchro-auto"

/**
 * Programme, ou déprogramme, la sauvegarde automatique.
 *
 * Six heures n'est PAS un réveil à heure fixe : c'est « au plus une fois par
 * tranche de six heures, dès que les conditions sont réunies ». Android
 * regroupe ces réveils (mode Doze), le délai peut donc glisser à sept ou huit
 * heures si le téléphone dort — jamais se déclencher plus tôt. En pratique,
 * avec ces deux contraintes, cela donne une passe par nuit, au branchement du
 * téléphone à la maison.
 *
 * `setRequiresCharging(true)` n'est pas un luxe : un gros rattrapage lit des
 * dizaines de milliers d'empreintes, c'est du calcul, et le faire sur batterie
 * en pleine journée viderait le téléphone.
 *
 * `UNMETERED` et non `CONNECTED` : le rattrapage peut représenter des
 * dizaines de gigaoctets, et l'utilisateur ne s'attend pas à les voir partir
 * sur son forfait.
 */
fun planifier(context: Context, actif: Boolean) {
    val gestionnaire = WorkManager.getInstance(context)
    if (!actif) {
        gestionnaire.cancelUniqueWork(NOM_PERIODIQUE)
        return
    }
    val demande = PeriodicWorkRequestBuilder<TravailSynchro>(6, TimeUnit.HOURS)
        .setConstraints(Constraints.Builder()
            .setRequiredNetworkType(NetworkType.UNMETERED)
            .setRequiresCharging(true)
            .build())
        .setBackoffCriteria(BackoffPolicy.EXPONENTIAL,
                            WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
        .build()
    // KEEP : reprogrammer a chaque ouverture de l'ecran remettrait le compteur
    // a zero, et la passe n'aurait jamais lieu sur un telephone qu'on ouvre
    // souvent.
    gestionnaire.enqueueUniquePeriodicWork(
        NOM_PERIODIQUE, ExistingPeriodicWorkPolicy.KEEP, demande)
}
```

Dans `ModeleAccueil`, appeler `TravailSynchro.planifier` à chaque changement de
`reglages.auto`, et au démarrage.

- [ ] **Étape 4 : lancer TOUTE la suite**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest
```

Attendu : SUCCÈS.

- [ ] **Étape 5 : valider par mutation**

Remplacer `if (auto) SEUIL_ALERTE_AUTO_JOURS else SEUIL_ALERTE_JOURS` par
`SEUIL_ALERTE_JOURS`. Relancer : seul
`le seuil d'alerte descend a trois jours en automatique` doit tomber. Restaurer.

- [ ] **Étape 6 : vérifier le manifeste FUSIONNÉ**

Le manifeste qui compte n'est pas la source. `WorkManager` déclare son propre
service de premier plan, et un `foregroundServiceType` manquant fait planter
tout appareil depuis Android 10 — invisible à la compilation et aux tests.

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew assembleDebug
grep -c foregroundServiceType \
  app/build/intermediates/merged_manifests/debug/processDebugManifest/AndroidManifest.xml
```

Attendu : au moins 2. Si le compte a baissé, le `tools:node="merge"` a sauté.

- [ ] **Étape 7 : commettre**

```bash
cd /home/invisart/dev/phone_camera_import && git add android/
git commit -F - <<'FIN'
feat(app): sauvegarde automatique, WiFi non facture et telephone en charge

Six heures n'est pas un reveil a heure fixe : c'est « au plus une fois
par tranche de six heures, des que les conditions sont reunies ».
Android regroupe ces reveils (Doze), le delai peut glisser a sept ou
huit heures - jamais se declencher plus tot. En pratique : une passe par
nuit, au branchement du telephone a la maison.

La charge n'est pas un luxe : un gros rattrapage lit des dizaines de
milliers d'empreintes, c'est du calcul. UNMETERED non plus : le
rattrapage peut faire des dizaines de gigaoctets.

Le seuil d'alerte descend a trois jours quand l'automatique est actif.
Sept jours sans geste volontaire n'ont rien d'anormal ; trois nuits sans
passe automatique, si. Sans ce seuil, l'automatique devient un silence
qu'on prend pour un succes.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 10 : les deux retouches du serveur

**Fichiers :**
- Modifier : `phototheque/devices.py`, `phototheque/app.py`
- Test : `tests/test_devices.py`, `tests/test_app.py`

**Interfaces :**
- Produit : `POST /sync/desappairer` (authentifiée par le jeton d'appareil),
  et `Devices.revoke()` qui supprime aussi les horizons.

- [ ] **Étape 1 : écrire les tests qui échouent**

Dans `tests/test_devices.py` :

```python
def test_revoquer_un_appareil_supprime_aussi_ses_horizons(tmp_path):
    """La table horizons n'a ni cle etrangere ni ON DELETE CASCADE.

    Et `PRAGMA foreign_keys` n'est jamais active (SQLite le laisse inactif par
    defaut) : sans suppression explicite, chaque revocation laisse ses lignes
    d'horizon orphelines, definitivement. Sans consequence de correction —
    l'identifiant d'appareil est un uuid4 tire a chaque appairage — mais c'est
    une fuite qui ne se repare jamais, et ce lot en multiplie les lignes.
    """
    from phototheque.devices import DeviceStore
    store = DeviceStore(tmp_path / "dev.db")
    dev_id, _ = store.pair("Pixel")
    store.set_horizon(dev_id, "DCIM/Camera", 1726574400.0)

    assert store.revoke(dev_id) is True

    assert store.get_horizons(dev_id) == {}
    store.close()
```

Dans `tests/test_app.py` :

```python
def test_le_telephone_peut_se_desappairer_lui_meme(tmp_path, monkeypatch):
    """Le telephone n'a qu'un jeton d'appareil, pas le mot de passe d'admin.

    Sans cette route il ne PEUT PAS se retirer : la seule revocation existante
    est derriere require_admin. Et le jour ou il en a besoin — certificat du
    NUC change — le TLS echoue avant le HTTP, donc aucun 401 n'arrive jamais,
    donc `oublier()` n'est pas declenche et l'ecran de scan est inatteignable.
    """
    a, client = _client(tmp_path, monkeypatch)
    dev_id, secret = a.devices().pair("Pixel")
    h = {"Authorization": f"Bearer {secret}"}
    a.devices().set_horizon(dev_id, "DCIM/Camera", 1726574400.0)

    r = client.post("/sync/desappairer", headers=h)

    assert r.status_code == 200
    assert client.get("/status", headers=h).status_code == 401
    assert a.devices().get_horizons(dev_id) == {}


def test_le_desappairage_exige_un_jeton_d_appareil(tmp_path, monkeypatch):
    """Sans jeton, personne ne fait deconnecter le telephone de quelqu'un."""
    a, client = _client(tmp_path, monkeypatch)
    assert client.post("/sync/desappairer").status_code == 401
```

- [ ] **Étape 2 : lancer les tests et vérifier qu'ils échouent**

```bash
cd /home/invisart/dev/phone_camera_import && python3 -m pytest -q \
  -k "desappairer or supprime_aussi_ses_horizons"
```

Attendu : ÉCHEC — 404 sur la route, et horizons non vides.

- [ ] **Étape 3 : écrire l'implémentation minimale**

Dans `phototheque/devices.py`, `revoke()` :

```python
def revoke(self, device_id: str) -> bool:
    """Retire un appareil ET ses horizons.

    La table `horizons` n'a ni clé étrangère ni `ON DELETE CASCADE`, et
    `PRAGMA foreign_keys` n'est jamais activé — SQLite le laisse inactif par
    défaut. Sans cette seconde requête, chaque révocation laissait ses lignes
    orphelines pour toujours.
    """
    with self._lock:
        cur = self._cx.execute("DELETE FROM devices WHERE id=?", (device_id,))
        self._cx.execute("DELETE FROM horizons WHERE appareil=?", (device_id,))
        self._cx.commit()
    return cur.rowcount > 0
```

Dans `phototheque/app.py`, à côté des autres routes `/sync/` :

```python
@app.post("/sync/desappairer")
def sync_desappairer(dev_id: str = Depends(require_device)) -> dict:
    """Permet au téléphone de se retirer LUI-MÊME (lot 2).

    La seule révocation existante, `POST /devices/{id}/revoke`, est derrière
    `require_admin` : le téléphone ne détient qu'un jeton d'appareil et ne peut
    pas l'appeler.

    Le risque est mesuré : un jeton volé permettrait de révoquer le téléphone
    légitime, qui se réappairerait. C'est un désagrément, à comparer à ce que
    le même jeton volé permet déjà — déposer des médias.

    L'application efface son état local QUOI QU'IL ARRIVE, sans attendre cette
    réponse : au moment précis où l'on désappaire pour se dépanner, le serveur
    est le plus souvent injoignable.
    """
    return {"retire": devices().revoke(dev_id)}
```

- [ ] **Étape 4 : lancer TOUTE la suite**

```bash
cd /home/invisart/dev/phone_camera_import && python3 -m pytest -q
```

Attendu : SUCCÈS.

- [ ] **Étape 5 : valider par mutation**

Retirer la ligne `DELETE FROM horizons` : le test des horizons doit tomber,
seul. Restaurer.

Remplacer `dev_id: str = Depends(require_device)` par `dev_id: str = "x"` :
`test_le_desappairage_exige_un_jeton_d_appareil` doit tomber. Restaurer.

- [ ] **Étape 6 : vérifier que les documents interactifs restent fermés**

Une route ajoutée est le moment de le revérifier, même si la coupure est
globale (`app.py:27-29`).

```bash
cd /home/invisart/dev/phone_camera_import && python3 -m pytest -q -k "docs"
```

- [ ] **Étape 7 : commettre**

```bash
git add phototheque/ tests/
git commit -F - <<'FIN'
feat(serveur): le telephone peut se retirer lui-meme, et revoke nettoie

Deux retouches, toutes deux au service du desappairage du lot 2.

Le telephone ne POUVAIT PAS se retirer : la seule route de revocation
est derriere le mot de passe d'admin, et il n'a qu'un jeton d'appareil.
Or le jour ou il en a besoin - certificat du NUC change - le TLS echoue
avant le HTTP, aucun 401 n'arrive jamais, oublier() n'est pas declenche
et l'ecran de scan est inatteignable une fois appaire. L'application
etait bloquee definitivement.

revoke() ne supprimait que la ligne devices. La table horizons n'a ni
cle etrangere ni ON DELETE CASCADE, et PRAGMA foreign_keys n'est jamais
active : chaque revocation laissait ses lignes orphelines a vie.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 11 : le désappairage côté application

**Fichiers :**
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/ui/EcranAppareil.kt`
- Créer : `android/app/src/main/kotlin/fr/izquierdo/phototheque/synchro/Desappairage.kt`
- Modifier : `android/.../ui/ModeleAccueil.kt`, `android/.../reseau/ClientServeur.kt`
- Test : `android/app/src/test/kotlin/fr/izquierdo/phototheque/synchro/DesappairageTest.kt`

**Interfaces :**
- Consomme : `Coffre.oublier()` (existant, `appairage/Appairage.kt:67`),
  `ClientServeur`.
- Produit : `Desappairage.executer(prevenirServeur: () -> Boolean, effacerLocal: () -> Unit): ResultatDesappairage`,
  `data class ResultatDesappairage(val serveurPrevenu: Boolean)`.

- [ ] **Étape 1 : écrire le test qui échoue**

```kotlin
package fr.izquierdo.phototheque.synchro

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DesappairageTest {

    @Test
    fun `l'effacement local a lieu meme quand le serveur est injoignable`() {
        // C'est le cas NORMAL d'usage de cette fonction : on desappaire pour
        // se depanner, et a ce moment-la le serveur est injoignable par
        // definition — certificat change, machine reinstallee, autre serveur.
        // Faire dependre le depannage du serveur qu'on ne joint plus serait
        // exactement l'impasse qu'on corrige.
        var efface = false

        val resultat = Desappairage.executer(
            prevenirServeur = { throw java.io.IOException("injoignable") },
            effacerLocal = { efface = true })

        assertTrue(efface)
        assertFalse(resultat.serveurPrevenu)
    }

    @Test
    fun `un serveur qui refuse n'empeche pas l'effacement`() {
        var efface = false

        val resultat = Desappairage.executer(
            prevenirServeur = { false },
            effacerLocal = { efface = true })

        assertTrue(efface)
        assertFalse(resultat.serveurPrevenu)
    }

    @Test
    fun `un serveur joignable est prevenu et l'effacement a lieu`() {
        var efface = false

        val resultat = Desappairage.executer(
            prevenirServeur = { true },
            effacerLocal = { efface = true })

        assertTrue(efface)
        assertTrue(resultat.serveurPrevenu)
    }
}
```

- [ ] **Étape 2 : lancer le test et vérifier qu'il échoue**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest --tests "*DesappairageTest*"
```

Attendu : ÉCHEC, `Unresolved reference: Desappairage`.

- [ ] **Étape 3 : écrire l'implémentation minimale**

```kotlin
package fr.izquierdo.phototheque.synchro

/** Ce qu'a donné un désappairage. L'effacement local, lui, a toujours eu lieu. */
data class ResultatDesappairage(val serveurPrevenu: Boolean)

/**
 * Désappairage : couper le lien.
 *
 * Ce n'est PAS le moyen de tout reprendre — la date de début fait ce travail,
 * sans rescanner de QR et de façon réversible. Son vrai métier est de se
 * dépanner et de changer de serveur.
 *
 * Or à ce moment précis, le serveur est injoignable par définition : si le
 * certificat du NUC a changé, l'épinglage fait échouer le TLS **avant** le
 * HTTP. L'effacement local ne peut donc rien attendre de lui.
 */
object Desappairage {

    fun executer(
        prevenirServeur: () -> Boolean,
        effacerLocal: () -> Unit,
    ): ResultatDesappairage {
        // Au mieux, et jamais bloquant. `Throwable` et non `Exception` : une
        // erreur de chargement de classe réseau ne doit pas non plus empêcher
        // l'utilisateur de se débloquer.
        val prevenu = try { prevenirServeur() } catch (e: Throwable) { false }
        // Inconditionnel, et APRÈS : c'est lui qui débloque.
        effacerLocal()
        return ResultatDesappairage(prevenu)
    }
}
```

Dans `ClientServeur`, ajouter :

```kotlin
/**
 * Demande au serveur de retirer cet appareil. Rend faux sur tout refus.
 *
 * Délai court et assumé : on ne fait pas attendre l'utilisateur devant un
 * serveur qu'on ne joindra pas.
 */
fun desappairer(): Boolean
```

Dans `ModeleAccueil` :

```kotlin
fun desappairer(surFait: (ResultatDesappairage) -> Unit) {
    viewModelScope.launch(Dispatchers.IO) {
        val resultat = Desappairage.executer(
            prevenirServeur = { Fabrique.serveur(getApplication(), coffre.charge())?.desappairer() ?: false },
            effacerLocal = {
                coffre.oublier()
                // Les reglages restent : ils ne sont pas lies a un serveur, et
                // les perdre obligerait a tout recocher pour un simple
                // changement de NUC.
                TravailSynchro.planifier(getApplication(), actif = false)
            })
        _etat.value = _etat.value.copy(appaire = false, revoque = false)
        surFait(resultat)
    }
}
```

`EcranAppareil` affiche la confirmation, avec sa conséquence en clair :

```kotlin
AlertDialog(
    title = { Text("Désappairer ce téléphone ?") },
    text = { Text("Vous devrez rescanner un QR. Le prochain appairage relira " +
                  "vos $nombreMedias médias (≈ $minutes min). Rien ne sera " +
                  "envoyé deux fois.") },
    ...)
```

et, après coup, si le serveur n'a pas été prévenu :

```kotlin
Text("Le serveur n'a pas pu être prévenu : l'appareil restera dans la liste " +
     "d'administration jusqu'à ce que vous l'y révoquiez.")
```

- [ ] **Étape 4 : lancer TOUTE la suite**

```bash
cd android && JAVA_HOME=~/outils/jdk17 ./gradlew testDebugUnitTest
```

Attendu : SUCCÈS.

- [ ] **Étape 5 : valider par mutation**

Déplacer `effacerLocal()` à l'intérieur du `try`, après `prevenirServeur()` :
`l'effacement local a lieu meme quand le serveur est injoignable` doit tomber.
Restaurer.

Remplacer `catch (e: Throwable) { false }` par `catch (e: Throwable) { true }` :
le même test doit tomber sur `assertFalse(resultat.serveurPrevenu)`. Restaurer.

- [ ] **Étape 6 : commettre**

```bash
cd /home/invisart/dev/phone_camera_import && git add android/
git commit -F - <<'FIN'
feat(app): desappairer le telephone depuis l'application

Ce n'est pas le moyen de tout reprendre - la date de debut fait ce
travail, sans rescanner de QR et de facon reversible. Son vrai metier
est de se depanner et de changer de serveur.

Or a ce moment precis, le serveur est injoignable par definition : si le
certificat du NUC a change, l'epinglage fait echouer le TLS AVANT le
HTTP. L'effacement local est donc inconditionnel et reussit toujours ;
le serveur est prevenu au mieux, et son echec est signale sans jamais
bloquer.

La confirmation annonce la consequence en clair plutot qu'un
« etes-vous sur ? ».

Les reglages survivent au desappairage : ils ne sont pas lies a un
serveur, et les perdre obligerait a tout recocher pour un simple
changement de NUC.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
```

---

## Tâche 12 : documentation, spec corrigée, et recette manuelle

**Fichiers :**
- Modifier : `docs/superpowers/specs/2026-09-23-app-android-lot2-design.md`,
  `docs/CONTRAT-APP.md`, `docs/APPLICATION-ANDROID.md`, `CLAUDE.md`

- [ ] **Étape 1 : corriger la spec**

§4.3 décrit l'ordre de reprise comme une réécriture de l'horizon serveur, et en
tire un coût de relecture après une fenêtre fermée. **La monotonie de la tâche 6
supprime ce coût** : le commit transmet `max(2020, 2026) = 2026`, la mémoire de
2026 survit au rattrapage, rien n'est relu ensuite, et l'ordre de reprise se
réduit à un plancher de sélection. Remplacer le paragraphe « Son coût, annoncé
et non découvert » par cette explication, et retirer la mention du « remède
local », devenu sans objet.

- [ ] **Étape 2 : documenter la nouvelle route**

Dans `docs/CONTRAT-APP.md`, ajouter `POST /sync/desappairer` : jeton
d'appareil, réponse `{"retire": true|false}`, et la règle qui compte —
l'application efface son état local **quoi qu'il arrive**, sans attendre.

Ajouter également, à la section 5, la règle de monotonie : l'application
transmet `max(nouvel horizon, horizon connu)`, et le serveur continue
d'enregistrer tel quel.

- [ ] **Étape 3 : documenter les écrans**

Dans `docs/APPLICATION-ANDROID.md` : les trois nouveaux écrans, comment les
atteindre, et ce que « toutes les 6 h » veut vraiment dire (Doze, contraintes,
une passe par nuit).

- [ ] **Étape 4 : mettre `CLAUDE.md` à jour**

État d'avancement, et ajouter aux pièges Android : `ExistingPeriodicWorkPolicy.KEEP`
ne reprogramme pas — reprogrammer à chaque ouverture d'écran remettrait le
compteur à zéro et la passe n'aurait jamais lieu.

- [ ] **Étape 5 : construire et déposer l'APK**

```bash
cd /home/invisart/dev/phone_camera_import && ./deploy/envoyer-apk.sh
```

⚠️ Ne jamais faire précéder d'un `./gradlew clean` : cela supprime l'APK.

- [ ] **Étape 6 : recette manuelle**

La recette qui fait foi est **[`docs/APPLICATION-ANDROID.md`](../../APPLICATION-ANDROID.md)
§9** (17 étapes, chacune avec sa raison). Celle qui figurait ici a été écrite
avant elle, ne couvrait ni la moitié des écrans ni les corrections de la
relecture finale, et deux recettes concurrentes est exactement le piège que
`CLAUDE.md` avait déjà dû signaler pour le lot 1 bis.

- [ ] **Étape 7 : commettre et pousser**

```bash
cd /home/invisart/dev/phone_camera_import && git add -A
git commit -F - <<'FIN'
docs: lot 2 - spec corrigee, contrat, mode d'emploi et recette

La spec prevoyait que l'ordre de reprise reecrive l'horizon serveur, et
en tirait un cout de relecture apres une fenetre fermee. La monotonie
rend cela inutile : le commit transmet max(2020, 2026), la memoire de
2026 survit au rattrapage, et rien n'est relu ensuite.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
FIN
git push origin dev
```
