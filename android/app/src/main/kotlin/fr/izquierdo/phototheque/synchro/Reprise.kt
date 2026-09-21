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
