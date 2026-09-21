package fr.izquierdo.phototheque.synchro

/** Ce qu'est devenu un envoi. */
enum class Issue {
    /** Le serveur a répondu 200 : le média est chez lui. */
    CONFIRME,

    /** Refusé (400, extension non prise en charge). Volontairement PAS un
     *  échec : bloquer l'horizon dessus fermerait le dossier à jamais. */
    IGNORE,

    /** Tout le reste : réseau coupé, 5xx, erreur de lecture locale. */
    ECHEC,
}

/** Un envoi tenté, avec la date du média concerné (secondes). */
data class Envoi(val dossier: String, val instant: Double, val issue: Issue)

object Horizons {

    /**
     * Horizon à transmettre pour chaque dossier : la date du dernier fichier
     * confirmé AVANT le premier échec de ce dossier.
     *
     * Pourquoi pas « la date la plus haute confirmée » : si le fichier n° 5
     * échoue et que le n° 6 réussit, retenir la plus haute ferait sauter
     * l'horizon par-dessus le n° 5, qui ne serait PLUS JAMAIS proposé par le
     * serveur — perte définitive et silencieuse.
     *
     * Un dossier dont le premier fichier échoue est absent du résultat : son
     * horizon ne doit pas bouger du tout.
     */
    fun calculer(envois: List<Envoi>): Map<String, Double> {
        val horizons = mutableMapOf<String, Double>()
        val arretes = mutableSetOf<String>()
        // Tri par date, puis ECHEC d'abord A DATE EGALE. Deux envois du meme
        // dossier peuvent porter exactement la meme date : DATE_MODIFIED n'a
        // qu'une precision d'une seconde et une rafale en produit plusieurs.
        // Sans ce second critere, `sortedBy` etant un tri STABLE, le resultat
        // dependrait de l'ordre de la liste d'entree — ce que le test
        // `l_ordre_de_la_liste_n_influence_pas_le_resultat` pretend justement
        // exclure. A egalite on retient le cas prudent : l'echec arrete le
        // dossier, quitte a reproposer quelques fichiers que l'anti-doublon
        // ecartera sans les transferer.
        for (envoi in envois.sortedWith(
            compareBy({ it.instant }, { if (it.issue == Issue.ECHEC) 0 else 1 })
        )) {
            if (envoi.dossier in arretes) continue
            when (envoi.issue) {
                Issue.ECHEC -> arretes += envoi.dossier
                Issue.CONFIRME, Issue.IGNORE -> horizons[envoi.dossier] = envoi.instant
            }
        }
        return horizons
    }
}
