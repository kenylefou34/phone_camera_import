package fr.izquierdo.phototheque.synchro

import fr.izquierdo.phototheque.ui.Reglages

/** Ce qu'affiche la case d'une ligne de l'arborescence. */
enum class Coche {
    AUCUNE,
    /** Seuls certains sous-dossiers sont pris : case à moitié pleine. */
    PARTIELLE,
    /** Ce dossier seulement. */
    DOSSIER,
    /** Ce dossier et toute sa descendance. */
    RECURSIVE,
    /**
     * Sauvegardé, mais pas par son propre réglage : un ANCÊTRE est coché
     * « et ses sous-dossiers ». Distinct de PARTIELLE, qui décrit l'inverse
     * (une partie seulement de la descendance) ; ici c'est la totalité, mais
     * décidée plus haut dans l'arbre — décocher ce nœud ne ferait rien, la
     * case reviendrait aussitôt à HERITEE au prochain passage.
     */
    HERITEE,
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
     * Les dossiers à proposer au serveur, d'après ce que l'utilisateur a coché.
     *
     * Fonction séparée, et pure, pour être vérifiable sur la JVM : c'est le point
     * où le lot 1 décidait à la place de l'utilisateur, et sa régression serait
     * muette — la synchronisation réussirait en ne sauvegardant pas les bons
     * dossiers. Vit ici, et non dans `TravailSynchro` (un `CoroutineWorker`
     * Android), pour que l'appel depuis `Orchestrateur` ne fasse pas dépendre
     * le cœur pur de la synchro d'une classe Android.
     */
    fun dossiersASauvegarder(reglages: Reglages, tous: Set<String>): Set<String> =
        resoudre(tous, reglages.dossiersSeuls, reglages.dossiersRecursifs)

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
     * pris. HERITEE est testée avant PARTIELLE : quand un ANCÊTRE est coché
     * en récursif, toute la descendance est déjà entièrement prise — il ne
     * peut plus y avoir de « partiel » à signaler pour ce nœud.
     */
    fun etat(noeud: Noeud, seuls: Set<String>, recursifs: Set<String>): Coche = when {
        noeud.chemin in recursifs -> Coche.RECURSIVE
        noeud.chemin in seuls -> Coche.DOSSIER
        parentRecursif(noeud.chemin, recursifs) != null -> Coche.HERITEE
        descendanceCochee(noeud, seuls, recursifs) -> Coche.PARTIELLE
        else -> Coche.AUCUNE
    }

    private fun descendanceCochee(
        noeud: Noeud, seuls: Set<String>, recursifs: Set<String>,
    ): Boolean = noeud.enfants.any {
        it.chemin in seuls || it.chemin in recursifs || descendanceCochee(it, seuls, recursifs)
    }

    /**
     * L'ancêtre récursif responsable de [chemin], ou `null` si aucun ne le
     * couvre.
     *
     * [chemin] lui-même n'est jamais son propre ancêtre : un dossier qui est
     * DANS [recursifs] est RECURSIVE, pas HERITEE. Quand plusieurs ancêtres
     * récursifs se recouvrent (« Pictures » et « Pictures/WhatsApp » tous les
     * deux cochés), le plus proche — le chemin le plus long — est le vrai
     * responsable : c'est lui que l'écran doit nommer.
     */
    fun parentRecursif(chemin: String, recursifs: Set<String>): String? =
        recursifs.filter { it != chemin && sousArbre(chemin, it) }
            .maxByOrNull { it.length }

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

    /**
     * Les dossiers configurés dont RIEN n'est visible sur le téléphone.
     *
     * Comparer chaque dossier configuré à [vus] par égalité stricte serait
     * faux pour une coche récursive : MediaStore ne rend que les dossiers
     * qui contiennent directement des médias, jamais un dossier intermédiaire
     * qui n'en a que par ses sous-dossiers. « Pictures » coché en récursif et
     * sauvegardé uniquement via « Pictures/WhatsApp » ne doit pas s'afficher
     * comme introuvable — c'est exactement le cas que l'écran doit RECONNAÎTRE
     * comme normal, pas signaler en rouge.
     */
    fun introuvables(reglages: Reglages, vus: Set<String>): Set<String> =
        (reglages.dossiersSeuls + reglages.dossiersRecursifs)
            .filterTo(mutableSetOf()) { racine -> vus.none { sousArbre(it, racine) } }
}
