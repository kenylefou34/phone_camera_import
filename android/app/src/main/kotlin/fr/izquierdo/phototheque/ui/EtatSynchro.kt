package fr.izquierdo.phototheque.ui

import fr.izquierdo.phototheque.synchro.Bilan

/**
 * État affiché par l'écran d'accueil. Le compteur de jours se calcule
 * uniquement à partir de [derniereReussiteMs] : une tentative qui échoue, ou
 * un serveur introuvable, ne le remettent jamais à zéro ni ne le remontent.
 */
data class EtatSynchro(
    val enCours: Boolean = false,
    val derniereReussiteMs: Long? = null,
    val dernierBilan: Bilan? = null,
    val accesPartiel: Boolean = false,
    val revoque: Boolean = false,
    val serveurIntrouvable: Boolean = false,
) {
    companion object {
        /** Au-delà, l'accueil passe en avertissement. */
        const val SEUIL_ALERTE_JOURS = 7L

        /** Jours entiers depuis la dernière synchro RÉUSSIE, null si jamais. */
        fun joursDepuis(maintenantMs: Long, derniereReussiteMs: Long?): Long? =
            derniereReussiteMs?.let { (maintenantMs - it) / (24 * 3600 * 1000L) }
    }
}
