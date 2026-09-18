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
     *
     * `null` et la liste VIDE ne veulent pas dire la même chose, et l'écart est
     * tout l'intérêt : `null` = on n'a pas encore regardé ; vide = on a regardé
     * et MediaStore n'a rien rendu, c'est-à-dire le cas le plus grave. Le
     * confondre avec « pas encore regardé » ferait disparaître l'écran qui
     * existe pour le dénoncer.
     */
    val dossiersVus: Map<String, Int>? = null,
) {
    /**
     * Ce que devient l'état une fois une synchronisation menée à son terme.
     *
     * Extrait du modèle de vue pour être vérifiable sur la JVM : c'est ici que
     * se joue la remise en route des avertissements de permission, que
     * [ModeleAccueil.synchroniser] vient d'éteindre au départ. Les oublier
     * rallumerait le compteur au vert sans aucun bandeau, sur un téléphone qui
     * ne sauvegarde plus rien.
     */
    fun apresSynchro(
        bilan: Bilan,
        accesPartiel: Boolean,
        accesRefuse: Boolean,
        derniereReussiteMs: Long?,
    ): EtatSynchro = copy(
        enCours = false,
        dernierBilan = bilan,
        revoque = bilan.revoque,
        // Le coffre vient d'être vidé : l'écran d'appairage doit reprendre la
        // main, pas rester sur un accueil orphelin.
        appaire = !bilan.revoque,
        accesPartiel = accesPartiel,
        permissionRefusee = accesRefuse,
        derniereReussiteMs = derniereReussiteMs,
    )

    companion object {
        /** Au-delà, l'accueil passe en avertissement. */
        const val SEUIL_ALERTE_JOURS = 7L

        /** Jours entiers depuis la dernière synchro RÉUSSIE, null si jamais. */
        fun joursDepuis(maintenantMs: Long, derniereReussiteMs: Long?): Long? =
            derniereReussiteMs?.let { (maintenantMs - it) / (24 * 3600 * 1000L) }

        /**
         * Vrai si cette synchronisation mérite d'avancer le compteur de jours.
         *
         * Trois conditions, et chacune a coûté un bogue :
         * - aucun échec local (un refus d'extension n'en est pas un) ;
         * - pas de révocation ;
         * - `errors` nul côté serveur : s'il range de travers, il n'a fait
         *   avancer AUCUN horizon (contrat, section 4.4).
         *
         * Et une quatrième, ajoutée après relecture : sans accès aux médias,
         * une synchro « parfaite » n'a rien sauvegardé du tout — elle a
         * proposé zéro fichier. Écrire cette date-là graverait un mensonge
         * durable sur le disque, que plus rien n'effacerait.
         */
        fun estUneReussite(bilan: Bilan, accesRefuse: Boolean): Boolean =
            !accesRefuse &&
            bilan.echecs == 0 &&
            !bilan.revoque &&
            (bilan.bilanServeur["errors"] ?: 0.0) == 0.0
    }
}
