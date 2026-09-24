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
     * La demande à retenir quand l'appairage change.
     *
     * Perdre l'appairage oublie l'écran demandé. Sans ça, la demande restait
     * mémorisée pendant tout le passage par l'écran de scan : désappairer
     * depuis « Cet appareil » faisait rouvrir ce même écran — et son bouton
     * « désappairer » — dès le réappairage suivant (constat C3 de la recette
     * du 24/09, qui a produit un vrai désappairage accidentel).
     *
     * Rester appairé garde la demande : c'est ce qui empêche une rotation de
     * ramener à l'accueil (issue #24).
     */
    fun demandeApres(demande: Ecran, appaire: Boolean): Ecran =
        if (appaire) demande else Ecran.ACCUEIL

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
