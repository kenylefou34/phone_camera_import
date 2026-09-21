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
        // La synchro ne s'est pas rendue au bout. On lit ici le bilan BRUT,
        // dont le drapeau couvre AUSSI un arret subi (contrainte reseau
        // perdue, arret systeme) : c'est TravailSynchro qui fait la part des
        // deux, et seulement pour ce qu'il affiche. Dans les deux cas
        // relancer nous-memes est faux — soit c'est le contraire de ce que
        // l'utilisateur vient de demander, soit ca double la replanification
        // que WorkManager fait deja tout seul.
        bilan.interrompu -> false
        // Seul un nouveau QR debloque : relancer tournerait en boucle.
        bilan.revoque -> false
        else -> bilan.echecs > 0
    }
}
