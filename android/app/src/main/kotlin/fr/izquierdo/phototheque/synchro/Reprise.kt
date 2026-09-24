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

    /**
     * Un lancement refusé parce qu'une autre synchronisation tient
     * `VerrouSynchro` : on relance plus tard, TOUJOURS.
     *
     * Il sortait en « réussite » muette (constat C1 de la recette du 24/09).
     * Le cas n'a rien de théorique : une synchronisation arrêtée par Android
     * pendant un appel réseau bloquant garde le verrou jusqu'à la fin de cet
     * appel, alors que WorkManager la croit déjà finie. Tout ce qui démarrait
     * pendant ce temps disparaissait — la passe automatique attendait six
     * heures, un appui sur « Sauvegarder maintenant » ne faisait rien.
     *
     * Pas de plafond, contrairement à une panne : le verrou finit toujours
     * par être rendu, et WorkManager espace lui-même les essais (délai qui
     * double, borné à 5 h). Plafonner ramènerait l'abandon muet dès que la
     * synchronisation qui tient le verrou dure plus de quelques minutes.
     * `tentatives` n'est pris que pour le dire explicitement.
     */
    @Suppress("UNUSED_PARAMETER")
    fun apresRefusDuVerrou(tentatives: Int): Boolean = true
}
