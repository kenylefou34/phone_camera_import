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
    val appaire: Boolean = false,
    val qrInvalide: Boolean = false,
    /**
     * Message d'une panne VISIBLE : réseau coupé en pleine synchro, serveur en
     * erreur, réponse illisible. Volontairement distinct de
     * [serveurIntrouvable], qui n'est PAS une panne : les confondre est
     * exactement ce qui rendait l'application muette.
     */
    val erreur: String? = null,
    /**
     * L'accès aux photos a été retiré dans les réglages Android. Sans ce
     * drapeau, l'application ne verrait plus aucun média et signalerait une
     * synchro parfaite — la panne muette par excellence.
     */
    val permissionRefusee: Boolean = false,
    /**
     * Dossiers réellement présents sur le téléphone, et nombre de médias de
     * chacun. Les trois dossiers sauvegardés sont codés en dur : si l'un
     * n'existe pas (WhatsApp récent range sous `Android/media/com.whatsapp/…`),
     * la synchro réussit avec ZÉRO média et rien ne le dit. Cette liste est ce
     * qui le révèle.
     */
    val dossiersVus: Map<String, Int> = emptyMap(),
) {
    companion object {
        /** Au-delà, l'accueil passe en avertissement. */
        const val SEUIL_ALERTE_JOURS = 7L

        /** Jours entiers depuis la dernière synchro RÉUSSIE, null si jamais. */
        fun joursDepuis(maintenantMs: Long, derniereReussiteMs: Long?): Long? =
            derniereReussiteMs?.let { (maintenantMs - it) / (24 * 3600 * 1000L) }
    }
}
