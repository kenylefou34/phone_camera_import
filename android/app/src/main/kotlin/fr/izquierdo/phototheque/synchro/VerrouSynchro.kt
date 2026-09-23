package fr.izquierdo.phototheque.synchro

import java.util.concurrent.atomic.AtomicBoolean

/**
 * Empêche deux synchronisations de tourner en même temps.
 *
 * `ExistingWorkPolicy.KEEP` (et `ExistingPeriodicWorkPolicy.KEEP`) ne
 * protègent chacune qu'À L'INTÉRIEUR de leur propre nom unique : la file
 * manuelle (« synchro ») et la file automatique (« synchro-auto ») peuvent
 * donc très bien démarrer en même temps. Or `TravailSynchro` garde son
 * avancement, sa dernière issue et son drapeau d'arrêt dans le companion
 * object de la classe — partagés par TOUTE exécution, quelle que soit la
 * file qui l'a déclenchée. Deux exécutions à la fois mélangeraient
 * l'avancement affiché, attribueraient un arrêt à la mauvaise, et se
 * disputeraient l'écriture des réglages (lecture-puis-écriture non atomique,
 * le même défaut que les tâches 5b et 7 ont déjà corrigé ailleurs).
 *
 * Pas de préemption : celle qui a déjà pris le verrou le garde jusqu'à sa
 * fin, l'autre ressort aussitôt sans rien publier ni réinitialiser. Ce n'est
 * pas un silence : l'exécution qui tient le verrou est déjà en train de
 * publier son propre avancement, ou est sur le point de le faire. Préempter
 * romprait une synchronisation déjà engagée en plein milieu d'un fichier —
 * exactement la limite déjà connue et assumée ailleurs (issue #33, gros
 * fichier interrompu) que ce projet évite d'aggraver.
 *
 * `AtomicBoolean` et non `@Volatile var` : `tenter()` doit être une lecture
 * ET une écriture en une seule opération indivisible (compare-and-set),
 * sinon deux exécutions qui liraient toutes les deux « libre » avant que
 * l'une n'écrive « pris » prendraient le verrou toutes les deux — la même
 * course que cet objet existe pour éliminer.
 */
object VerrouSynchro {
    private val pris = AtomicBoolean(false)

    /** Vrai si on a pris le verrou. Faux si une autre exécution le détient déjà. */
    fun tenter(): Boolean = pris.compareAndSet(false, true)

    /** Relâche le verrou. Sans effet s'il n'était pas déjà pris. */
    fun liberer() {
        pris.set(false)
    }
}
