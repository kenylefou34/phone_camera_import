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
